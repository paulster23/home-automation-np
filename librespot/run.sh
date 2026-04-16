#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# librespot runner — registers "Naboo" as a Spotify Connect device,
# encodes audio to MP3, and serves it via HTTP on port 8765.
#
# Architecture:
#   librespot (PCM) | ffmpeg (encode MP3) | serve_http.py (HTTP server)
#
# serve_http.py binds port 8765 immediately on startup and stays bound.
# It uses select() to handle both stdin (audio) and new HTTP connections
# simultaneously — no chicken-and-egg blocking issue.
#
# When librespot exits, ffmpeg gets SIGPIPE, serve_http.py gets EOF on stdin
# and exits cleanly. The LaunchAgent (KeepAlive) restarts the whole pipeline.
#
# Logs: ~/containers/home-automation/librespot/log/
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BASE_DIR="$HOME/containers/home-automation/librespot"
LOG_DIR="$BASE_DIR/log"
mkdir -p "$LOG_DIR"

LIBRESPOT="/opt/homebrew/bin/librespot"
FFMPEG="/opt/homebrew/bin/ffmpeg"
PYTHON="/usr/bin/python3"

# Guard against stale FIFO from failed architecture attempts or reboots that
# don't clear /tmp. ffmpeg refuses to overwrite an existing file at its output
# path, so any leftover FIFO causes an immediate crash loop.
rm -f /tmp/librespot.fifo

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") Starting librespot pipeline" >> "$LOG_DIR/run.log"

exec "$LIBRESPOT" \
  --name "Naboo" \
  --device-type speaker \
  --bitrate 320 \
  --backend pipe \
  --format S16 \
  --onevent "$BASE_DIR/on_event.sh" \
  --disable-audio-cache \
  --cache "$HOME/.config/librespot" \
  --initial-volume 100 \
  2>>"$LOG_DIR/librespot.err" \
| "$FFMPEG" \
  -re \
  -hide_banner -loglevel error \
  -f s16le -ar 44100 -ac 2 \
  -i pipe:0 \
  -f mp3 -b:a 192k \
  pipe:1 \
  2>>"$LOG_DIR/stream.err" \
| "$PYTHON" "$BASE_DIR/serve_http.py" \
  >> "$LOG_DIR/http.log" 2>&1
