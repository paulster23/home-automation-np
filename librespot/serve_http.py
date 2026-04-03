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
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(1)
srv.setblocking(False)

client = None
stdin_fd = sys.stdin.buffer.fileno()

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
