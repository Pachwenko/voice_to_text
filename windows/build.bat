@echo off
REM Voice to Text Windows - Build Executable Script
REM Creates a standalone .exe that can be deployed without Python installed

echo.
echo ============================================
echo   Voice to Text Builder
echo ============================================
echo.

REM Check if venv exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install/upgrade build dependencies
echo Installing build dependencies...
pip install -q --upgrade pip setuptools wheel
pip install -q pyinstaller

REM Install project dependencies
echo Installing project dependencies...
pip install -q -r requirements.txt

REM Create build directory
if not exist "build" mkdir build

REM Run PyInstaller
echo.
echo Building executable... This may take a minute...
echo.

pyinstaller ^
    --name "VoiceToText" ^
    --onefile ^
    --windowed ^
    --icon=voice_to_text.ico ^
    --add-data ".env.example;." ^
    --add-data "vocabulary.example.txt;." ^
    --hidden-import=rich ^
    --hidden-import=pynput.keyboard._win32 ^
    --collect-all=sounddevice ^
    --collect-all=soundfile ^
    --collect-all=openai ^
    --paths=.. ^
    --distpath dist ^
    --workpath build ^
    voice_to_text_windows.py

REM Create default .env and vocabulary.txt in the dist folder
if not exist "dist\.env" (
    copy ".env.example" "dist\.env" >nul
)
if not exist "dist\vocabulary.txt" (
    copy "vocabulary.example.txt" "dist\vocabulary.txt" >nul
)

REM Check build success
if exist "dist\VoiceToText.exe" (
    echo.
    echo ============================================
    echo   SUCCESS!
    echo ============================================
    echo.
    echo Executable created: dist\VoiceToText.exe
    echo.
    echo Before deploying, remember to:
    echo  1. Create a .env file with OPENAI_API_KEY
    echo  2. Optionally add vocabulary.txt for custom words
    echo.
    echo To run: .\dist\VoiceToText.exe
    echo.
    pause
) else (
    echo.
    echo ============================================
    echo   BUILD FAILED
    echo ============================================
    echo.
    echo Check the output above for errors.
    echo Common issues:
    echo  - Missing dependencies (run: pip install -r requirements.txt)
    echo  - Python not in PATH
    echo  - Insufficient disk space
    echo.
    pause
)

REM Deactivate venv
deactivate
