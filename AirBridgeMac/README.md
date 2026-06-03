# AirBridge macOS

AirBridge macOS is the native Mac version of AirBridge. It uses the same local-network protocol as the Windows, iOS, and Android versions:

- UDP `45678` broadcast discovery.
- Nearby-segment HTTP scanning.
- HTTP `/api/state` for device information.
- HTTP `/api/inbox/message` for receiving text messages.
- HTTP `/api/inbox/file` for receiving files.

## Open in Xcode

On macOS, open the project with Xcode:

```text
AirBridgeMac\AirBridgeMac.xcodeproj
```

Select the `AirBridgeMac` scheme and run it.

## Received Files

Received files are saved to:

```text
~/Downloads/AirBridge Received
```

## Transfer with Windows, iOS, or Android

1. Run `AirBridge.exe` on Windows.
2. Run `AirBridgeIOS` on iPhone/iPad, AirBridge Android on Android, or `AirBridgeMac` on Mac.
3. Connect the devices to the same reachable local network.
4. Devices should discover each other automatically. If broadcast discovery is blocked, manually enter the address shown by the peer.
