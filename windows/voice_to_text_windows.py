"""
Voice to Text - Windows Version
Hold the configured hotkey (default: Right Ctrl + Right Alt) to record, release to transcribe and paste.
Uses Windows API RegisterHotKey for hotkey detection (eliminates pynput listener issues).
Uses pynput keyboard.Controller only for text pasting simulation.
Uses the same Whisper/OpenAI transcription flow as the macOS script but with
Windows-compatible paste and sound notifications.
"""

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
import sys
import os
from pathlib import Path
import ctypes
from ctypes import wintypes
from pynput import keyboard

# Add parent directory to path so we can import from src/
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.voice_logger import setup_logger, console, print_log_location
from src.audio_processor import process_audio_for_whisper, AudioLevelMonitor
from dotenv import load_dotenv
import winsound
import argparse
import json
import logging
from typing import Optional, Tuple, List, Dict, Any
from rich.panel import Panel
from rich.table import Table

# Setup logger (handles both terminal + file logging)
logger = setup_logger("voice_to_text_windows")

# Load environment variables from .env file
load_dotenv()

# Configuration
SAMPLE_RATE: int = 44100
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
API_TIMEOUT: int = 30  # seconds
MAX_RECORDING_SECONDS: int = 300  # 5-minute safety failsafe
MIN_AUDIO_DURATION: float = 0.3  # seconds
CLIPBOARD_COPY_DELAY: float = 0.15  # seconds
CLIPBOARD_RESTORE_DELAY: float = 0.9  # seconds
RESULT_CHECK_INTERVAL: float = 0.05  # seconds

# Default hotkey
DEFAULT_HOTKEY: str = 'ctrl_r+alt_gr'

CONFIG_PATH: str = os.path.join(os.path.dirname(__file__), 'config.json')
SELECTED_DEVICE: Optional[int] = None
SELECTED_SR: int = SAMPLE_RATE

# Audio processing settings
AUDIO_BOOST: float = 0.0  # Gain boost in dB (positive = louder)
AUDIO_NORMALIZE: bool = False  # Whether to normalize loudness

# Global hotkey state tracking
recording_active = False
hotkey_pressed = False  # Track if hotkey is currently pressed
hotkey_registered = False  # Track if RegisterHotKey succeeded


