# Building Standalone Executable

This guide explains how to build a standalone `.exe` file that can be deployed and run on Windows machines without requiring Python to be installed.

## What You Get

Building creates `dist/VoiceToText.exe` - a single executable file that includes:
- All Python dependencies (sounddevice, numpy, openai, etc.)
- The voice_to_text_windows.py script
- Rich library for nice terminal output
- Everything needed to run Voice to Text

**File size**: ~100-150 MB (depending on dependencies)

## Prerequisites

1. **Python 3.8+** installed and in PATH
2. **pip** (comes with Python)
3. **~1 GB free disk space** (for building)

## Quick Start

### Option 1: Batch Script (Easiest for Windows)

Double-click `build.bat`:

```bash
# Or run from cmd/PowerShell
.\build.bat
```

The script will:
1. Create a virtual environment
2. Install PyInstaller and dependencies
3. Build the executable
4. Show success/failure message

### Option 2: PowerShell Script

```powershell
# Run in PowerShell
.\build.ps1
```

Same as above but with colored output.

### Option 3: Manual Build

```bash
# Create and activate venv
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build executable
pyinstaller ^
    --name "VoiceToText" ^
    --onefile ^
    --windowed ^
    --add-data ".env.example;." ^
    --add-data "vocabulary.example.txt;." ^
    --hidden-import=rich ^
    --hidden-import=pynput.keyboard._win32 ^
    --collect-all=sounddevice ^
    --collect-all=soundfile ^
    --collect-all=openai ^
    --paths=.. ^
    voice_to_text_windows.py
```

## Output

After building successfully:

```
dist/
├── VoiceToText.exe          ← Your standalone executable
├── .env                     ← Default config (modify this!)
├── vocabulary.txt           ← Default vocabulary (optional)
└── outputs/                 ← Created at runtime (logs)
build/                       ← Build artifacts (safe to delete)
VoiceToText.spec             ← Build configuration (safe to delete)
```

**Important**: The `.env` file in `dist/` is created with the example template. You **MUST** edit it and add your `OPENAI_API_KEY`.

## Deployment

The executable comes with default `.env` and `vocabulary.txt` files embedded. Users can override by placing their own files next to the exe.

### For Single User

1. Copy entire `dist/` folder to desired location
2. Edit `dist/.env` and add your `OPENAI_API_KEY`:
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```
3. Optionally edit `dist/vocabulary.txt` for custom words
4. Run `VoiceToText.exe`

The exe will read from these local files if they exist, otherwise uses embedded defaults.

### For Multiple Users / Distribution

Create a deployment folder:

```
VoiceToText/
├── VoiceToText.exe           ← Standalone executable
├── .env                      ← Edit to add API key
├── vocabulary.txt            ← Optional custom words
├── README.txt                ← Setup instructions
└── SETUP_INSTRUCTIONS.txt    ← (Optional)
```

**Setup Instructions to include:**

```
SETUP INSTRUCTIONS
==================

1. Extract all files to a folder
2. Open .env file and replace:
   OPENAI_API_KEY=your-key-here
3. (Optional) Edit vocabulary.txt with your custom words
4. Double-click VoiceToText.exe to run

The app will:
- Read .env and vocabulary.txt from the same folder
- Create an outputs/ folder for logs
- Store settings in config.json
```

Zip and distribute. Users just need to:
1. Extract the folder
2. Edit `.env` with their `OPENAI_API_KEY`
3. Run `VoiceToText.exe`

## Configuration Files

The executable comes with embedded `.env` and `vocabulary.txt` files as fallbacks. It checks for local files in this priority order:

**Priority (highest to lowest):**
1. Local `.env` file in same folder as exe (user's custom settings)
2. Local `vocabulary.txt` file in same folder as exe (user's custom words)
3. Embedded defaults in the exe

**File Layout:**
```
Same Folder as VoiceToText.exe:
├── VoiceToText.exe           ← Executable (embeds defaults)
├── .env                      ← OPTIONAL (overrides embedded .env)
├── vocabulary.txt            ← OPTIONAL (overrides embedded vocab)
├── config.json               ← AUTO-CREATED (device settings)
└── outputs/                  ← AUTO-CREATED (logs folder)
```

**What this means:**
- Users can run the exe with no files → uses embedded defaults
- Users can add `.env` next to exe → their API key loads instead
- Users can add `vocabulary.txt` → their custom words load instead
- Perfect for distribution without exposing credentials

## Logging & Outputs

When running, the executable creates:

```
outputs/
└── windows.log          ← Rotating log file (10MB max, keeps 5 backups)
```

## Troubleshooting

### "PyInstaller not found"

```bash
pip install pyinstaller
```

### Build fails with "hidden imports"

Make sure all dependencies are installed:

```bash
pip install -r requirements.txt
```

### "ModuleNotFoundError" when running executable

This usually means a dependency wasn't bundled correctly. Try:

```bash
# Clean and rebuild
rm -r dist build
./build.bat
```

### Antivirus warns about executable

This is common with PyInstaller-built executables. The file is safe - PyInstaller bundles everything including dlls, which antivirus software sometimes flags as suspicious.

To verify safety:
- Build it yourself from source code
- Keep the source code available for review
- Use VirusTotal to scan if concerned

### Executable is too large

100-150 MB is normal for PyInstaller bundles with numpy, scipy, and audio libraries. To reduce:

1. Remove `--collect-all` flags if dependencies aren't needed
2. Use UPX compression (advanced)
3. Create a smaller version without numpy/visualization

## Advanced Options

### Custom Icon

Replace the `.ico` file or build without it:

```bash
# Remove this line from build script
--icon=voice_to_text.ico
```

### Different Output Name

```bash
--name "MyVoiceApp"          # Creates MyVoiceApp.exe instead
```

### Console Window

Remove `--windowed` to show console:

```bash
# Shows command window with debug output
--onefile ^
# (remove --windowed)
```

### Code Signing

For professional distribution, sign the executable:

```bash
# After building
signtool sign /f certificate.pfx dist\VoiceToText.exe
```

## Clean Up

Remove build artifacts:

```bash
# Delete these folders/files after successful build
rm -r build
rm -r dist\*.pyd
rm VoiceToText.spec
```

Keep only `dist/VoiceToText.exe`

## Size Optimization

To create a smaller executable:

```bash
# Use UPX compression (if installed)
pyinstaller --upx-dir=C:\path\to\upx ...

# Or strip debug symbols
strip dist\VoiceToText.exe
```

## Version Info

To add version info to executable properties:

1. Create `version.txt` with product info
2. Use PyInstaller's `--version-file` option
3. (Advanced - requires version file format)

## Multi-Platform Distribution

If you need macOS version, use:
```bash
cd ../macos
python -m PyInstaller voice_to_text.py --onefile
```

(Note: PyInstaller on Windows can't build macOS executables - must build on Mac)

## Next Steps

- ✅ Built executable: `dist/VoiceToText.exe`
- ✅ Create `.env` with your API key
- ✅ Optionally add `vocabulary.txt`
- ✅ Test by running the executable
- ✅ Distribute to other users

Enjoy! 🎉
