# AirBridge

AirBridge 是一个无需登录的局域网文件和消息传输小工具，使用方式有点像 AirDrop：两台设备在同一 Wi-Fi 或局域网中运行后，就能互相发现、发送文字和文件。

## 下载

最新 Windows 版可在 GitHub Releases 下载：

```text
https://github.com/MickeyWzt/airbridge/releases
```

如果你是从源码运行或二次开发，请继续看下面的说明。

## 功能

- 无账号、无登录、无云端服务器
- 独立 Windows 桌面窗口，不需要打开浏览器
- 自动发现同一局域网和邻近网段里的 AirBridge 设备
- 支持手动输入对方地址，适合广播被路由器或防火墙拦截的网络
- Windows 版支持启动时检查 GitHub Releases 更新，并自动下载替换 exe
- 支持发送文字消息
- 支持拖拽或选择文件发送
- 支持托盘图标和接收通知
- 收到的文件保存在 `AirBridge-Received`
- 已包含 Windows 应用图标和浏览器页签图标

## 运行

如果使用已经打包好的程序，直接双击：

```text
dist\AirBridge.exe
```

如果从源码运行，先安装桌面界面依赖：

```powershell
python -m pip install -r requirements.txt
```

在 Windows 上双击：

```bat
run_airbridge.bat
```

或者在命令行运行：

```powershell
python airbridge_desktop.py
```

启动后会打开 AirBridge 桌面窗口，并显示本机地址，例如：

```text
http://192.168.1.8:8765
```

另一台设备也运行 AirBridge 后，通常会自动出现在“附近设备”里。AirBridge 会先用 UDP 广播发现设备，再扫描邻近网段的常用端口，适合 `10.85.167.x` 和 `10.85.168.x` 这种同一网络但广播不互通的情况。如果仍然没有出现，把对方窗口里的本机地址复制到“手动添加”输入框再点击“添加设备”。

增强发现默认扫描当前网段和前后相邻网段的 `8765-8767` 端口。可以用环境变量调整：

```powershell
$env:AIRBRIDGE_SCAN_RADIUS="2"
$env:AIRBRIDGE_SCAN_PORTS="8765,8766,8767,8768"
```

仍然可以运行浏览器兼容版：

```powershell
python airbridge.py
```

## 打包成下载包

生成可分发 zip：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_zip.ps1
```

输出文件：

```text
dist\AirBridge.zip
```

## 打包成 exe

如果已经安装 PyInstaller，可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

输出文件：

```text
dist\AirBridge.exe
```

打包时会使用 `airbridge_desktop.py` 作为桌面应用入口，并使用 `assets\airbridge.ico` 作为 exe 图标。

如果提示没有 PyInstaller，可先安装：

```powershell
python -m pip install pyinstaller PySide6
```

## 自动更新

Windows 桌面版从 `v0.1.2` 开始支持自动更新。程序启动后会检查 GitHub 最新 Release：

```text
https://github.com/MickeyWzt/airbridge/releases/latest
```

如果发现新版，会弹出更新提示；确认后会下载新的 `AirBridge.exe`，关闭当前程序，替换旧 exe，并自动重新启动。

注意：`v0.1.1` 以及更早的 exe 没有内置更新器，所以旧用户至少需要手动下载一次 `v0.1.2` 或更新版本。之后才可以自动提示和更新。

## iOS 适配版

iPhone/iPad 版本在 `AirBridgeIOS` 文件夹中，是额外的原生 SwiftUI 工程，不会替换 Windows 桌面版。

```text
AirBridgeIOS\AirBridgeIOS.xcodeproj
```

iOS 版使用和 Windows 版一致的局域网协议：UDP 自动发现设备，HTTP 收发消息和文件。因此 Windows 电脑和 iPhone/iPad 在同一个 Wi-Fi 下可以互传。首次运行 iOS App 时，请允许本地网络访问。

## macOS 适配版

Mac 版本在 `AirBridgeMac` 文件夹中，也是额外的原生 SwiftUI 工程。

```text
AirBridgeMac\AirBridgeMac.xcodeproj
```

macOS 版同样使用 AirBridge 的 UDP/HTTP 局域网协议，可与 Windows、iPhone/iPad、Mac 互传。收到的文件默认保存到：

```text
~/Downloads/AirBridge Received
```

## 协议

AirBridge 的局域网发现和传输协议见：

```text
docs\PROTOCOL.md
```

## 开源协议

AirBridge 使用 MIT License 开源。

## 网络和安全说明

AirBridge 设计为可信局域网内使用。它不会上传到云端，也不会要求登录。第一次运行时，Windows 防火墙可能会询问是否允许访问网络；如果要让其他设备访问，请允许专用网络访问。

不要在不可信公共 Wi-Fi 中接收陌生设备文件。