class VoiceRecorder:
    """Records audio, transcribes it using OpenAI Whisper, and pastes results.

    This class handles the audio recording pipeline including:
    - Starting/stopping audio streams with device fallback
    - Async transcription via OpenAI Whisper API
    - Clipboard management and text pasting
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
        self.audio_monitor: AudioLevelMonitor = AudioLevelMonitor(SELECTED_SR)

    def start_recording(self) -> bool:
        """Start recording audio from the selected input device.

        Attempts to verify device/sample rate compatibility by testing against
        multiple fallback rates. Initializes audio stream with callback-based
        frame collection and duration failsafe.

        Returns:
            bool: True if stream started successfully, False otherwise.
        """
        # Ensure input settings work on this device/sample rate (attempt fallbacks)
        global SELECTED_SR
        device = sd.default.device[0] if sd.default.device else None
        tried_rates: List[int] = [SELECTED_SR, SAMPLE_RATE, 48000, 44100, 16000]
        for r in tried_rates:
            try:
                sd.check_input_settings(device=device, samplerate=r)
                SELECTED_SR = r
                logger.debug(f"Using sample rate: {r}Hz")
                break
            except Exception as e:
                logger.debug(f"Sample rate {r}Hz not supported: {e}")
                continue

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
                    self.audio_monitor.update(indata)  # Track audio levels in real-time
                    duration_s: float = len(self.frames) * frame_count / SELECTED_SR
                    if duration_s > MAX_RECORDING_SECONDS:
                        logger.warning("Failsafe: Maximum recording duration reached")
                        self.recording = False

        # Use selected samplerate (may have been adjusted above)
        device = sd.default.device[0] if sd.default.device else None

        # Try with different latency settings to work around WDM-KS issues
        for latency_mode in ['high', 'low']:
            try:
                self.stream = sd.InputStream(
                    device=device,
                    channels=1,
                    samplerate=SELECTED_SR,
                    callback=callback,
                    latency=latency_mode,
                    blocksize=2048
                )
                self.stream.start()
                play_sound('start')
                logger.info(f"Recording started (latency: {latency_mode})...")
                return True
            except Exception as e:
                logger.debug(f"Failed with latency={latency_mode}: {e}")
                if latency_mode == 'low':
                    # If both latency modes fail, log and return False
                    logger.error(f"Failed to start recording: {e}", exc_info=True)
                    break

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

        # Report audio quality
        report = self.audio_monitor.get_report()
        quality, recommendation = self.audio_monitor.get_quality_assessment()
        logger.debug(
            f"Audio quality: {quality} | "
            f"Peak: {report['peak_db']:.1f}dB, "
            f"RMS: {report['rms_db']:.1f}dB"
        )
        if quality not in ['good', 'excellent']:
            logger.info(f"Audio tip: {recommendation}")

        # Reset monitor for next recording
        self.audio_monitor = AudioLevelMonitor(SELECTED_SR)

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

        Uses optional prompt to guide transcription with custom vocabulary.
        Prompt should contain relevant terminology separated by commas.

        Args:
            audio_data: Raw audio frames as numpy array.
            prompt: Optional custom vocabulary to improve transcription.
                   Example: "Python, JavaScript, async, await, TypeScript"

        Returns:
            Optional[str]: Transcribed text, or None if audio too short.

        Raises:
            Exception: If transcription API call fails.
        """
        min_samples: int = int(SELECTED_SR * MIN_AUDIO_DURATION)
        if audio_data is None or len(audio_data) < min_samples:
            logger.info("Recording too short, skipping transcription")
            return None

        temp_path: Optional[str] = None
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_path = temp_file.name
            temp_file.close()

            # Apply audio processing (gain boost and normalization)
            processed_audio = process_audio_for_whisper(
                audio_data,
                sample_rate=SELECTED_SR,
                gain_db=AUDIO_BOOST,
                normalize=AUDIO_NORMALIZE
            )

            logger.debug(f"Writing audio to temp file: {temp_path}")
            sf.write(temp_path, processed_audio, SELECTED_SR)

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
        """Copy text to clipboard and simulate Ctrl+V paste into active window.

        Preserves the original clipboard content by restoring it after pasting.
        Uses pynput for initial paste attempt, falls back to PowerShell SendKeys.

        Args:
            text: Text to paste into the active window.
        """
        if not text:
            return

        logger.info(f"Pasting {len(text)} characters...")

        old_clipboard: str = ""
        try:
            old_clipboard = pyperclip.paste()
        except Exception as e:
            logger.debug(f"Failed to read existing clipboard: {e}")

        pyperclip.copy(text)
        time.sleep(CLIPBOARD_COPY_DELAY)

        # Simulate Ctrl+V using pynput to paste into the active window
        try:
            controller: keyboard.Controller = keyboard.Controller()
            controller.press(keyboard.Key.ctrl)
            controller.press('v')
            controller.release('v')
            controller.release(keyboard.Key.ctrl)
            logger.debug("Paste via pynput succeeded")
        except Exception as e:
            logger.warning(f"Paste simulation failed: {e}, trying PowerShell fallback...")
            # As a fallback, try the Windows clipboard paste via Powershell (best-effort)
            try:
                subprocess.run([
                    'powershell', '-Command', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("^{v}")'
                ], capture_output=True, timeout=5)
                logger.debug("Paste via PowerShell succeeded")
            except Exception as ps_e:
                logger.error(f"Both paste methods failed: {ps_e}")

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
                logger.info(f"Success: {result}")
                self.paste_text(result)
                play_sound('success')
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
    """Play system notification sound.

    Maps sound type to Windows system sounds via winsound.MessageBeep.
    Silently fails if audio system unavailable.

    Args:
        type_: Sound type ('start', 'stop', 'success', or 'error').
    """
    mapping: Dict[str, int] = {
        'start': winsound.MB_OK,
        'stop': winsound.MB_ICONASTERISK,
        'success': winsound.MB_ICONEXCLAMATION,
        'error': winsound.MB_ICONHAND
    }
    try:
        code: int = mapping.get(type_, winsound.MB_OK)
        winsound.MessageBeep(code)
    except Exception as e:
        logger.debug(f"Failed to play sound '{type_}': {e}")


