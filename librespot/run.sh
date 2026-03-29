#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# librespot runner — registers "Naboo" as a Spotify Connect device via Bonjour,
# streams audio out as an MP3 HTTP server on port 8765.
#
# Architecture:
#   librespot (pipe backend) → ffmpeg (encode + serve HTTP)
#
# When a Spotify client connects and plays:
#   1. librespot streams raw PCM to ffmpeg via stdin
#   2. ffmpeg encodes to MP3 and serves http://192.168.1.70:8765
#   3. on_event.sh fires PLAYER_EVENT=playing → HA webhook → naboo plays stream
#
# When playback stops or the HTTP client disconnects:
#   1. ffmpeg exits → SIGPIPE to librespot → pipeline exits
#   2. on_event.sh fires PLAYER_EVENT=stopped → HA webhook → naboo stops
#   3. LaunchAgent (KeepAlive) restarts the pipeline in a few seconds
#   4. "Naboo" re-announces via Bonjour; device reappears in Spotify app quickly
#
# Logs: ~/containers/home-automation/librespot/log/
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BASE_DIR="$HOME/containers/home-automation/librespot"
LOG_DIR="$BASE_DIR/log"
mkdir -p "$LOG_DIR"

LIBRESPOT="/opt/homebrew/bin/librespot"
FFMPEG="/opt/homebrew/bin/ffmpeg"

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") Starting librespot pipeline" >> "$LOG_DIR/run.log"

# Pipeline: librespot (PCM) → ffmpeg (encode MP3) → serve_http.py (HTTP server)
#
# serve_http.py always drains stdin even when no HTTP client is connected.
# This prevents the pipe from filling up and blocking librespot — the root
# cause of the "Naboo shows in Spotify but no audio" deadlock.
#
# ffmpeg flags:
#   -re                 read input at native frame rate (44.1 kHz = realtime).
#                       Without this, serve_http.py drains the pipe at max speed
#                       when no HTTP client is connected, which removes all
#                       backpressure and makes librespot race through tracks
#                       in seconds instead of minutes.
#   -f s16le            input format: signed 16-bit little-endian PCM
#   -ar 44100 -ac 2     44.1 kHz stereo (librespot default)
#   -b:a 192k           MP3 output bitrate
#   pipe:1              write encoded MP3 to stdout (serve_http.py reads it)

exec "$LIBRESPOT" \
  --name "Naboo" \
  --device-type speaker \
  --bitrate 320 \
  --backend pipe \
  --format S16 \
  --onevent "$BASE_DIR/on_event.sh" \
  --disable-audio-cache \
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
| python3 "$BASE_DIR/serve_http.py"
