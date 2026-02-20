"""
Voice to Text - macOS Version
Hold the configured hotkey (default: Right Cmd + Right Option) to record,
release to transcribe and paste. Uses OpenAI Whisper transcription with
macOS-compatible AppleScript-based pasting.

macOS Permissions Note:
This script requires two permissions:
  1. Input Monitoring: Lets script detect hotkey presses
  2. Accessibility: Lets script paste via AppleScript

Grant Accessibility via: System Settings > Privacy & Security > Accessibility
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import from src/
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.voice_logger import setup_logger, console, print_log_location

import sounddevice as sd
import soundfile as sf
import numpy as np
from openai import OpenAI
import tempfile
import os
import pyperclip
import time
import threading
import queue
import subprocess
from typing import Optional, Set, Dict, List
from pynput import keyboard
from dotenv import load_dotenv
from rich.panel import Panel

# Setup logger (handles both terminal + file logging)
logger = setup_logger("voice_to_text_macos")

# Load environment variables from .env file
load_dotenv()

# Configuration
SAMPLE_RATE: int = 44100
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
API_TIMEOUT: int = 30  # seconds
MAX_RECORDING_SECONDS: int = 300  # 5-minute safety failsafe
MIN_AUDIO_DURATION: float = 0.3  # seconds
CLIPBOARD_COPY_DELAY: float = 0.2  # seconds (slightly longer on macOS)
CLIPBOARD_RESTORE_DELAY: float = 1.0  # seconds
RESULT_CHECK_INTERVAL: float = 0.05  # seconds

# Default hotkey: Right Command + Right Option
HOTKEY_KEY: Set = {keyboard.Key.cmd_r, keyboard.Key.alt_r}
current_pressed_keys: Set = set()
CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), 'config.json')

class VoiceRecorder:
    """Records audio, transcribes it using OpenAI Whisper, and pastes results on macOS.

    This class handles the audio recording pipeline including:
    - Starting/stopping audio streams
    - Async transcription via OpenAI Whisper API
    - Clipboard management and text pasting via AppleScript
    - Thread-safe state management
    - Optional custom vocabulary for transcription

    Attributes:
        openai: OpenAI API client instance
        recording: Whether audio is currently being recorded
        frames: List of audio frame chunks
        stream: Active audio input stream
        lock: Threading lock for state safety
        result_queue: Queue for async transcription results
        transcribing: Whether transcription is in progress
        vocabulary_prompt: Optional custom vocabulary for Whisper API
    """

    def __init__(self, vocabulary_prompt: Optional[str] = None) -> None:
        """Initialize the VoiceRecorder with OpenAI client and thread-safe state.

        Args:
            vocabulary_prompt: Optional custom vocabulary to guide transcription.
        """
        self.openai: OpenAI = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT)
        self.recording: bool = False
        self.frames: List[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None
        self.lock: threading.Lock = threading.Lock()
        self.result_queue: queue.Queue = queue.Queue()
        self.transcribing: bool = False
        self.vocabulary_prompt: Optional[str] = vocabulary_prompt
        self.pending_audio_queue: queue.Queue = queue.Queue()  # Queue for pending recordings

    def start_recording(self) -> bool:
        """Start recording audio from the default input device.

        Initializes audio stream with callback-based frame collection and
        duration failsafe. Plays start notification sound.

        Returns:
            bool: True if stream started successfully, False otherwise.
        """
        with self.lock:
            if self.recording:
                logger.warning("Recording already in progress")
                return False
            self.recording = True
            self.frames = []

        def callback(indata: np.ndarray, frame_count: int, time_info, status) -> None:
            if status:
                logger.warning(f"Audio status: {status}")
            with self.lock:
                if self.recording:
                    self.frames.append(indata.copy())
                    duration_s: float = len(self.frames) * frame_count / SAMPLE_RATE
                    if duration_s > MAX_RECORDING_SECONDS:
                        logger.warning("Failsafe: Maximum recording duration reached")
                        self.recording = False

        try:
            # letting sounddevice choose the default input device
            self.stream = sd.InputStream(
                channels=1,
                samplerate=SAMPLE_RATE,
                callback=callback
            )
            self.stream.start()
            play_sound('start')
            logger.info("Recording started...")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            with self.lock:
                self.recording = False
                self.frames = []
            return False

    def stop_recording(self) -> Optional[np.ndarray]:
        """Stop recording and return the collected audio frames.

        Closes the audio stream and concatenates all captured frames into a
        single numpy array. Returns None if no audio was captured.

        Returns:
            Optional[np.ndarray]: Audio data as numpy array, or None if empty.
        """
        with self.lock:
            if not self.recording:
                return None
            self.recording = False

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}", exc_info=True)
            self.stream = None

        play_sound('stop')
        logger.info("Stopped recording")

        with self.lock:
            if self.frames:
                audio: np.ndarray = np.concatenate(self.frames, axis=0)
                self.frames = []
                return audio
            self.frames = []
            return None

    def transcribe_async(self, audio_data: np.ndarray, prompt: Optional[str] = None) -> None:
        """Start async transcription of audio data using OpenAI Whisper API.

        Spawns a daemon thread to transcribe the audio without blocking the main
        event loop. Results are placed in result_queue for later retrieval.
        If already transcribing, queues the audio for later processing.

        Args:
            audio_data: Raw audio frames as numpy array.
            prompt: Optional custom vocabulary prompt for Whisper model.
        """
        if self.transcribing:
            logger.debug("Transcription in progress, queueing audio...")
            self.pending_audio_queue.put(audio_data)
            return

        self.transcribing = True

        def do_transcribe() -> None:
            try:
                result: Optional[str] = self._transcribe(audio_data, prompt=prompt)
                self.result_queue.put(('success', result))
            except Exception as e:
                logger.error(f"Transcription failed: {e}", exc_info=True)
                self.result_queue.put(('error', str(e)))
            finally:
                self.transcribing = False

        thread: threading.Thread = threading.Thread(target=do_transcribe, daemon=True)
        thread.start()

    def _transcribe(self, audio_data: np.ndarray, prompt: Optional[str] = None) -> Optional[str]:
        """Transcribe audio data using OpenAI Whisper API.

        Writes audio to temporary WAV file, uploads to OpenAI Whisper API,
        and returns transcribed text. Validates minimum audio duration.

        Args:
            audio_data: Raw audio frames as numpy array.
            prompt: Optional custom vocabulary to improve transcription.

        Returns:
            Optional[str]: Transcribed text, or None if audio too short.

        Raises:
            Exception: If transcription API call fails.
        """
        min_samples: int = int(SAMPLE_RATE * MIN_AUDIO_DURATION)
        if audio_data is None or len(audio_data) < min_samples:
            logger.info("Recording too short, skipping transcription")
            return None

        temp_path: Optional[str] = None
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_path = temp_file.name
            temp_file.close()

            logger.debug(f"Writing audio to temp file: {temp_path}")
            sf.write(temp_path, audio_data, SAMPLE_RATE)

            logger.info("Transcribing with OpenAI Whisper...")
            with open(temp_path, 'rb') as f:
                kwargs = {"model": "whisper-1", "file": f}
                if prompt:
                    kwargs["prompt"] = prompt
                    logger.debug(f"Using custom vocabulary prompt: {prompt}")
                result = self.openai.audio.transcriptions.create(**kwargs)
            return result.text

        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            raise e
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError as e:
                    logger.warning(f"Failed to delete temp file {temp_path}: {e}")

    def paste_text(self, text: str) -> None:
        """Copy text to clipboard and simulate Cmd+V paste into active window.

        Uses AppleScript for robust pasting on macOS. Preserves the original
        clipboard content by restoring it after pasting.

        Args:
            text: Text to paste into the active window.
        """
        if not text:
            return

        logger.info(f"Pasting {len(text)} characters...")

        # Save current clipboard
        old_clipboard: str = ""
        try:
            old_clipboard = pyperclip.paste()
        except Exception as e:
            logger.debug(f"Failed to read existing clipboard: {e}")

        pyperclip.copy(text)
        time.sleep(CLIPBOARD_COPY_DELAY)

        # Simulate Cmd+V using AppleScript (more robust on macOS)
        try:
            subprocess.run([
                'osascript', '-e', 'tell application "System Events" to keystroke "v" using command down'
            ], capture_output=True, text=True, check=True, timeout=5)
            logger.debug("Paste via AppleScript succeeded")
        except subprocess.CalledProcessError as e:
            err_msg: str = e.stderr.strip()
            logger.error(f"Paste failed: {err_msg}")
            if "not allowed to send keystrokes" in err_msg or "1002" in err_msg:
                console.print("\n[red][!] ACTION REQUIRED[/red]: Terminal needs 'Accessibility' permission to paste.")
                console.print("    Go to: System Settings > Privacy & Security > Accessibility")
                console.print("    Enable your terminal application (e.g., iTerm, VS Code).")
                play_sound('error')
        except Exception as e:
            logger.error(f"AppleScript error: {e}", exc_info=True)

        # Restore clipboard (give the paste slightly longer to happen before restoring)
        time.sleep(CLIPBOARD_RESTORE_DELAY)
        try:
            pyperclip.copy(old_clipboard)
        except Exception as e:
            logger.debug(f"Failed to restore clipboard: {e}")

    def check_results(self) -> Optional[bool]:
        """Check if transcription result is ready and paste if successful.

        Non-blocking check of result queue. Returns True if text was pasted,
        False if an error occurred, None if no result ready yet.
        Automatically processes next queued audio if available.

        Returns:
            Optional[bool]: True if successful, False if error, None if pending.
        """
        try:
            status, result = self.result_queue.get_nowait()
            if status == 'success' and result:
                logger.info(f"✓ Success: {result}")
                self.paste_text(result)
            elif status == 'success' and not result:
                logger.warning("Recording too short or no speech detected")
                play_sound('error')
            else:
                logger.error(f"Transcription failed: {result}")
                play_sound('error')

            # Process next queued audio if available
            try:
                next_audio = self.pending_audio_queue.get_nowait()
                logger.info("Processing next queued recording...")
                self.transcribe_async(next_audio, prompt=self.vocabulary_prompt)
            except queue.Empty:
                pass

            return status == 'success' and result is not None
        except queue.Empty:
            return None


def play_sound(type_: str) -> None:
    """Play system notification sound on macOS.

    Maps sound type to macOS system sounds and plays asynchronously.

    Args:
        type_: Sound type ('start', 'stop', 'success', or 'error').
    """
    sounds: Dict[str, str] = {
        'start': '/System/Library/Sounds/Tink.aiff',
        'stop': '/System/Library/Sounds/Pop.aiff',
        'success': '/System/Library/Sounds/Glass.aiff',
        'error': '/System/Library/Sounds/Basso.aiff'
    }
    sound_file = sounds.get(type_)
    if sound_file and os.path.exists(sound_file):
        try:
            subprocess.Popen(['afplay', sound_file], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception as e:
            logger.debug(f"Failed to play sound '{type_}': {e}")


def load_custom_vocabulary(vocab_path: Optional[str] = None) -> Optional[str]:
    """Load custom vocabulary from file for Whisper prompt.

    Reads comma or newline-separated words/phrases from a text file.

    Args:
        vocab_path: Path to vocabulary file. If None, looks for
                   'vocabulary.txt' in same directory.

    Returns:
        Formatted prompt string or None if file not found.
    """
    if not vocab_path:
        vocab_path = os.path.join(os.path.dirname(__file__), 'vocabulary.txt')

    if not os.path.exists(vocab_path):
        return None

    try:
        with open(vocab_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if not content:
            return None

        if ',' in content:
            words = [w.strip() for w in content.split(',') if w.strip()]
        else:
            words = [w.strip() for w in content.split('\n') if w.strip()]

        prompt = ', '.join(words)
        logger.info(f"Loaded {len(words)} vocabulary items from {vocab_path}")
        return prompt

    except Exception as e:
        logger.warning(f"Failed to load vocabulary from {vocab_path}: {e}")
        return None


# Global State for Hotkey Handling
recorder: VoiceRecorder = VoiceRecorder()  # Will be re-initialized in main() with vocabulary


def on_press(key) -> None:
    """Keyboard press event handler - starts recording on hotkey press.

    Tracks currently pressed keys and starts recording when hotkey is pressed.

    Args:
        key: Key object from keyboard.Listener.
    """
    try:
        if key in HOTKEY_KEY:
            current_pressed_keys.add(key)
            if all(k in current_pressed_keys for k in HOTKEY_KEY):
                # Check if already recording to avoid "key repeat" triggers
                with recorder.lock:
                    is_active = recorder.recording or recorder.transcribing

                if not is_active:
                    logger.info("Recording started")
                    recorder.start_recording()
    except Exception as e:
        logger.error(f"Error on key press: {e}", exc_info=True)


def on_release(key) -> None:
    """Keyboard release event handler - stops recording and starts transcription.

    Stops recording when hotkey is released and submits captured audio
    for transcription with optional custom vocabulary.

    Args:
        key: Key object from keyboard.Listener.
    """
    try:
        if key in HOTKEY_KEY:
            if recorder.recording:
                audio = recorder.stop_recording()
                if audio is not None and len(audio) > 0:
                    logger.info("Audio captured, starting transcription...")
                    recorder.transcribe_async(audio, prompt=recorder.vocabulary_prompt)
                else:
                    logger.warning("No audio captured")

            if key in current_pressed_keys:
                current_pressed_keys.remove(key)
    except Exception as e:
        logger.error(f"Error on key release: {e}", exc_info=True)


def main() -> None:
    """Main entry point for voice-to-text application on macOS."""
    # Load custom vocabulary
    vocab_prompt: Optional[str] = None
    vocab_prompt = load_custom_vocabulary()

    # Re-initialize recorder with vocabulary
    global recorder
    recorder = VoiceRecorder(vocabulary_prompt=vocab_prompt)

    # Print welcome banner with rich
    welcome_text = """[bold cyan]Voice to Text[/] (macOS)

[yellow]🎤 Hotkey:[/] [bold green]Right Cmd + Right Option[/]
[yellow]⏸  Action:[/] Hold to record, release to transcribe & paste
[yellow]🛑 Exit:[/] Press Ctrl+C to quit

[dim]─[/] Logs appear below [dim]─[/]"""

    console.print(Panel(welcome_text, style="blue", expand=False))
    print_log_location()

    # Verify audio device
    try:
        dev = sd.query_devices(kind='input')
        logger.info(f"Default Input Device: {dev['name']}")
    except Exception as e:
        logger.warning(f"Could not query default input device: {e}")

    # Start Keyboard Listener
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    logger.info("Keyboard listener started")

    try:
        while True:
            recorder.check_results()
            time.sleep(RESULT_CHECK_INTERVAL)
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️  Stopping...[/]")
    finally:
        listener.stop()
        console.print("[cyan]✓ Goodbye![/]\n")

if __name__ == "__main__":
    main()
