#!/usr/bin/env python3
"""
spotify_auth.py — One-time OAuth flow to get a Spotify refresh token.

1. Opens the Spotify auth page in your browser.
2. You authorize the app.
3. You get redirected to https://localhost:8888/callback?code=XXXX
   (the page won't load — that's fine, just copy the full URL from the address bar)
4. Paste the URL here and the script writes the refresh token to ~/.streamdeck_env
"""

import json
import os
import re
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_URI  = "https://localhost:8888/callback"
SCOPE         = "user-read-recently-played"
ENV_FILE      = os.path.expanduser("~/.streamdeck_env")

# Client credentials come from ~/.streamdeck_env — never hardcode them here.
def _env(key):
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"')
    return input(f"{key} not found in {ENV_FILE} — paste it: ").strip()

CLIENT_ID     = _env("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = _env("SPOTIFY_CLIENT_SECRET")

# Build auth URL
params = urllib.parse.urlencode({
    "client_id":     CLIENT_ID,
    "response_type": "code",
    "redirect_uri":  REDIRECT_URI,
    "scope":         SCOPE,
})
auth_url = f"https://accounts.spotify.com/authorize?{params}"

print("Opening Spotify authorization in your browser...")
webbrowser.open(auth_url)
print()
print("After you click Agree, your browser will land on a page that won't load.")
print("Copy the full URL from the address bar and paste it here.")
print()

raw = input("Paste URL: ").strip()

# Extract code
match = re.search(r"[?&]code=([^&]+)", raw)
if not match:
    print("ERROR: No 'code' found in that URL.")
    raise SystemExit(1)
code = match.group(1)

# Exchange code for tokens
data = urllib.parse.urlencode({
    "grant_type":   "authorization_code",
    "code":         code,
    "redirect_uri": REDIRECT_URI,
}).encode()

import base64
credentials = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
req = urllib.request.Request(
    "https://accounts.spotify.com/api/token",
    data=data,
    headers={
        "Authorization": f"Basic {credentials}",
        "Content-Type":  "application/x-www-form-urlencoded",
    },
)

with urllib.request.urlopen(req) as resp:
    tokens = json.loads(resp.read())

refresh_token = tokens.get("refresh_token")
if not refresh_token:
    print("ERROR: No refresh token in response:", tokens)
    raise SystemExit(1)

# Write to ~/.streamdeck_env
lines = []
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        lines = [l for l in f.readlines() if not l.startswith("SPOTIFY_REFRESH_TOKEN=")
                                           and not l.startswith("SPOTIFY_CLIENT_ID=")
                                           and not l.startswith("SPOTIFY_CLIENT_SECRET=")]

lines += [
    f"SPOTIFY_CLIENT_ID={CLIENT_ID}\n",
    f"SPOTIFY_CLIENT_SECRET={CLIENT_SECRET}\n",
    f"SPOTIFY_REFRESH_TOKEN={refresh_token}\n",
]

with open(ENV_FILE, "w") as f:
    f.writelines(lines)

print()
print("Done! Refresh token written to ~/.streamdeck_env")
