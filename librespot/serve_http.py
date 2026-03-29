#!/usr/bin/env python3
"""
Minimal HTTP streaming server for librespot audio.

Reads encoded MP3 bytes from stdin (piped from ffmpeg) and serves them to
a single HTTP client on port 8765.

Key property: stdin is ALWAYS drained, even when no client is connected.
This prevents the upstream ffmpeg→librespot pipeline from blocking on a
full pipe buffer — the root cause of the Naboo playback deadlock.

When a new HTTP client connects while one is already active, the old
connection is closed and the new one takes over (handles HA reconnects).

Exits when stdin closes (librespot/ffmpeg stopped) → LaunchAgent restarts.
"""
import socket
import sys

PORT = 8765
CHUNK = 8192
HTTP_HEADER = (
    b"HTTP/1.0 200 OK\r\n"
    b"Content-Type: audio/mpeg\r\n"
    b"Cache-Control: no-cache, no-store\r\n"
    b"Pragma: no-cache\r\n"
    b"\r\n"
)

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(1)
srv.setblocking(False)  # Non-blocking accept — never stall on waiting for clients

client = None

while True:
    # Always read stdin first — this is what keeps upstream from blocking.
    # When librespot is playing, ffmpeg produces ~24 KB/s of MP3 data.
    # When librespot is idle, ffmpeg produces nothing and read() blocks here
    # (which is fine — no audio to serve anyway).
    data = sys.stdin.buffer.read(CHUNK)
    if not data:
        break  # stdin closed → ffmpeg/librespot exited → exit cleanly

    # Accept any pending connection (non-blocking — returns immediately if none).
    try:
        conn, addr = srv.accept()
        # New client connected. Close the old one if present.
        if client:
            try:
                client.close()
            except OSError:
                pass
        client = conn
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client.sendall(HTTP_HEADER)
    except BlockingIOError:
        pass  # No pending connection — that's normal, keep draining stdin

    # Forward audio data to the connected client.
    if client:
        try:
            client.sendall(data)
        except OSError:
            # Client disconnected — stop sending, keep draining stdin.
            try:
                client.close()
            except OSError:
                pass
            client = None
    # If no client: data is silently discarded. Upstream never blocks.

# Clean up
if client:
    try:
        client.close()
    except OSError:
        pass
srv.close()
