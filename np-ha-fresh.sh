#!/bin/bash
# np-ha-fresh.sh — stage a FRESH New Paltz Home Assistant config dir.
#
# Per plans/NP_IMPLEMENTATION_PLAN.md §4.2: "Fresh HA instance — do NOT restore
# BK's backup (entity/IP soup)." The existing homeassistant/ dir is a clone of
# Brooklyn carried over in the move; it is ARCHIVED, never deleted, so rollback
# stays one mv away.
#
# Idempotent: refuses to run twice rather than clobbering a live config.
# Starts no containers.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

STAMP="20260914"
ARCHIVE="homeassistant.bk-clone-${STAMP}"
FAIL=0
say() { printf '%s\n' "$*"; }

say "== 0. preconditions =="
if [ -d "$ARCHIVE" ]; then
  say "   ERROR: $ARCHIVE already exists — this script has already run."
  say "   Refusing to run again. Inspect by hand."
  exit 1
fi
if [ ! -d homeassistant ]; then
  say "   ERROR: no homeassistant/ directory to archive"
  exit 1
fi
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx homeassistant; then
  say "   ERROR: the homeassistant container is RUNNING. Stop it first:"
  say "       docker compose stop homeassistant"
  exit 1
fi
say "   ok — homeassistant/ present, container not running, no prior archive"

say "== 1. clear any stale git index.lock (bridge leaves these) =="
if [ -f .git/index.lock ]; then
  rm -f .git/index.lock && say "   removed .git/index.lock"
else
  say "   none present"
fi

say "== 2. archive the Brooklyn clone =="
mv homeassistant "$ARCHIVE" || { say "   ERROR: mv failed"; exit 1; }
say "   homeassistant/ -> $ARCHIVE  ($(du -sh "$ARCHIVE" 2>/dev/null | cut -f1))"

say "== 3. restore the git-tracked shared building blocks =="
mkdir -p homeassistant
git checkout -- homeassistant/ 2>/dev/null
RESTORED=$(git ls-files homeassistant/ | wc -l | tr -d ' ')
PRESENT=$(git ls-files homeassistant/ | while read -r f; do [ -f "$f" ] && echo "$f"; done | wc -l | tr -d ' ')
say "   tracked files: $RESTORED   restored to disk: $PRESENT"
[ "$RESTORED" = "$PRESENT" ] || { say "   ERROR: not all tracked files came back"; FAIL=1; }

say "== 4. drop Brooklyn-only custom_components from the FRESH dir =="
# spotify_voice_assistant and windmillac are Brooklyn integrations. They are
# tracked, so they came back in step 3; move them into the archive rather than
# leaving manifest-less dirs for HA to warn about on every start.
for cc in spotify_voice_assistant windmillac; do
  if [ -d "homeassistant/custom_components/$cc" ]; then
    mkdir -p "$ARCHIVE/_readded_custom_components"
    mv "homeassistant/custom_components/$cc" "$ARCHIVE/_readded_custom_components/$cc"
    say "   moved custom_components/$cc into the archive (Brooklyn-only)"
  fi
done
rmdir homeassistant/custom_components 2>/dev/null && say "   removed empty custom_components/"

say "== 5. write configuration.np.yml =="
cat > homeassistant/configuration.np.yml <<'CFGEOF'
# ═══════════════════════════════════════════════════════════════
# New Paltz — Home Assistant site configuration
#
# This is the TRACKED source of truth for NP. configuration.yaml is a
# copy of it and is deliberately divergent from Brooklyn's — the same
# pattern frigate/config.np.yml uses, for the same reason: one file
# cannot describe two houses, and the live copy must never be committed
# over the other site's.
#
# Deliberately NOT carried over from Brooklyn:
#   spotify_voice_assistant / intent_script  — BK voice stack
#   shell_command.playball                   — points at 192.168.1.70
#   input_boolean voice helpers, timer       — BK voice pipeline
#   custom_components (windmillac, HACS)     — no HACS at NP
#   frontend.themes                          — no themes dir here
#
# No http: block. HA 2026.7+ migrates http: config into .storage/http on
# first boot and IGNORES YAML on every boot after, and leaving the block
# present also raises a Repair issue. See TROUBLESHOOTING.md 2026-09-03
# for the 400 Bad Request incident this caused at Brooklyn.
# ═══════════════════════════════════════════════════════════════

# Brings in frontend, history, logbook, mobile_app, zeroconf, ssdp,
# dhcp discovery, backup, and the rest of the standard set.
default_config:

automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml

conversation:

logger:
  default: info

# ── Database housekeeping ─────────────────────────────────────
# 14 days rather than Brooklyn's 30. This instance tracks a handful of
# climate entities and one camera, and it lives on the M1's 460 GB boot
# disk inside a 4.1 GB Docker VM — keep the DB small on purpose.
recorder:
  purge_keep_days: 14
  commit_interval: 1
CFGEOF
cp homeassistant/configuration.np.yml homeassistant/configuration.yaml
say "   wrote configuration.np.yml and copied it to configuration.yaml"

say "== 6. empty the include targets =="
printf '%s\n' "# New Paltz automations. HVAC automations land here once the" \
              "# Serin CN105 dongles are adopted. Empty list until then." "[]" \
  > homeassistant/automations.yaml
printf '%s\n' "# New Paltz scripts." "{}" > homeassistant/scripts.yaml
printf '%s\n' "# New Paltz scenes." "[]" > homeassistant/scenes.yaml
say "   automations.yaml / scripts.yaml / scenes.yaml reset to empty"

say "== 7. minimal secrets.yaml =="
if [ ! -f homeassistant/secrets.yaml ]; then
  printf '%s\n' "# New Paltz secrets. Nothing referenced yet." > homeassistant/secrets.yaml
  say "   created"
else
  say "   already present, left alone"
fi

say "== 8. assert the result, don't assume it =="
for f in configuration.yaml configuration.np.yml automations.yaml scripts.yaml scenes.yaml; do
  [ -f "homeassistant/$f" ] && say "   present: $f" || { say "   MISSING: $f"; FAIL=1; }
done
if cmp -s homeassistant/configuration.np.yml homeassistant/configuration.yaml; then
  say "   configuration.yaml matches configuration.np.yml byte for byte"
else
  say "   ERROR: configuration.yaml does not match configuration.np.yml"; FAIL=1
fi
if grep -qE "^[^#]*(spotify_voice_assistant|shell_command|intent_script|192\.168\.1\.)" homeassistant/configuration.yaml; then
  say "   ERROR: Brooklyn config survived into configuration.yaml:"
  grep -nE "^[^#]*(spotify_voice_assistant|shell_command|intent_script|192\.168\.1\.)" homeassistant/configuration.yaml | sed 's/^/     /'
  FAIL=1
else
  say "   no Brooklyn integrations or 192.168.1.x addresses in configuration.yaml"
fi
if [ -f "homeassistant/custom_sentences/en/music.yaml" ]; then
  say "   custom_sentences restored ($(ls homeassistant/custom_sentences/en | wc -l | tr -d ' ') files)"
else
  say "   WARNING: custom_sentences missing"
fi
say "   archive retained: $ARCHIVE"

say ""
if [ "$FAIL" -eq 0 ]; then
  say "ALL CHECKS PASSED. Fresh NP config staged, Brooklyn clone archived."
else
  say "SOME CHECKS FAILED, see above. Roll back with:"
  say "   rm -rf homeassistant && mv $ARCHIVE homeassistant"
fi
say ""
say "Next:  docker compose up -d mosquitto homeassistant"
