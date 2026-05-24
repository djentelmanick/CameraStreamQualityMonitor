#!/usr/bin/env python3

import os
import time
import socket
import random
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CAMERA_ID    = os.environ.get("CAMERA_ID", "camera-1")
LATENCY_MS   = float(os.environ.get("LATENCY_MS", "50"))
PACKET_LOSS  = float(os.environ.get("PACKET_LOSS", "0.02"))
BITRATE_KBPS = float(os.environ.get("BITRATE_KBPS", "2048"))
PORT         = int(os.environ.get("PORT", "8554"))


def jitter_value(base: float, pct: float = 0.15) -> float:
    noise = base * pct * (random.random() * 2 - 1)
    return max(0.0, base + noise)


def handle_client(conn: socket.socket, addr):
    try:
        data = conn.recv(1024).decode("utf-8", errors="replace")
        if not data:
            return

        if random.random() < PACKET_LOSS * 0.3:
            log.debug(f"[{CAMERA_ID}] Simulating dropped connection from {addr}")
            conn.close()
            return

        delay_s = jitter_value(LATENCY_MS) / 1000.0
        time.sleep(delay_s)

        jitter_ms = round(jitter_value(LATENCY_MS * 0.2, pct=0.5), 2)

        response = (
            "RTSP/1.0 200 OK\r\n"
            "CSeq: 1\r\n"
            f"Server: MockCamera/{CAMERA_ID}\r\n"
            "Public: OPTIONS, DESCRIBE, SETUP, PLAY, PAUSE, TEARDOWN\r\n"
            f"X-Camera-ID: {CAMERA_ID}\r\n"
            f"X-RTP-PacketLoss: {round(jitter_value(PACKET_LOSS, pct=0.3), 4)}\r\n"
            f"X-RTP-Jitter: {jitter_ms}\r\n"
            f"X-RTP-Bitrate: {round(jitter_value(BITRATE_KBPS, pct=0.1), 1)}\r\n"
            "\r\n"
        )
        conn.sendall(response.encode())
        log.info(f"[{CAMERA_ID}] Responded to {addr[0]} | delay={delay_s*1000:.1f}ms | loss={PACKET_LOSS:.1%}")

    except Exception as e:
        log.error(f"[{CAMERA_ID}] Error handling {addr}: {e}")
    finally:
        conn.close()


def run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(32)
    log.info(f"Mock RTSP server [{CAMERA_ID}] listening on port {PORT}")
    log.info(f"  Config: latency={LATENCY_MS}ms, packet_loss={PACKET_LOSS:.1%}, bitrate={BITRATE_KBPS}kbps")

    while True:
        try:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            log.error(f"Accept error: {e}")


if __name__ == "__main__":
    run_server()
