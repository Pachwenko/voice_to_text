# Voice to Text (Windows)

Hold a hotkey to record audio, release to transcribe with OpenAI Whisper, and automatically paste the result into any active window.

## Features

- 🎤 Simple hotkey-based recording (default: `Right Ctrl + Right Alt`)
- 🤖 OpenAI Whisper transcription
- 📋 Auto-paste to active window
- 🔧 Customizable hotkeys and input devices
- 🔊 Audio feedback (start/stop/error notifications)
- ⚙️ Persistent configuration
- 🐛 Comprehensive logging for debugging

## Quick Start

### 1. Installation

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` and add your OpenAI API key:

```bash
copy .env.example .env
```

Edit `.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run

```bash
python voice_to_text_windows.py
```

That's it! Hold `Right Ctrl + Right Alt` to record.

## Usage

### Basic Operation

1. **Press and hold** the hotkey (default: `Right Ctrl + Right Alt`)
2. **Speak clearly** into your microphone
3. **Release** the hotkey
4. Text appears in your active window automatically

### CLI Arguments

```bash
# List available input devices
python voice_to_text_windows.py --list-devices

# Use specific input device
python voice_to_text_windows.py --device 2

# Save device selection to config
python voice_to_text_windows.py --device 2 --save-device

# Change hotkey (examples)
python voice_to_text_windows.py --hotkey "f19"
python voice_to_text_windows.py --hotkey "alt+s"
python voice_to_text_windows.py --hotkey "ctrl+shift+r"

# Save hotkey to config
python voice_to_text_windows.py --hotkey "f19" --save-hotkey

# Use custom vocabulary for better transcription
python voice_to_text_windows.py --vocabulary custom_words.txt

# Test your audio setup
python voice_to_text_windows.py --diagnose

# Set sample rate
python voice_to_text_windows.py --sr 48000

# Enable debug logging
python voice_to_text_windows.py --verbose
```

## Configuration

Settings are saved to `config.json` in the same directory. You can manually edit it or use CLI flags:

```json
{
  "device": 2,
  "hotkey": "ctrl+shift+r"
}
```

### Supported Hotkeys

Single keys:
- Function keys: `f1` through `f24`
- Examples: `f19`, `f12`

Modifier combinations:
- `ctrl+shift+r` (Ctrl+Shift+R)
- `alt+s` (Alt+S)
- `ctrl+alt+a` (Ctrl+Alt+A)
- `shift+f12` (Shift+F12)

## Troubleshooting

### "No audio captured" message

**Problem**: Recording runs but produces no audio.

**Solutions**:
1. Check microphone is enabled in Windows sound settings
2. Verify microphone isn't muted
3. Test with `--diagnose` flag:
   ```bash
   python voice_to_text_windows.py --diagnose
   ```
   This saves a 3-second test recording to `test_record.wav`

4. List devices to ensure correct one is selected:
   ```bash
   python voice_to_text_windows.py --list-devices
   ```

5. Try a different device:
   ```bash
   python voice_to_text_windows.py --device 1
   ```

### "Recording too short or no speech detected"

**Problem**: Recording completes but Whisper can't detect speech.

**Solutions**:
1. **Speak louder** and closer to microphone
2. **Record longer** (at least 0.3 seconds of speech)
3. **Check audio input device** - use `--list-devices` to verify
4. **Test microphone** with `--diagnose` and listen to `test_record.wav`
5. **Reduce background noise** - Whisper works better in quiet environments

### "Failed to start recording"

**Problem**: Recording won't start with an error message.

**Solutions**:
1. **Check device availability**:
   ```bash
   python voice_to_text_windows.py --list-devices
   ```

2. **Try default device** (remove `--device` flag)

3. **Check sample rate** - try different rates:
   ```bash
   python voice_to_text_windows.py --sr 44100
   ```

4. **Check permissions** - ensure app has microphone access in Windows Settings

5. **Enable verbose logging** to see detailed errors:
   ```bash
   python voice_to_text_windows.py --verbose
   ```

