#!/usr/bin/env python3

import os
import re
import time
import socket
import hashlib
import secrets
import logging
import threading
import urllib.request
import base64
import yaml
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG_FILE = "/app/exporter_config.yml"
SCRAPE_INTERVAL = 1
LISTEN_PORT = 9115
RTSP_TIMEOUT = float(os.environ.get("RTSP_TIMEOUT", "5"))
VM_PUSH_URL = os.environ.get("VM_PUSH_URL", "http://victoriametrics:8428/api/v1/import/prometheus")
GRAFANA_BASE_URL = os.environ.get("GRAFANA_BASE_URL", "http://grafana:3000")
GRAFANA_AUTH = os.environ.get("GRAFANA_AUTH", "admin:admin")
GRAFANA_STREAM_ID = os.environ.get("GRAFANA_STREAM_ID", "cameras")

HIKVISION_MAIN_CHANNEL = 101


@dataclass
class CameraConfig:
    name: str
    host: str
    port: int
    path: str = "/"
    username: str = ""
    password: str = ""
    vendor: str = ""
    channel: int = HIKVISION_MAIN_CHANNEL
    http_port: int = 80
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class CameraMetrics:
    up: float = 0.0
    latency_ms: float = 0.0
    packet_loss: float = 0.0
    jitter_ms: float = 0.0
    bitrate_kbps: float = 0.0
    last_scrape: float = 0.0
    error: str = ""


def hikvision_stream_path(channel: int) -> str:
    return f"/Streaming/Channels/{channel}"


def camera_from_dict(c: dict) -> CameraConfig:
    vendor = (c.get("vendor") or "").strip().lower()
    channel = int(c.get("channel", HIKVISION_MAIN_CHANNEL))
    port = c.get("port")
    if port is None:
        port = 554 if vendor == "hikvision" else 8554
    else:
        port = int(port)

    path = c.get("path") or "/"
    if vendor == "hikvision" and path in ("/", ""):
        path = hikvision_stream_path(channel)

    http_port = int(c.get("http_port", 80))

    return CameraConfig(
        name=c["name"],
        host=c["host"],
        port=port,
        path=path,
        username=c.get("username") or "",
        password=c.get("password") or "",
        vendor=vendor,
        channel=channel,
        http_port=http_port,
        labels=c.get("labels") or {},
    )


def _parse_digest_challenge(www_authenticate: str) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for match in re.finditer(r'(\w+)=("([^"]*)"|([^,\s]+))', www_authenticate):
        params[match.group(1)] = match.group(3) if match.group(3) is not None else match.group(2)
    return params


def _digest_authorization(
    method: str,
    rtsp_url: str,
    username: str,
    password: str,
    challenge: Dict[str, str],
) -> str:
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    opaque = challenge.get("opaque", "")
    qop_raw = challenge.get("qop", "")

    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{rtsp_url}".encode()).hexdigest()

    if qop_raw:
        qop = qop_raw.split(",")[0].strip()
        nc = "00000001"
        cnonce = secrets.token_hex(8)
        response = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
        header = (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{rtsp_url}", response="{response}", algorithm=MD5, '
            f'cnonce="{cnonce}", nc={nc}, qop={qop}'
        )
    else:
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        header = (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{rtsp_url}", response="{response}"'
        )

    if opaque:
        header += f', opaque="{opaque}"'
    return f"Authorization: {header}"


