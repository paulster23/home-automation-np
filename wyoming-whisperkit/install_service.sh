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
echo "RETIRED 2026-08-31: WhisperKit (CoreML/ANE, Mac-only) was replaced by the"
echo "wyoming-whisper container on woodhull. Do NOT point HA at 192.168.1.70:7892 —"  # host-audit:ok — retirement notice, not a live target
echo "that host is powered down. Kept for reference only; see home-automation/CONTEXT.md."
echo "  Settings → Integrations → Wyoming Protocol → (edit existing or add new)"
