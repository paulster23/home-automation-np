#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Home Automation Stack — Health Check Script
# Run manually: ./monitoring/health-check.sh
# Run via cron (every 5 min): add to crontab with:
#   */5 * * * * cd ~/home-automation && ./monitoring/health-check.sh >> /tmp/ha-health.log 2>&1
# ═══════════════════════════════════════════════════════════════

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
SERVICES=("mosquitto" "frigate" "homeassistant" "music-assistant" "whisper")
FAILED=()

echo ""
echo "═══ Health Check: $TIMESTAMP ═══"

# Check Docker daemon is accessible
if ! docker ps >/dev/null 2>&1; then
    echo "ERROR: Docker daemon not accessible"
    exit 1
fi

# ── Container Status ───────────────────────────────────────────
echo ""
echo "Containers:"
for service in "${SERVICES[@]}"; do
    STATUS=$(docker inspect "$service" --format='{{.State.Status}}' 2>/dev/null || echo "missing")
    HEALTH=$(docker inspect "$service" --format='{{.State.Health.Status}}' 2>/dev/null || echo "none")

    if [ "$STATUS" == "running" ]; then
        if [ "$HEALTH" == "healthy" ] || [ "$HEALTH" == "none" ]; then
            printf "  ✓ %-20s running" "$service"
            [ "$HEALTH" != "none" ] && printf " (%s)" "$HEALTH"
            echo ""
        else
            printf "  ⚠ %-20s running but %s\n" "$service" "$HEALTH"
            FAILED+=("$service (unhealthy)")
        fi
    else
        printf "  ✗ %-20s %s\n" "$service" "$STATUS"
        FAILED+=("$service ($STATUS)")
    fi
done

# ── Memory Usage ───────────────────────────────────────────────
echo ""
echo "Memory:"
docker stats --no-stream --format "  {{.Name}}: {{.MemUsage}} ({{.MemPerc}})" 2>/dev/null | \
    grep -E "mosquitto|frigate|homeassistant|music-assistant|whisper" || echo "  (could not read stats)"

# ── Frigate Storage ────────────────────────────────────────────
echo ""
echo "Frigate storage:"
FRIGATE_SIZE=$(docker exec frigate du -sh /media/frigate 2>/dev/null | awk '{print $1}' || echo "N/A")
DISK_AVAIL=$(df -h ~/home-automation/frigate/storage 2>/dev/null | tail -1 | awk '{print $4}' || echo "N/A")
echo "  Used: $FRIGATE_SIZE | Available: $DISK_AVAIL"

# ── HA Database Size ───────────────────────────────────────────
echo ""
echo "HA database:"
HA_DB=$(du -sh ~/home-automation/homeassistant/home-assistant_v2.db 2>/dev/null | awk '{print $1}' || echo "N/A")
echo "  home-assistant_v2.db: $HA_DB"

# ── Summary ────────────────────────────────────────────────────
echo ""
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "✓ All services OK"
    exit 0
else
    echo "✗ Issues detected:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
