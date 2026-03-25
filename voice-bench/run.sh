#!/bin/bash
# voice-bench run script
# Creates / reuses a local venv, installs dependencies, then runs the daemon.

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

if [ ! -d "$VENV" ]; then
  echo "[voice-bench] Creating virtual environment…"
  python3 -m venv "$VENV"
fi

echo "[voice-bench] Installing / verifying dependencies…"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$DIR/requirements.txt"

echo "[voice-bench] Starting daemon…"
exec "$VENV/bin/python" "$DIR/voice_bench.py" "$@"