def _basic_authorization(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Authorization: Basic {token}"


def _recv_rtsp(sock: socket.socket) -> str:
    sock.settimeout(RTSP_TIMEOUT)
    data = b""
    while b"\r\n\r\n" not in data:
        part = sock.recv(8192)
        if not part:
            break
        data += part

    header_end = data.find(b"\r\n\r\n")
    if header_end == -1:
        return data.decode("utf-8", errors="replace")

    headers = data[:header_end].decode("utf-8", errors="replace")
    body = data[header_end + 4 :]
    content_length = 0
    for line in headers.splitlines():
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
            break

    while len(body) < content_length:
        part = sock.recv(8192)
        if not part:
            break
        body += part

    return headers + "\r\n\r\n" + body.decode("utf-8", errors="replace")


def _rtsp_request(
    sock: socket.socket,
    method: str,
    rtsp_url: str,
    cseq: int,
    extra_headers: Optional[List[str]] = None,
) -> str:
    lines = [
        f"{method} {rtsp_url} RTSP/1.0",
        f"CSeq: {cseq}",
        "User-Agent: rtsp-exporter/1.0",
    ]
    if extra_headers:
        lines.extend(extra_headers)
    lines.extend(["", ""])
    sock.sendall("\r\n".join(lines).encode())
    return _recv_rtsp(sock)


def _status_code(response: str) -> int:
    first = response.split("\r\n", 1)[0]
    parts = first.split()
    if len(parts) >= 2 and parts[0].startswith("RTSP/"):
        try:
            return int(parts[1])
        except ValueError:
            pass
    return 0


def _www_authenticate(response: str) -> Optional[str]:
    for line in response.splitlines():
        if line.lower().startswith("www-authenticate:"):
            return line.split(":", 1)[1].strip()
    return None


def _probe_method(camera: CameraConfig) -> str:
    if camera.vendor == "hikvision":
        return "DESCRIBE"
    return "OPTIONS"


def _rtsp_probe(sock: socket.socket, camera: CameraConfig, rtsp_url: str) -> Tuple[str, float]:
    method = _probe_method(camera)
    t0 = time.perf_counter()
    cseq = 1
    headers: List[str] = []
    if camera.username and camera.vendor != "hikvision":
        headers.append(_basic_authorization(camera.username, camera.password))

    response = _rtsp_request(sock, method, rtsp_url, cseq, headers or None)
    code = _status_code(response)

    if code == 401 and camera.username:
        www = _www_authenticate(response)
        cseq += 1
        auth_headers: List[str] = []
        if www and www.lower().startswith("digest"):
            challenge = _parse_digest_challenge(www)
            auth_headers.append(
                _digest_authorization(method, rtsp_url, camera.username, camera.password, challenge)
            )
        else:
            auth_headers.append(_basic_authorization(camera.username, camera.password))
        if method == "DESCRIBE":
            auth_headers.append("Accept: application/sdp")
        response = _rtsp_request(sock, method, rtsp_url, cseq, auth_headers)

    latency_ms = (time.perf_counter() - t0) * 1000
    return response, latency_ms


def _apply_rtp_headers(m: CameraMetrics, response: str) -> None:
    for line in response.splitlines():
        if line.startswith("X-RTP-PacketLoss:"):
            m.packet_loss = float(line.split(":", 1)[1].strip())
        elif line.startswith("X-RTP-Jitter:"):
            m.jitter_ms = float(line.split(":", 1)[1].strip())
        elif line.startswith("X-RTP-Bitrate:"):
            m.bitrate_kbps = float(line.split(":", 1)[1].strip())


def _parse_sdp_bitrate_kbps(response: str) -> Optional[float]:
    if "\r\n\r\n" not in response:
        return None
    body = response.split("\r\n\r\n", 1)[1]
    in_video = False
    video_bw = 0.0
    session_bw = 0.0
    for line in body.splitlines():
        if line.startswith("m=video"):
            in_video = True
            continue
        if line.startswith("m="):
            in_video = False
        if line.startswith("b=AS:"):
            value = float(line.split(":", 1)[1].strip())
            if in_video:
                video_bw = max(video_bw, value)
            else:
                session_bw = max(session_bw, value)
    return video_bw or session_bw or None


def _isapi_get(camera: CameraConfig, path: str) -> Optional[str]:
    if not camera.username:
        return None
    url = f"http://{camera.host}:{camera.http_port}{path}"
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, f"http://{camera.host}", camera.username, camera.password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(password_mgr))
    try:
        with opener.open(url, timeout=RTSP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.debug(f"[{camera.name}] ISAPI {path}: {e}")
        return None


def _parse_isapi_bitrate_kbps(xml: str) -> Optional[float]:
    for tag in ("constantBitRate", "vbrUpperCap"):
        match = re.search(rf"<{tag}>(\d+)</{tag}>", xml)
        if match:
            return float(match.group(1))
    return None


def _apply_hikvision_metrics(m: CameraMetrics, camera: CameraConfig, rtsp_response: str) -> None:
    cfg_bitrate = None
    xml = _isapi_get(camera, f"/ISAPI/Streaming/channels/{camera.channel}")
    if xml:
        cfg_bitrate = _parse_isapi_bitrate_kbps(xml)

    sdp_bitrate = _parse_sdp_bitrate_kbps(rtsp_response)

    if cfg_bitrate:
        m.bitrate_kbps = cfg_bitrate
    elif sdp_bitrate:
        m.bitrate_kbps = sdp_bitrate


def probe_rtsp(camera: CameraConfig) -> CameraMetrics:
    m = CameraMetrics(last_scrape=time.time())
    rtsp_url = f"rtsp://{camera.host}:{camera.port}{camera.path}"

    try:
        t0 = time.perf_counter()
        sock = socket.create_connection((camera.host, camera.port), timeout=RTSP_TIMEOUT)
        connect_ms = (time.perf_counter() - t0) * 1000

        response, probe_ms = _rtsp_probe(sock, camera, rtsp_url)
        sock.close()

        code = _status_code(response)
        if code == 200:
            m.up = 1.0
            m.latency_ms = round(connect_ms + probe_ms, 2)
            _apply_rtp_headers(m, response)
            if camera.vendor == "hikvision":
                _apply_hikvision_metrics(m, camera, response)
        elif code == 401:
            m.up = 0.0
            m.error = "authentication required"
            log.warning(f"[{camera.name}] RTSP 401 — проверьте username/password")
        else:
            m.up = 0.0
            m.error = response.split("\r\n", 1)[0][:120]
            log.warning(f"[{camera.name}] RTSP {code}: {m.error}")

    except socket.timeout:
        m.up = 0.0
        m.error = "connection timeout"
        log.warning(f"[{camera.name}] Timeout ({RTSP_TIMEOUT}s)")
    except ConnectionRefusedError:
        m.up = 0.0
        m.error = "connection refused"
        log.warning(f"[{camera.name}] Connection refused")
    except Exception as e:
        m.up = 0.0
        m.error = str(e)
        log.error(f"[{camera.name}] Error: {e}")

    return m


class MetricsStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, tuple[CameraConfig, CameraMetrics]] = {}

    def update(self, camera: CameraConfig, metrics: CameraMetrics):
        with self._lock:
            self._data[camera.name] = (camera, metrics)

    def snapshot(self) -> list:
        with self._lock:
            return list(self._data.values())

    def remove_stale(self, active_names: set):
        with self._lock:
            stale = [name for name in self._data if name not in active_names]
            for name in stale:
                log.info(f"Removing stale camera from metrics store: {name}")
                del self._data[name]

    def render_prometheus(self) -> str:
        lines = []
        with self._lock:
            items = list(self._data.values())

        def lbl(camera: CameraConfig) -> str:
            base = (
                f'camera="{camera.name}",host="{camera.host}",port="{camera.port}",'
                f'vendor="{camera.vendor or "generic"}"'
            )
            for k, v in camera.labels.items():
                base += f',{k}="{v}"'
            return "{" + base + "}"

        defs = [
            ("camera_up", "gauge", "Camera RTSP endpoint availability (1=up, 0=down)"),
            ("camera_rtsp_latency_ms", "gauge", "RTSP connection round-trip latency in milliseconds"),
            ("camera_rtp_packet_loss_ratio", "gauge", "RTP packet loss ratio (0..1)"),
            ("camera_rtp_jitter_ms", "gauge", "RTP jitter in milliseconds"),
            ("camera_stream_bitrate_kbps", "gauge", "Stream bitrate in kbps (configured or SDP b=AS)"),
            ("camera_last_scrape_timestamp", "gauge", "Unix timestamp of last successful scrape"),
        ]
        for name, mtype, help_text in defs:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {mtype}")

        for camera, m in items:
            l = lbl(camera)
            lines.append(f"camera_up{l} {m.up}")
            lines.append(f"camera_rtsp_latency_ms{l} {m.latency_ms}")
            lines.append(f"camera_rtp_packet_loss_ratio{l} {m.packet_loss}")
            lines.append(f"camera_rtp_jitter_ms{l} {m.jitter_ms}")
            lines.append(f"camera_stream_bitrate_kbps{l} {m.bitrate_kbps}")
            lines.append(f"camera_last_scrape_timestamp{l} {m.last_scrape}")

        return "\n".join(lines) + "\n"


