$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Project = Join-Path $Root "AirBridgeAndroid"
$SigningDir = Join-Path $Project "signing"
$SigningProps = Join-Path $SigningDir "signing.properties"
$Keystore = Join-Path $SigningDir "airbridge-release.jks"
$Dist = Join-Path $Root "dist"
$ApkSource = Join-Path $Project "app\build\outputs\apk\release\app-release.apk"
$ApkDest = Join-Path $Dist "AirBridgeAndroid-release.apk"

New-Item -ItemType Directory -Force -Path $SigningDir | Out-Null
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

function New-RandomPassword {
    $bytes = New-Object byte[] 24
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    [Convert]::ToBase64String($bytes).TrimEnd("=")
}

if (-not (Test-Path $SigningProps)) {
    $storePassword = New-RandomPassword
    @"
storeFile=airbridge-release.jks
storePassword=$storePassword
keyAlias=airbridge
keyPassword=$storePassword
"@ | Set-Content -LiteralPath $SigningProps -Encoding ASCII
}

$props = @{}
Get-Content -LiteralPath $SigningProps -Encoding UTF8 | ForEach-Object {
    if ($_ -match "^\s*([^#=]+?)\s*=\s*(.+)\s*$") {
        $props[$matches[1]] = $matches[2]
    }
}

if (-not (Test-Path $Keystore)) {
    $keytool = (Get-Command keytool -ErrorAction Stop).Source
    & $keytool -genkeypair `
        -v `
        -keystore $Keystore `
        -storepass $props["storePassword"] `
        -keypass $props["keyPassword"] `
        -alias $props["keyAlias"] `
        -keyalg RSA `
        -keysize 2048 `
        -storetype JKS `
        -validity 10000 `
        -dname "CN=AirBridge, OU=AirBridge, O=AirBridge, L=Local, S=Local, C=US"
}

$GradleCandidates = @()
if ($env:GRADLE_HOME) {
    $GradleCandidates += (Join-Path $env:GRADLE_HOME "bin\gradle.bat")
}
$GradleCandidates += "D:\Android\Gradle\gradle-8.10.2\bin\gradle.bat"
$gradleCommand = $null
foreach ($candidate in $GradleCandidates) {
    if ($candidate -and (Test-Path $candidate)) {
        $gradleCommand = $candidate
        break
    }
}
if (-not $gradleCommand) {
    $gradleCommand = (Get-Command gradle -ErrorAction Stop).Source
}

if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = "D:\Android\Sdk"
}
if (-not $env:ANDROID_SDK_ROOT) {
    $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
}
if (-not $env:GRADLE_USER_HOME) {
    $env:GRADLE_USER_HOME = Join-Path $Project ".gradle"
}

Push-Location $Project
try {
    & $gradleCommand assembleRelease
}
finally {
    Pop-Location
}

if (-not (Test-Path $ApkSource)) {
    throw "Release APK not found: $ApkSource"
}
Copy-Item -LiteralPath $ApkSource -Destination $ApkDest -Force
Write-Host "Created $ApkDest"
