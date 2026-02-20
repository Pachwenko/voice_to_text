# Voice to Text

Hold a hotkey, speak, and automatically transcribe and paste text. Cross-platform (Windows & macOS).

## Install

```bash
# Windows
cd windows
pip install -r requirements.txt

# macOS
cd macos
pip install -r requirements.txt
```

## Setup

1. **Get an OpenAI API key** from https://platform.openai.com/api-keys

2. **Create `.env` file** in project root:
```
OPENAI_API_KEY=sk-...your-key...
```

3. **Windows only - Find your audio device:**
```bash
python voice_to_text_windows.py --list-devices
```

4. **Test it:**
```bash
python voice_to_text_windows.py --diagnose
```

## Usage

```bash
# Windows
python voice_to_text_windows.py

# macOS
python voice_to_text.py
```

**Press Right Ctrl + Right Alt** (or your configured hotkey) to record. Release to transcribe and paste.

## Configuration

Settings persist in `config.json`. Common options:

```bash
# Change hotkey
python voice_to_text_windows.py --hotkey "alt+shift+r" --save-hotkey

# Adjust audio boost (for quiet audio)
python voice_to_text_windows.py --boost 10 --save-audio

# Disable loudness normalization
python voice_to_text_windows.py --no-normalize --save-audio

# Select different audio device
python voice_to_text_windows.py --device 65 --save-device
```

**Find your hotkey:**
```bash
python voice_to_text_windows.py --detect-hotkey
```
Press the keys you want to use, it will show you the format to use.

## Logs

Check `outputs/windows.log` or `outputs/macos.log` if something goes wrong.

## Troubleshooting

**"Failed to register hotkey"**
- Your hotkey is already in use. Run `--detect-hotkey` and choose a different one

**"No audio captured"**
- Check device: `python voice_to_text_windows.py --list-devices`
- Run diagnostic: `python voice_to_text_windows.py --diagnose`
- Try boosting audio: `--boost 12`

**"Whisper API error"**
- Verify your `OPENAI_API_KEY` is correct and has quota
- Check your internet connection

**Script exits immediately**
- Run with `--verbose` to see detailed logs: `python voice_to_text_windows.py --verbose`
- Check `outputs/windows.log` for errors

## Files

- `src/` - Shared Python modules (audio processing, logging)
- `windows/` - Windows implementation
- `macos/` - macOS implementation
- `windows/config.json` - Your saved settings
- `outputs/` - Log files
