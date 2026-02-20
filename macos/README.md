# Voice to Text (macOS)

Hold Right Cmd + Right Option to record audio, release to transcribe with OpenAI Whisper, and automatically paste the result into any active window.

## Prerequisites

macOS requires two system permissions:
1. **Input Monitoring** - Lets the script detect hotkey presses
2. **Accessibility** - Lets the script paste text via AppleScript

### Grant Accessibility Permission

1. Open **System Settings → Privacy & Security → Accessibility**
2. Click the **+** button and add your terminal app (e.g., iTerm, Terminal, VS Code)
3. Enable (toggle ON) for the application
4. Restart your terminal

## Features

- 🎤 Simple hotkey-based recording (Right Cmd + Right Option)
- 🤖 OpenAI Whisper transcription
- 📋 Auto-paste to active window via AppleScript
- 🔊 macOS system sounds for feedback (Tink, Pop, Glass, Basso)
- ⚙️ Custom vocabulary support for better recognition
- 🐛 Comprehensive logging with file rotation
- 📁 Outputs directory with rotating logs
- 🔄 Audio queueing for rapid-fire recordings

## Quick Start

### 1. Installation

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` and add your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env`:
```
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run

```bash
python voice_to_text.py
```

That's it! Hold **Right Cmd + Right Option** to record.

## Usage

### Basic Operation

1. **Press and hold** Right Cmd + Right Option
2. **Speak clearly** into your microphone
3. **Release** the keys
4. Text appears in your active window automatically

### CLI Arguments

```bash
# List available input devices
python voice_to_text.py --list-devices

# Use specific input device
python voice_to_text.py --device 2

# Save device selection to config
python voice_to_text.py --device 2 --save-device

# Use custom vocabulary for better transcription
python voice_to_text.py --vocabulary custom_words.txt

# Test your audio setup
python voice_to_text.py --diagnose

# Set sample rate
python voice_to_text.py --sr 48000

# Enable debug logging
python voice_to_text.py --verbose
```

## Configuration

Settings are saved to `config.json` in the same directory:

```json
{
  "device": 2
}
```

## Troubleshooting

### "not allowed to send keystrokes" error

**Problem**: Pasting fails with AppleScript permission error.

**Solution**:
1. Go to **System Settings → Privacy & Security → Accessibility**
2. Enable your terminal application (iTerm, Terminal, VS Code, etc.)
3. Restart your terminal
4. Try again

### "No audio captured" message

**Problem**: Recording runs but produces no audio.

**Solutions**:
1. Check microphone is enabled in System Settings → Sound
2. Verify microphone isn't muted (check menu bar)
3. Test with `--diagnose` flag:
   ```bash
   python voice_to_text.py --diagnose
   ```
   This saves a 3-second test recording to `test_record.wav`

4. List devices to ensure correct one is selected:
   ```bash
   python voice_to_text.py --list-devices
   ```

5. Try a different device:
   ```bash
   python voice_to_text.py --device 1
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
   python voice_to_text.py --list-devices
   ```

2. **Try default device** (remove `--device` flag)

3. **Check sample rate** - try different rates:
   ```bash
   python voice_to_text.py --sr 44100
   ```

4. **Enable verbose logging** to see detailed errors:
   ```bash
   python voice_to_text.py --verbose
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
   python voice_to_text.py --verbose
   ```

5. **Check internet connection** - Whisper API requires network access

### Paste not working in specific apps

**Problem**: Text pastes fine in some apps but not others.

**Solutions**:
1. **Check app permissions** - Some apps block automation. Go to **System Settings → Privacy & Security** and verify permissions for the target app.
2. **Try manual paste** with **Cmd+V** if auto-paste fails (text is still in clipboard)
3. **Check if app supports text input** - paste only works in text input fields
4. **Run Terminal as Administrator** - Some apps require elevated privileges

## Debug Logging

Enable debug output to see detailed operation information:

```bash
python voice_to_text.py --verbose
```

This shows:
- Device initialization
- API calls and timing
- Clipboard operations
- AppleScript execution details
- All errors with full traceback

Logs are saved to `outputs/macos.log` for persistent history.

## Dependencies

- `sounddevice` - Audio capture
- `soundfile` - WAV file writing
- `numpy` - Audio data handling
- `openai` - Whisper transcription API
- `pyperclip` - Clipboard access
- `pynput` - Keyboard listening
- `python-dotenv` - Environment variable loading
- `rich` - Colored terminal output

## Performance Notes

- Default timeout for OpenAI API: **30 seconds**
- Maximum recording duration: **5 minutes** (safety failsafe)
- Minimum audio duration for transcription: **0.3 seconds**
- Polling interval: **50ms** for result checking
- Clipboard delay: **0.2 seconds** (longer on macOS for stability)

## Keyboard Behavior

The Right Cmd + Right Option hotkey requires both keys to be pressed simultaneously to trigger recording. This prevents accidental activation while using standard Mac shortcuts.

## Custom Vocabulary

Improve Whisper's transcription accuracy for technical terms:

1. Create a `vocabulary.txt` file in the same directory as the script
2. Add terms, one per line or comma-separated:
   ```
   Python, JavaScript, async, await
   TypeScript, React, Node.js
   ```

3. The script auto-loads it, or use:
   ```bash
   python voice_to_text.py --vocabulary my_words.txt
   ```

## Tips & Best Practices

1. **For code**: Speak slowly and use hyphens between words (e.g., "underscore", "dash")
2. **Clean environment**: Less background noise = better transcription
3. **Test first**: Always run `--diagnose` after setup to verify audio works
4. **Save settings**: Use `--save-device` to persist your preferred input device
5. **Check logs**: Use `--verbose` when troubleshooting issues
6. **Multiple recordings**: Queue up recordings by pressing the hotkey while transcribing - each gets processed in order

## macOS-Specific Notes

- Uses **AppleScript** for pasting (more reliable than keyboard simulation on macOS)
- Respects macOS system sounds for notifications
- Logs are saved to `outputs/macos.log`
- Works with any text input field that accepts clipboard operations

## License

Depends on OpenAI API terms of service.

---

**Need help?** Check the Troubleshooting section above or run with `--verbose` for detailed logs.
