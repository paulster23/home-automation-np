#!/bin/bash
# Play a random podcast via spotify_voice_assistant
# Edit the PODCASTS array to match your actual favorites
source ~/containers/home-automation/secrets/ha.env

PODCASTS=(
  "Radiolab"
  "Fresh Air"
  "99% Invisible"
  "How I Built This"
  "Hardcore History"
)

QUERY="${PODCASTS[$RANDOM % ${#PODCASTS[@]}]}"

curl -s -X POST $HA_URL/api/services/spotify_voice_assistant/podcast_play \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$QUERY\"}"