def list_input_devices() -> List[Tuple[int, dict]]:
    """List all available input audio devices.

    Queries system for input devices and prints formatted table with index,
    name, channel count, sample rate, and default device marker.

    Returns:
        List of tuples (device_index, device_info) for all input devices.
    """
    try:
        infos = sd.query_devices()
    except Exception as e:
        logger.error(f"Could not query devices: {e}", exc_info=True)
        return []

    inputs: List[Tuple[int, dict]] = []
    table = Table(title="Available Input Devices")
    table.add_column("Index", style="cyan")
    table.add_column("Device Name", style="green")
    table.add_column("Channels", justify="right", style="yellow")
    table.add_column("Sample Rate", justify="right", style="magenta")
    table.add_column("Status", style="blue")

    for i, info in enumerate(infos):
        if info.get('max_input_channels', 0) > 0:
            inputs.append((i, info))
            status: str = ''
            try:
                default = sd.default.device
                if isinstance(default, tuple) and default[0] == i:
                    status = '[DEFAULT]'
            except Exception:
                status = ''

            table.add_row(
                str(i),
                info['name'],
                str(info.get('max_input_channels')),
                f"{info.get('default_samplerate', 0):.0f} Hz",
                status
            )

    console.print(table)
    return inputs


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json file.

    Persists device selection and other settings for next session.
    Silently fails if write fails.

    Args:
        config: Configuration dictionary to save.
    """
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        logger.debug(f"Config saved to {CONFIG_PATH}")
    except Exception as e:
        logger.warning(f"Failed to save config: {e}")


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json file.

    Reads persisted settings like device selection. Returns empty dict
    if file doesn't exist or fails to parse.

    Returns:
        Configuration dictionary.
    """
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"Loaded config from {CONFIG_PATH}")
                return config
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
    return {}


