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
GO_LABEL="com.go-librespot.naboo"   # JOB 1: go-librespot daemon (run-naboo.sh)
STREAM_LABEL="com.naboo.stream"     # JOB 2: serve_http + ffmpeg (run-go.sh)

log() {
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [watchdog] $*" >> "$LOG"
}

# Kickstart a specific launchd job. -k forces an immediate restart regardless of
# the job's ThrottleInterval; safe here because the watchdog only runs every 5
# minutes, so it can never itself cause a storm.
kick() {
  local label="$1" reason="$2"
  log "RESTARTING ${label} — ${reason}"
  launchctl kickstart -k "gui/$(id -u)/${label}" >> "$LOG" 2>&1
  log "kickstart ${label} issued"
}

# ── Check 0: one-shot force restart ──────────────────────────────────────────
# Touch $BASE_DIR/.force_restart to make the next watchdog run kickstart BOTH
# jobs (used for deploying script/config changes without host access).
if [ -f "$BASE_DIR/.force_restart" ]; then
  rm -f "$BASE_DIR/.force_restart"
  kick "$GO_LABEL" "force-restart flag found"
  kick "$STREAM_LABEL" "force-restart flag found"
  exit 0
fi

# ── Check 1: go-librespot daemon (JOB 1) ─────────────────────────────────────
# Match the invocation from run-naboo.sh. Restart JOB 1 only — the stream side
# is independent and the FIFO holder keeps it alive across go-librespot restarts.
PIDS=$(pgrep -f "go-librespot --config_dir" 2>/dev/null)
if [ -z "$PIDS" ]; then
  kick "$GO_LABEL" "go-librespot process not found"
  exit 0
fi

# ── Check 2: serve_http.py :8765 listener (JOB 2) ────────────────────────────
# serve_http.py binds :8765 on startup and holds it open permanently. Check the
# bound socket via lsof WITHOUT opening a TCP connection (it is single-client and
# a probe connection would evict ESPHome). Restart JOB 2 only.
if ! lsof -i "TCP:${STREAM_PORT}" -sTCP:LISTEN -t > /dev/null 2>&1; then
  kick "$STREAM_LABEL" "serve_http.py port ${STREAM_PORT} not listening"
  exit 0
fi

# ── Check 3: ffmpeg process (JOB 2) ──────────────────────────────────────────
# serve_http.py respawns a crashed ffmpeg in-process, but if it is wedged with no
# ffmpeg at all, restart JOB 2 to rebuild the holder + encoder cleanly.
FFMPEG_PIDS=$(pgrep -x ffmpeg 2>/dev/null)
if [ -z "$FFMPEG_PIDS" ]; then
  kick "$STREAM_LABEL" "ffmpeg process not found (encoder down)"
  exit 0
fi

# ── All checks passed ────────────────────────────────────────────────────────
log "OK — go-librespot (pids=${PIDS}) :${STREAM_PORT} listening ffmpeg (pids=${FFMPEG_PIDS})"
