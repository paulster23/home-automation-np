#!/usr/bin/env python3
"""
go-librespot event handler — polls REST API, fires HA webhooks.
Replaces on_event.sh for go-librespot (which has no --onevent hook).

State machine:
  playing  → send librespot_playing (unless already playing — track skip)
  paused   → debounce 3s → send librespot_stopped
  stopped  → debounce 5s → send librespot_stopped
  (same logic as on_event.sh; debounce absorbs skip/transition noise)

API: GET localhost:3678/status  (go-librespot has no GET /player — see api-spec.yml)
  { "paused": bool, "stopped": bool, ... }
  If stopped=true → stopped; paused=true → paused; else → playing.
"""
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

HA_URL = "http://192.168.1.71:8123"
API_URL = "http://localhost:3678/status"
ROOT_URL = "http://localhost:3678/"  # reachability check — responds even with no session
BASE_DIR = Path.home() / "containers/home-automation/librespot"
LOG_FILE = BASE_DIR / "log/events.log"
STATE_FILE = BASE_DIR / "log/.librespot_state"

PLAYING_WEBHOOK = "librespot_playing"
STOPPED_WEBHOOK = "librespot_stopped"
PAUSE_DEBOUNCE_S = 3
STOP_DEBOUNCE_S = 5
POLL_INTERVAL_S = 1.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{ts} PLAYER_EVENT={msg}\n")
    except OSError:
        pass


def send_webhook(name: str) -> None:
    subprocess.run(
        ["curl", "-s", "-m", "5", "-X", "POST",
         f"{HA_URL}/api/webhook/{name}",
         "-H", "Content-Type: application/json", "-d", "{}"],
        capture_output=True,
    )
    log(f"webhook sent: {name}")


def read_saved_state() -> str:
    try:
        return STATE_FILE.read_text().strip()
    except OSError:
        return "stopped"


def write_state(state: str) -> None:
    try:
        STATE_FILE.write_text(state)
    except OSError:
        pass


def poll_api() -> Optional[str]:
    """Return 'playing', 'paused', or 'stopped'; None if API unreachable."""
    try:
        with urlopen(API_URL, timeout=2) as r:
            data = json.loads(r.read())
        if data.get("stopped", False):
            return "stopped"
        if data.get("paused", False):
            return "paused"
        # Fallback: string state field (alternate API shape)
        s = str(data.get("state", ""))
        if s in ("stopped", "paused"):
            return s
        # If no track loaded at all, treat as stopped
        if not data.get("track") and not data.get("uri"):
            return "stopped"
        return "playing"
    except (URLError, OSError, json.JSONDecodeError):
        return None


# ── Debounce timer ────────────────────────────────────────────────────────────

class Debounce:
    def __init__(self):
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def schedule(self, delay: float, fn):
        self.cancel()
        with self._lock:
            self._timer = threading.Timer(delay, fn)
            self._timer.daemon = True
            self._timer.start()


_debounce = Debounce()


def _fire_stopped():
    log(f"→ notifying HA: {STOPPED_WEBHOOK}")
    send_webhook(STOPPED_WEBHOOK)


# ── State machine ─────────────────────────────────────────────────────────────

def on_state_change(new: str, prev: str) -> None:
    if new == "playing":
        _debounce.cancel()
        write_state("playing")
        if prev == "playing":
            log("→ track change (stream live, skipping webhook)")
        else:
            log(f"→ notifying HA: {PLAYING_WEBHOOK}")
            send_webhook(PLAYING_WEBHOOK)

    elif new == "paused":
        write_state("paused")
        log(f"→ paused, debouncing {PAUSE_DEBOUNCE_S}s")
        _debounce.schedule(PAUSE_DEBOUNCE_S, _fire_stopped)

    elif new == "stopped":
        write_state("stopped")
        log(f"→ stopped, debouncing {STOP_DEBOUNCE_S}s")
        _debounce.schedule(STOP_DEBOUNCE_S, _fire_stopped)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    log("go-event started")
    prev = read_saved_state()

    # Wait for the API server to come up (go-librespot starts alongside us).
    # Use GET / — /status may not answer until a Spotify session exists, so a
    # failed /status is NOT fatal; we just keep polling in the main loop.
    for _ in range(30):
        try:
            with urlopen(ROOT_URL, timeout=2) as r:
                r.read()
            log(f"API ready (initial saved state: {prev})")
            break
        except (URLError, OSError):
            time.sleep(1)
    else:
        log("API root not reachable after 30s — continuing to poll anyway")

    while True:
        time.sleep(POLL_INTERVAL_S)
        cur = poll_api()
        if cur is None:
            continue
        if cur != prev:
            log(f"state {prev} → {cur}")
            on_state_change(cur, prev)
            prev = cur


if __name__ == "__main__":
    main()
