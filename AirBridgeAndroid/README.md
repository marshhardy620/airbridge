# AirBridge Android

AirBridge Android 是 Windows / iOS / macOS 版的移动端适配，使用同一套局域网协议：

- UDP `45678` 广播发现设备
- HTTP `/api/state` 获取设备状态
- HTTP `/api/inbox/message` 接收消息
- HTTP `/api/inbox/file` 接收文件

## 打开方式

1. 在 Android Studio 中打开 `AirBridgeAndroid` 文件夹。
2. 等待 Gradle Sync 完成。
3. 连接 Android 手机，开启 USB 调试。
4. 选择真机后点击 Run。

## 和 Windows 互传

1. Windows 上运行 `dist\AirBridge.exe`。
2. Android 手机上运行 AirBridge。
3. 两台设备连接同一个 Wi-Fi。
4. 如果没有自动出现，在 Android 的“手动添加”里输入 Windows 显示的地址，例如 `http://10.85.168.94:8765`。

Android 版会发送 UDP 广播，也会扫描当前网段和相邻网段的 `8765-8767` 端口，适合学校网络里 `10.85.167.x` 和 `10.85.168.x` 这种广播不互通的情况。

## 文件位置

收到的文件会保存到 Android App 的外部文件目录：

```text
Android/data/com.airbridge.android/files/AirBridge Received
```

部分新版 Android 文件管理器会隐藏 `Android/data`，可以先用 AirBridge 的接收记录确认文件名。
