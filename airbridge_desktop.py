#!/usr/bin/env python3
"""
AirBridge Desktop: Qt desktop shell for no-login LAN transfers.

The desktop UI reuses the same HTTP receiver and UDP discovery backend from
airbridge.py, so browser and desktop builds stay compatible with each other.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import airbridge


def fmt_time(ms: int) -> str:
    return time.strftime("%H:%M", time.localtime(ms / 1000))


def fmt_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class AirBridgeRuntime:
    def __init__(self) -> None:
        port = int(os.environ.get("AIRBRIDGE_PORT", "0") or "0") or airbridge.find_free_port()
        host = airbridge.get_lan_ip()
        name = os.environ.get("AIRBRIDGE_NAME") or f"{socket.gethostname()}-{uuid.uuid4().hex[:4]}"
        airbridge.RECEIVED_DIR.mkdir(parents=True, exist_ok=True)

        self.state = airbridge.AirBridgeState(name=name, host=host, port=port)
        self.server = ThreadingHTTPServer(("", port), airbridge.AirBridgeHandler)
        self.server.state = self.state  # type: ignore[attr-defined]
        self.discovery = airbridge.Discovery(self.state)
        self.server_thread: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        self.discovery.start()
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.discovery.stop_event.set()
        self.server.shutdown()
        self.server.server_close()


class UiSignals(QObject):
    status = Signal(str)
    error = Signal(str)
    activity = Signal(dict)
    refresh = Signal()
    busy = Signal(bool)


class DropPanel(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)
        title = QLabel("拖拽文件到这里")
        title.setObjectName("dropTitle")
        hint = QLabel("或点击下方按钮选择文件发送给当前设备")
        hint.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(hint)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if Path(path).is_file():
                    paths.append(path)
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()


class AirBridgeDesktop(QMainWindow):
    def __init__(self, runtime: AirBridgeRuntime) -> None:
        super().__init__()
        self.runtime = runtime
        self.signals = UiSignals()
        self.selected_peer_id = ""
        self.known_inbox_ids: set[str] = set()
        self.activities: list[dict] = []
        self.activity_widgets: list[QWidget] = []
        self.is_first_refresh = True

        self.setWindowTitle("AirBridge")
        self.setMinimumSize(1120, 720)
        self.setWindowIcon(QIcon(str(airbridge.ICON_PATH)))

        self._build_ui()
        self._wire_signals()
        self._setup_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_state)
        self.timer.start(1000)
        self.refresh_state()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = self._build_sidebar()
        self.chat = self._build_chat()
        self.info = self._build_info_panel()

        outer.addWidget(self.sidebar)
        outer.addWidget(self.chat, 1)
        outer.addWidget(self.info)
        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidebar")
        panel.setFixedWidth(310)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        brand = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setFixedSize(42, 42)
        icon_label.setPixmap(QIcon(str(airbridge.ICON_PATH)).pixmap(QSize(42, 42)))
        title_box = QVBoxLayout()
        title = QLabel("AirBridge")
        title.setObjectName("brandTitle")
        subtitle = QLabel("无需登录的局域网投送")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        brand.addWidget(icon_label)
        brand.addLayout(title_box)
        brand.addStretch()
        layout.addLayout(brand)

        self.local_url = QLineEdit(self.runtime.state.url)
        self.local_url.setReadOnly(True)
        self.local_url.setObjectName("localUrl")
        layout.addWidget(self.local_url)

        copy_btn = QPushButton("复制本机地址")
        copy_btn.clicked.connect(self.copy_local_url)
        layout.addWidget(copy_btn)

        heading = QLabel("附近设备")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        self.peer_list = QListWidget()
        self.peer_list.setObjectName("peerList")
        self.peer_list.setIconSize(QSize(28, 28))
        layout.addWidget(self.peer_list, 1)

        manual_title = QLabel("手动添加")
        manual_title.setObjectName("sectionTitle")
        layout.addWidget(manual_title)
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("例如 192.168.1.8:8765")
        layout.addWidget(self.manual_input)
        self.add_peer_btn = QPushButton("添加设备")
        layout.addWidget(self.add_peer_btn)

        return panel

    def _build_chat(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("chat")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        self.peer_title = QLabel("选择一个设备")
        self.peer_title.setObjectName("chatTitle")
        self.peer_subtitle = QLabel("正在通过广播和邻近网段扫描寻找设备")
        self.peer_subtitle.setObjectName("muted")
        title_box = QVBoxLayout()
        title_box.addWidget(self.peer_title)
        title_box.addWidget(self.peer_subtitle)
        top.addLayout(title_box)
        top.addStretch()
        self.refresh_btn = QPushButton("刷新")
        top.addWidget(self.refresh_btn)
        layout.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("activityScroll")
        activity_host = QWidget()
        self.activity_layout = QVBoxLayout(activity_host)
        self.activity_layout.setContentsMargins(10, 10, 10, 10)
        self.activity_layout.setSpacing(10)
        self.activity_layout.addStretch()
        self.scroll.setWidget(activity_host)
        layout.addWidget(self.scroll, 1)

        self.drop_panel = DropPanel()
        layout.addWidget(self.drop_panel)

        input_row = QHBoxLayout()
        self.message_input = QPlainTextEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("输入消息...")
        self.message_input.setFixedHeight(84)
        input_row.addWidget(self.message_input, 1)
        buttons = QVBoxLayout()
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primaryButton")
        self.file_btn = QPushButton("发送文件")
        buttons.addWidget(self.send_btn)
        buttons.addWidget(self.file_btn)
        buttons.addStretch()
        input_row.addLayout(buttons)
        layout.addLayout(input_row)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("status")
        layout.addWidget(self.status_label)
        return panel

    def _build_info_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("infoPanel")
        panel.setFixedWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("接收与设置")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.received_count = QLabel("还没有收到内容")
        self.received_count.setObjectName("muted")
        layout.addWidget(self.received_count)

        open_dir_btn = QPushButton("打开接收文件夹")
        open_dir_btn.clicked.connect(self.open_received_dir)
        layout.addWidget(open_dir_btn)

        self.network_tip = QLabel(
            "提示：首次运行时允许 Windows 防火墙的专用网络访问，其他设备才能发现这台电脑。"
        )
        self.network_tip.setWordWrap(True)
        self.network_tip.setObjectName("tip")
        layout.addWidget(self.network_tip)

        layout.addStretch()
        version = QLabel(f"{airbridge.APP_NAME} {airbridge.APP_VERSION}")
        version.setObjectName("muted")
        layout.addWidget(version)
        return panel

    def _wire_signals(self) -> None:
        self.peer_list.currentItemChanged.connect(self.on_peer_changed)
        self.refresh_btn.clicked.connect(self.refresh_state)
        self.add_peer_btn.clicked.connect(self.add_manual_peer)
        self.send_btn.clicked.connect(self.send_message)
        self.file_btn.clicked.connect(self.pick_files)
        self.drop_panel.files_dropped.connect(self.send_files)
        self.signals.status.connect(self.set_status)
        self.signals.error.connect(self.show_error)
        self.signals.activity.connect(self.add_activity)
        self.signals.refresh.connect(self.refresh_state)
        self.signals.busy.connect(self.set_busy)

    def _setup_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(str(airbridge.ICON_PATH)), self)
        menu = QMenu()
        show_action = QAction("显示 AirBridge", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def show_normal(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self.runtime.stop()
        QApplication.quit()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.runtime.stop()
        super().closeEvent(event)

    def copy_local_url(self) -> None:
        QApplication.clipboard().setText(self.runtime.state.url)
        self.set_status("已复制本机地址")

    def open_received_dir(self) -> None:
        airbridge.RECEIVED_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(airbridge.RECEIVED_DIR)))

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_busy(self, busy: bool) -> None:
        for widget in (self.send_btn, self.file_btn, self.add_peer_btn, self.refresh_btn):
            widget.setEnabled(not busy)

    def show_error(self, text: str) -> None:
        self.set_status(text)
        QMessageBox.warning(self, "AirBridge", text)

    def current_peer(self) -> airbridge.Peer | None:
        if not self.selected_peer_id:
            return None
        with self.runtime.state.lock:
            return self.runtime.state.peers.get(self.selected_peer_id)

    def refresh_state(self) -> None:
        peers = self.runtime.state.visible_peers()
        peer_ids = {peer["id"] for peer in peers}
        if self.selected_peer_id not in peer_ids:
            self.selected_peer_id = peers[0]["id"] if peers else ""

        self.peer_list.blockSignals(True)
        self.peer_list.clear()
        selected_row = -1
        for row, peer in enumerate(peers):
            label = f'{peer["name"]}\n{peer["host"]}:{peer["port"]}'
            item = QListWidgetItem(QIcon(str(airbridge.ICON_PATH)), label)
            item.setData(Qt.ItemDataRole.UserRole, peer["id"])
            item.setSizeHint(QSize(100, 58))
            self.peer_list.addItem(item)
            if peer["id"] == self.selected_peer_id:
                selected_row = row
        if selected_row >= 0:
            self.peer_list.setCurrentRow(selected_row)
        self.peer_list.blockSignals(False)

        peer = self.current_peer()
        if peer:
            self.peer_title.setText(peer.name)
            self.peer_subtitle.setText(f"{peer.host}:{peer.port}")
        else:
            self.peer_title.setText("选择一个设备")
            self.peer_subtitle.setText("正在通过广播和邻近网段扫描寻找设备")

        state = self.runtime.state.to_state()
        inbox = state.get("inbox", [])
        if self.is_first_refresh:
            self.known_inbox_ids = {str(item.get("id", "")) for item in inbox}
            self.is_first_refresh = False
        else:
            for item in reversed(inbox):
                item_id = str(item.get("id", ""))
                if item_id and item_id not in self.known_inbox_ids:
                    self.known_inbox_ids.add(item_id)
                    activity = self.inbox_to_activity(item)
                    self.add_activity(activity)
                    self.notify(activity)

        self.received_count.setText(f"已收到 {len(inbox)} 条内容" if inbox else "还没有收到内容")

    def inbox_to_activity(self, item: dict) -> dict:
        return {
            "id": str(item.get("id") or uuid.uuid4().hex),
            "direction": "in",
            "kind": item.get("kind", "message"),
            "peer_name": item.get("from_name", "Nearby device"),
            "created_at": int(item.get("created_at") or airbridge.now_ms()),
            "text": item.get("text", ""),
            "filename": item.get("filename", ""),
            "size": int(item.get("size") or 0),
            "path": item.get("saved_path", ""),
        }

    def add_activity(self, activity: dict) -> None:
        if any(existing["id"] == activity["id"] for existing in self.activities):
            return
        self.activities.append(activity)
        self.activities.sort(key=lambda item: item["created_at"])
        self.rebuild_activities()

    def rebuild_activities(self) -> None:
        while self.activity_layout.count() > 0:
            item = self.activity_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.activities:
            empty = QLabel("还没有传输记录。选择左侧设备后，可以发送消息或拖拽文件。")
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.activity_layout.addWidget(empty)
            self.activity_layout.addStretch()
            return

        for activity in self.activities[-80:]:
            self.activity_layout.addWidget(self.make_bubble(activity))
        self.activity_layout.addStretch()
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def make_bubble(self, activity: dict) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        bubble = QFrame()
        bubble.setObjectName("sentBubble" if activity["direction"] == "out" else "inBubble")
        bubble.setMaximumWidth(560)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 10, 12, 10)
        bubble_layout.setSpacing(6)

        who = "我" if activity["direction"] == "out" else activity["peer_name"]
        meta = QLabel(f"{who} · {fmt_time(activity['created_at'])}")
        meta.setObjectName("bubbleMeta")
        bubble_layout.addWidget(meta)

        if activity["kind"] == "file":
            name = QLabel(f"{activity['filename']} · {fmt_bytes(activity['size'])}")
            name.setWordWrap(True)
            name.setObjectName("bubbleText")
            bubble_layout.addWidget(name)
            if activity.get("path"):
                open_btn = QPushButton("打开文件")
                open_btn.clicked.connect(lambda _=False, p=activity["path"]: self.open_path(p))
                bubble_layout.addWidget(open_btn)
        else:
            text = QLabel(activity.get("text", ""))
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.setObjectName("bubbleText")
            bubble_layout.addWidget(text)

        if activity["direction"] == "out":
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch()
        return row

    def open_path(self, path: str) -> None:
        target = Path(path)
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        else:
            self.show_error("文件不存在，可能已经被移动或删除。")

    def notify(self, activity: dict) -> None:
        if not self.tray:
            return
        if activity["kind"] == "file":
            body = f'{activity["peer_name"]} 发来文件：{activity["filename"]}'
        else:
            body = f'{activity["peer_name"]}: {activity.get("text", "")[:60]}'
        self.tray.showMessage("AirBridge 收到新内容", body, QSystemTrayIcon.MessageIcon.Information, 3500)

    def on_peer_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None:
            self.selected_peer_id = ""
        else:
            self.selected_peer_id = str(current.data(Qt.ItemDataRole.UserRole))
        self.refresh_state()

    def send_message(self) -> None:
        peer = self.current_peer()
        text = self.message_input.toPlainText().strip()
        if not peer:
            self.show_error("请先选择一个附近设备。")
            return
        if not text:
            self.set_status("请输入消息内容")
            return
        self.message_input.clear()
        self.signals.busy.emit(True)
        self.set_status("正在发送消息...")
        threading.Thread(target=self._send_message_worker, args=(peer, text), daemon=True).start()

    def _send_message_worker(self, peer: airbridge.Peer, text: str) -> None:
        try:
            airbridge.post_json(
                peer.host,
                peer.port,
                "/api/inbox/message",
                {
                    "fromId": self.runtime.state.id,
                    "fromName": self.runtime.state.name,
                    "text": text,
                    "createdAt": airbridge.now_ms(),
                },
            )
            self.signals.activity.emit(
                {
                    "id": uuid.uuid4().hex,
                    "direction": "out",
                    "kind": "message",
                    "peer_name": peer.name,
                    "created_at": airbridge.now_ms(),
                    "text": text,
                }
            )
            self.signals.status.emit("消息已发送")
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"发送失败：{exc}")
        finally:
            self.signals.busy.emit(False)

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要发送的文件")
        if paths:
            self.send_files(paths)

    def send_files(self, paths: list[str]) -> None:
        peer = self.current_peer()
        if not peer:
            self.show_error("请先选择一个附近设备。")
            return
        clean_paths = [str(Path(path)) for path in paths if Path(path).is_file()]
        if not clean_paths:
            return
        self.signals.busy.emit(True)
        self.set_status(f"正在发送 {len(clean_paths)} 个文件...")
        threading.Thread(target=self._send_files_worker, args=(peer, clean_paths), daemon=True).start()

    def _send_files_worker(self, peer: airbridge.Peer, paths: list[str]) -> None:
        try:
            for file_path in paths:
                path = Path(file_path)
                size = path.stat().st_size
                if size > airbridge.MAX_UPLOAD_BYTES:
                    raise RuntimeError(f"{path.name} 超过 1GB 限制")
                data = path.read_bytes()
                airbridge.post_multipart(
                    peer.host,
                    peer.port,
                    "/api/inbox/file",
                    {
                        "from_id": self.runtime.state.id,
                        "from_name": self.runtime.state.name,
                        "created_at": str(airbridge.now_ms()),
                    },
                    "file",
                    path.name,
                    data,
                    timeout=120,
                )
                self.signals.activity.emit(
                    {
                        "id": uuid.uuid4().hex,
                        "direction": "out",
                        "kind": "file",
                        "peer_name": peer.name,
                        "created_at": airbridge.now_ms(),
                        "filename": path.name,
                        "size": size,
                        "path": str(path),
                    }
                )
            self.signals.status.emit("文件已发送")
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"发送失败：{exc}")
        finally:
            self.signals.busy.emit(False)

    def add_manual_peer(self) -> None:
        raw_url = self.manual_input.text().strip()
        if not raw_url:
            return
        self.signals.busy.emit(True)
        self.set_status("正在添加设备...")
        threading.Thread(target=self._add_manual_peer_worker, args=(raw_url,), daemon=True).start()

    def _add_manual_peer_worker(self, raw_url: str) -> None:
        try:
            if not raw_url.startswith(("http://", "https://")):
                raw_url = f"http://{raw_url}"
            parsed = urlparse(raw_url)
            if not parsed.hostname:
                raise RuntimeError("地址无效")
            if parsed.scheme == "https":
                raise RuntimeError("局域网设备地址请使用 http")
            port = parsed.port or 80
            conn = http.client.HTTPConnection(parsed.hostname, port, timeout=6)
            try:
                conn.request("GET", "/api/state")
                response = conn.getresponse()
                body = response.read()
                if response.status >= 400:
                    raise RuntimeError(body.decode("utf-8", "replace") or f"HTTP {response.status}")
                remote_state = json.loads(body.decode("utf-8") or "{}")
            finally:
                conn.close()

            device = remote_state.get("device", {})
            peer = airbridge.Peer(
                id=str(device.get("id") or uuid.uuid4().hex[:12]),
                name=str(device.get("name") or parsed.hostname),
                host=str(device.get("host") or parsed.hostname),
                port=int(device.get("port") or port),
                url=str(device.get("url") or f"http://{parsed.hostname}:{port}"),
                source="manual",
            )
            self.runtime.state.add_peer(peer)
            self.selected_peer_id = peer.id
            self.signals.status.emit("设备已添加")
            self.signals.refresh.emit()
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"添加失败：{exc}")
        finally:
            self.signals.busy.emit(False)


STYLE = """
QWidget#root {
    background: #f5f7fb;
    color: #172033;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame#sidebar, QFrame#infoPanel {
    background: #ffffff;
    border: 0;
}
QFrame#sidebar {
    border-right: 1px solid #dce3ec;
}
QFrame#infoPanel {
    border-left: 1px solid #dce3ec;
}
QWidget#chat {
    background: #f5f7fb;
}
QLabel#brandTitle {
    font-size: 20px;
    font-weight: 800;
    color: #111827;
}
QLabel#chatTitle {
    font-size: 21px;
    font-weight: 760;
    color: #111827;
}
QLabel#sectionTitle {
    font-size: 14px;
    font-weight: 760;
    color: #172033;
}
QLabel#muted, QLabel.muted {
    color: #66758c;
}
QLabel#tip {
    color: #516176;
    background: #eef6ff;
    border: 1px solid #d5e7ff;
    border-radius: 8px;
    padding: 10px;
    line-height: 1.4;
}
QLineEdit, QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #d9e2ee;
    border-radius: 8px;
    padding: 9px;
    selection-background-color: #22c55e;
}
QLineEdit#localUrl {
    background: #edf3fb;
    color: #243247;
}
QListWidget#peerList {
    border: 1px solid #dce3ec;
    border-radius: 8px;
    background: #f9fbfd;
    outline: 0;
}
QListWidget#peerList::item {
    border-radius: 8px;
    padding: 8px;
    margin: 4px;
}
QListWidget#peerList::item:selected {
    background: #dff6ec;
    color: #122018;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #ccd7e5;
    border-radius: 8px;
    padding: 9px 12px;
    color: #182238;
    font-weight: 650;
}
QPushButton:hover {
    background: #f3f8ff;
}
QPushButton:disabled {
    color: #94a3b8;
    background: #f1f5f9;
}
QPushButton#primaryButton {
    background: #14a86b;
    border-color: #14a86b;
    color: white;
}
QScrollArea#activityScroll {
    border: 1px solid #dce3ec;
    border-radius: 8px;
    background: #eef3f9;
}
QFrame#dropPanel {
    border: 1px dashed #9fb4ce;
    border-radius: 8px;
    background: #ffffff;
}
QFrame#dropPanel[dragging="true"] {
    border-color: #14a86b;
    background: #ecfdf5;
}
QLabel#dropTitle {
    font-size: 15px;
    font-weight: 760;
    color: #172033;
}
QFrame#inBubble {
    background: #ffffff;
    border: 1px solid #dce3ec;
    border-radius: 8px;
}
QFrame#sentBubble {
    background: #dff8ec;
    border: 1px solid #bdeccf;
    border-radius: 8px;
}
QLabel#bubbleMeta {
    color: #64748b;
    font-size: 12px;
}
QLabel#bubbleText {
    color: #111827;
    font-size: 14px;
    line-height: 1.45;
}
QLabel#emptyState {
    color: #66758c;
    padding: 24px;
}
QLabel#status {
    color: #516176;
}
"""


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AirBridge")
    app.setWindowIcon(QIcon(str(airbridge.ICON_PATH)))

    runtime = AirBridgeRuntime()
    runtime.start()
    window = AirBridgeDesktop(runtime)
    window.show()

    try:
        return app.exec()
    finally:
        runtime.stop()


if __name__ == "__main__":
    raise SystemExit(main())
