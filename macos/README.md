# Voice to Text (macOS)

A high-performance, background voice-to-text utility for macOS. It allows you to record audio by holding a hotkey and automatically transcribes and pastes the text into your active application.

## Features
- **Global Hotkey**: Uses **Right Command + Right Option**.
- **Auto-Paste**: Directly inserts transcription into the active text field.
- **Safety Failsafe**: Automatically stops recording after 5 minutes.
- **Low Latency**: Uses OpenAI Whisper API.

## Setup & Usage

```bash
./run.sh
```

## How to Record
1. Click into any text field.
2. **Hold Right Command + Right Option** together to start recording.
3. **Release** either key to finish.


## macOS Permissions (Crucial)

macOS requires two specific permissions for this script to function:

1.  **Input Monitoring**: Required for the script to "hear" the hotkey press while running in the background.
    - System Settings > Privacy & Security > Input Monitoring
    - Add/Enable your Terminal (e.g., Terminal, iTerm2, or VS Code).
2.  **Accessibility**: Required for the script to "paste" the text into other apps.
    - System Settings > Privacy & Security > Accessibility
    - Add/Enable your Terminal.

> **Note**: If you grant permissions and it still doesn't work, **restart your terminal app**.

## Configuration
You can modify `voice_to_text.py` to change:
- `MAX_RECORDING_SECONDS`: Safety limit (default 300s).
- `OPENAI_API_KEY`: Your Whisper API key.
- `SAMPLE_RATE`: Audio quality (default 44100).
