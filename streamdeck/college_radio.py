#!/usr/bin/env python3
"""Play a random college-radio station from the radio-browser feed.

Fetches https://de1.api.radio-browser.info/json/stations/bytag/college, filters
to working MP3/AAC streams, turns on the speaker, and plays a random one on Naboo
(the HA Voice PE). Each run picks a fresh random station and avoids replaying the
one that played last time. Stdlib only.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

# radio-browser mirrors flap (transient 503s) — try several, with a retry each.
FEED_PATH = "/json/stations/bytag/college"
MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
    "https://fi1.api.radio-browser.info",
]
FETCH_ATTEMPTS_PER_MIRROR = 2
HA_ENV = os.path.expanduser("~/containers/home-automation/secrets/ha.env")
LAST_FILE = os.path.expanduser("~/.streamdeck_college_last")
MEDIA_PLAYER = "media_player.home_assistant_voice_0a3a76_media_player"
SPEAKER_SWITCH = "switch.speaker"
OK_CODECS = {"MP3", "AAC", "AAC+"}
MAX_PLAY_ATTEMPTS = 3


def load_ha_env():
    """Parse simple KEY=VALUE lines from ha.env (the .py runs outside a shell)."""
    env = {}
    with open(HA_ENV) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    url, token = env.get("HA_URL"), env.get("HA_TOKEN")
    if not url or not token:
        sys.exit("ERROR: HA_URL/HA_TOKEN missing from %s" % HA_ENV)
    return url.rstrip("/"), token


def fetch_stations():
    """Try each mirror (with one retry) until one returns the feed."""
    last_err = None
    for base in MIRRORS:
        for attempt in range(FETCH_ATTEMPTS_PER_MIRROR):
            req = urllib.request.Request(
                base + FEED_PATH,
                headers={"User-Agent": "streamdeck-college-radio/1.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.loads(r.read())
            except Exception as e:
                last_err = "%s: %s" % (base, e)
                print("fetch failed (%s, attempt %d): %s"
                      % (base, attempt + 1, e), file=sys.stderr)
                time.sleep(1)
    raise RuntimeError("all mirrors failed; last error: %s" % last_err)


def ha_post(ha_url, token, service, payload):
    """POST a service call. Returns HTTP status code (raises on connection error)."""
    req = urllib.request.Request(
        "%s/api/services/%s" % (ha_url, service),
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    ha_url, token = load_ha_env()

    try:
        stations = fetch_stations()
    except Exception as e:
        sys.exit("ERROR: could not fetch radio-browser feed: %s" % e)

    candidates = [
        s
        for s in stations
        if s.get("lastcheckok") == 1
        and s.get("url_resolved")
        and (s.get("codec") or "").upper() in OK_CODECS
    ]
    print("feed returned %d stations, %d working MP3/AAC candidates"
          % (len(stations), len(candidates)))
    if not candidates:
        sys.exit("ERROR: no working MP3/AAC college stations in feed")

    # Avoid replaying the station from the previous press, if we have alternatives.
    last_uuid = ""
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE) as f:
            last_uuid = f.read().strip()
    pool = [s for s in candidates if s.get("stationuuid") != last_uuid] or candidates

    # Turn the speaker on first so audio is audible the moment the stream starts.
    ha_post(ha_url, token, "switch/turn_on", {"entity_id": SPEAKER_SWITCH})

    random.shuffle(pool)
    for station in pool[:MAX_PLAY_ATTEMPTS]:
        name = station.get("name", "?").strip()
        url = station["url_resolved"]
        status = ha_post(
            ha_url,
            token,
            "media_player/play_media",
            {
                "entity_id": MEDIA_PLAYER,
                "media_content_id": url,
                "media_content_type": "music",
            },
        )
        if status == 200:
            with open(LAST_FILE, "w") as f:
                f.write(station.get("stationuuid", ""))
            print("PLAYING: %s\n%s" % (name, url))
            return
        print("play_media returned HTTP %s for %s; trying next" % (status, name),
              file=sys.stderr)

    sys.exit("ERROR: all %d play attempts failed" % min(MAX_PLAY_ATTEMPTS, len(pool)))


if __name__ == "__main__":
    main()
