#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# go-librespot runner (Naboo) — JOB 1 of 2.
#
# Runs ONLY go-librespot. It registers "Naboo" as a Spotify Connect device and
# writes raw PCM to a named FIFO (log/naboo.pcm.fifo) whenever a Spotify session
# is active. This process is long-lived and INDEPENDENT of the audio consumer:
# the device stays registered across playback stop / transfer / idle. The stream
# side (com.naboo.stream → run-go.sh → serve_http.py) holds the FIFO open and
# turns the PCM into the :8765 MP3 stream.
#
# Why split from the old single pipeline (run-go.sh, pre-2026-06-13):
#   The old chain  go-librespot | ffmpeg | serve_http  under one KeepAlive job
#   meant a dropped HTTP client or a Spotify transfer closed the pipe, ffmpeg
#   SIGPIPE'd, serve_http exited, `set -e` killed the script, and launchd
#   respawned the WHOLE thing ~15×/min — a storm that crashed Docker Desktop.
#   See TROUBLESHOOTING.md 2026-06-13.
#
# Restart safety: launchd ThrottleInterval=30 in com.go-librespot.naboo.plist
#   PLUS the rate guard below — a failing start can never respawn faster than
#   once per 30s.
#
# Logs: log/librespot.log (go-librespot), log/run.log (start/stop events).
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail   # NOT -e: this script is a thin launcher, we manage failures.

BASE_DIR="$HOME/containers/home-automation/librespot"
LOG_DIR="$BASE_DIR/log"
CONFIG_DIR="$BASE_DIR/go-config"
FIFO="$LOG_DIR/naboo.pcm.fifo"
mkdir -p "$LOG_DIR"

GO_LIBRESPOT="$(command -v go-librespot)"

# ── Rate guard (req #4 safety net, belt-and-suspenders with ThrottleInterval) ──
# Never let this job effectively (re)start faster than once per MIN_INTERVAL.
GUARD="$LOG_DIR/.golibre_last_start"
MIN_INTERVAL=30
now=$(date +%s)
last=$(cat "$GUARD" 2>/dev/null || echo 0)
delta=$(( now - last ))
if [ "$last" -gt 0 ] && [ "$delta" -ge 0 ] && [ "$delta" -lt "$MIN_INTERVAL" ]; then
  wait_s=$(( MIN_INTERVAL - delta ))
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") [go-librespot] rate guard: started ${delta}s ago, sleeping ${wait_s}s" >> "$LOG_DIR/run.log"
  sleep "$wait_s"
fi
date +%s > "$GUARD"

# Ensure the FIFO exists (consumer side also ensures it; first-up wins).
if [ ! -p "$FIFO" ]; then
  rm -f "$FIFO"
  mkfifo "$FIFO"
fi

echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") Starting go-librespot (Naboo) → FIFO" >> "$LOG_DIR/run.log"

# exec so launchd supervises go-librespot directly (clean signal delivery).
exec "$GO_LIBRESPOT" --config_dir "$CONFIG_DIR" 2>>"$LOG_DIR/librespot.log"
