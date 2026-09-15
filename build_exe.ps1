# PowerShell script to build the CS2 Media Control EXE
$ErrorActionPreference = "Stop"

Write-Host "Checking for virtual environment..." -ForegroundColor Cyan

# 1. Create/Check Virtual Environment
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment '.venv'..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "Virtual environment found." -ForegroundColor Green
}

# 2. Activate Virtual Environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& ".\.venv\Scripts\Activate.ps1"

# 3. Install Requirements
Write-Host "Installing requirements..." -ForegroundColor Cyan
pip install -r requirements.txt
pip install pyinstaller

# 4. Build EXE
Write-Host "Building EXE with PyInstaller..." -ForegroundColor Cyan
# --noconsole: No terminal window
# --onefile: Single EXE file
# --name: Name of the output file
pyinstaller --noconsole --onefile --name "CS2MediaControl" --collect-submodules winrt --add-data "assets;assets" cs2_media_control.py

# 5. Cleanup and Move
Write-Host "Cleaning up..." -ForegroundColor Cyan
if (Test-Path "dist\CS2MediaControl.exe") {
    Copy-Item "dist\CS2MediaControl.exe" "." -Force
    Write-Host "Build complete! CS2MediaControl.exe is ready in this folder." -ForegroundColor Green

    # Optional: Clean up build folders
    Remove-Item "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "dist" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "CS2MediaControl.spec" -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Build failed! EXE not found in dist folder." -ForegroundColor Red
    exit 1
}

Write-Host "Don't forget to run 'install_config.ps1' to setup the game config if you haven't yet!" -ForegroundColor Magenta
