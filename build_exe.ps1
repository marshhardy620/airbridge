$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = "C:\Python312\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}
$Icon = Join-Path $Root "assets\airbridge.ico"
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name AirBridge --icon $Icon --add-data "${Icon};assets" airbridge_desktop.py
Write-Host "Created $(Join-Path $Root 'dist\AirBridge.exe')"
