"""
Voice to Text - Global Hotkey Recorder (macOS Version)
Runs in background.
Hold F19 to record (Map this in Karabiner!).
Release to transcribe and paste.
Pastes transcription directly into the active window.
"""

"""
macOS actually requires TWO separate permissions for this script:

Input Monitoring (which you granted): This lets the script hear the hotkey.
Accessibility (which is missing): This lets the script paste the text (send keystrokes).
The error osascript is not allowed to send keystrokes confirms Accessibility is missing.

To fix (takes 10 seconds):

Open System Settings -> Privacy & Security -> Accessibility.
Find your terminal (e.g., Use the + to add VS Code, iTerm, or Terminal).
Enable (toggle ON).
Restart the terminal app.
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
from pynput import keyboard
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
# DEVICE_ID = 6  # Removed hardcoded ID to allow auto-detection
SAMPLE_RATE = 44100
# Note: Ensure this API key is valid and secure in your .env file
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_TIMEOUT = 30  # seconds
MAX_RECORDING_SECONDS = 300  # 5-minute safety failsafe
HOTKEY = keyboard.Key.ctrl_l  # Use Left Control (Universal, non-intrusive)

class VoiceRecorder:
    def __init__(self):
        self.openai = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT)
        self.recording = False
        self.frames = []
        self.stream = None
        self.lock = threading.Lock()  # Protect state
        self.result_queue = queue.Queue()
        self.transcribing = False

    def start_recording(self):
        """Start recording audio"""
        with self.lock:
            if self.recording:
                return False
            self.recording = True
            self.frames = []

        def callback(indata, frame_count, time_info, status):
            if status:
                print(f"Audio status: {status}")
            with self.lock:
                if self.recording:
                    self.frames.append(indata.copy())
                    # Failsafe check: stop if we've reached the maximum duration
                    if len(self.frames) * frame_count / SAMPLE_RATE > MAX_RECORDING_SECONDS:
                        print("Failsafe: Maximum recording duration reached.")
                        self.recording = False  # The next loop or check_results will handle the rest

        try:
            # letting sounddevice choose the default input device
            self.stream = sd.InputStream(
                channels=1,
                samplerate=SAMPLE_RATE,
                callback=callback
            )
            self.stream.start()
            play_sound('start')
            print("Recording...")
            return True
        except Exception as e:
            print(f"Failed to start recording: {e}")
            with self.lock:
                self.recording = False
                self.frames = []
            return False

    def stop_recording(self):
        """Stop recording and return audio data"""
        with self.lock:
            if not self.recording:
                return None
            self.recording = False

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"Error stopping stream: {e}")
            self.stream = None

        play_sound('stop')
        print("Stopped recording")

        with self.lock:
            if self.frames:
                audio = np.concatenate(self.frames, axis=0)
                self.frames = []
                return audio
            self.frames = []
            return None

    def transcribe_async(self, audio_data):
        """Transcribe audio in background thread"""
        if self.transcribing:
            print("Already transcribing, please wait...")
            return

        self.transcribing = True

        def do_transcribe():
            try:
                result = self._transcribe(audio_data)
                self.result_queue.put(('success', result))
            except Exception as e:
                self.result_queue.put(('error', str(e)))
            finally:
                self.transcribing = False

        thread = threading.Thread(target=do_transcribe, daemon=True)
        thread.start()

    def _transcribe(self, audio_data):
        """Send audio to Whisper API (internal)"""
        min_samples = int(SAMPLE_RATE * 0.3)
        if audio_data is None or len(audio_data) < min_samples:
            return None

        temp_path = None
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_path = temp_file.name
            temp_file.close()

            sf.write(temp_path, audio_data, SAMPLE_RATE)

            with open(temp_path, 'rb') as f:
                result = self.openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=f
                )
            return result.text

        except Exception as e:
            print(f"Transcription error: {e}")
            raise e
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def paste_text(self, text):
        """Copy text to clipboard and paste it"""
        if not text:
            return

        print(f"Clipboard: Copying {len(text)} characters...")

        # Save current clipboard
        old_clipboard = ""
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            pass

        pyperclip.copy(text)
        time.sleep(0.2)  # Give clipboard time to update

        # Simulate Cmd+V using AppleScript (more robust on macOS)
        print("Simulating Cmd+V with AppleScript...")
        try:
            subprocess.run([
                'osascript', '-e', 'tell application "System Events" to keystroke "v" using command down'
            ], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip()
            print(f"Paste failed: {err_msg}")
            if "not allowed to send keystrokes" in err_msg or "1002" in err_msg:
                print("\n[!] ACTION REQUIRED: Terminal needs 'Accessibility' permission to paste.")
                print("    Go to: System Settings > Privacy & Security > Accessibility")
                print("    Enable your terminal application (e.g., iTerm, VS Code).")
                play_sound('error')

        # Restore clipboard (give the paste slightly longer to happen before restoring)
        time.sleep(1.0)
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            pass

    def check_results(self):
        """Check for completed transcription results (non-blocking)"""
        try:
            status, result = self.result_queue.get_nowait()
            if status == 'success' and result:
                print(f"Text: {result}")
                self.paste_text(result)
                # play_sound('success')
                return True
            elif status == 'success' and not result:
                print("Recording too short or no speech detected")
                play_sound('error')
            else:
                print(f"Transcription failed: {result}")
                play_sound('error')
            return False
        except queue.Empty:
            return None

def play_sound(type_):
    """Play system sounds asynchronously"""
    # macOS system sounds
    sounds = {
        'start': '/System/Library/Sounds/Tink.aiff',
        'stop': '/System/Library/Sounds/Pop.aiff',
        'success': '/System/Library/Sounds/Glass.aiff',
        'error': '/System/Library/Sounds/Basso.aiff'
    }
    sound_file = sounds.get(type_)
    if sound_file and os.path.exists(sound_file):
        subprocess.Popen(['afplay', sound_file], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

# Global State for Hotkey Handling
recorder = VoiceRecorder()


def on_press(key):
    try:
        if key == HOTKEY:
            # Check if already recording to avoid "key repeat" triggers
            with recorder.lock:
                is_active = recorder.recording or recorder.transcribing

            if not is_active:
                print("\nStarted recording...")
                recorder.start_recording()
    except Exception as e:
        print(f"Error on key press: {e}")


def on_release(key):
    try:
        if key == HOTKEY:
            if recorder.recording:
                audio = recorder.stop_recording()
                if audio is not None and len(audio) > 0:
                    print("Transcribing...")
                    recorder.transcribe_async(audio)
                else:
                    print("No audio captured")
    except Exception:
        pass


def main():
    print("=" * 50)
    print("  Voice to Text (macOS)")
    print("  Hold LEFT CONTROL to record")
    print("  Release to paste")
    print("  Press Ctrl+C to quit")
    print("=" * 50)

    # Verify audio device
    try:
        print(f"Default Input Device: {sd.query_devices(kind='input')['name']}")
    except Exception as e:
        print("Warning: Could not query default input device.")
        print(e)

    # Start Keyboard Listener
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    try:
        while True:
            recorder.check_results()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        listener.stop()
        print("Goodbye!")

if __name__ == "__main__":
    main()
