#!/usr/bin/env python3
"""
AirBridge: no-login LAN file and message transfer.

Run this file on two devices in the same local network. Each device advertises
itself over UDP and receives files/messages over a small local HTTP server.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="cgi")

import cgi
import concurrent.futures
import http.client
import ipaddress
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


APP_NAME = "AirBridge"
APP_VERSION = "0.1.2"
DISCOVERY_PORT = 45678
PEER_TTL_SECONDS = 20
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
LAN_SCAN_INTERVAL_SECONDS = 35
LAN_SCAN_TIMEOUT_SECONDS = 0.35
LAN_SCAN_MAX_WORKERS = 64
LAN_SCAN_DEFAULT_PORTS = (8765, 8766, 8767)
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_PATH = APP_DIR / "assets" / "airbridge.ico"
RECEIVED_DIR = Path.cwd() / "AirBridge-Received"


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_filename(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^\w.\- ()\[\]\u4e00-\u9fff]", "_", name, flags=re.UNICODE)
    return name[:180] or "file"


def unique_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    base = safe_filename(filename)
    candidate = directory / base
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(1, 10_000):
        candidate = directory / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not create a unique filename")


def add_ip_candidate(candidates: list[str], address: str) -> None:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return
    if ip.version != 4 or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return
    if address not in candidates:
        candidates.append(address)


def ip_rank(address: str) -> int:
    ip = ipaddress.ip_address(address)
    first = int(address.split(".", 1)[0])
    second = int(address.split(".")[1])
    if address.startswith("192.168."):
        return 0
    if first == 10:
        return 1
    if first == 172 and 16 <= second <= 31:
        return 2
    if first == 100 and 64 <= second <= 127:
        return 8
    if first == 198 and second in (18, 19):
        return 9
    if ip.is_private:
        return 3
    return 7


def get_lan_ip() -> str:
    candidates: list[str] = []
    try:
        output = subprocess.check_output(["ipconfig"], text=True, encoding="utf-8", errors="ignore")
        for match in re.finditer(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", output):
            add_ip_candidate(candidates, match.group(0))
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            add_ip_candidate(candidates, s.getsockname()[0])
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = item[4][0]
            add_ip_candidate(candidates, addr)
    except OSError:
        pass

    candidates.sort(key=ip_rank)
    return candidates[0] if candidates else "127.0.0.1"


def find_free_port(start: int = 8765, end: int = 8865) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available port found")


def post_json(host: str, port: int, path: str, payload: dict[str, Any], timeout: int = 8) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("POST", path, body, {"Content-Type": "application/json; charset=utf-8"})
        response = conn.getresponse()
        data = response.read()
        if response.status >= 400:
            raise RuntimeError(data.decode("utf-8", "replace") or f"HTTP {response.status}")
        return json.loads(data.decode("utf-8") or "{}")
    finally:
        conn.close()


def post_multipart(
    host: str,
    port: int,
    path: str,
    fields: dict[str, str],
    file_field: str,
    filename: str,
    data: bytes,
    timeout: int = 30,
) -> dict[str, Any]:
    boundary = f"airbridge-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_filename(filename)}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(data)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)

    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body,
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        response = conn.getresponse()
        response_data = response.read()
        if response.status >= 400:
            raise RuntimeError(response_data.decode("utf-8", "replace") or f"HTTP {response.status}")
        return json.loads(response_data.decode("utf-8") or "{}")
    finally:
        conn.close()


@dataclass
class Peer:
    id: str
    name: str
    host: str
    port: int
    url: str
    last_seen: float = field(default_factory=time.time)
    source: str = "auto"


@dataclass
class InboxItem:
    id: str
    kind: str
    from_id: str
    from_name: str
    created_at: int
    text: str = ""
    filename: str = ""
    size: int = 0
    download_url: str = ""
    saved_path: str = ""


class AirBridgeState:
    def __init__(self, name: str, host: str, port: int) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.peers: dict[str, Peer] = {}
        self.inbox: list[InboxItem] = []
        self.files: dict[str, Path] = {}
        self.lock = threading.RLock()

    def add_peer(self, peer: Peer) -> None:
        if peer.id == self.id:
            return
        with self.lock:
            existing = self.peers.get(peer.id)
            if existing:
                existing.name = peer.name or existing.name
                existing.host = peer.host
                existing.port = peer.port
                existing.url = peer.url
                existing.last_seen = time.time()
                existing.source = peer.source
            else:
                self.peers[peer.id] = peer

    def visible_peers(self) -> list[dict[str, Any]]:
        cutoff = time.time() - PEER_TTL_SECONDS
        with self.lock:
            stale_ids = [
                peer_id
                for peer_id, peer in self.peers.items()
                if peer.last_seen < cutoff and peer.source != "manual"
            ]
            for peer_id in stale_ids:
                self.peers.pop(peer_id, None)

            peers = sorted(self.peers.values(), key=lambda p: (p.name.lower(), p.host, p.port))
            return [
                {
                    "id": peer.id,
                    "name": peer.name,
                    "host": peer.host,
                    "port": peer.port,
                    "url": peer.url,
                    "lastSeen": int(peer.last_seen * 1000),
                    "source": peer.source,
                }
                for peer in peers
            ]

    def add_inbox(self, item: InboxItem) -> None:
        with self.lock:
            self.inbox.insert(0, item)
            self.inbox = self.inbox[:200]

    def to_state(self) -> dict[str, Any]:
        with self.lock:
            inbox = [item.__dict__ for item in self.inbox[:100]]
        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "device": {
                "id": self.id,
                "name": self.name,
                "host": self.host,
                "port": self.port,
                "url": self.url,
                "receivedDir": str(RECEIVED_DIR),
            },
            "peers": self.visible_peers(),
            "inbox": inbox,
        }


class Discovery:
    def __init__(self, state: AirBridgeState) -> None:
        self.state = state
        self.stop_event = threading.Event()

    def payload(self) -> bytes:
        return json.dumps(
            {
                "app": APP_NAME,
                "version": APP_VERSION,
                "id": self.state.id,
                "name": self.state.name,
                "host": self.state.host,
                "port": self.state.port,
                "url": self.state.url,
                "ts": now_ms(),
            }
        ).encode("utf-8")

    def start(self) -> None:
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()
        if os.environ.get("AIRBRIDGE_NO_SCAN") != "1":
            threading.Thread(target=self._scan_loop, daemon=True).start()

    def _broadcast_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.sendto(self.payload(), ("255.255.255.255", DISCOVERY_PORT))
            except OSError:
                pass
            self.stop_event.wait(2.5)

    def _listen_loop(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", DISCOVERY_PORT))
            except OSError:
                return
            s.settimeout(1)
            while not self.stop_event.is_set():
                try:
                    data, addr = s.recvfrom(4096)
                    payload = json.loads(data.decode("utf-8"))
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    continue

                if payload.get("app") != APP_NAME:
                    continue
                try:
                    port = int(payload.get("port"))
                except (TypeError, ValueError):
                    continue

                host = str(payload.get("host") or addr[0])
                if host.startswith("127."):
                    host = addr[0]

                self.state.add_peer(
                    Peer(
                        id=str(payload.get("id", "")),
                        name=str(payload.get("name") or "Nearby device"),
                        host=host,
                        port=port,
                        url=f"http://{host}:{port}",
                    )
                )

    def _scan_loop(self) -> None:
        while not self.stop_event.is_set():
            self._scan_lan_once()
            self.stop_event.wait(LAN_SCAN_INTERVAL_SECONDS)

    def _scan_lan_once(self) -> None:
        hosts = self._scan_hosts()
        ports = self._scan_ports()
        if not hosts or not ports:
            return

        tasks: list[tuple[str, int]] = [(host, port) for host in hosts for port in ports]
        with concurrent.futures.ThreadPoolExecutor(max_workers=LAN_SCAN_MAX_WORKERS) as executor:
            futures = [executor.submit(self._probe_peer, host, port) for host, port in tasks]
            for future in concurrent.futures.as_completed(futures):
                if self.stop_event.is_set():
                    break
                peer = future.result()
                if peer:
                    self.state.add_peer(peer)

    def _scan_ports(self) -> list[int]:
        raw = os.environ.get("AIRBRIDGE_SCAN_PORTS", "")
        ports: list[int] = []
        if raw:
            for part in raw.split(","):
                try:
                    port = int(part.strip())
                except ValueError:
                    continue
                if 1 <= port <= 65535 and port not in ports:
                    ports.append(port)
        else:
            ports = list(LAN_SCAN_DEFAULT_PORTS)
        if self.state.port not in ports:
            ports.insert(0, self.state.port)
        return ports

    def _scan_hosts(self) -> list[str]:
        try:
            ip = ipaddress.ip_address(self.state.host)
        except ValueError:
            return []
        if ip.version != 4 or ip.is_loopback:
            return []

        parts = [int(part) for part in self.state.host.split(".")]
        radius = int(os.environ.get("AIRBRIDGE_SCAN_RADIUS", "1") or "1")
        radius = max(0, min(radius, 4))
        third_octets = range(max(0, parts[2] - radius), min(255, parts[2] + radius) + 1)

        hosts: list[str] = []
        if parts[0] == 10:
            prefixes = [f"{parts[0]}.{parts[1]}.{third}" for third in third_octets]
        elif parts[0] == 172 and 16 <= parts[1] <= 31:
            prefixes = [f"{parts[0]}.{parts[1]}.{third}" for third in third_octets]
        elif parts[0] == 192 and parts[1] == 168:
            prefixes = [f"{parts[0]}.{parts[1]}.{third}" for third in third_octets]
        else:
            prefixes = [".".join(map(str, parts[:3]))]

        for prefix in prefixes:
            for last in range(1, 255):
                host = f"{prefix}.{last}"
                if host != self.state.host:
                    hosts.append(host)
        return hosts

    def _probe_peer(self, host: str, port: int) -> Peer | None:
        conn = http.client.HTTPConnection(host, port, timeout=LAN_SCAN_TIMEOUT_SECONDS)
        try:
            conn.request("GET", "/api/state")
            response = conn.getresponse()
            if response.status >= 400:
                return None
            body = response.read(1024 * 128)
            payload = json.loads(body.decode("utf-8") or "{}")
        except (OSError, TimeoutError, http.client.HTTPException, json.JSONDecodeError, UnicodeDecodeError):
            return None
        finally:
            conn.close()

        if payload.get("app") != APP_NAME:
            return None
        device = payload.get("device") or {}
        peer_id = str(device.get("id") or "")
        if not peer_id or peer_id == self.state.id:
            return None
        peer_host = str(device.get("host") or host)
        if peer_host.startswith("127."):
            peer_host = host
        try:
            peer_port = int(device.get("port") or port)
        except (TypeError, ValueError):
            peer_port = port
        return Peer(
            id=peer_id,
            name=str(device.get("name") or "Nearby device"),
            host=peer_host,
            port=peer_port,
            url=str(device.get("url") or f"http://{peer_host}:{peer_port}"),
            source="scan",
        )


def html_page() -> bytes:
    return HTML.encode("utf-8")


class AirBridgeHandler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    @property
    def state(self) -> AirBridgeState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        stdout = getattr(sys, "stdout", None)
        if stdout:
            stdout.write(f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} {format % args}\n")

    def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_OPTIONS(self) -> None:
        self._send(204, b"")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, html_page(), "text/html; charset=utf-8")
        elif parsed.path == "/favicon.ico":
            if ICON_PATH.exists():
                self._send(200, ICON_PATH.read_bytes(), "image/x-icon")
            else:
                self._send(204, b"")
        elif parsed.path == "/api/state":
            self.send_json(self.state.to_state())
        elif parsed.path.startswith("/download/"):
            file_id = parsed.path.rsplit("/", 1)[-1]
            with self.state.lock:
                path = self.state.files.get(file_id)
            if not path or not path.exists():
                self.send_json({"ok": False, "error": "File not found"}, 404)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.end_headers()
            with path.open("rb") as f:
                while True:
                    chunk = f.read(1024 * 256)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        else:
            self.send_json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/send-message":
                self.handle_send_message()
            elif parsed.path == "/api/inbox/message":
                self.handle_inbox_message()
            elif parsed.path == "/api/send-file":
                self.handle_send_file()
            elif parsed.path == "/api/inbox/file":
                self.handle_inbox_file()
            elif parsed.path == "/api/peers/manual":
                self.handle_manual_peer()
            else:
                self.send_json({"ok": False, "error": "Not found"}, 404)
        except Exception as exc:  # noqa: BLE001 - surface local tool errors to UI.
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def multipart(self) -> cgi.FieldStorage:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES:
            raise RuntimeError("File is too large")
        return cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(length),
            },
        )

    def peer_by_id(self, peer_id: str) -> Peer:
        with self.state.lock:
            peer = self.state.peers.get(peer_id)
        if not peer:
            raise RuntimeError("Please select a nearby device first")
        return peer

    def handle_send_message(self) -> None:
        payload = self.read_json()
        peer = self.peer_by_id(str(payload.get("peerId", "")))
        text = str(payload.get("text", "")).strip()
        if not text:
            raise RuntimeError("Message is empty")

        post_json(
            peer.host,
            peer.port,
            "/api/inbox/message",
            {
                "fromId": self.state.id,
                "fromName": self.state.name,
                "text": text,
                "createdAt": now_ms(),
            },
        )
        self.send_json({"ok": True})

    def handle_inbox_message(self) -> None:
        payload = self.read_json()
        item = InboxItem(
            id=uuid.uuid4().hex,
            kind="message",
            from_id=str(payload.get("fromId", "")),
            from_name=str(payload.get("fromName") or "Nearby device"),
            created_at=int(payload.get("createdAt") or now_ms()),
            text=str(payload.get("text", "")),
        )
        self.state.add_inbox(item)
        self.send_json({"ok": True, "id": item.id})

    def handle_send_file(self) -> None:
        form = self.multipart()
        peer_id = str(form.getfirst("peer_id", ""))
        peer = self.peer_by_id(peer_id)
        file_item = form["file"] if "file" in form else None
        if file_item is None or not getattr(file_item, "filename", ""):
            raise RuntimeError("No file selected")

        filename = safe_filename(file_item.filename)
        data = file_item.file.read()
        if not data:
            raise RuntimeError("Selected file is empty")

        result = post_multipart(
            peer.host,
            peer.port,
            "/api/inbox/file",
            {
                "from_id": self.state.id,
                "from_name": self.state.name,
                "created_at": str(now_ms()),
            },
            "file",
            filename,
            data,
        )
        self.send_json({"ok": True, "remote": result})

    def handle_inbox_file(self) -> None:
        form = self.multipart()
        file_item = form["file"] if "file" in form else None
        if file_item is None or not getattr(file_item, "filename", ""):
            raise RuntimeError("No file received")

        filename = safe_filename(file_item.filename)
        path = unique_path(RECEIVED_DIR, filename)
        size = 0
        with path.open("wb") as out:
            while True:
                chunk = file_item.file.read(1024 * 256)
                if not chunk:
                    break
                size += len(chunk)
                out.write(chunk)

        item_id = uuid.uuid4().hex
        with self.state.lock:
            self.state.files[item_id] = path
        item = InboxItem(
            id=item_id,
            kind="file",
            from_id=str(form.getfirst("from_id", "")),
            from_name=str(form.getfirst("from_name", "Nearby device")),
            created_at=int(form.getfirst("created_at", str(now_ms()))),
            filename=path.name,
            size=size,
            download_url=f"/download/{item_id}",
            saved_path=str(path),
        )
        self.state.add_inbox(item)
        self.send_json({"ok": True, "id": item_id, "filename": path.name, "size": size})

    def handle_manual_peer(self) -> None:
        payload = self.read_json()
        raw_url = str(payload.get("url", "")).strip()
        if not raw_url:
            raise RuntimeError("Address is empty")
        if not raw_url.startswith(("http://", "https://")):
            raw_url = f"http://{raw_url}"
        parsed = urlparse(raw_url)
        if not parsed.hostname:
            raise RuntimeError("Invalid address")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # GET the remote state with stdlib so manual add works without browser CORS.
        conn = http.client.HTTPConnection(parsed.hostname, port, timeout=6)
        try:
            conn.request("GET", "/api/state")
            response = conn.getresponse()
            body = response.read()
            if response.status >= 400:
                raise RuntimeError(body.decode("utf-8", "replace") or f"HTTP {response.status}")
            state = json.loads(body.decode("utf-8") or "{}")
        finally:
            conn.close()

        device = state.get("device", {})
        peer_id = str(device.get("id") or uuid.uuid4().hex[:12])
        peer = Peer(
            id=peer_id,
            name=str(device.get("name") or parsed.hostname),
            host=str(device.get("host") or parsed.hostname),
            port=int(device.get("port") or port),
            url=str(device.get("url") or f"http://{parsed.hostname}:{port}"),
            source="manual",
        )
        self.state.add_peer(peer)
        self.send_json({"ok": True, "peer": peer.__dict__})


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AirBridge</title>
  <link rel="icon" href="/favicon.ico" />
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --line: #dce3ec;
      --text: #172033;
      --muted: #66758c;
      --accent: #2563eb;
      --accent-strong: #1d4ed8;
      --green: #16a34a;
      --danger: #dc2626;
      --shadow: 0 18px 48px rgba(25, 38, 63, .08);
      font-family: Inter, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
    }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    header {
      height: 68px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 0 28px;
      background: rgba(255, 255, 255, .88);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(14px);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 760;
      font-size: 18px;
    }
    .mark {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      background: #101827;
      box-shadow: 0 8px 18px rgba(17, 28, 46, .16);
      flex: 0 0 36px;
      overflow: hidden;
    }
    .mark img {
      width: 100%;
      height: 100%;
      display: block;
      object-fit: cover;
    }
    .local-url {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      min-width: 0;
    }
    .local-url code {
      padding: 7px 10px;
      background: #edf3fb;
      border: 1px solid var(--line);
      border-radius: 8px;
      color: #22304a;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 46vw;
    }
    main {
      display: grid;
      grid-template-columns: 310px minmax(0, 1fr) 360px;
      gap: 18px;
      padding: 18px;
      min-height: 0;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-height: 0;
    }
    .sidebar, .activity {
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      overflow: hidden;
    }
    h2 {
      margin: 0;
      font-size: 15px;
      letter-spacing: 0;
    }
    .hint {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .peer-list, .inbox-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      overflow-y: auto;
      padding-right: 4px;
    }
    .peer {
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
      cursor: pointer;
      transition: border .16s, box-shadow .16s, transform .16s;
    }
    .peer:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(21, 34, 56, .08); }
    .peer.selected { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37, 99, 235, .12); }
    .peer strong { display: block; font-size: 14px; color: var(--text); }
    .peer span { display: block; margin-top: 5px; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
    .manual {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      margin-top: auto;
    }
    input, textarea, button {
      font: inherit;
    }
    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px 12px;
      outline: none;
      color: var(--text);
      background: #fff;
    }
    input:focus, textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, .12);
    }
    button.primary, button.secondary {
      border: 0;
      border-radius: 8px;
      padding: 11px 14px;
      font-weight: 680;
      cursor: pointer;
      white-space: nowrap;
    }
    button.primary { background: var(--accent); color: #fff; }
    button.primary:hover { background: var(--accent-strong); }
    button.secondary {
      border: 1px solid var(--line);
      color: var(--text);
      background: #fff;
    }
    button:disabled {
      cursor: not-allowed;
      opacity: .5;
    }
    .workspace {
      padding: 22px;
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 18px;
      min-height: 0;
    }
    .target {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }
    .target strong {
      display: block;
      font-size: 18px;
    }
    .target span {
      color: var(--muted);
      font-size: 13px;
    }
    .send-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, .75fr);
      gap: 18px;
      min-height: 0;
    }
    .composer, .drop {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-height: 0;
    }
    textarea {
      min-height: 220px;
      resize: vertical;
      line-height: 1.55;
    }
    .dropzone {
      min-height: 220px;
      border: 1.5px dashed #9fb3ce;
      border-radius: 8px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 22px;
      color: var(--muted);
      background: #f8fbff;
      transition: border .16s, background .16s;
    }
    .dropzone.drag {
      border-color: var(--green);
      background: #effcf6;
    }
    .dropzone strong {
      display: block;
      color: var(--text);
      font-size: 16px;
      margin-bottom: 7px;
    }
    .status {
      min-height: 24px;
      color: var(--muted);
      font-size: 13px;
    }
    .status.ok { color: var(--green); }
    .status.error { color: var(--danger); }
    .item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }
    .item .meta {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 7px;
    }
    .item .text {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 14px;
      line-height: 1.45;
    }
    .file-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .file-row a {
      color: var(--accent);
      font-weight: 680;
      text-decoration: none;
      overflow-wrap: anywhere;
    }
    .empty {
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 16px;
      line-height: 1.5;
      font-size: 13px;
    }
    @media (max-width: 1050px) {
      main { grid-template-columns: 1fr; }
      .send-grid { grid-template-columns: 1fr; }
      header { align-items: flex-start; height: auto; padding: 16px; flex-direction: column; }
      .local-url code { max-width: calc(100vw - 36px); }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div class="brand"><div class="mark"><img src="/favicon.ico" alt="" aria-hidden="true" /></div><span>AirBridge</span></div>
      <div class="local-url">Local Address <code id="localUrl">Starting...</code></div>
    </header>
    <main>
      <section class="sidebar">
        <div>
          <h2>Nearby Devices</h2>
          <p class="hint">AirBridge automatically finds devices with broadcast discovery and nearby-segment scanning.</p>
        </div>
        <div id="peerList" class="peer-list"></div>
        <div class="manual">
          <input id="manualUrl" placeholder="Manual address, e.g. 192.168.1.8:8765" />
          <button class="secondary" id="addPeerBtn">Add</button>
        </div>
      </section>

      <section class="workspace">
        <div class="target">
          <div>
            <strong id="targetName">Select a device</strong>
            <span id="targetUrl">Select a nearby device to send messages or files</span>
          </div>
          <button class="secondary" id="refreshBtn">Refresh</button>
        </div>
        <div class="send-grid">
          <div class="composer">
            <h2>Send Message</h2>
            <textarea id="messageBox" placeholder="Type the message to send..."></textarea>
            <button class="primary" id="sendMessageBtn">Send Message</button>
            <div id="messageStatus" class="status"></div>
          </div>
          <div class="drop">
            <h2>Send File</h2>
            <label class="dropzone" id="dropzone">
              <input id="fileInput" type="file" multiple hidden />
              <span><strong>Drop files here</strong>or click to choose files</span>
            </label>
            <button class="primary" id="sendFileBtn">Send File</button>
            <div id="fileStatus" class="status"></div>
          </div>
        </div>
      </section>

      <section class="activity">
        <div>
          <h2>Received Files and Messages</h2>
          <p class="hint">Files are saved in the AirBridge-Received folder next to the program.</p>
        </div>
        <div id="inboxList" class="inbox-list"></div>
      </section>
    </main>
  </div>

  <script>
    let state = null;
    let selectedPeerId = "";
    let selectedFiles = [];

    const $ = (id) => document.getElementById(id);
    const fmtBytes = (n) => {
      if (!n) return "0 B";
      const units = ["B", "KB", "MB", "GB"];
      let value = n, i = 0;
      while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
      return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
    };
    const fmtTime = (ms) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const setStatus = (id, text, type = "") => {
      const el = $(id);
      el.textContent = text;
      el.className = `status ${type}`;
    };

    async function loadState() {
      const res = await fetch("/api/state");
      state = await res.json();
      render();
    }

    function renderPeers() {
      const list = $("peerList");
      list.innerHTML = "";
      if (!state.peers.length) {
        list.innerHTML = '<div class="empty">No devices found yet. Start AirBridge on another device or enter its address manually.</div>';
        return;
      }
      for (const peer of state.peers) {
        const btn = document.createElement("button");
        btn.className = `peer ${peer.id === selectedPeerId ? "selected" : ""}`;
        btn.innerHTML = `<strong>${peer.name}</strong><span>${peer.url}${peer.source === "manual" ? " · manual" : ""}</span>`;
        btn.onclick = () => { selectedPeerId = peer.id; render(); };
        list.appendChild(btn);
      }
    }

    function renderTarget() {
      const peer = state.peers.find(p => p.id === selectedPeerId);
      $("targetName").textContent = peer ? peer.name : "Select a device";
      $("targetUrl").textContent = peer ? peer.url : "Select a nearby device to send messages or files";
      $("sendMessageBtn").disabled = !peer;
      $("sendFileBtn").disabled = !peer;
    }

    function renderInbox() {
      const list = $("inboxList");
      list.innerHTML = "";
      if (!state.inbox.length) {
        list.innerHTML = '<div class="empty">Received items will appear here.</div>';
        return;
      }
      for (const item of state.inbox) {
        const div = document.createElement("div");
        div.className = "item";
        if (item.kind === "file") {
          div.innerHTML = `
            <div class="meta">${fmtTime(item.created_at)} · From ${item.from_name} · ${fmtBytes(item.size)}</div>
            <div class="file-row">
              <a href="${item.download_url}">${item.filename}</a>
            </div>`;
        } else {
          div.innerHTML = `
            <div class="meta">${fmtTime(item.created_at)} · From ${item.from_name}</div>
            <div class="text">${escapeHtml(item.text)}</div>`;
        }
        list.appendChild(div);
      }
    }

    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function render() {
      $("localUrl").textContent = state.device.url;
      renderPeers();
      renderTarget();
      renderInbox();
    }

    async function sendMessage() {
      const text = $("messageBox").value.trim();
      if (!text) return setStatus("messageStatus", "Enter a message first.", "error");
      setStatus("messageStatus", "Sending...");
      const res = await fetch("/api/send-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ peerId: selectedPeerId, text })
      });
      const data = await res.json();
      if (!data.ok) return setStatus("messageStatus", data.error || "Send failed.", "error");
      $("messageBox").value = "";
      setStatus("messageStatus", "Message sent.", "ok");
    }

    async function sendFiles() {
      if (!selectedFiles.length) return setStatus("fileStatus", "Select a file first.", "error");
      for (const file of selectedFiles) {
        setStatus("fileStatus", `Sending ${file.name}...`);
        const fd = new FormData();
        fd.append("peer_id", selectedPeerId);
        fd.append("file", file);
        const res = await fetch("/api/send-file", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.ok) return setStatus("fileStatus", data.error || "Send failed.", "error");
      }
      selectedFiles = [];
      $("fileInput").value = "";
      setStatus("fileStatus", "File sent.", "ok");
    }

    async function addManualPeer() {
      const url = $("manualUrl").value.trim();
      if (!url) return;
      const res = await fetch("/api/peers/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();
      if (!data.ok) {
        alert(data.error || "Add failed");
        return;
      }
      selectedPeerId = data.peer.id;
      $("manualUrl").value = "";
      await loadState();
    }

    $("sendMessageBtn").onclick = sendMessage;
    $("sendFileBtn").onclick = sendFiles;
    $("addPeerBtn").onclick = addManualPeer;
    $("refreshBtn").onclick = loadState;
    $("fileInput").onchange = (event) => {
      selectedFiles = Array.from(event.target.files || []);
      setStatus("fileStatus", selectedFiles.length ? `Selected ${selectedFiles.length} files.` : "");
    };
    $("dropzone").onclick = () => $("fileInput").click();
    $("dropzone").ondragover = (event) => { event.preventDefault(); $("dropzone").classList.add("drag"); };
    $("dropzone").ondragleave = () => $("dropzone").classList.remove("drag");
    $("dropzone").ondrop = (event) => {
      event.preventDefault();
      $("dropzone").classList.remove("drag");
      selectedFiles = Array.from(event.dataTransfer.files || []);
      setStatus("fileStatus", selectedFiles.length ? `Selected ${selectedFiles.length} files.` : "");
    };

    loadState().catch(err => console.error(err));
    setInterval(() => loadState().catch(() => {}), 2000);
  </script>
</body>
</html>
"""


def run() -> None:
    port = int(os.environ.get("AIRBRIDGE_PORT", "0") or "0") or find_free_port()
    host = get_lan_ip()
    name = os.environ.get("AIRBRIDGE_NAME") or f"{socket.gethostname()}-{uuid.uuid4().hex[:4]}"
    RECEIVED_DIR.mkdir(parents=True, exist_ok=True)

    state = AirBridgeState(name=name, host=host, port=port)
    server = ThreadingHTTPServer(("", port), AirBridgeHandler)
    server.state = state  # type: ignore[attr-defined]
    discovery = Discovery(state)
    discovery.start()

    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Device: {state.name}")
    print(f"Open:   {state.url}")
    print(f"Files:  {RECEIVED_DIR}")
    print("Tip: allow Python/AirBridge through Windows Firewall for other devices.")

    if os.environ.get("AIRBRIDGE_NO_BROWSER") != "1":
        threading.Timer(0.5, lambda: webbrowser.open(state.url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        discovery.stop_event.set()
        server.shutdown()


if __name__ == "__main__":
    run()
