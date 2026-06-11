#!/bin/bash
# Good Night — stop media, turn off speaker and plug_1
# Mirrors the GoodNight voice intent in configuration.yaml
source ~/containers/home-automation/secrets/ha.env

curl -s -X POST $HA_URL/api/services/media_player/media_stop \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.home_assistant_voice_0a3a76_media_player"}'

curl -s -X POST $HA_URL/api/services/switch/turn_off \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": ["switch.speaker", "switch.plug_1"]}'
