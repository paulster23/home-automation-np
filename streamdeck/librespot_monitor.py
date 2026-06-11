#!/usr/bin/env python3
"""
librespot_monitor.py — Health check for librespot / Naboo.

Detects when librespot is running but Spotify can't see Naboo as a device
(the degraded state that causes 10-15s lag on button press), and restarts it.

Designed to run on a schedule every 5 minutes via a scheduled task.
"""

import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

NABOO_NAME  = "Naboo"
HEAL_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "librespot_heal.sh")

# ── Load env ──────────────────────────────────────────────────────────────────
env = {}
with open(os.path.expanduser("~/containers/home-automation/secrets/spotify.env")) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

SPOTIFY_CLIENT_ID     = env["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = env["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_REFRESH_TOKEN = env["SPOTIFY_REFRESH_TOKEN"]


def log(msg):
    print(msg, flush=True)


# ── 1. Is librespot even running? ─────────────────────────────────────────────
result = subprocess.run(["pgrep", "-f", "librespot"], capture_output=True, text=True)
librespot_pid = result.stdout.strip().split("\n")[0] if result.returncode == 0 else None

if not librespot_pid:
    log("librespot not running — watchdog should handle this. Exiting.")
    sys.exit(0)

log(f"librespot running (PID {librespot_pid})")

# ── 2. Refresh Spotify token ──────────────────────────────────────────────────
try:
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "refresh_token": SPOTIFY_REFRESH_TOKEN,
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        access_token = json.loads(r.read())["access_token"]
except Exception as ex:
    log(f"Could not refresh Spotify token: {ex} — skipping check.")
    sys.exit(0)

# ── 3. Check if Naboo is visible as a Spotify device ─────────────────────────
try:
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player/devices",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        devices = json.loads(r.read()).get("devices", [])
except Exception as ex:
    log(f"Could not fetch Spotify devices: {ex} — skipping check.")
    sys.exit(0)

naboo_device = next((d for d in devices if d["name"] == NABOO_NAME), None)
naboo_visible = naboo_device is not None
naboo_device_id = naboo_device["id"] if naboo_device else None

if naboo_visible:
    log("Naboo visible to Spotify — healthy, nothing to do.")
    sys.exit(0)

# ── 4. Check if music is currently playing (don't interrupt active playback) ──
try:
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
    state = json.loads(raw) if raw else {}
    is_playing = state.get("is_playing", False)
    playing_device = (state.get("device") or {}).get("id", "")
except Exception:
    is_playing = False
    playing_device = ""

if is_playing and playing_device == naboo_device_id:
    log("Music is actively playing on Naboo — skipping restart to avoid interruption.")
    sys.exit(0)

# ── 5. Degraded: librespot running but Spotify can't see it — restart ─────────
log("DEGRADED: librespot running but not visible to Spotify. Restarting...")
result = subprocess.run(["bash", HEAL_SCRIPT], capture_output=True, text=True)
log(result.stdout.strip())
if result.returncode != 0:
    log(f"Heal script failed: {result.stderr.strip()}")
    sys.exit(1)

log("Heal complete — librespot should be fresh for next button press.")
