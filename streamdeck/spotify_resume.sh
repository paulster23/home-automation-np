#!/bin/bash
# Play Spotify radio seeded from your most recently played track.
DIR="$(cd "$(dirname "$0")" && pwd)"
/opt/homebrew/bin/python3.11 "$DIR/spotify_resume.py"
