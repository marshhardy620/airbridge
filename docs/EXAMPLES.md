# Examples

These examples show practical AirBridge workflows and the checks that usually make troubleshooting faster.

## Example 1: Send Text Between Two Windows PCs

1. Download the latest Windows build on both PCs.
2. Connect both PCs to the same Wi-Fi or LAN.
3. Start AirBridge on both PCs.
4. Wait for the other device to appear in the nearby devices list.
5. Send a short test message before sending files.

Expected result: the receiving device shows the message without needing an account, login, or cloud service.

## Example 2: Transfer a Small File First

1. Start AirBridge on both devices.
2. Send a small file such as a text file or screenshot.
3. Confirm it appears in the receiver's `AirBridge-Received` folder.
4. Try larger files only after the small-file test succeeds.

This keeps early testing simple and separates network discovery issues from file-size or storage issues.

## Example 3: Add a Peer Manually

Use this when automatic discovery does not find another device.

1. On the other device, copy the local AirBridge address shown in the app, such as `http://192.168.1.8:8765`.
2. Paste that address into the manual peer entry field.
3. Add the peer and send a short text message.

If manual entry works but discovery does not, the network is probably blocking UDP broadcast traffic.

## Example 4: Test a Segmented Network

Some networks place devices on nearby but different subnets, such as `10.85.167.x` and `10.85.168.x`.

1. Start AirBridge on both devices.
2. Increase scan radius before launching:

```powershell
$env:AIRBRIDGE_SCAN_RADIUS="2"
python airbridge_desktop.py
```

3. If needed, include additional ports:

```powershell
$env:AIRBRIDGE_SCAN_PORTS="8765,8766,8767,8768"
python airbridge_desktop.py
```

## Example 5: Report a Discovery Bug

Include:

- Sender and receiver operating systems.
- AirBridge version or commit.
- Whether manual peer entry works.
- Whether either device uses a VPN.
- Firewall status.
- The local addresses shown by both devices.
- Logs or screenshots with private data removed.
