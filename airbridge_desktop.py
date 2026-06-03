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
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
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


GITHUB_REPO = "MickeyWzt/airbridge"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
LATEST_RELEASE_URL = f"{RELEASES_URL}/latest"


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


def version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts: list[int] = []
    for part in cleaned.split("."):
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or "0"))
    return tuple(parts or [0])


def newer_version(remote: str, current: str) -> bool:
    remote_parts = list(version_tuple(remote))
    current_parts = list(version_tuple(current))
    size = max(len(remote_parts), len(current_parts))
    remote_parts.extend([0] * (size - len(remote_parts)))
    current_parts.extend([0] * (size - len(current_parts)))
    return tuple(remote_parts) > tuple(current_parts)


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
    update_available = Signal(object)
    update_ready = Signal(object)


class DropPanel(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(6)
        title = QLabel("Drop files here")
        title.setObjectName("dropTitle")
        hint = QLabel("Or click the button below to choose files for the current device")
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
        self.update_check_inflight = False

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
        QTimer.singleShot(2500, lambda: self.check_for_updates(manual=False))

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
        subtitle = QLabel("LAN transfer without login")
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

        copy_btn = QPushButton("Copy Local Address")
        copy_btn.clicked.connect(self.copy_local_url)
        layout.addWidget(copy_btn)

        heading = QLabel("Nearby Devices")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        self.peer_list = QListWidget()
        self.peer_list.setObjectName("peerList")
        self.peer_list.setIconSize(QSize(28, 28))
        layout.addWidget(self.peer_list, 1)

        manual_title = QLabel("Add Manually")
        manual_title.setObjectName("sectionTitle")
        layout.addWidget(manual_title)
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("e.g. 192.168.1.8:8765")
        layout.addWidget(self.manual_input)
        self.add_peer_btn = QPushButton("Add Device")
        layout.addWidget(self.add_peer_btn)

        return panel

    def _build_chat(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("chat")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        self.peer_title = QLabel("Select a Device")
        self.peer_title.setObjectName("chatTitle")
        self.peer_subtitle = QLabel("Scanning with broadcast and nearby network segments")
        self.peer_subtitle.setObjectName("muted")
        title_box = QVBoxLayout()
        title_box.addWidget(self.peer_title)
        title_box.addWidget(self.peer_subtitle)
        top.addLayout(title_box)
        top.addStretch()
        self.refresh_btn = QPushButton("Refresh")
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
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.setFixedHeight(84)
        input_row.addWidget(self.message_input, 1)
        buttons = QVBoxLayout()
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.file_btn = QPushButton("Send File")
        buttons.addWidget(self.send_btn)
        buttons.addWidget(self.file_btn)
        buttons.addStretch()
        input_row.addLayout(buttons)
        layout.addLayout(input_row)

        self.status_label = QLabel("Ready")
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

        title = QLabel("Inbox and Settings")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.received_count = QLabel("No received items yet")
        self.received_count.setObjectName("muted")
        layout.addWidget(self.received_count)

        open_dir_btn = QPushButton("Open Received Folder")
        open_dir_btn.clicked.connect(self.open_received_dir)
        layout.addWidget(open_dir_btn)

        self.update_btn = QPushButton("Check for Updates")
        self.update_btn.clicked.connect(lambda: self.check_for_updates(manual=True))
        layout.addWidget(self.update_btn)

        self.network_tip = QLabel(
            "Tip: allow Windows Firewall private-network access on first run so other devices can discover this PC."
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
        self.signals.update_available.connect(self.prompt_update)
        self.signals.update_ready.connect(self.prompt_install_update)

    def _setup_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(str(airbridge.ICON_PATH)), self)
        menu = QMenu()
        show_action = QAction("Show AirBridge", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("Quit", self)
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
        self.set_status("Local address copied")

    def open_received_dir(self) -> None:
        airbridge.RECEIVED_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(airbridge.RECEIVED_DIR)))

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_busy(self, busy: bool) -> None:
        for widget in (self.send_btn, self.file_btn, self.add_peer_btn, self.refresh_btn, self.update_btn):
            widget.setEnabled(not busy)

    def show_error(self, text: str) -> None:
        self.set_status(text)
        QMessageBox.warning(self, "AirBridge", text)

    def check_for_updates(self, manual: bool = False) -> None:
        if self.update_check_inflight:
            return
        self.update_check_inflight = True
        if manual:
            self.set_status("Checking for updates...")
        threading.Thread(target=self._check_for_updates_worker, args=(manual,), daemon=True).start()

    def _check_for_updates_worker(self, manual: bool) -> None:
        try:
            info = self.fetch_latest_update()
            if info:
                self.signals.update_available.emit(info)
            elif manual:
                self.signals.status.emit("Already up to date")
        except Exception as exc:  # noqa: BLE001
            if manual:
                self.signals.error.emit(f"Update check failed: {exc}")
        finally:
            self.update_check_inflight = False

    def fetch_latest_update(self) -> dict[str, str] | None:
        request = urllib.request.Request(
            LATEST_RELEASE_API,
            headers={
                "User-Agent": f"AirBridge/{airbridge.APP_VERSION}",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                return self.fetch_latest_update_from_redirect()
            raise

        tag = str(payload.get("tag_name") or "")
        if not tag or not newer_version(tag, airbridge.APP_VERSION):
            return None

        exe_url = ""
        for asset in payload.get("assets") or []:
            if asset.get("name") == "AirBridge.exe":
                exe_url = str(asset.get("browser_download_url") or "")
                break
        if not exe_url:
            raise RuntimeError("Latest release does not include an AirBridge.exe download asset")

        return {
            "tag": tag,
            "name": str(payload.get("name") or tag),
            "page_url": str(payload.get("html_url") or RELEASES_URL),
            "exe_url": exe_url,
        }

    def fetch_latest_update_from_redirect(self) -> dict[str, str] | None:
        request = urllib.request.Request(
            LATEST_RELEASE_URL,
            headers={"User-Agent": f"AirBridge/{airbridge.APP_VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            final_url = response.geturl()
        tag = final_url.rstrip("/").rsplit("/", 1)[-1]
        if not tag or tag == "latest" or not newer_version(tag, airbridge.APP_VERSION):
            return None
        return {
            "tag": tag,
            "name": f"AirBridge {tag}",
            "page_url": f"{RELEASES_URL}/tag/{tag}",
            "exe_url": f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/AirBridge.exe",
        }

    def prompt_update(self, info: object) -> None:
        update = dict(info)  # type: ignore[arg-type]
        result = QMessageBox.question(
            self,
            "Update Available",
            (
                f"Found AirBridge {update.get('tag')}。\n"
                f"Current version: v{airbridge.APP_VERSION}\n\n"
                "Download and update now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.download_update(update)

    def download_update(self, info: dict[str, str]) -> None:
        if not getattr(sys, "frozen", False):
            QDesktopServices.openUrl(QUrl(info.get("page_url") or RELEASES_URL))
            self.set_status("Source-run mode cannot replace the EXE automatically; opened the download page")
            return
        self.signals.busy.emit(True)
        self.set_status("Downloading update...")
        threading.Thread(target=self._download_update_worker, args=(info,), daemon=True).start()

    def _download_update_worker(self, info: dict[str, str]) -> None:
        try:
            temp_dir = Path(tempfile.gettempdir()) / "AirBridgeUpdate"
            temp_dir.mkdir(parents=True, exist_ok=True)
            part_path = temp_dir / f"AirBridge-{info['tag']}.exe.part"
            exe_path = temp_dir / f"AirBridge-{info['tag']}.exe"
            request = urllib.request.Request(
                info["exe_url"],
                headers={"User-Agent": f"AirBridge/{airbridge.APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=60) as response, part_path.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 512)
                    if not chunk:
                        break
                    out.write(chunk)
            part_path.replace(exe_path)
            payload = dict(info)
            payload["downloaded_path"] = str(exe_path)
            self.signals.update_ready.emit(payload)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"Update download failed: {exc}")
        finally:
            self.signals.busy.emit(False)

    def prompt_install_update(self, info: object) -> None:
        update = dict(info)  # type: ignore[arg-type]
        result = QMessageBox.question(
            self,
            "Update Downloaded",
            "The update has finished downloading. Restart and install the new AirBridge now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.install_update(update["downloaded_path"])
        else:
            self.set_status("Update downloaded; restart/install canceled")

    def install_update(self, downloaded_path: str) -> None:
        current_exe = Path(sys.executable).resolve()
        updater_path = Path(tempfile.gettempdir()) / f"AirBridgeUpdate-{uuid.uuid4().hex}.ps1"
        script = f"""
param(
    [int]$PidToWait,
    [string]$Target,
    [string]$Downloaded
)
$ErrorActionPreference = "Stop"
try {{
    Wait-Process -Id $PidToWait -Timeout 90 -ErrorAction SilentlyContinue
}} catch {{}}
Start-Sleep -Milliseconds 700
$installed = $false
for ($i = 0; $i -lt 30; $i++) {{
    try {{
        Copy-Item -LiteralPath $Downloaded -Destination $Target -Force
        Unblock-File -LiteralPath $Target -ErrorAction SilentlyContinue
        $installed = $true
        break
    }} catch {{
        Start-Sleep -Seconds 1
    }}
}}
if ($installed) {{
    Start-Process -FilePath $Target
}}
Remove-Item -LiteralPath $Downloaded -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
        updater_path.write_text(script, encoding="utf-8")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(updater_path),
                "-PidToWait",
                str(os.getpid()),
                "-Target",
                str(current_exe),
                "-Downloaded",
                downloaded_path,
            ],
            creationflags=creation_flags,
        )
        self.quit_app()

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
            self.peer_title.setText("Select a Device")
            self.peer_subtitle.setText("Scanning with broadcast and nearby network segments")

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

        self.received_count.setText(f"Received {len(inbox)} items" if inbox else "No received items yet")

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
            empty = QLabel("No transfer history yet. Select a device on the left to send messages or drop files.")
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

        who = "Me" if activity["direction"] == "out" else activity["peer_name"]
        meta = QLabel(f"{who} · {fmt_time(activity['created_at'])}")
        meta.setObjectName("bubbleMeta")
        bubble_layout.addWidget(meta)

        if activity["kind"] == "file":
            name = QLabel(f"{activity['filename']} · {fmt_bytes(activity['size'])}")
            name.setWordWrap(True)
            name.setObjectName("bubbleText")
            bubble_layout.addWidget(name)
            if activity.get("path"):
                open_btn = QPushButton("Open File")
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
            self.show_error("File does not exist. It may have been moved or deleted.")

    def notify(self, activity: dict) -> None:
        if not self.tray:
            return
        if activity["kind"] == "file":
            body = f'{activity["peer_name"]} sent a file: {activity["filename"]}'
        else:
            body = f'{activity["peer_name"]}: {activity.get("text", "")[:60]}'
        self.tray.showMessage("AirBridge Received New Content", body, QSystemTrayIcon.MessageIcon.Information, 3500)

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
            self.show_error("Select a nearby device first.")
            return
        if not text:
            self.set_status("Enter a message first")
            return
        self.message_input.clear()
        self.signals.busy.emit(True)
        self.set_status("Sending message...")
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
            self.signals.status.emit("Message sent")
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"Send failed: {exc}")
        finally:
            self.signals.busy.emit(False)

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Files to Send")
        if paths:
            self.send_files(paths)

    def send_files(self, paths: list[str]) -> None:
        peer = self.current_peer()
        if not peer:
            self.show_error("Select a nearby device first.")
            return
        clean_paths = [str(Path(path)) for path in paths if Path(path).is_file()]
        if not clean_paths:
            return
        self.signals.busy.emit(True)
        self.set_status(f"Sending {len(clean_paths)} files...")
        threading.Thread(target=self._send_files_worker, args=(peer, clean_paths), daemon=True).start()

    def _send_files_worker(self, peer: airbridge.Peer, paths: list[str]) -> None:
        try:
            for file_path in paths:
                path = Path(file_path)
                size = path.stat().st_size
                if size > airbridge.MAX_UPLOAD_BYTES:
                    raise RuntimeError(f"{path.name} exceeds the 1 GB limit")
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
            self.signals.status.emit("File sent")
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"Send failed: {exc}")
        finally:
            self.signals.busy.emit(False)

    def add_manual_peer(self) -> None:
        raw_url = self.manual_input.text().strip()
        if not raw_url:
            return
        self.signals.busy.emit(True)
        self.set_status("Adding device...")
        threading.Thread(target=self._add_manual_peer_worker, args=(raw_url,), daemon=True).start()

    def _add_manual_peer_worker(self, raw_url: str) -> None:
        try:
            if not raw_url.startswith(("http://", "https://")):
                raw_url = f"http://{raw_url}"
            parsed = urlparse(raw_url)
            if not parsed.hostname:
                raise RuntimeError("Invalid address")
            if parsed.scheme == "https":
                raise RuntimeError("Use http for local-network device addresses")
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
            self.signals.status.emit("Device added")
            self.signals.refresh.emit()
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"Add failed: {exc}")
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
