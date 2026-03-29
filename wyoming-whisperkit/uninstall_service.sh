#!/bin/bash
# Uninstall wyoming-whisperkit LaunchAgent.
set -euo pipefail

PLIST_DST="$HOME/Library/LaunchAgents/com.wyoming.whisperkit.plist"

if [ -f "$PLIST_DST" ]; then
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  rm "$PLIST_DST"
  echo "✓ wyoming-whisperkit uninstalled."
else
  echo "com.wyoming.whisperkit.plist not found in LaunchAgents — nothing to do."
fi
