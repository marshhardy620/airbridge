# AirBridge macOS

AirBridge macOS 是 AirBridge 的原生 Mac 版本，和 Windows/iOS 版使用同一套局域网协议：

- UDP `45678` 广播发现设备
- 邻近网段 HTTP 扫描
- HTTP `/api/state` 获取设备信息
- HTTP `/api/inbox/message` 收消息
- HTTP `/api/inbox/file` 收文件

## 打开方式

在 macOS 上用 Xcode 打开：

```text
AirBridgeMac.xcodeproj
```

选择 `AirBridgeMac` scheme 运行。

## 文件保存位置

收到的文件会保存到：

```text
~/Downloads/AirBridge Received
```

## 和 Windows / iOS 互传

1. Windows 上运行 `AirBridge.exe`
2. iPhone/iPad 上运行 `AirBridgeIOS`
3. Mac 上运行 `AirBridgeMac`
4. 设备在同一个可互访局域网内即可自动发现；如果广播被阻断，可手动输入对方显示的地址。