store = MetricsStore()

config_changed = threading.Event()


def push_to_grafana_live():
    items = store.snapshot()
    if not items:
        return

    timestamp_ns = int(time.time() * 1_000_000_000)
    lines = []

    for camera, m in items:
        tag_str = f"camera={camera.name}"
        for k, v in sorted(camera.labels.items()):
            tag_str += f",{k}={v}"

        field_str = (
            f"up={int(m.up)}i,"
            f"latency_ms={m.latency_ms:.4f},"
            f"packet_loss={m.packet_loss:.6f},"
            f"jitter_ms={m.jitter_ms:.4f},"
            f"bitrate_kbps={m.bitrate_kbps:.2f}"
        )
        lines.append(f"camera_metrics,{tag_str} {field_str} {timestamp_ns}")

    online = sum(1 for _, m in items if m.up >= 0.5)
    offline = len(items) - online
    lines.append(f"camera_summary online={online}i,offline={offline}i,total={len(items)}i {timestamp_ns}")

    data = "\n".join(lines).encode("utf-8")
    url = f"{GRAFANA_BASE_URL}/api/live/push/{GRAFANA_STREAM_ID}"
    auth = base64.b64encode(GRAFANA_AUTH.encode()).decode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "text/plain", "Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            log.info(f"Grafana Live push → {resp.status}")
    except Exception as e:
        log.error(f"Grafana Live push failed: {e}")