### "Transcription error" / No text produced

**Problem**: Recording works but transcription fails.

**Solutions**:
1. **Verify API key** in `.env` file - should start with `sk-`
2. **Check OpenAI account** - ensure it has credits/active subscription
3. **Test API connectivity**:
   ```bash
   python -c "from openai import OpenAI; OpenAI(api_key='your-key').models.list()"
   ```

4. **Enable verbose logging**:
   ```bash
   python voice_to_text_windows.py --verbose
   ```

5. **Check internet connection** - Whisper API requires network access

### "Paste simulation failed"

**Problem**: Text isn't pasting into applications.

**Solutions**:
1. **Run as Administrator** - some apps require elevated permissions
2. **Check clipboard** - text should still be in clipboard as fallback
3. **Manually paste** with `Ctrl+V` if auto-paste fails
4. **Check active window** - paste only works in text input fields

### Wrong audio device selected

**Problem**: Recording from wrong microphone.

**Solutions**:
1. List all devices:
   ```bash
   python voice_to_text_windows.py --list-devices
   ```

2. Select correct device:
   ```bash
   python voice_to_text_windows.py --device 2
   ```

3. Save selection:
   ```bash
   python voice_to_text_windows.py --device 2 --save-device
   ```

4. Verify in Windows Settings → Sound → Input devices

### Hotkey not working

**Problem**: Pressing hotkey doesn't start recording.

**Solutions**:
1. **Verify hotkey is set correctly**:
   ```bash
   python voice_to_text_windows.py --hotkey "ctrl+shift+r" --verbose
   ```

2. **Try single-key hotkey** instead:
   ```bash
   python voice_to_text_windows.py --hotkey "f19"
   ```

3. **Check for conflicts** - Some Windows shortcuts or apps might intercept keys
   - Try different key combination
   - Disable conflicting hotkeys in other apps

4. **Run as Administrator** - helps with low-level keyboard access

5. **Check config.json** for invalid hotkey string:
   ```json
   {
     "hotkey": "ctrl+shift+r"
   }
   ```

## Debug Logging

Enable debug output to see detailed operation information:

```bash
python voice_to_text_windows.py --verbose
```

This shows:
- Sample rate selection and fallbacks
- Device initialization
- Hotkey parsing
- API calls and timing
- Clipboard operations
- All errors with full traceback

## Dependencies

- `sounddevice` - Audio capture
- `soundfile` - WAV file writing
- `numpy` - Audio data handling
- `openai` - Whisper transcription API
- `pyperclip` - Clipboard access
- `pynput` - Keyboard listening
- `python-dotenv` - Environment variable loading

## Performance Notes

- Default timeout for OpenAI API: **30 seconds**
- Maximum recording duration: **5 minutes** (safety failsafe)
- Minimum audio duration for transcription: **0.3 seconds**
- Polling interval: **50ms** for result checking
- Sample rates tested: 44100Hz, 48000Hz, 16000Hz (fallback chain)

## Keyboard Listener Behavior

The keyboard listener runs in a separate thread and monitors all keyboard events globally. This allows the hotkey to work even when the application window is not focused.

**Note**: On some systems, global keyboard listening may require running as Administrator.

## Custom Vocabulary (Planned Feature)

Support for custom word lists to improve Whisper transcription accuracy for:
- Python/JavaScript syntax keywords
- Domain-specific terminology
- Project-specific terminology

Check back for updates!

## Tips & Best Practices

1. **For code**: Speak slowly and use hyphens between words (e.g., "underscore", "dash")
2. **Clean environment**: Less background noise = better transcription
3. **Test first**: Always run `--diagnose` after setup to verify audio works
4. **Save settings**: Use `--save-device` and `--save-hotkey` to persist your preferences
5. **Check logs**: Use `--verbose` when troubleshooting issues

## License

Depends on OpenAI API terms of service.

---

**Need help?** Check the Troubleshooting section above or run with `--verbose` for detailed logs.
