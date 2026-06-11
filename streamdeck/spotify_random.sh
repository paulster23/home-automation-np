#!/bin/bash
# Play something random from your liked songs on Spotify (shuffled)
# Uses spotify:user:paulster23:collection — your saved tracks library
source ~/containers/home-automation/secrets/ha.env

# Start liked songs on Naboo
curl -s -X POST $HA_URL/api/services/spotify_voice_assistant/play \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"uri": "spotify:user:paulster23:collection", "device_name": "Naboo"}'
