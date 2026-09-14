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
elif cmp -s frigate/config.np.yml frigate/config.yml; then
  say "   config.yml already matches config.np.yml byte for byte, nothing to do"
else
  if [ -f frigate/config.yml ]; then
    BK="frigate/config.bk-$(date +%Y%m%d-%H%M%S).yml"
    cp frigate/config.yml "$BK"
    say "   backed up the existing config.yml to $BK"
  fi
  cp frigate/config.np.yml frigate/config.yml
  say "   copied config.np.yml over config.yml"
fi

say "== 4. what config.yml actually asks for =="
if grep -qE "^[^#]*type:[[:space:]]*zmq" frigate/config.yml; then
  say "   live detector is zmq, correct for the M1"
else
  say "   ERROR: config.yml has no live zmq detector line"
  FAIL=1
fi
if grep -qE "^[^#]*(openvino|preset-vaapi|/dev/dri)" frigate/config.yml; then
  say "   ERROR: config.yml still carries woodhull hardware (openvino / vaapi / dri)"
  grep -nE "^[^#]*(openvino|preset-vaapi|/dev/dri)" frigate/config.yml | sed 's/^/     /'
  FAIL=1
else
  say "   no openvino, vaapi or /dev/dri left in config.yml"
fi

say "== 5. detector preflight =="
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

say "== 6. merged compose, reads only =="
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
say "Start only these services:"
say "   cd ~/containers/home-automation"
say "   docker compose up -d mosquitto homeassistant   # live since 2026-09-14"
say "   docker compose up -d frigate                   # once a camera is mounted"
say ""
say "Do NOT run a bare docker compose up. It would also start whisper,"
say "which the M1 replaces with native wyoming-whisperkit."
say ""
say "NOTE: homeassistant IS ours now. New Paltz runs its own autonomous"
say "instance so freeze protection survives a WAN outage. It is NOT a copy"
say "of Brooklyn - see homeassistant/configuration.np.yml."
