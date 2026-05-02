#!/usr/bin/env python3
"""
HTTP streaming server for librespot audio.

Reads MP3 bytes from stdin (piped from ffmpeg) and serves them to a single
HTTP client on port 8765. Stays bound to port 8765 while waiting for a client
— naboo can connect at any time and immediately start receiving audio.

Single-client: if a new client connects, the old one is closed.
"""
import select
import socket
import sys
import time

PORT = 8765
CHUNK = 2048  # smaller chunks → smoother pacing, faster select() loop
# 192k MP3 = 24000 bytes/sec × 1.05 = 25200. The 5% headroom lets ESPHome
# build a small safety buffer so pipeline stalls between tracks don't cause
# dropouts. Rate-limit is unconditional — without it librespot/ffmpeg run at
# CPU speed (runaway decode), and ESPHome greedily downloads the entire track
# over localhost eliminating backpressure and making skips/pauses unresponsive.
BYTES_PER_SEC = int(192 * 1000 * 1.05 // 8)  # 25200
# Small TCP send buffer: limits in-flight data to ~170ms at 25200 bytes/sec.
# Default macOS SO_SNDBUF is ~128 KB = 5+ seconds of audio buffered in the
# kernel — that's the main source of the lag and skip latency.
SNDBUF = 8192
HTTP_HEADER = (
    b"HTTP/1.0 200 OK\r\n"
    b"Content-Type: audio/mpeg\r\n"
    b"Cache-Control: no-cache, no-store\r\n"
    b"Pragma: no-cache\r\n"
    b"\r\n"
)

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(1)
srv.setblocking(False)

client = None
stdin_fd = sys.stdin.buffer.fileno()

# Cumulative rate-limiter: tracks total bytes processed and wall-clock start
# so we sleep only the deficit — no oversleep when sendall() itself takes time.
_rate_start = time.monotonic()
_rate_bytes = 0

while True:
    # Monitor stdin (audio from ffmpeg) and the server socket simultaneously.
    # Timeout 1s so we don't block forever if stdin goes quiet.
    read_fds = [srv, stdin_fd]
    try:
        readable, _, _ = select.select(read_fds, [], [], 1.0)
    except (OSError, ValueError):
        break

    for fd in readable:

        # ── New HTTP client ───────────────────────────────────────────────────
        if fd is srv:
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            if client:
                try:
                    client.close()
                except OSError:
                    pass
            client = conn
            client.setblocking(True)
            try:
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            try:
                # Small send buffer limits kernel-buffered data to ~170ms,
                # keeping skip/pause latency low. macOS rounds up to minimum.
                client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SNDBUF)
            except OSError:
                pass
            # Reset rate-limiter on each new connection so idle time between
            # plays doesn't accumulate a negative deficit. Without this, a
            # pause/resume cycle lets the deficit go deeply negative, causing
            # a burst send that pre-fills ESPHome's buffer and grows lag with
            # every play cycle.
            _rate_start = time.monotonic()
            _rate_bytes = 0
            try:
                client.sendall(HTTP_HEADER)
            except OSError:
                try:
                    client.close()
                except OSError:
                    pass
                client = None

        # ── Audio data from ffmpeg via stdin ──────────────────────────────────
        elif fd == stdin_fd:
            try:
                data = sys.stdin.buffer.read1(CHUNK)
            except OSError:
                data = b""
            if not data:
                # stdin closed — ffmpeg exited, we're done
                raise SystemExit(0)
            if client:
                try:
                    client.sendall(data)
                except OSError:
                    try:
                        client.close()
                    except OSError:
                        pass
                    client = None

            # Unconditional real-time rate limiter (cumulative).
            # Sleeps only the deficit so sendall() time counts toward pacing.
            _rate_bytes += len(data)
            expected = _rate_bytes / BYTES_PER_SEC
            deficit = expected - (time.monotonic() - _rate_start)
            if deficit > 0:
                time.sleep(deficit)
