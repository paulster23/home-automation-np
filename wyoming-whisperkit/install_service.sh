#!/bin/bash
# Install wyoming-whisperkit as a macOS LaunchAgent.
# Run once from the wyoming-whisperkit/ directory.
set -euo pipefail

PLIST_NAME="com.wyoming.whisperkit.plist"
PLIST_SRC="$(pwd)/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

if [ ! -f "$PLIST_SRC" ]; then
  echo "ERROR: $PLIST_SRC not found.  Run this script from the wyoming-whisperkit/ directory."
  exit 1
fi

mkdir -p log

cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"
echo "✓ wyoming-whisperkit installed and started."
echo "  Logs: $(pwd)/log/whisper.log"
echo "  Port: tcp://0.0.0.0:7892"
echo ""
echo "To point HA at it, update the Wyoming integration host/port to 192.168.1.70:7892"
echo "  Settings → Integrations → Wyoming Protocol → (edit existing or add new)"
