#!/bin/bash
# Turn speaker on
source ~/.streamdeck_env
curl -s -X POST $HA_URL/api/services/switch/turn_on \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "switch.speaker"}'
