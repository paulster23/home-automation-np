#!/bin/bash
# Go back to previous track
source ~/.streamdeck_env
curl -s -X POST $HA_URL/api/services/media_player/media_previous_track \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "media_player.home_assistant_voice_0a3a76_media_player"}'
