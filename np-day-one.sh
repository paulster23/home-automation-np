#!/bin/bash
# Staging for New Paltz day one. Run on the Mac (media), at NP, before any
# docker compose up. Idempotent: safe to run twice. Writes nothing outside
# this directory and starts no containers.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

FAIL=0
say() { printf '%s\n' "$*"; }

say "== 1. compose override symlink =="
if [ -L docker-compose.override.yml ]; then
  say "   already linked -> $(readlink docker-compose.override.yml)"
elif [ -e docker-compose.override.yml ]; then
  say "   ERROR: docker-compose.override.yml exists and is not a symlink"
  FAIL=1
else
  ln -s overrides/np.yml docker-compose.override.yml
  say "   created docker-compose.override.yml -> overrides/np.yml"
fi

say "== 2. .env =="
if [ -f .env ]; then
  say "   .env already exists, leaving it alone:"
  sed 's/^/     /' .env
else
  printf 'HOST_IP=192.168.2.70\nFRIGATE_MEDIA=./frigate/storage\n' > .env
  say "   wrote .env  HOST_IP=192.168.2.70  FRIGATE_MEDIA=./frigate/storage"
fi

say "== 3. frigate config =="
if [ ! -f frigate/config.np.yml ]; then
  say "   MISSING frigate/config.np.yml"
  FAIL=1
elif grep -q "apple-silicon" frigate/config.yml 2>/dev/null; then
  say "   config.yml is already the NP config, not overwriting"
else
  if [ -f frigate/config.yml ]; then
    cp frigate/config.yml "frigate/config.bk-$(date +%Y%m%d-%H%M%S).yml"
    say "   backed up Brooklyn config.yml alongside it"
  fi
  cp frigate/config.np.yml frigate/config.yml
  say "   config.yml is now the NP apple-silicon config"
fi

say "== 4. detector preflight =="
if [ -f frigate/model_cache/yolo.onnx ]; then
  say "   yolo.onnx present, $(wc -c < frigate/model_cache/yolo.onnx | tr -d ' ') bytes"
else
  say "   MISSING frigate/model_cache/yolo.onnx, the ZMQ detector has no model"
  FAIL=1
fi
if [ -d /Applications/FrigateDetector.app ]; then
  say "   FrigateDetector.app present"
else
  say "   MISSING /Applications/FrigateDetector.app"
  FAIL=1
fi
if pgrep -f FrigateDetector >/dev/null 2>&1; then
  say "   FrigateDetector is running"
else
  say "   FrigateDetector is NOT running, open it before starting Frigate"
  FAIL=1
fi
if nc -z 127.0.0.1 5555 >/dev/null 2>&1; then
  say "   detector listening on 127.0.0.1:5555"
else
  say "   nothing listening on 127.0.0.1:5555"
  FAIL=1
fi

say "== 5. merged compose, reads only =="
if docker compose config >/dev/null 2>&1; then
  say "   docker compose config parses OK"
  if docker compose config 2>/dev/null | grep -q "/dev/dri"; then
    say "   ERROR: /dev/dri survived into the merged config, the reset tag did not apply"
    FAIL=1
  else
    say "   /dev/dri absent from merged config, the reset tag worked"
  fi
else
  say "   docker compose config FAILED, run it by hand to see why"
  FAIL=1
fi

say ""
if [ "$FAIL" -eq 0 ]; then
  say "ALL CHECKS PASSED."
else
  say "SOME CHECKS FAILED, see above."
fi
say ""
say "Start only these two services:"
say "   cd ~/containers/home-automation"
say "   docker compose up -d mosquitto frigate"
say ""
say "Do NOT run a bare docker compose up. It would also start homeassistant,"
say "which woodhull owns, and whisper, which the M1 replaces with native"
say "wyoming-whisperkit."
