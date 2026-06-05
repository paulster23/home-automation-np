#!/usr/bin/env python3
"""
HTTP streaming server for librespot audio.

Reads MP3 bytes from stdin (piped from ffmpeg) and serves them to a single
HTTP client on port 8765. Stays bound to port 8765 while waiting for a client
— naboo can connect at any time and immediately start receiving audio.

Single-client: if a new client connects, the old one is closed.

Stream health logging
─────────────────────
Writes timestamped events to log/stream.log (same dir as this script):
  CLIENT_CONNECT <ip>:<port>       — ESPHome opened the HTTP connection
  CLIENT_DISCONNECT <reason>       — ESPHome dropped, or replaced by new connect
  STALL_START idle=<ms>ms          — stdin from ffmpeg went dry (pipe stall)
  STALL_END <ms>ms                 — audio resumed after a stall
  THROUGHPUT bytes=<n> rate=<bps>bps elapsed=<s>s  — every 10s while streaming
  STDIN_EOF                        — ffmpeg exited, pipeline is done
voice-bench tails this file to correlate pipe stalls with dropout events.
"""
import select
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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

# Stall detection: log STALL_START when stdin is silent for this long.
# 100ms is well below audible; it catches pipeline pauses before they empty
# ESPHome's buffer (typically 1–2s deep at 192kbps).
STALL_THRESHOLD_MS = 100

# Log a THROUGHPUT line every N seconds while a client is connected.
THROUGHPUT_INTERVAL = 10.0

HTTP_HEADER = (
    b"HTTP/1.0 200 OK\r\n"
    b"Content-Type: audio/mpeg\r\n"
    b"Cache-Control: no-cache, no-store\r\n"
    b"Pragma: no-cache\r\n"
    b"\r\n"
)

# ── Stream health log ─────────────────────────────────────────────────────────
_LOG_DIR = Path(__file__).parent / "log"


def _stream_log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_DIR / "stream.log", "a") as f:
            f.write(f"{ts} {msg}\n")
    except OSError:
        pass


# ── Server setup ──────────────────────────────────────────────────────────────
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

# Stall detection state
_last_data_mono  = time.monotonic()   # monotonic time of the last stdin read
_stall_start_mono = None              # set when STALL_START is logged; None otherwise

# Throughput tracking state (cumulative per client session)
_tp_bytes        = 0
_tp_session_start = time.monotonic()
_tp_last_report  = time.monotonic()

while True:
    # Select timeout 0.2s for responsive stall detection (was 1.0s).
    # At 192kbps each 2 KB chunk arrives every ~85ms, so 0.2s is one missed
    # chunk — fast enough to catch real stalls before ESPHome's buffer empties.
    read_fds = [srv, stdin_fd]
    try:
        readable, _, _ = select.select(read_fds, [], [], 0.2)
    except (OSError, ValueError):
        break

    for fd in readable:

        # ── New HTTP client ───────────────────────────────────────────────────
        if fd is srv:
            try:
                conn, addr = srv.accept()
            except OSError:
                continue
            if client:
                try:
                    client.close()
                except OSError:
                    pass
                _stream_log("CLIENT_DISCONNECT replaced")
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
            _stream_log(f"CLIENT_CONNECT {addr[0]}:{addr[1]}")

            # Reset rate-limiter on each new connection so idle time between
            # plays doesn't accumulate a negative deficit. Without this, a
            # pause/resume cycle lets the deficit go deeply negative, causing
            # a burst send that pre-fills ESPHome's buffer and grows lag with
            # every play cycle.
            _rate_start = time.monotonic()
            _rate_bytes = 0

            # Reset stall tracker and throughput for the new client session.
            _last_data_mono   = time.monotonic()
            _stall_start_mono = None
            _tp_bytes         = 0
            _tp_session_start = time.monotonic()
            _tp_last_report   = time.monotonic()

            try:
                client.sendall(HTTP_HEADER)
            except OSError:
                _stream_log("CLIENT_DISCONNECT header_send_error")
                try:
                    client.close()
                except OSError:
                    pass
                client = None
                _stall_start_mono = None  # clear any active stall — session is over

        # ── Audio data from ffmpeg via stdin ──────────────────────────────────
        elif fd == stdin_fd:
            try:
                data = sys.stdin.buffer.read1(CHUNK)
            except OSError:
                data = b""
            if not data:
                # stdin closed — ffmpeg exited, pipeline is done
                _stream_log("STDIN_EOF pipeline_exited")
                raise SystemExit(0)

            now = time.monotonic()

            # Stall recovery: log STALL_END if we were in a stall
            if _stall_start_mono is not None:
                stall_ms = int((now - _stall_start_mono) * 1000)
                _stream_log(f"STALL_END {stall_ms}ms")
                _stall_start_mono = None
            _last_data_mono = now

            if client:
                try:
                    client.sendall(data)
                except OSError:
                    _stream_log("CLIENT_DISCONNECT send_error")
                    try:
                        client.close()
                    except OSError:
                        pass
                    client = None
                    _stall_start_mono = None  # clear any active stall — session is over

            # Throughput tracking — cumulative bytes and rate for this session.
            _tp_bytes += len(data)
            now2 = time.monotonic()
            if now2 - _tp_last_report >= THROUGHPUT_INTERVAL:
                elapsed = max(now2 - _tp_session_start, 0.001)
                bps     = int(_tp_bytes / elapsed)
                _stream_log(
                    f"THROUGHPUT bytes={_tp_bytes} rate={bps}bps elapsed={elapsed:.1f}s"
                )
                _tp_last_report = now2

            # Unconditional real-time rate limiter (cumulative).
            # Sleeps only the deficit so sendall() time counts toward pacing.
            _rate_bytes += len(data)
            expected = _rate_bytes / BYTES_PER_SEC
            deficit  = expected - (time.monotonic() - _rate_start)
            if deficit > 0:
                time.sleep(deficit)

    # ── Stall detection ───────────────────────────────────────────────────────
    # Only meaningful when a client is connected — no point logging stalls when
    # nobody is listening. Check after processing all readable fds so we don't
    # fire if stdin was readable this iteration.
    if client and stdin_fd not in readable:
        now      = time.monotonic()
        idle_ms  = (now - _last_data_mono) * 1000
        if idle_ms > STALL_THRESHOLD_MS and _stall_start_mono is None:
            _stall_start_mono = _last_data_mono
            _stream_log(f"STALL_START idle={idle_ms:.0f}ms")
