#!/usr/bin/env python3
"""
Re-auth with explicit playlist scopes using the music-assistant.io redirect URI.
When the browser lands on music-assistant.io (page won't load), copy the full URL
from the address bar and paste it back here.
"""
import json, os, re, base64, urllib.parse, urllib.request, webbrowser

REDIRECT_URI  = "https://music-assistant.io/callback"
SCOPE         = "playlist-modify-public playlist-modify-private user-read-private"
ENV_FILE      = os.path.expanduser("~/containers/home-automation/secrets/spotify.env")

# Load credentials from secrets/spotify.env (never hardcode here)
_env = {}
with open(ENV_FILE) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            _env[k.strip()] = v.strip()
CLIENT_ID     = _env["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = _env["SPOTIFY_CLIENT_SECRET"]

params = urllib.parse.urlencode({
    "client_id": CLIENT_ID, "response_type": "code",
    "redirect_uri": REDIRECT_URI, "scope": SCOPE,
})
webbrowser.open(f"https://accounts.spotify.com/authorize?{params}")
print("Browser opened. After you click Agree, your browser will land on music-assistant.io")
print("The page won't load — that's fine. Copy the full URL from the address bar.\n")

raw = input("Paste URL: ").strip()
match = re.search(r"[?&]code=([^&]+)", raw)
if not match:
    print("ERROR: no 'code' found in URL"); raise SystemExit(1)

data = urllib.parse.urlencode({
    "grant_type": "authorization_code", "code": match.group(1), "redirect_uri": REDIRECT_URI,
}).encode()
creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data,
    headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(req) as resp:
    tokens = json.loads(resp.read())

refresh_token = tokens.get("refresh_token")
if not refresh_token:
    print("ERROR:", tokens); raise SystemExit(1)

lines = []
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        lines = [l for l in f if not l.startswith("SPOTIFY_REFRESH_TOKEN=")]
lines.append(f"SPOTIFY_REFRESH_TOKEN={refresh_token}\n")
with open(ENV_FILE, "w") as f:
    f.writelines(lines)

print(f"\nDone! New refresh token written to {ENV_FILE}")
print(f"Token: {refresh_token}")
