$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $Root "dist"
$PackageDir = Join-Path $Dist "AirBridge"
$ZipPath = Join-Path $Dist "AirBridge.zip"

New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
Copy-Item -Path (Join-Path $Root "airbridge.py") -Destination $PackageDir -Force
Copy-Item -Path (Join-Path $Root "airbridge_desktop.py") -Destination $PackageDir -Force
Copy-Item -Path (Join-Path $Root "run_airbridge.bat") -Destination $PackageDir -Force
Copy-Item -Path (Join-Path $Root "README.md") -Destination $PackageDir -Force
Copy-Item -Path (Join-Path $Root "requirements.txt") -Destination $PackageDir -Force
$AssetsSource = Join-Path $Root "assets"
$AssetsDest = Join-Path $PackageDir "assets"
if (Test-Path $AssetsDest) {
    Remove-Item -Path $AssetsDest -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $AssetsDest | Out-Null
Copy-Item -Path (Join-Path $AssetsSource "airbridge.ico") -Destination $AssetsDest -Force
Copy-Item -Path (Join-Path $AssetsSource "airbridge.png") -Destination $AssetsDest -Force

if (Test-Path $ZipPath) {
    Remove-Item -Path $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force
Remove-Item -Path $PackageDir -Recurse -Force
Write-Host "Created $ZipPath"
