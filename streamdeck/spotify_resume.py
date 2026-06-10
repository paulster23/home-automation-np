#!/usr/bin/env python3
"""
spotify_resume.py — Cycle through top artists and play a Deezer-seeded radio on Naboo.

Plays the seed track immediately while building the playlist in a background
thread. Once the playlist is ready, replaces the queue seamlessly by resuming
the seed track from its current position.
"""

import base64
import concurrent.futures
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

HISTORY_SIZE  = 50
IDX_FILE      = os.path.expanduser("~/.streamdeck_spotify_idx")
NABOO_NAME    = "Naboo"

# ── Load env ──────────────────────────────────────────────────────────────────
env = {}
with open(os.path.expanduser("~/.streamdeck_env")) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

HA_URL                = env["HA_URL"]
HA_TOKEN              = env["HA_TOKEN"]
SPOTIFY_CLIENT_ID     = env["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = env["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_REFRESH_TOKEN = env["SPOTIFY_REFRESH_TOKEN"]


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "streamdeck/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def spotify_search_track(title, artist, token):
    q = urllib.parse.quote(f"{title} {artist}")
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/search?q={q}&type=track&limit=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            hits = json.loads(r.read()).get("tracks", {}).get("items", [])
            return hits[0]["uri"] if hits else None
    except Exception:
        return None


def ha_get(path):
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        headers={"Authorization": f"Bearer {HA_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def ha_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=data,
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get_device_id(token, name):
    """Return the Spotify device ID for the named device, or None if not found."""
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        devices = json.loads(r.read()).get("devices", [])
    for d in devices:
        if d["name"] == name:
            return d["id"]
    return None


def spotify_transfer_to_naboo(token, device_id):
    """Activate Naboo as the target device without starting playback."""
    body = json.dumps({"device_ids": [device_id], "play": False}).encode()
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            pass
        return True
    except Exception:
        return False


def spotify_put_play(uris, token, device_id, offset_uri=None, position_ms=None):
    """PUT /me/player/play. Returns True on success, False on non-retryable error,
    raises urllib.error.HTTPError with reason NO_ACTIVE_DEVICE when device is absent."""
    body = {"uris": uris, "device_id": device_id}
    if offset_uri:
        body["offset"] = {"uri": offset_uri}
    if position_ms is not None:
        body["position_ms"] = position_ms
    play_data = json.dumps(body).encode()
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player/play",
        data=play_data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        pass
    return True


def try_play(uris, token, device_id, retries=8, delay=2, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            spotify_put_play(uris, token, device_id, **kwargs)
            print(f"Playback started (attempt {attempt}).")
            return True
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 404 and "NO_ACTIVE_DEVICE" in body:
                print(f"Attempt {attempt}: device not ready, retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"Spotify play error {e.code}: {body}", file=sys.stderr)
                return False
    print("ERROR: Naboo never became active after retries.", file=sys.stderr)
    return False


# ── 1. Refresh Spotify access token ──────────────────────────────────────────
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

# ── 1b. Resolve Naboo's current device ID ─────────────────────────────────────
naboo_device_id = get_device_id(access_token, NABOO_NAME)
if naboo_device_id is None:
    print(f"ERROR: '{NABOO_NAME}' not visible to Spotify — is librespot running?", file=sys.stderr)
    print("Run: open /Users/media/streamdeck/librespot_heal.app", file=sys.stderr)
    sys.exit(1)

# ── 2. Fetch Spotify top tracks, dedupe by artist ─────────────────────────────
req = urllib.request.Request(
    f"https://api.spotify.com/v1/me/top/tracks?time_range=medium_term&limit={HISTORY_SIZE}",
    headers={"Authorization": f"Bearer {access_token}"},
)
with urllib.request.urlopen(req, timeout=10) as r:
    items = json.loads(r.read()).get("items", [])

if not items:
    print("ERROR: No top tracks found.", file=sys.stderr)
    sys.exit(1)

seen, tracks = set(), []
for t in items:
    aid = t["artists"][0]["id"]
    if aid not in seen:
        seen.add(aid)
        tracks.append(t)

# ── 3. Read and advance index ─────────────────────────────────────────────────
try:
    idx = int(open(IDX_FILE).read().strip())
except (FileNotFoundError, ValueError):
    idx = 0

idx = idx % len(tracks)
track = tracks[idx]
with open(IDX_FILE, "w") as f:
    f.write(str((idx + 1) % len(tracks)))

artist     = track["artists"][0]["name"]
track_name = track["name"]
seed_uri   = track["uri"]
print(f"[{idx + 1}/{len(tracks)}] Seeding from: {artist} — {track_name}")

# ── 4. Turn on speaker; kick off playlist build in background ─────────────────
speaker = ha_get("/api/states/switch.speaker").get("state")
if speaker != "on":
    print("Speaker was off — turning on.")
    ha_post("/api/services/switch/turn_on", {"entity_id": "switch.speaker"})

playlist_uris  = []
playlist_error = [None]

def build_playlist():
    q = urllib.parse.quote(artist)
    try:
        deezer_search = http_get(f"https://api.deezer.com/search/artist?q={q}&limit=5")
    except Exception as ex:
        playlist_error[0] = f"Deezer search failed: {ex}"
        return

    deezer_id = None
    for da in deezer_search.get("data", []):
        if da.get("name", "").lower() == artist.lower():
            deezer_id = da["id"]
            break

    if not deezer_id:
        playlist_error[0] = f"'{artist}' not found on Deezer"
        return

    try:
        radio = http_get(f"https://api.deezer.com/artist/{deezer_id}/radio?limit=25")
    except Exception as ex:
        playlist_error[0] = f"Deezer radio failed: {ex}"
        return

    deezer_tracks = radio.get("data", [])
    if not deezer_tracks:
        playlist_error[0] = "No Deezer radio tracks"
        return

    print(f"Got {len(deezer_tracks)} Deezer tracks — matching to Spotify...")

    def match_track(dt):
        return spotify_search_track(
            dt.get("title", ""), dt.get("artist", {}).get("name", ""), access_token
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(match_track, deezer_tracks))

    matched = [uri for uri in results if uri and uri != seed_uri]
    playlist_uris.extend(matched)
    print(f"Playlist ready: {len(matched)} tracks.")

playlist_ready = threading.Event()

_orig_build = build_playlist
def build_playlist():
    _orig_build()
    playlist_ready.set()

playlist_thread = threading.Thread(target=build_playlist, daemon=True)
playlist_thread.start()

# ── 5. Play as soon as device is ready; use full list if playlist already built ─
def try_play_smart(retries=8, delay=2):
    """
    Each retry checks whether the playlist is ready.
    If so, plays the full URI list directly — no second PUT, no stutter.
    """
    for attempt in range(1, retries + 1):
        if playlist_ready.is_set() and playlist_uris:
            uris = [seed_uri] + playlist_uris
            label = f"full list ({len(uris)} tracks)"
        else:
            uris = [seed_uri]
            label = "seed only"
        try:
            spotify_put_play(uris, access_token, naboo_device_id)
            print(f"Playback started (attempt {attempt}, {label}).")
            return uris
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code == 404 and "NO_ACTIVE_DEVICE" in body:
                print(f"Attempt {attempt}: device not ready — transferring to Naboo...")
                spotify_transfer_to_naboo(access_token, naboo_device_id)
                time.sleep(1)
            else:
                print(f"Spotify play error {e.code}: {body}", file=sys.stderr)
                return None
    # Dump available devices to help diagnose
    try:
        req = urllib.request.Request(
            "https://api.spotify.com/v1/me/player/devices",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            devices = json.loads(r.read()).get("devices", [])
        if devices:
            print("Devices Spotify can see:", file=sys.stderr)
            for d in devices:
                print(f"  {d['id']} — {d['name']} ({d['type']}, active={d['is_active']})", file=sys.stderr)
        else:
            print("No devices visible to Spotify at all.", file=sys.stderr)
    except Exception as ex:
        print(f"Could not fetch devices: {ex}", file=sys.stderr)
    print("ERROR: Naboo never became active after retries.", file=sys.stderr)
    return None

played_uris = try_play_smart()
if played_uris is None:
    sys.exit(1)

# ── 6. If we only played the seed, wait for playlist then replace seamlessly ───
if played_uris == [seed_uri]:
    playlist_thread.join(timeout=60)

    if playlist_error[0]:
        print(f"Playlist build failed: {playlist_error[0]} — seed track only.")
        sys.exit(0)

    if not playlist_uris:
        print("No tracks matched — seed track only.")
        sys.exit(0)

    # Get current position to avoid restarting the seed
    position_ms = 0
    try:
        req = urllib.request.Request(
            "https://api.spotify.com/v1/me/player",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            state = json.loads(r.read())
        position_ms = state.get("progress_ms", 0)
        print(f"Resuming seed at {position_ms}ms.")
    except Exception:
        pass

    all_uris = [seed_uri] + playlist_uris
    try:
        spotify_put_play(all_uris, access_token, naboo_device_id, offset_uri=seed_uri, position_ms=position_ms)
        print(f"Queue replaced: {len(all_uris)} tracks for {artist}.")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Queue replace error {e.code}: {body}", file=sys.stderr)
else:
    print(f"Playing {len(played_uris)} tracks for {artist}.")
