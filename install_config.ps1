# PowerShell script to install the CS2 Media Control config
$ErrorActionPreference = "Stop"

Write-Host "Searching for CS2 installation path..." -ForegroundColor Cyan

# Attempt to get CS2 path from Registry (Valve's specific key)
try {
    $cs2Reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\WOW6432Node\Valve\cs2" -ErrorAction Stop
    $installPath = $cs2Reg.installpath
}
catch {
    Write-Host "Error: Could not find CS2 installation path in Registry (HKLM:\SOFTWARE\WOW6432Node\Valve\cs2)." -ForegroundColor Red
    Write-Host "Please ensure CS2 is installed."
    exit 1
}

Write-Host "Found CS2 Path: $installPath" -ForegroundColor Green

# Construct the config directory path
# CS2 cfg folder is now located at: game\csgo\cfg
$cfgPath = Join-Path $installPath "game\csgo\cfg"

if (-not (Test-Path $cfgPath)) {
    Write-Host "Error: Config folder not found at: $cfgPath" -ForegroundColor Red
    exit 1
}

# Source file (assumed to be in the same folder as this script)
$scriptPath = $PSScriptRoot
$configFile = "gamestate_integration_media.cfg"
$sourcePath = Join-Path $scriptPath $configFile

if (-not (Test-Path $sourcePath)) {
    Write-Host "Error: Source config file not found at: $sourcePath" -ForegroundColor Red
    exit 1
}

# Copy the file
$destPath = Join-Path $cfgPath $configFile

Write-Host "Copying $configFile to $cfgPath..." -ForegroundColor Cyan

try {
    Copy-Item -Path $sourcePath -Destination $destPath -Force
    Write-Host "Success! Config installed." -ForegroundColor Green
    Write-Host "You can now restart CS2 for changes to take effect." -ForegroundColor Green
}
catch {
    Write-Host "Error copying file: $_" -ForegroundColor Red
    Write-Host "Try running this script as Administrator." -ForegroundColor Yellow
}
