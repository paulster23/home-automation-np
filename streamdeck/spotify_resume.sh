#!/bin/bash
# Play Spotify radio seeded from your most recently played track.
DIR="$(cd "$(dirname "$0")" && pwd)"
# Last-run log: lets Claude diagnose button presses by reading the file.
{
  echo "=== $(date) invoked-as=$0 user=$(whoami) ==="
  /opt/homebrew/bin/python3.11 "$DIR/spotify_resume.py"
  echo "exit: $?"
} > "$DIR/spotify_resume.last.log" 2>&1
