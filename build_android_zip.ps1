$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $Root "dist"
$Source = Join-Path $Root "AirBridgeAndroid"
$PackageDir = Join-Path $Dist "AirBridgeAndroid-source"
$ZipPath = Join-Path $Dist "AirBridgeAndroid-source.zip"

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
if (Test-Path $PackageDir) {
    Remove-Item -Path $PackageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

$ExcludeDirs = @(".gradle", "build", ".idea")
Get-ChildItem -Path $Source -Recurse -Force | ForEach-Object {
    $relative = $_.FullName.Substring($Source.Length).TrimStart("\", "/")
    if (-not $relative) {
        return
    }
    $skip = $false
    foreach ($exclude in $ExcludeDirs) {
        if ($relative -eq $exclude -or $relative.StartsWith("$exclude\")) {
            $skip = $true
            break
        }
    }
    if ($skip) {
        return
    }
    $target = Join-Path $PackageDir $relative
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

if (Test-Path $ZipPath) {
    Remove-Item -Path $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force
Remove-Item -Path $PackageDir -Recurse -Force
Write-Host "Created $ZipPath"
