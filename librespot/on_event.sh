#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# librespot event handler — called by librespot's --onevent on playback events.
#
# Environment variables from librespot:
#   PLAYER_EVENT  — playing | paused | stopped | changed | preloading | ...
#   TRACK_ID      — Spotify track URI (when applicable)
#
# This script notifies HA via local webhooks, which trigger automations
# to play/stop the HTTP stream on naboo (the Voice PE).
#
# KEY DESIGN: the HTTP stream (serve_http.py) stays connected across track
# changes. We only send librespot_playing on FIRST play or resume-after-pause
# and librespot_stopped on REAL pauses/stops (not track skips).
#
# Race-condition handling: paused/stopped handlers sleep before sending the
# stop webhook. The playing handler kills any sleeping debounce process via
# PID file, so a quick paused→playing sequence (track skip) never reaches HA.
#
# Webhooks have no auth (HA is not internet-exposed).
# Connect via the Mac host's LAN IP so Docker's port-mapping routes it in.
# HA will see the request from the Docker bridge IP (not loopback), which is
# why automations.yaml sets local_only: false on both librespot webhook triggers.
# ─────────────────────────────────────────────────────────────────────────────
HA_URL="http://192.168.1.70:8123"
BASE_DIR="$HOME/containers/home-automation/librespot"
LOG="$BASE_DIR/log/events.log"
STATE_FILE="$BASE_DIR/log/.librespot_state"
DEBOUNCE_PID_FILE="$BASE_DIR/log/.debounce_pid"

log() {
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") PLAYER_EVENT=$PLAYER_EVENT ${1:-}" >> "$LOG"
}

send_webhook() {
  curl -s -m 5 -X POST \
    "${HA_URL}/api/webhook/$1" \
    -H "Content-Type: application/json" \
    -d '{}' >> "$LOG" 2>&1
}

kill_debounce() {
  local pid
  pid=$(cat "$DEBOUNCE_PID_FILE" 2>/dev/null)
  if [ -n "$pid" ]; then
    kill "$pid" 2>/dev/null
    rm -f "$DEBOUNCE_PID_FILE"
  fi
}

case "$PLAYER_EVENT" in

  playing)
    # Kill any sleeping paused/stopped debounce handler before it fires.
    kill_debounce

    PREV_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo "stopped")
    echo "playing" > "$STATE_FILE"

    if [ "$PREV_STATE" = "playing" ]; then
      # Stream is already connected — this is a track change. Do nothing.
      log "→ track change (stream connected, skipping webhook)"
    else
      # First play or resume after real pause/stop — connect naboo.
      log "→ notifying HA: librespot_playing"
      send_webhook "librespot_playing"
    fi
    ;;

  paused)
    echo "paused" > "$STATE_FILE"
    echo $$ > "$DEBOUNCE_PID_FILE"
    trap 'rm -f "$DEBOUNCE_PID_FILE"' EXIT

    # Debounce: track skips fire paused→playing within ~1s.
    # Real user pauses stay paused. Wait 3s to tell them apart.
    log "→ paused, debouncing (3s)"
    sleep 3

    # If a playing event killed us during the sleep, we never reach here.
    # If we're still alive, this is a real pause.
    log "→ notifying HA: librespot_stopped (paused)"
    send_webhook "librespot_stopped"
    ;;

  stopped)
    echo "stopped" > "$STATE_FILE"
    echo $$ > "$DEBOUNCE_PID_FILE"
    trap 'rm -f "$DEBOUNCE_PID_FILE"' EXIT

    # Debounce: librespot fires stopped→playing on some transitions.
    # Wait 5s — if a playing event arrives, it kills us before we fire.
    log "→ stopped, debouncing (5s)"
    sleep 5

    log "→ notifying HA: librespot_stopped"
    send_webhook "librespot_stopped"
    ;;

  session_connected|session_disconnected)
    # New Spotify session — reset state so the next "playing" event fires the
    # webhook instead of assuming the stream is still alive from a prior session.
    echo "stopped" > "$STATE_FILE"
    log "→ reset state to stopped (new session)"
    ;;

  end_of_track)
    # Natural track completion — the next play_request_id_changed is a skip,
    # not a fresh voice-initiated play. Leave a flag so we can tell them apart.
    touch "$BASE_DIR/log/.end_of_track_flag"
    log "→ end_of_track (flagged for next play_request_id_changed)"
    ;;

  play_request_id_changed)
    # Fires on BOTH:
    #   (a) voice-triggered plays via spotify_voice_assistant (Spotify Web API),
    #       which bypass session_connected — we need to reset state here so the
    #       next "playing" event reconnects naboo.
    #   (b) natural track advances (end_of_track → play_request_id_changed).
    #       In this case we must NOT reset state or a post-stop auto-advance
    #       will re-trigger the librespot_playing webhook and restart the stream.
    #
    # Distinguish them via the end_of_track flag file.
    if [ -f "$BASE_DIR/log/.end_of_track_flag" ]; then
      rm -f "$BASE_DIR/log/.end_of_track_flag"
      log "→ play_request_id_changed after end_of_track (track skip, ignoring)"
    else
      echo "stopped" > "$STATE_FILE"
      log "→ reset state to stopped (fresh play request, no preceding end_of_track)"
    fi
    ;;

  # Ignore everything else (preloading, changed, volume_set, etc.)
  *)
    log "ignored"
    ;;

esac
