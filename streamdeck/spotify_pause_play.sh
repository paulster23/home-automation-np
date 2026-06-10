#!/bin/bash
# True pause/resume toggle — works for both Spotify and radio streams.
# Saves what was playing to ~/.streamdeck_pause_state and restores on next press.
source ~/.streamdeck_env

STATE_FILE=~/.streamdeck_pause_state
HA_VOICE="media_player.home_assistant_voice_0a3a76_media_player"
HA_SPOTIFY="media_player.spotify_paulster23"

# Get current states
VOICE_STATE=$(curl -s "$HA_URL/api/states/$HA_VOICE" \
  -H "Authorization: Bearer $HA_TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null)

SPOTIFY_STATE=$(curl -s "$HA_URL/api/states/$HA_SPOTIFY" \
  -H "Authorization: Bearer $HA_TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null)

if [ "$SPOTIFY_STATE" = "playing" ] || [ "$VOICE_STATE" = "playing" ]; then
  # --- PAUSE ---
  if [ "$SPOTIFY_STATE" = "playing" ]; then
    echo "spotify" > "$STATE_FILE"
    curl -s -X POST "$HA_URL/api/services/media_player/media_pause" \
      -H "Authorization: Bearer $HA_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"entity_id\": \"$HA_SPOTIFY\"}"
  else
    # Radio: get the stream URL from Voice PE attributes, then stop
    MEDIA_INFO=$(curl -s "$HA_URL/api/states/$HA_VOICE" \
      -H "Authorization: Bearer $HA_TOKEN")
    MEDIA_URL=$(echo "$MEDIA_INFO" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d['attributes'].get('media_content_id',''))" 2>/dev/null)
    MEDIA_TYPE=$(echo "$MEDIA_INFO" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d['attributes'].get('media_content_type','music'))" 2>/dev/null)

    if [ -n "$MEDIA_URL" ]; then
      echo "radio|$MEDIA_URL|$MEDIA_TYPE" > "$STATE_FILE"
    fi

    curl -s -X POST "$HA_URL/api/services/media_player/media_stop" \
      -H "Authorization: Bearer $HA_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"entity_id\": \"$HA_VOICE\"}"
  fi

else
  # --- RESUME ---
  [ -f "$STATE_FILE" ] || exit 0

  SAVED=$(cat "$STATE_FILE")
  TYPE=$(echo "$SAVED" | cut -d'|' -f1)

  if [ "$TYPE" = "spotify" ]; then
    curl -s -X POST "$HA_URL/api/services/media_player/media_play" \
      -H "Authorization: Bearer $HA_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"entity_id\": \"$HA_SPOTIFY\"}"

  elif [ "$TYPE" = "radio" ]; then
    MEDIA_URL=$(echo "$SAVED" | cut -d'|' -f2)
    MEDIA_TYPE=$(echo "$SAVED" | cut -d'|' -f3)

    # Ensure speaker is on before restarting stream
    SPEAKER=$(curl -s "$HA_URL/api/states/switch.speaker" \
      -H "Authorization: Bearer $HA_TOKEN" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])" 2>/dev/null)
    if [ "$SPEAKER" != "on" ]; then
      curl -s -X POST "$HA_URL/api/services/switch/turn_on" \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"entity_id": "switch.speaker"}'
    fi

    curl -s -X POST "$HA_URL/api/services/media_player/play_media" \
      -H "Authorization: Bearer $HA_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"entity_id\": \"$HA_VOICE\", \"media_content_id\": \"$MEDIA_URL\", \"media_content_type\": \"$MEDIA_TYPE\"}"
  fi

  rm -f "$STATE_FILE"
fi
