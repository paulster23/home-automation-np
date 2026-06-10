#!/bin/bash
# Skip to next track via Spotify API, then resume via HA
DIR="$(cd "$(dirname "$0")" && pwd)"
/opt/homebrew/bin/python3.11 "$DIR/spotify_skip.py"
