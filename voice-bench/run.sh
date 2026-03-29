#!/bin/bash
# voice-bench run script
# Creates / reuses a local venv, installs dependencies, then runs the daemon.

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

if [ ! -f "$VENV/bin/python" ]; then
  echo "[voice-bench] Creating virtual environment…"
  python3 -m venv "$VENV"
  echo "[voice-bench] Installing dependencies…"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$DIR/requirements.txt"
else
  # venv already exists — skip pip to keep startup fast and avoid port race
  echo "[voice-bench] venv ready, skipping pip."
fi

echo "[voice-bench] Starting daemon…"
exec "$VENV/bin/python" "$DIR/voice_bench.py" "$@"
