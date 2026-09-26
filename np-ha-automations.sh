#!/bin/bash
# Stage the New Paltz HVAC automations + the ntfy rest_command.
# Writes configuration.np.yml's notify block, automations.yaml and scripts.yaml,
# then validates with HA's own check_config before anything is reloaded.
set -uo pipefail
cd ~/containers/home-automation || exit 1
HA=homeassistant

# ── 1. append the rest_command block to configuration.np.yml (idempotent) ─────
if grep -q "^rest_command:" "$HA/configuration.np.yml"; then
  echo "rest_command block already present, leaving it"
else
cat >> "$HA/configuration.np.yml" <<'CFGEOF'

# ── Paging ────────────────────────────────────────────────────────
# ntfy lives on woodhull in BROOKLYN. Verified 2026-09-14 from inside
# this container: 192.168.1.71:8111 answers in ~56 ms — but woodhull's
# TAILNET address (100.103.72.117) does NOT resolve/connect from in here
# at all. The container can only use the LAN address, and that works
# solely because the Mac runs Tailscale with RouteAll: true.
#
# ⛔ `tailscale set --accept-routes=false` on this Mac SILENTLY kills New
#    Paltz's ability to page. That is Site Magic step 4 — do not run it
#    until a gateway tunnel is proven. See plans/ + project memory.
#
# Consequence to design around: if the INTER-SITE link is down, the page
# does not arrive. So every automation below acts on the hardware FIRST
# and notifies SECOND — a failed notify must never block the heat.
rest_command:
  ntfy:
    url: "http://192.168.1.71:8111/homelab"
    method: POST
    content_type: "text/plain; charset=utf-8"
    payload: "{{ message }}"
    timeout: 10
    headers:
      Title: "{{ title }}"
      Priority: "{{ priority | default('default') }}"
      Tags: "{{ tags | default('house') }}"
CFGEOF
echo "appended rest_command to configuration.np.yml"
fi
cp "$HA/configuration.np.yml" "$HA/configuration.yaml"

# ── 2. automations ───────────────────────────────────────────────────────────
cat > "$HA/automations.yaml" <<'AUTOEOF'
# New Paltz automations.
#
# ⚠️ The climate entities below DO NOT EXIST YET. They appear when the Serin
# CN105 dongles are flashed and adopted (reserved .81 / .82). Until then these
# automations load cleanly and simply never trigger — that is intentional, so
# the logic is written and reviewed in Brooklyn rather than on a ladder.
#
# Adding units 3-5 later: extend the entity_id lists in BOTH automations and
# both scripts. There are four lists; a grep for "climate.np_" finds them all.

- id: np_freeze_protection
  alias: "NP · Freeze protection"
  description: >-
    Any head unit reporting under 45 °F for 5 minutes puts every unit into heat
    at 55 °F, then pages. This is the one automation that must survive a WAN
    outage: the climate calls are local (ESPHome native API over the LAN) and
    run before the notify, so an unreachable ntfy cannot stop the heat.
    The 5-minute debounce rejects a single bad reading; a spurious trigger only
    turns the heat on, which is harmless, while a missed one is not.
  mode: single
  max_exceeded: silent
  triggers:
    - trigger: numeric_state
      entity_id:
        - climate.np_living
        - climate.np_kitchen
      attribute: current_temperature
      below: 45
      for: "00:05:00"
  actions:
    - action: climate.set_hvac_mode
      target:
        entity_id: &np_all_units
          - climate.np_living
          - climate.np_kitchen
      data:
        hvac_mode: heat
    - action: climate.set_temperature
      target:
        entity_id: *np_all_units
      data:
        temperature: 55
    - action: rest_command.ntfy
      data:
        title: "NP FREEZE RISK"
        priority: "urgent"
        tags: "rotating_light,snowflake"
        message: >-
          {{ trigger.to_state.name }} read
          {{ trigger.to_state.attributes.current_temperature }}°F.
          All New Paltz units forced to heat 55°F.

