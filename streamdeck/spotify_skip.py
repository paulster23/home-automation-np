#!/usr/bin/env python3
"""Skip to the next track via Spotify API."""

import base64
import json
import os
import time
import urllib.parse
import urllib.request

# ── Load env ──────────────────────────────────────────────────────────────────
env = {}
with open(os.path.expanduser("~/.streamdeck_env")) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

SPOTIFY_CLIENT_ID     = env["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = env["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_REFRESH_TOKEN = env["SPOTIFY_REFRESH_TOKEN"]
HA_URL                = env["HA_URL"]
HA_TOKEN              = env["HA_TOKEN"]

# ── Refresh access token ──────────────────────────────────────────────────────
creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
data = urllib.parse.urlencode({
    "grant_type":    "refresh_token",
    "refresh_token": SPOTIFY_REFRESH_TOKEN,
}).encode()
req = urllib.request.Request(
    "https://accounts.spotify.com/api/token",
    data=data,
    headers={
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/x-www-form-urlencoded",
    },
)
with urllib.request.urlopen(req) as r:
    access_token = json.loads(r.read())["access_token"]

# ── Skip ──────────────────────────────────────────────────────────────────────
NABOO_DEVICE_ID = "0596f720dd52a9e2e2d0020d00931a1b91014e64"

req = urllib.request.Request(
    f"https://api.spotify.com/v1/me/player/next?device_id={NABOO_DEVICE_ID}",
    data=b"",
    headers={"Authorization": f"Bearer {access_token}"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    pass  # 204 No Content on success

time.sleep(1)

# ── Resume via HA ─────────────────────────────────────────────────────────────
data = json.dumps({"entity_id": "media_player.spotify_paulster23"}).encode()
req = urllib.request.Request(
    f"{HA_URL}/api/services/media_player/media_play",
    data=data,
    headers={
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type":  "application/json",
    },
)
with urllib.request.urlopen(req) as r:
    pass

print("Skipped and playing.")
