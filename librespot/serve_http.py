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
  STALL_END <ms>ms silence=<n>     — audio resumed; n = silence bytes filled

Silence keepalive (2026-06-09, fixes "Naboo silent after heal")
───────────────────────────────────────────────────────────────
The Voice PE abandons HTTP streams that go dry for more than a few seconds;
the close is only visible on our next write (CLIENT_DISCONNECT send_error
right after STALL_END — see TODO.md / stream.log 2026-05-16, 05-19, 06-10).
While stdin is stalled and a client is connected, we feed valid silent MP3
frames (silence.mp3, generated with ffmpeg anullsrc) at the real-time rate,
so the client never sees a dry stream. Counting silence toward the rate
limiter also kills the unpaced catch-up burst that used to follow stalls.
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

# Silent MP3 payload for the stall keepalive (frame-stripped anullsrc output,
# loops cleanly). If the asset is missing we run without keepalive (old
# behavior) rather than failing the pipeline.
try:
    SILENCE = (Path(__file__).parent / "silence.mp3").read_bytes()
except OSError:
    SILENCE = b""

# Keepalive is for bridging TRANSIENT stalls (librespot heals, track changes,
# queue replaces) — not for holding an idle system "playing" forever. The
# stop/resilience automations can ping-pong the Voice PE onto a dead-idle
# stream; without a cap it would sit playing silence indefinitely and the
# amp premute automation (requires paused/idle) would never fire. After the
# cap we stop filling: the client starves, drops to idle, and the normal
# wind-down chain (premute etc.) takes over. A fresh play reconnects via the
# librespot_playing webhook automation regardless.
SILENCE_MAX_S = 45

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

# Silence keepalive state
_silence_off  = 0      # cycling read offset into SILENCE
_silence_sent = 0      # bytes of silence filled during the current stall
_cap_logged   = False  # SILENCE_CAP logged for the current stall

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
                _stream_log(f"STALL_END {stall_ms}ms silence={_silence_sent}")
                _stall_start_mono = None
                _silence_sent = 0
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

    # ── Stall detection + silence keepalive ───────────────────────────────────
    # Only meaningful when a client is connected — no point logging stalls when
    # nobody is listening. Check after processing all readable fds so we don't
    # fire if stdin was readable this iteration.
    if client and stdin_fd not in readable:
        now      = time.monotonic()
        idle_ms  = (now - _last_data_mono) * 1000
        if idle_ms > STALL_THRESHOLD_MS and _stall_start_mono is None:
            _stall_start_mono = _last_data_mono
            _silence_sent = 0
            _cap_logged = False
            _stream_log(f"STALL_START idle={idle_ms:.0f}ms")

        # While stalled, keep the client fed with silent MP3 frames at the
        # real-time rate. Bytes count toward the rate limiter so real audio
        # resumes without a catch-up burst and pacing stays continuous.
        if _stall_start_mono is not None and SILENCE:
            capped = (now - _stall_start_mono) > SILENCE_MAX_S
            if capped and not _cap_logged:
                _stream_log(f"SILENCE_CAP {SILENCE_MAX_S}s reached — letting client starve")
                _cap_logged = True
            while client and not capped:
                deficit = (_rate_bytes / BYTES_PER_SEC) - (time.monotonic() - _rate_start)
                if deficit > 0:
                    break  # at/ahead of real-time — fill more on a later pass
                chunk = SILENCE[_silence_off:_silence_off + CHUNK]
                if len(chunk) < CHUNK:
                    chunk += SILENCE[:CHUNK - len(chunk)]
                _silence_off = (_silence_off + CHUNK) % len(SILENCE)
                try:
                    client.sendall(chunk)
                except OSError:
                    _stream_log("CLIENT_DISCONNECT send_error_silence")
                    try:
                        client.close()
                    except OSError:
                        pass
                    client = None
                    _stall_start_mono = None
                    break
                _rate_bytes   += len(chunk)
                _silence_sent += len(chunk)
                _tp_bytes     += len(chunk)
