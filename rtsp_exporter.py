#!/usr/bin/env python3
"""
rtsp_exporter.py — Кастомный Prometheus-экспортёр для мониторинга RTSP/RTP-потоков.

Собирает метрики:
  - camera_up                   (1/0 — доступность)
  - camera_rtsp_latency_ms      (задержка подключения, мс)
  - camera_rtp_packet_loss_ratio (доля потерянных пакетов 0..1)
  - camera_rtp_jitter_ms        (джиттер, мс)
  - camera_stream_bitrate_kbps  (битрейт потока, кбит/с)
  - camera_last_scrape_timestamp (unix-время последнего опроса)
"""

import time
import socket
import struct
import random
import logging
import threading
import yaml
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Конфигурация ────────────────────────────────────────────────────────────

CONFIG_FILE = "/app/exporter_config.yml"
SCRAPE_INTERVAL = 15   # секунд между опросами камер
LISTEN_PORT = 9115
RTSP_TIMEOUT = 5       # таймаут подключения к камере

# ─── Структуры данных ─────────────────────────────────────────────────────────

@dataclass
class CameraConfig:
    name: str
    host: str
    port: int
    path: str = "/"
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


# ─── Сбор метрик ─────────────────────────────────────────────────────────────

def probe_rtsp(camera: CameraConfig) -> CameraMetrics:
    """
    Подключается к RTSP-эндпоинту по TCP и отправляет минимальный RTSP OPTIONS-запрос.
    Измеряет round-trip latency. Остальные метрики получаем из специального
    заголовка X-RTP-Stats (который отдаёт наш mock-сервер) или вычисляем эвристически.
    """
    m = CameraMetrics(last_scrape=time.time())
    rtsp_url = f"rtsp://{camera.host}:{camera.port}{camera.path}"

    try:
        t0 = time.perf_counter()
        sock = socket.create_connection((camera.host, camera.port), timeout=RTSP_TIMEOUT)
        connect_ms = (time.perf_counter() - t0) * 1000

        # Отправляем RTSP OPTIONS — минимальный валидный запрос
        request = (
            f"OPTIONS {rtsp_url} RTSP/1.0\r\n"
            f"CSeq: 1\r\n"
            f"User-Agent: rtsp-exporter/1.0\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode())

        t1 = time.perf_counter()
        response = sock.recv(4096).decode("utf-8", errors="replace")
        rtt_ms = (time.perf_counter() - t1) * 1000 + connect_ms

        sock.close()

        if "RTSP/1.0 200" in response:
            m.up = 1.0
            m.latency_ms = round(rtt_ms, 2)

            # Парсим опциональные заголовки из mock-сервера
            for line in response.splitlines():
                if line.startswith("X-RTP-PacketLoss:"):
                    m.packet_loss = float(line.split(":")[1].strip())
                elif line.startswith("X-RTP-Jitter:"):
                    m.jitter_ms = float(line.split(":")[1].strip())
                elif line.startswith("X-RTP-Bitrate:"):
                    m.bitrate_kbps = float(line.split(":")[1].strip())
        else:
            m.up = 0.0
            m.error = f"Unexpected response: {response[:80]}"

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


# ─── Хранилище метрик ─────────────────────────────────────────────────────────

class MetricsStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, tuple[CameraConfig, CameraMetrics]] = {}

    def update(self, camera: CameraConfig, metrics: CameraMetrics):
        with self._lock:
            self._data[camera.name] = (camera, metrics)

    def remove_stale(self, active_names: set):
        """Удаляет из хранилища камеры, которых больше нет в конфиге."""
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
            base = f'camera="{camera.name}",host="{camera.host}",port="{camera.port}"'
            for k, v in camera.labels.items():
                base += f',{k}="{v}"'
            return "{" + base + "}"

        # Метаданные метрик
        defs = [
            ("camera_up", "gauge", "Camera RTSP endpoint availability (1=up, 0=down)"),
            ("camera_rtsp_latency_ms", "gauge", "RTSP connection round-trip latency in milliseconds"),
            ("camera_rtp_packet_loss_ratio", "gauge", "RTP packet loss ratio (0..1)"),
            ("camera_rtp_jitter_ms", "gauge", "RTP jitter in milliseconds"),
            ("camera_stream_bitrate_kbps", "gauge", "Estimated stream bitrate in kbps"),
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


# ─── Фоновый поллер ──────────────────────────────────────────────────────────

def load_cameras(config_path: str) -> List[CameraConfig]:
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        cameras = []
        for c in cfg.get("cameras", []):
            cameras.append(CameraConfig(
                name=c["name"],
                host=c["host"],
                port=int(c.get("port", 554)),
                path=c.get("path", "/"),
                labels=c.get("labels", {}),
            ))
        log.info(f"Loaded {len(cameras)} camera(s) from config")
        return cameras
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        return []


def poll_loop():
    while True:
        cameras = load_cameras(CONFIG_FILE)
        # Удаляем из хранилища камеры, которые были убраны из конфига
        store.remove_stale({cam.name for cam in cameras})
        threads = []
        for camera in cameras:
            def task(cam=camera):
                log.info(f"Probing {cam.name} ({cam.host}:{cam.port})")
                metrics = probe_rtsp(cam)
                store.update(cam, metrics)
                status = "UP" if metrics.up else "DOWN"
                log.info(f"  [{cam.name}] {status} | latency={metrics.latency_ms}ms | loss={metrics.packet_loss:.1%}")
            t = threading.Thread(target=task, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        time.sleep(SCRAPE_INTERVAL)


# ─── HTTP-сервер для Prometheus ───────────────────────────────────────────────

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

    def log_message(self, fmt, *args):
        pass  # подавляем стандартный лог HTTP


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
