#!/usr/bin/env bash
# patch_hacs.sh — Reapplies the HACS startup-timeout patch before HA starts.
#
# Problem: HACS self-updates overwrite custom_components/hacs/base.py, losing
# the asyncio.wait_for() wrapper that prevents DNS failures from blocking HA
# startup indefinitely.
#
# This script is called by the homeassistant container's entrypoint override in
# docker-compose.yml before /init runs. It re-checks and reapplies the patch on
# every container start so the fix survives HACS updates automatically.
#
# See: home-automation/homeassistant/scripts/patch_hacs.py for patch logic.
# Added 2026-04-30.

set -eo pipefail

BASE_PY="/config/custom_components/hacs/base.py"
MARKER="asyncio.wait_for(self.async_load_hacs_from_github(), timeout=30)"

if [ ! -f "$BASE_PY" ]; then
    echo "[patch_hacs] base.py not found — HACS not installed, nothing to patch"
    exit 0
fi

if grep -qF "$MARKER" "$BASE_PY"; then
    echo "[patch_hacs] patch present — nothing to do"
    exit 0
fi

echo "[patch_hacs] patch missing (HACS likely updated itself) — reapplying..."
python3 /config/scripts/patch_hacs.py || {
    echo "[patch_hacs] WARNING: patcher failed — HA will start without the patch"
    exit 0  # Never block HA startup
}