- id: np_climate_unavailable
  alias: "NP · Climate entity unavailable"
  description: >-
    A dongle that drops off Wi-Fi stops reporting temperature, which would make
    freeze protection silently blind — the trigger above can never fire on an
    entity that is 'unavailable'. This is the watchdog for that blind spot.
    30 minutes tolerates a reboot or a brief AP blip.
    TEMPORARY (2026-09-26, Paul): the kitchen dongle sits at ~-92 dBm and drops
    off several times a night, so it gets 2 h until the NP network upgrade. Put
    it back in the 30-minute list once the kitchen signal is fixed.
  mode: single
  triggers:
    - trigger: state
      entity_id:
        - climate.np_living
      to: "unavailable"
      for: "00:30:00"
    - trigger: state
      entity_id:
        - climate.np_kitchen
      to: "unavailable"
      for: "02:00:00"
  actions:
    - action: rest_command.ntfy
      data:
        title: "NP HVAC sensor offline"
        priority: "high"
        tags: "warning"
        message: >-
          {{ trigger.to_state.name }} has been unavailable for {{ trigger.for }} (h:mm:ss).
          Freeze protection cannot see this unit.

- id: np_kuma_heartbeat
  alias: "NP · Kuma heartbeat"
  description: >-
    Pushes to Uptime Kuma monitor 36 every 5 minutes so Brooklyn can tell a
    dead Home Assistant from a merely-quiet one. Kuma monitor 35 pings the
    Mac; it stays green while this container is stopped, crash-looping, or
    wedged — which is exactly when freeze protection is not running.
    Unconditional on purpose: it reports that HA is ALIVE, never whether HA
    is HAPPY. Gating it on the state of another automation would turn one
    alert into two meanings. The message body carries the freeze-protection
    state and the count of responding climate entities for context only.
    Also fires on HA start so the monitor recovers within seconds of a
    restart instead of waiting out the 5-minute cycle.
  mode: single
  max_exceeded: silent
  triggers:
    - trigger: time_pattern
      minutes: "/5"
    - trigger: homeassistant
      event: start
  actions:
    - action: rest_command.kuma_heartbeat
      data:
        msg: >-
          freeze={{ states('automation.np_freeze_protection') }}
          units={{ states.climate | rejectattr('state', 'in', ['unavailable', 'unknown']) | list | count }}
AUTOEOF

# ── 3. scripts ───────────────────────────────────────────────────────────────
cat > "$HA/scripts.yaml" <<'SCREOF'
# New Paltz scripts. Run from the HA companion app.

np_away:
  alias: "NP · Away"
  icon: mdi:home-export-outline
  description: >-
    Departure setback. Winter holds 52 °F, which is well clear of the 45 °F
    freeze trigger so the two never fight each other. Summer turns the units
    off outright. Month-based rather than a thermostat mode, because an empty
    house has nobody to flip it.
  mode: single
  sequence:
    - choose:
        - conditions:
            - condition: template
              value_template: "{{ now().month in [10, 11, 12, 1, 2, 3, 4] }}"
          sequence:
            - action: climate.set_hvac_mode
              target:
                entity_id: &np_units
                  - climate.np_living
                  - climate.np_kitchen
              data:
                hvac_mode: heat
            - action: climate.set_temperature
              target:
                entity_id: *np_units
              data:
                temperature: 52
      default:
        - action: climate.set_hvac_mode
          target:
            entity_id: *np_units
          data:
            hvac_mode: "off"
    - action: rest_command.ntfy
      data:
        title: "NP set to Away"
        priority: "low"
        tags: "house"
        message: >-
          {{ 'Winter setback, holding 52°F.' if now().month in [10,11,12,1,2,3,4]
             else 'Summer, units off.' }}

np_arrive:
  alias: "NP · Arriving"
  icon: mdi:home-import-outline
  description: >-
    Pre-condition before a drive up. Trigger it manually ~2 h out; a geofence
    can replace the manual trigger later.
  mode: single
  sequence:
    - action: climate.set_hvac_mode
      target:
        entity_id: &np_units2
          - climate.np_living
          - climate.np_kitchen
      data:
        hvac_mode: heat
    - action: climate.set_temperature
      target:
        entity_id: *np_units2
      data:
        temperature: 68
    - action: rest_command.ntfy
      data:
        title: "NP warming up"
        priority: "low"
        tags: "fire"
        message: "New Paltz pre-conditioning to 68°F."
SCREOF

echo "== validating with HA's own checker =="
docker exec homeassistant python3 -m homeassistant --script check_config -c /config 2>&1 | tail -25
