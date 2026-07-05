#!/bin/bash
# Play a random college-radio station from radio-browser.
DIR="$(cd "$(dirname "$0")" && pwd)"
# Last-run log: lets Claude diagnose button presses by reading the file.
{
  echo "=== $(date) invoked-as=$0 user=$(whoami) ==="
  /opt/homebrew/bin/python3.11 "$DIR/college_radio.py"
  echo "exit: $?"
} > "$DIR/college_radio.last.log" 2>&1
