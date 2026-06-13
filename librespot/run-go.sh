#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Naboo stream side — JOB 2 of 2 (label: com.naboo.stream).
#
# Runs the long-lived consumer of go-librespot's PCM FIFO:
#   serve_http.py — owns the :8765 HTTP listener, holds the FIFO open (keepalive
#                   writer), and supervises ffmpeg (FIFO PCM → MP3) internally.
#   go-event.py   — polls go-librespot's HTTP API (localhost:3678/status) and
#                   fires HA webhooks (stream start + amp unmute).
#
# go-librespot itself runs in the SEPARATE job com.go-librespot.naboo
# (run-naboo.sh). That decoupling is the fix for the 2026-06-13 storm: a dropped
# HTTP client or a Spotify playback transfer no longer tears down go-librespot
# or the :8765 listener — only the transient FIFO writer (go-librespot session)
# comes and goes, and the FIFO holder inside serve_http.py absorbs that.
#
# Restart safety: launchd ThrottleInterval=30 in com.naboo.stream.plist PLUS the
#   rate guard below. serve_http.py respawns a crashed ffmpeg internally (also
#   throttled) WITHOUT exiting, so in steady state this job effectively never
#   restarts.
#
# Logs (same names as before for log-tailer compatibility):
#   log/http.log    — serve_http.py output
#   log/stream.err  — ffmpeg errors (written by serve_http.py)
#   log/events.log  — go-event.py webhook events
#   log/stream.log  — serve_http.py stream health (STALL_START etc.)
#   log/run.log     — this script's start/stop events
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail   # NOT -e: no fragile multi-member audio pipe here anymore.

BASE_DIR="$HOME/containers/home-automation/librespot"
LOG_DIR="$BASE_DIR/log"
FIFO="$LOG_DIR/naboo.pcm.fifo"
PYTHON="/usr/bin/python3"
SERVE_PORT="${SERVE_PORT:-8765}"
mkdir -p "$LOG_DIR"

# ── Rate guard (req #4 safety net, belt-and-suspenders with ThrottleInterval) ──
GUARD="$LOG_DIR/.stream_last_start"
MIN_INTERVAL=30
now=$(date +%s)
last=$(cat "$GUARD" 2>/dev/null || echo 0)
delta=$(( now - last ))
if [ "$last" -gt 0 ] && [ "$delta" -ge 0 ] && [ "$delta" -lt "$MIN_INTERVAL" ]; then
  wait_s=$(( MIN_INTERVAL - delta ))
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [stream] rate guard: started ${delta}s ago, sleeping ${wait_s}s" >> "$LOG_DIR/run.log"
  sleep "$wait_s"
fi
date +%s > "$GUARD"

# Ensure the FIFO exists (go-librespot side also ensures it; first-up wins).
if [ ! -p "$FIFO" ]; then
  rm -f "$FIFO"
  mkfifo "$FIFO"
fi

# Release port 8765 from any stale serve_http (e.g. a previous instance that
# launchd has not fully reaped). Only ours — serve_http binds it.
lsof -ti :"$SERVE_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") Starting Naboo stream side (serve_http :$SERVE_PORT + ffmpeg + go-event)" >> "$LOG_DIR/run.log"

# Event handler in background; kill it when this script exits.
"$PYTHON" "$BASE_DIR/go-event.py" >> "$LOG_DIR/events.log" 2>&1 &
EVENT_PID=$!
trap 'kill "$EVENT_PID" 2>/dev/null || true' EXIT

# serve_http.py is the foreground long-lived process: it binds :8765, holds the
# FIFO open, and spawns/supervises ffmpeg internally. It does NOT exit on a
# dropped client, zero consumers, or a transient FIFO-writer close; it only
# exits on its own fatal error, at which point launchd (throttled) restarts us.
SERVE_PORT="$SERVE_PORT" PCM_FIFO="$FIFO" "$PYTHON" "$BASE_DIR/serve_http.py" \
  >> "$LOG_DIR/http.log" 2>&1

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") Stream side exited" >> "$LOG_DIR/run.log"
