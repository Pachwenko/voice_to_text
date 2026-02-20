# Voice to Text Windows - Build Executable Script (PowerShell)
# Creates a standalone .exe that can be deployed without Python installed

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Voice to Text Builder" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if venv exists
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate venv
& ".\venv\Scripts\Activate.ps1"

# Install/upgrade build dependencies
Write-Host "Installing build dependencies..." -ForegroundColor Yellow
pip install -q --upgrade pip setuptools wheel
pip install -q pyinstaller

# Install project dependencies
Write-Host "Installing project dependencies..." -ForegroundColor Yellow
pip install -q -r requirements.txt

# Create build directory
if (-not (Test-Path "build")) {
    New-Item -ItemType Directory -Path "build" -Force > $null
}

# Run PyInstaller
Write-Host ""
Write-Host "Building executable... This may take a minute..." -ForegroundColor Yellow
Write-Host ""

pyinstaller `
    --name "VoiceToText" `
    --onefile `
    --windowed `
    --icon=voice_to_text.ico `
    --add-data ".env.example;." `
    --add-data "vocabulary.example.txt;." `
    --hidden-import=rich `
    --hidden-import=pynput.keyboard._win32 `
    --collect-all=sounddevice `
    --collect-all=soundfile `
    --collect-all=openai `
    --paths=.. `
    --distpath dist `
    --workpath build `
    voice_to_text_windows.py

# Create default .env and vocabulary.txt in the dist folder
if (-not (Test-Path "dist\.env")) {
    Copy-Item ".env.example" "dist\.env" -Force
}
if (-not (Test-Path "dist\vocabulary.txt")) {
    Copy-Item "vocabulary.example.txt" "dist\vocabulary.txt" -Force
}

# Check build success
if (Test-Path "dist\VoiceToText.exe") {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "   SUCCESS!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Executable created: dist\VoiceToText.exe" -ForegroundColor Green
    Write-Host ""
    Write-Host "Before deploying, remember to:" -ForegroundColor Yellow
    Write-Host " 1. Create a .env file with OPENAI_API_KEY" -ForegroundColor Yellow
    Write-Host " 2. Optionally add vocabulary.txt for custom words" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To run: .\dist\VoiceToText.exe" -ForegroundColor Cyan
    Write-Host ""
    Read-Host "Press Enter to continue"
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "   BUILD FAILED" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the output above for errors." -ForegroundColor Yellow
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host " - Missing dependencies (run: pip install -r requirements.txt)" -ForegroundColor Yellow
    Write-Host " - Python not in PATH" -ForegroundColor Yellow
    Write-Host " - Insufficient disk space" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to continue"
}

# Deactivate venv
deactivate
