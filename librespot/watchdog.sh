#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# librespot watchdog — ensures "Naboo" stays alive and registered.
#
# Checks every 5 minutes (via LaunchAgent StartInterval):
#   1. librespot process is running
#   2. HTTP stream on port 8765 responds within 3s
#
# If either check fails, forces a full restart via launchctl kickstart.
# The LaunchAgent's KeepAlive will then restart the process.
#
# Why not check the Spotify device API?
#   Spotify's /me/player/devices has up to 60s propagation lag — a device can
#   appear "missing" from the API while librespot is running fine, causing
#   spurious restarts. Process + port checks are instant and authoritative.
#
# Why kickstart instead of kill?
#   launchctl kickstart forces launchd to restart the job cleanly, resetting
#   the backoff timer if it hit a crash loop. `kill` alone would restart it
#   too, but kickstart is the correct launchd idiom.
#
# Logs: ~/containers/home-automation/librespot/log/watchdog.log
# Install: see com.librespot.naboo-watchdog.plist
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR="$HOME/containers/home-automation/librespot"
LOG="$BASE_DIR/log/watchdog.log"
STREAM_PORT=8765
LABEL="com.librespot.naboo"

log() {
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [watchdog] $*" >> "$LOG"
}

restart_librespot() {
  log "RESTARTING librespot — $1"
  # kickstart forces an immediate restart regardless of throttle state
  launchctl kickstart -k "gui/$(id -u)/${LABEL}" >> "$LOG" 2>&1
  log "kickstart issued"
}

# ── Check 1: process ─────────────────────────────────────────────────────────
PIDS=$(pgrep -x librespot 2>/dev/null)
if [ -z "$PIDS" ]; then
  restart_librespot "librespot process not found"
  exit 0
fi

# ── Check 2: serve_http.py port is listening ─────────────────────────────────
# serve_http.py binds port 8765 on startup and holds it open permanently.
# nc -z connects and immediately closes — serve_http accepts but doesn't
# send anything until it has audio data, so the probe is harmless.
if ! nc -z -w 2 127.0.0.1 "${STREAM_PORT}" 2>/dev/null; then
  restart_librespot "serve_http.py port ${STREAM_PORT} not listening"
  exit 0
fi

# ── Check 3: ffmpeg process is running ───────────────────────────────────────
# serve_http.py can stay alive with port 8765 open even after ffmpeg dies
# (broken pipe from the librespot stdout → ffmpeg → serve_http chain).
# The watchdog previously passed in this state, leaving MA connected to a
# silent stream. Check that at least one ffmpeg process exists.
FFMPEG_PIDS=$(pgrep -x ffmpeg 2>/dev/null)
if [ -z "$FFMPEG_PIDS" ]; then
  restart_librespot "ffmpeg process not found (pipe broken)"
  exit 0
fi

# ── All checks passed ────────────────────────────────────────────────────────
log "OK — librespot running (pids=${PIDS}) port ${STREAM_PORT} open ffmpeg running (pids=${FFMPEG_PIDS})"
