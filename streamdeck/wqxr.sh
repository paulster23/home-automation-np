#!/bin/bash
# WQXR — Classical 105.9 FM
source ~/containers/home-automation/secrets/ha.env

SPEAKER=$(curl -s $HA_URL/api/states/switch.speaker \
  -H "Authorization: Bearer $HA_TOKEN" | python3 -c "
import sys, json
try: print(json.load(sys.stdin).get('state', ''))
except: print('')
" 2>/dev/null)

curl -s -X POST $HA_URL/api/services/media_player/play_media \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.home_assistant_voice_0a3a76_media_player", "media_content_id": "http://stream.wqxr.org/wqxr", "media_content_type": "music"}' || true

if [ "$SPEAKER" != "on" ]; then
  curl -s -X POST $HA_URL/api/services/switch/turn_on \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"entity_id": "switch.speaker"}' || true
fi