def load_custom_vocabulary(vocab_path: Optional[str] = None) -> Optional[str]:
    """Load custom vocabulary from file for Whisper prompt.

    Reads comma or newline-separated words/phrases from a text file.
    Each line or comma-separated item becomes part of the prompt.

    File format examples:
    - Comma-separated: "Python, JavaScript, async, await, TypeScript"
    - Line-separated:
      Python
      JavaScript
      async
      await

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

        # Handle both comma-separated and line-separated formats
        if ',' in content:
            # Comma-separated
            words = [w.strip() for w in content.split(',') if w.strip()]
        else:
            # Line-separated
            words = [w.strip() for w in content.split('\n') if w.strip()]

        prompt = ', '.join(words)
        logger.info(f"Loaded {len(words)} vocabulary items from {vocab_path}")
        return prompt

    except Exception as e:
        logger.warning(f"Failed to load vocabulary from {vocab_path}: {e}")
        return None


def choose_device_interactive() -> Optional[int]:
    """Interactively prompt user to select an input device.

    Lists devices and asks user for numeric index. Returns None if blank
    or default device desired.

    Returns:
        Device index (int) or None for default.
    """
    inputs = list_input_devices()
    if not inputs:
        logger.error("No input devices found.")
        return None
    try:
        choice = input("Enter device index to use (or blank for default): ").strip()
        if not choice:
            return None
        idx = int(choice)
        return idx
    except Exception as e:
        logger.error(f"Invalid selection: {e}")
        return None


def record_test(duration: int = 3, filename: str = 'test_record.wav') -> None:
    """Record a short test audio clip for diagnostics.

    Useful for testing device configuration and audio capture before
    running the full voice-to-text pipeline.

    Args:
        duration: Recording duration in seconds (default: 3).
        filename: Output WAV file path (default: 'test_record.wav').
    """
    logger.info(f"Recording test clip ({duration}s) to {filename}...")
    try:
        device = sd.default.device[0] if sd.default.device else None
        sd.default.samplerate = SELECTED_SR
        sd.default.channels = 1
        data = sd.rec(
            int(duration * SELECTED_SR),
            device=device,
            samplerate=SELECTED_SR,
            channels=1,
            dtype='float32'
        )
        sd.wait()
        sf.write(filename, data, SELECTED_SR)
        logger.info(f"Saved test clip: {filename}")
    except Exception as e:
        logger.error(f"Test recording failed: {e}", exc_info=True)





# Global state
recorder: VoiceRecorder = VoiceRecorder()  # Will be re-initialized in main() with vocabulary


def detect_hotkey_mode() -> None:
    """Listen for keypresses and log them to help user find a working hotkey.

    This mode helps identify which key combinations are available on the user's system.
    Press the key combination you want to use, and it will be logged.
    Press Ctrl+C to exit.
    """
    console.print("[cyan]Hotkey Detection Mode - Press any keys to log them[/]")
    console.print("[yellow]Examples: Press 'Right Ctrl + Right Alt' or any key combo you want to use[/]")
    console.print("[yellow]Press Ctrl+C to exit[/]\n")

    pressed_keys = set()

    def on_press(key):
        try:
            # Get the key name
            if hasattr(key, 'name'):
                key_name = key.name
            elif hasattr(key, 'char'):
                key_name = key.char if key.char else str(key)
            else:
                key_name = str(key)

            pressed_keys.add(key_name)
            # Show current pressed keys
            keys_list = ", ".join(sorted(pressed_keys))
            console.print(f"[green]Pressed keys: {keys_list}[/]", end='\r')
        except Exception as e:
            logger.debug(f"Error in on_press: {e}")

    def on_release(key):
        try:
            # When user releases all keys, print the combination
            if hasattr(key, 'name'):
                key_name = key.name
            elif hasattr(key, 'char'):
                key_name = key.char if key.char else str(key)
            else:
                key_name = str(key)

            if key_name in pressed_keys:
                pressed_keys.discard(key_name)

            # If no keys pressed anymore, show the combo that was just released
            if not pressed_keys and key_name not in ['shift', 'ctrl', 'alt']:
                # Build the hotkey string from the last combo
                console.print(f"\n[cyan]Try using one of these hotkey formats:[/]")
                console.print(f"[white]--hotkey \"ctrl_r+alt_gr\" (Right Ctrl + Right Alt)[/]")
                console.print(f"[white]--hotkey \"alt+s\" (Alt + S)[/]")
                console.print(f"[white]--hotkey \"f13\" through \"f24\" (Function keys)[/]\n")
        except Exception as e:
            logger.debug(f"Error in on_release: {e}")

    # Use pynput to listen for keys
    from pynput import keyboard as kb
    listener = kb.Listener(on_press=on_press, on_release=on_release)
    try:
        listener.start()
        listener.join()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting hotkey detection...[/]")
        listener.stop()


def on_hotkey_press() -> None:
    """Called when hotkey is fully pressed - start recording."""
    global recording_active
    try:
        if recording_active:
            return

        with recorder.lock:
            is_active = recorder.recording or recorder.transcribing

        if not is_active:
            # Small delay to let audio system settle (helps with threading conflicts)
            time.sleep(0.05)
            if recorder.start_recording():
                recording_active = True
                logger.info("Recording started")
    except Exception as e:
        logger.error(f"Error on hotkey press: {e}", exc_info=True)


def on_hotkey_release() -> None:
    """Called when hotkey is fully released - stop recording and transcribe."""
    global recording_active
    try:
        recording_active = False
        if recorder.recording:
            audio = recorder.stop_recording()
            if audio is not None and len(audio) > 0:
                logger.info("Audio captured, starting transcription...")
                recorder.transcribe_async(audio, prompt=recorder.vocabulary_prompt)
            else:
                logger.warning("No audio captured")
    except Exception as e:
        logger.error(f"Error on hotkey release: {e}", exc_info=True)


def main() -> None:
    """Main entry point for voice-to-text application.

    Handles CLI argument parsing, device selection, hotkey configuration,
    and main event loop for recording/transcription.
    """
    parser = argparse.ArgumentParser(
        description='Voice to Text (Windows) - Hold hotkey to record, release to transcribe and paste'
    )
    parser.add_argument('--list-devices', action='store_true', help='List input devices and exit')
    parser.add_argument('--device', type=int, help='Input device index to use')
    parser.add_argument('--save-device', action='store_true', help='Save selected device to config')
    parser.add_argument('--diagnose', action='store_true', help='Run a short test recording and exit')
    parser.add_argument('--detect-hotkey', action='store_true', help='Detect available hotkeys by logging keypresses')
    parser.add_argument('--sr', type=int, help='Preferred sample rate (e.g., 44100)')
    parser.add_argument('--hotkey', type=str, default=None, help='Hotkey binding (default: ctrl_r+alt_gr). Examples: ctrl_r+alt_gr, f19, alt+s, ctrl+shift+r')
    parser.add_argument('--save-hotkey', action='store_true', help='Save hotkey to config')
    parser.add_argument('--vocabulary', type=str, default=None, help='Path to vocabulary file for custom words (default: vocabulary.txt in script dir)')
    parser.add_argument('--boost', type=float, default=0.0, help='Audio gain boost in dB (e.g., 6 to 12 for quiet audio)')
    parser.add_argument('--no-normalize', action='store_true', help='Disable loudness normalization (enabled by default)')
    parser.add_argument('--save-audio', action='store_true', help='Save audio processing settings (boost, normalize) to config')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config()

    # Determine hotkey: CLI > config > default
    hotkey_str: str = DEFAULT_HOTKEY

    if args.hotkey:
        # User provided hotkey via CLI
        hotkey_str = args.hotkey
        logger.info(f"Using hotkey from CLI: {hotkey_str}")
    elif 'hotkey' in config:
        # Use saved hotkey from config
        hotkey_str = config['hotkey']
        logger.info(f"Using hotkey from config: {hotkey_str}")
    else:
        logger.info(f"Using default hotkey: {hotkey_str}")

    logger.info(f"Configured hotkey: {hotkey_str}")

    # Print welcome banner with rich
    welcome_text = f"""[bold cyan]Voice to Text[/] (Windows)

