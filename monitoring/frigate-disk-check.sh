#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Frigate Disk Usage Monitor
# Warns when recording storage exceeds thresholds
# Run via cron (daily at 6am): add to crontab with:
#   0 6 * * * cd ~/home-automation && ./monitoring/frigate-disk-check.sh >> /tmp/frigate-disk.log 2>&1
# ═══════════════════════════════════════════════════════════════

FRIGATE_PATH="$HOME/home-automation/frigate/storage"
WARN_PERCENT=75    # Warn at 75% full
CRIT_PERCENT=90    # Critical at 90% full
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Get disk usage stats
USED=$(df -h "$FRIGATE_PATH" 2>/dev/null | tail -1 | awk '{print $3}')
TOTAL=$(df -h "$FRIGATE_PATH" 2>/dev/null | tail -1 | awk '{print $2}')
PERCENT=$(df "$FRIGATE_PATH" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
FRIGATE_SIZE=$(du -sh "$FRIGATE_PATH" 2>/dev/null | awk '{print $1}')

if [ -z "$PERCENT" ]; then
    echo "[$TIMESTAMP] ERROR: Cannot read disk stats for $FRIGATE_PATH"
    exit 1
fi

if [ "$PERCENT" -ge "$CRIT_PERCENT" ]; then
    echo "[$TIMESTAMP] CRITICAL: Disk ${PERCENT}% full — Frigate storage: $FRIGATE_SIZE used of $TOTAL ($USED used)"
    echo "[$TIMESTAMP] ACTION: Reduce Frigate retention or free disk space immediately"
    exit 2
elif [ "$PERCENT" -ge "$WARN_PERCENT" ]; then
    echo "[$TIMESTAMP] WARNING: Disk ${PERCENT}% full — Frigate storage: $FRIGATE_SIZE used of $TOTAL ($USED used)"
    echo "[$TIMESTAMP] ACTION: Consider reducing Frigate retention days"
    exit 1
else
    echo "[$TIMESTAMP] OK: Disk ${PERCENT}% full — Frigate storage: $FRIGATE_SIZE used of $TOTAL ($USED used)"
    exit 0
fi
