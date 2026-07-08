#!/bin/bash
# ─────────────────────────────────────────────────────────────
# launchagent-watchdog.sh — re-bootstrap Naboo LaunchAgents that
# silently drop from launchd
#
# Context: the three librespot agents (go-librespot daemon, stream side,
# process watchdog) keep vanishing from launchd. launchctl load doesn't
# persist and launchctl enable didn't hold either — 5 recurrences through
# 2026-07-04 (TROUBLESHOOTING.md). The process-level watchdog (watchdog.sh,
# runs as com.librespot.naboo-watchdog) can't heal that outer failure when
# its own agent is the one that dropped.
#
# This runs from the HOST CRONTAB every 5 min (infra/crontab.txt) — cron
# has been drop-proof where launchd hasn't (camera-monitor watchdog
# pattern, zero drops since 2026-06-10). For each label missing from
# launchd it restores the plist from the repo if needed, then
# bootout/bootstrap/kickstart.
#
# Silent when all agents are registered; logs only actions and failures.
# Log: log/launchagent-watchdog.log
#
# Test the heal path safely (watchdog agent is idempotent):
#   launchctl bootout gui/$(id -u)/com.librespot.naboo-watchdog
#   ./launchagent-watchdog.sh
#   launchctl list | grep naboo-watchdog
# ─────────────────────────────────────────────────────────────

BASE_DIR="/Users/media/containers/home-automation/librespot"
LOG="${BASE_DIR}/log/launchagent-watchdog.log"
AGENT_DIR="/Users/media/Library/LaunchAgents"
uid=$(id -u)

LABELS="
com.go-librespot.naboo
com.naboo.stream
com.librespot.naboo-watchdog
"

mkdir -p "${BASE_DIR}/log"

for label in $LABELS; do
  # Registered with launchd? `print` fails when the label is unknown to the
  # GUI domain — catches both "never loaded" and "silently dropped".
  launchctl print "gui/${uid}/${label}" >/dev/null 2>&1 && continue

  ts=$(date '+%Y-%m-%d %H:%M:%S %Z')
  plist="${AGENT_DIR}/${label}.plist"

  # Installed plist gone entirely — restore from the repo copy.
  if [ ! -f "$plist" ]; then
    if cp "${BASE_DIR}/${label}.plist" "$plist" 2>/dev/null; then
      echo "[$ts] WATCHDOG ${label}: plist missing from ${AGENT_DIR} — restored from repo" >> "$LOG"
    else
      echo "[$ts] WATCHDOG ${label}: plist missing and repo copy unreadable — manual intervention needed" >> "$LOG"
      continue
    fi
  fi

  launchctl bootout "gui/${uid}/${label}" 2>/dev/null
  if launchctl bootstrap "gui/${uid}" "$plist" 2>>"$LOG"; then
    launchctl kickstart "gui/${uid}/${label}" 2>/dev/null
    echo "[$ts] WATCHDOG ${label}: not registered — bootstrapped + kickstarted" >> "$LOG"
  else
    echo "[$ts] WATCHDOG ${label}: bootstrap FAILED — manual intervention needed" >> "$LOG"
  fi
done