def push_to_vm(metrics_text: str):
    data = metrics_text.encode("utf-8")
    req = urllib.request.Request(
        VM_PUSH_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            log.info(f"Pushed metrics to VM, status={resp.status}")
    except Exception as e:
        log.error(f"Failed to push metrics to VM: {e}")


def load_cameras(config_path: str) -> List[CameraConfig]:
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        cameras = [camera_from_dict(c) for c in cfg.get("cameras", [])]
        log.info(f"Loaded {len(cameras)} camera(s) from config")
        return cameras
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        return []


def poll_loop():
    while True:
        cameras = load_cameras(CONFIG_FILE)
        store.remove_stale({cam.name for cam in cameras})
        threads = []
        for camera in cameras:
            def task(cam=camera):
                log.info(f"Probing {cam.name} ({cam.host}:{cam.port}{cam.path})")
                metrics = probe_rtsp(cam)
                store.update(cam, metrics)
                status = "UP" if metrics.up else "DOWN"
                log.info(f"  [{cam.name}] {status} | latency={metrics.latency_ms}ms | loss={metrics.packet_loss:.1%}")
            t = threading.Thread(target=task, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        push_to_vm(store.render_prometheus())
        push_to_grafana_live()
        config_changed.wait(timeout=SCRAPE_INTERVAL)
        config_changed.clear()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/metrics", "/"):
            body = store.render_prometheus().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/reload":
            config_changed.set()
            log.info("Config reload triggered via POST /reload")
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    log.info(f"Starting rtsp-exporter on :{LISTEN_PORT}")
    poller = threading.Thread(target=poll_loop, daemon=True)
    poller.start()

    server = HTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    log.info(f"Metrics available at http://0.0.0.0:{LISTEN_PORT}/metrics")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
