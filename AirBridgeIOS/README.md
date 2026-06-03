# AirBridge iOS

AirBridge iOS 是 Windows 版 AirBridge 的移动端适配，不是 Apple-only 版本。它使用和 Windows 桌面版一致的局域网协议：

- UDP `45678` 广播发现设备
- HTTP `/api/state` 读取设备信息
- HTTP `/api/inbox/message` 接收消息
- HTTP `/api/inbox/file` 接收文件

这样 iPhone/iPad 和 Windows 电脑在同一个 Wi-Fi 下可以互相发现并传输消息、文件。

## 打开方式

在 macOS 上用 Xcode 打开：

```text
AirBridgeIOS.xcodeproj
```

然后选择 iPhone 真机或 iOS 模拟器运行。真机互传时，请在首次弹出的本地网络权限提示中选择允许。

## 和 Windows 互传

1. Windows 上运行 `dist\AirBridge.exe`
2. iPhone/iPad 上运行 AirBridge iOS
3. 两台设备连接同一个 Wi-Fi
4. 如果没有自动出现，在任意一端手动输入对方显示的地址，例如 `192.168.1.8:8765`

## 注意

iOS 对本地网络访问有系统权限限制。第一次运行时必须允许本地网络访问，否则无法发现或连接 Windows 设备。
