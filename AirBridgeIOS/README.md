# AirBridge iOS

AirBridge iOS is the iPhone/iPad port of the Windows AirBridge app. It is not an Apple-only version; it uses the same local-network protocol as the Windows desktop app:

- UDP `45678` broadcast discovery.
- HTTP `/api/state` for device information.
- HTTP `/api/inbox/message` for receiving text messages.
- HTTP `/api/inbox/file` for receiving files.

With this shared protocol, an iPhone or iPad and a Windows PC can discover each other and transfer messages and files on the same Wi-Fi network.

## Open in Xcode

On macOS, open the project with Xcode:

```text
AirBridgeIOS\AirBridgeIOS.xcodeproj
```

Then select an iPhone device or iOS simulator and run the app. For real-device transfers, allow Local Network access when iOS shows the first-run permission prompt.

## Transfer with Windows

1. Run `dist\AirBridge.exe` on Windows.
2. Run AirBridge iOS on the iPhone or iPad.
3. Connect both devices to the same Wi-Fi.
4. If automatic discovery does not find the peer, manually enter the address shown by the other device, for example `192.168.1.8:8765`.

## Notes

iOS restricts local-network access through a system permission prompt. The app must be allowed to access the local network, otherwise it cannot discover or connect to Windows devices.
