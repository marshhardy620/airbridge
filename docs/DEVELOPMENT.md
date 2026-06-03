# Development

This guide describes the lightweight checks and local workflows that are useful before changing AirBridge.

## Repository Shape

- `airbridge.py` is the browser-compatible Python app.
- `airbridge_desktop.py` is the Windows desktop app entry point.
- `AirBridgeAndroid/` contains the native Android project.
- `AirBridgeIOS/` contains the native iPhone/iPad SwiftUI project.
- `AirBridgeMac/` contains the native macOS SwiftUI project.
- `docs/PROTOCOL.md` documents the shared LAN protocol.

## Local Python Checks

Run these from the repository root:

```powershell
python -m py_compile airbridge.py airbridge_desktop.py
```

Install desktop dependencies when you need to run the Windows UI from source:

```powershell
python -m pip install -r requirements.txt
python airbridge_desktop.py
```

## Protocol Compatibility

Before changing transfer behavior, check whether the change affects:

- UDP discovery on port `45678`.
- `GET /api/state`.
- `POST /api/inbox/message`.
- `POST /api/inbox/file`.
- Manual peer entry when broadcast discovery is blocked.

If any of those change, update `docs/PROTOCOL.md`, `README.md`, and the pull request notes.

## Platform Notes

- Windows packaging uses `build_zip.ps1` and `build_exe.ps1`.
- Android work should be opened in Android Studio through `AirBridgeAndroid/`.
- iOS work requires Xcode and `AirBridgeIOS/AirBridgeIOS.xcodeproj`.
- macOS work requires Xcode and `AirBridgeMac/AirBridgeMac.xcodeproj`.

## Release Checklist

Before publishing a Windows release:

1. Run the Python syntax check.
2. Build the zip or EXE package.
3. Confirm the release asset names match the updater expectations.
4. Check the release notes against `CHANGELOG.md`.
5. Keep the local-network and trusted-LAN security notes visible.
