# AirBridge Android

AirBridge Android is the mobile Android port of AirBridge. It uses the same local-network protocol as the Windows, iOS, and macOS versions:

- UDP `45678` broadcast discovery.
- HTTP `/api/state` for device state.
- HTTP `/api/inbox/message` for receiving text messages.
- HTTP `/api/inbox/file` for receiving files.

## Open in Android Studio

1. Open the `AirBridgeAndroid` folder in Android Studio.
2. Wait for Gradle Sync to finish.
3. Connect an Android phone and enable USB debugging.
4. Select the physical device and click Run.

## Build APK

From the repository root, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android_release_apk.ps1
```

The script creates a local Android release signing key and outputs:

```text
dist\AirBridgeAndroid-release.apk
```

The signing key is stored in `AirBridgeAndroid\signing` and is not committed to GitHub. Do not delete that folder, or future APKs will not be able to update over the installed app.

## Transfer with Windows

1. Run `dist\AirBridge.exe` on Windows.
2. Run AirBridge on the Android phone.
3. Connect both devices to the same Wi-Fi or reachable LAN.
4. If the peer does not appear automatically, use manual peer entry on Android and enter the address shown by Windows, for example `http://10.85.168.94:8765`.

The Android app sends UDP broadcasts and scans the current and adjacent network segments on ports `8765-8767`. This is useful on school or office networks where addresses such as `10.85.167.x` and `10.85.168.x` can reach each other but broadcast discovery does not cross segments.

## Received Files

Received files are saved in the Android app's external files directory:

```text
Android/data/com.airbridge.android/files/AirBridge-Received
```

Some newer Android file managers hide `Android/data`. If that happens, use the received-file list inside AirBridge to confirm the file name.