[yellow]Hotkey:[/] [bold green]{hotkey_str}[/]
[yellow]Action:[/] Hold to record, release to transcribe & paste
[yellow]Exit:[/] Press Ctrl+C to quit

Logs appear below"""

    console.print(Panel(welcome_text, style="blue", expand=False))
    print_log_location()

    if args.sr:
        global SELECTED_SR
        SELECTED_SR = args.sr
        logger.info(f"Sample rate set to: {args.sr}Hz")

    # Configure audio processing (CLI > config > default)
    global AUDIO_BOOST, AUDIO_NORMALIZE

    # Determine boost: CLI > config > default (0.0)
    if args.boost != 0.0:
        # User provided boost via CLI
        AUDIO_BOOST = args.boost
        logger.debug(f"Using boost from CLI: {AUDIO_BOOST}dB")
    elif 'audio_boost' in config:
        # Use saved boost from config
        AUDIO_BOOST = config['audio_boost']
        logger.debug(f"Using boost from config: {AUDIO_BOOST}dB")
    else:
        # Use default (no boost)
        AUDIO_BOOST = 0.0

    # Determine normalize: CLI > config > default (True)
    if args.no_normalize:
        # User disabled normalization via CLI
        AUDIO_NORMALIZE = False
        logger.debug("Normalization disabled via CLI")
    elif 'audio_normalize' in config:
        # Use saved normalize setting from config
        AUDIO_NORMALIZE = config['audio_normalize']
        logger.debug(f"Using normalization from config: {AUDIO_NORMALIZE}")
    else:
        # Use default (enabled)
        AUDIO_NORMALIZE = True

    processing_info = []
    if AUDIO_BOOST != 0:
        processing_info.append(f"gain: +{AUDIO_BOOST}dB" if AUDIO_BOOST > 0 else f"gain: {AUDIO_BOOST}dB")
    if AUDIO_NORMALIZE:
        processing_info.append("normalization: enabled")
    if processing_info:
        logger.info(f"Audio processing: {', '.join(processing_info)}")

    # Load custom vocabulary
    vocab_prompt: Optional[str] = None
    if args.vocabulary:
        vocab_prompt = load_custom_vocabulary(args.vocabulary)
    else:
        # Try to load default vocabulary.txt if it exists
        vocab_prompt = load_custom_vocabulary()

    # Re-initialize recorder with vocabulary
    global recorder
    recorder = VoiceRecorder(vocabulary_prompt=vocab_prompt)

    if args.list_devices:
        list_input_devices()
        return

    if args.detect_hotkey:
        detect_hotkey_mode()
        return

    # Determine device to use: CLI -> config -> default
    selected: Optional[int] = None
    if args.device is not None:
        selected = args.device
    elif 'device' in config:
        # Load device from config and try to find it
        saved_device = config.get('device')
        saved_device_name = config.get('device_name', '')

        try:
            device_info = sd.query_devices(saved_device)
            current_name = device_info['name']

            if current_name == saved_device_name:
                # Device still exists with the same name - use it
                selected = saved_device
                logger.info(f"Loaded saved device {saved_device}: {current_name}")
            else:
                # Device index exists but name changed - warn and try to find by name
                logger.warning(f"Saved device #{saved_device} name changed from '{saved_device_name}' to '{current_name}'")
                selected = None
        except Exception as e:
            # Device ID not found - try to find by name
            logger.debug(f"Saved device #{saved_device} not available: {e}")
            selected = None

        # If device not found by ID, try to find by name
        if selected is None and saved_device_name:
            logger.info(f"Searching for device by name: '{saved_device_name}'")
            try:
                devices = sd.query_devices()

                # Search for device with matching name (case-insensitive, partial match)
                for idx in range(len(devices)):
                    dev_info = sd.query_devices(idx)
                    dev_name = dev_info['name'] if isinstance(dev_info, dict) else dev_info['name']
                    # Check if saved device name is contained in current device name
                    if saved_device_name.lower() in dev_name.lower():
                        selected = idx
                        logger.info(f"Found matching device #{idx}: {dev_name}")
                        break

                if selected is None:
                    logger.warning(f"Could not find device matching '{saved_device_name}'. Will prompt user to select.")
            except Exception as e:
                logger.debug(f"Error searching for device by name: {e}")

    if selected is None and sys.stdin.isatty():
        # interactive fallback
        logger.info("No device specified; you may choose one interactively:")
        selected = choose_device_interactive()

    if selected is not None:
        try:
            device_info = sd.query_devices(selected)
            device_name = device_info['name']

            sd.default.device = selected
            logger.info(f"Using input device: {selected} - {device_name}")

            if args.save_device:
                config['device'] = selected
                config['device_name'] = device_name
                save_config(config)
                logger.info(f"Device saved to config: {selected} ({device_name})")
        except Exception as e:
            logger.error(f"Failed to set selected device {selected}: {e}", exc_info=True)

    # Save hotkey to config if requested
    if args.save_hotkey:
        config['hotkey'] = args.hotkey
        save_config(config)
        logger.info(f"Hotkey saved to config: {args.hotkey}")

    # Save audio processing settings if requested
    if args.save_audio:
        config['audio_boost'] = AUDIO_BOOST
        config['audio_normalize'] = AUDIO_NORMALIZE
        save_config(config)
        logger.info(f"Audio settings saved to config: boost={AUDIO_BOOST}dB, normalize={AUDIO_NORMALIZE}")

    # Auto-detect device's native sample rate (unless user specified one)
    if not args.sr:
        try:
            if selected is not None:
                dev_info = sd.query_devices(selected)
            else:
                dev_info = sd.query_devices(kind='input')

            device_sr = int(dev_info['default_samplerate'])
            SELECTED_SR = device_sr
            logger.info(f"Default Input Device: {dev_info['name']} ({device_sr} Hz)")
            logger.debug(f"Auto-set sample rate to device's native rate: {device_sr} Hz")
        except Exception as e:
            logger.warning(f"Could not query default input device: {e}")
    else:
        logger.info(f"Using user-specified sample rate: {SELECTED_SR} Hz")

    # Run diagnostics if requested
    if args.diagnose:
        record_test(duration=3, filename='test_record.wav')
        return

    # Setup hotkey listener using pynput
    logger.info(f"Setting up hotkey listener for: {hotkey_str}")

    from pynput import keyboard as kb

    # Parse the hotkey string to know what to listen for
    hotkey_parts = [p.strip().lower() for p in hotkey_str.split('+')]
    logger.debug(f"Hotkey parts: {hotkey_parts}")

    # Map hotkey strings to pynput key objects
    def get_key_from_name(name: str):
        """Convert key name to pynput key object."""
        name = name.lower()

        # Single character keys
        if len(name) == 1:
            return name

        # Special keys
        special_keys = {
            'ctrl': kb.Key.ctrl,
            'ctrl_l': kb.Key.ctrl_l,
            'ctrl_r': kb.Key.ctrl_r,
            'alt': kb.Key.alt,
            'alt_l': kb.Key.alt_l,
            'alt_r': kb.Key.alt_r,
            'alt_gr': kb.Key.alt_gr,
            'shift': kb.Key.shift,
            'shift_l': kb.Key.shift_l,
            'shift_r': kb.Key.shift_r,
            'space': kb.Key.space,
            'enter': kb.Key.enter,
            'tab': kb.Key.tab,
            'escape': kb.Key.esc,
            'backspace': kb.Key.backspace,
            'delete': kb.Key.delete,
            'insert': kb.Key.insert,
        }

        # Function keys
        if name.startswith('f') and name[1:].isdigit():
            try:
                fn = int(name[1:])
                return getattr(kb.Key, f'f{fn}')
            except (AttributeError, ValueError):
                pass

        if name in special_keys:
            return special_keys[name]

        # Try as attribute
        try:
            return getattr(kb.Key, name)
        except AttributeError:
            logger.warning(f"Unknown key: {name}")
            return None

    # Convert hotkey parts to pynput keys
    hotkey_keys = [get_key_from_name(part) for part in hotkey_parts]
    hotkey_keys = [k for k in hotkey_keys if k is not None]

    if not hotkey_keys:
        logger.error(f"Could not parse hotkey: {hotkey_str}")
        console.print(f"[red]ERROR: Could not parse hotkey '{hotkey_str}'[/]")
        return

    logger.info(f"Hotkey keys: {hotkey_keys}")

    # Track which hotkey keys are currently pressed
    hotkey_pressed_keys = set()

    def on_press(key):
        """Called when any key is pressed."""
        nonlocal hotkey_pressed_keys

        for hotkey_key in hotkey_keys:
            if key == hotkey_key:
                hotkey_pressed_keys.add(hotkey_key)
                logger.debug(f"Hotkey key pressed: {key}, total pressed: {len(hotkey_pressed_keys)}")

                # Check if all hotkey keys are pressed
                if hotkey_pressed_keys == set(hotkey_keys):
                    logger.info("Hotkey PRESSED - starting recording")
                    on_hotkey_press()
                break

    def on_release(key):
        """Called when any key is released."""
        nonlocal hotkey_pressed_keys

        for hotkey_key in hotkey_keys:
            if key == hotkey_key:
                hotkey_pressed_keys.discard(hotkey_key)
                logger.debug(f"Hotkey key released: {key}, remaining: {len(hotkey_pressed_keys)}")

                # Check if we just released one of the hotkey keys
                if hotkey_pressed_keys != set(hotkey_keys):
                    logger.info("Hotkey RELEASED - stopping recording")
                    on_hotkey_release()
                break

    # Create and start the listener
    listener = kb.Listener(on_press=on_press, on_release=on_release)
    logger.info(f"Starting hotkey listener for: {hotkey_str}")

    try:
        listener.start()
        logger.info("Hotkey listener started successfully")

        # Main loop - just monitor transcription results
        while True:
            recorder.check_results()
            time.sleep(RESULT_CHECK_INTERVAL)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/]")
    finally:
        # Stop the hotkey listener
        try:
            listener.stop()
            logger.info("Hotkey listener stopped")
        except Exception as e:
            logger.debug(f"Error stopping listener: {e}")
        console.print("[cyan]Goodbye![/]\n")


if __name__ == "__main__":
    main()
