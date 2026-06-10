#!/bin/bash
# librespot_heal.sh — Kill librespot so the watchdog restarts it fresh.

PID=$(pgrep -f "librespot" | head -1)

if [ -z "$PID" ]; then
    echo "librespot not running — nothing to restart"
    exit 1
fi

echo "Killing librespot (PID $PID)..."
kill "$PID"

# Wait for watchdog to bring it back as a new PID
for i in $(seq 1 20); do
    sleep 1
    NEW_PID=$(pgrep -f "librespot" | head -1)
    if [ -n "$NEW_PID" ] && [ "$NEW_PID" != "$PID" ]; then
        echo "librespot restarted (PID $NEW_PID) after ${i}s"
        exit 0
    fi
done

echo "ERROR: librespot did not restart within 20s"
exit 1
