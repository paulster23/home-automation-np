# Home Automation — To-Do List

## Pending Right Now

- [ ] **Restart stack after performance changes** — Run `docker compose down`, `docker volume rm home-automation_piper-data`, `docker compose up -d`. Verify 5 containers running. Delete leftover Piper Wyoming integration in HA UI (Settings → Devices & Services).

---

## Spotify: Voice Control (Spotify Connect Not Available)

**Goal:** Play specific songs/podcasts by voice via Music Assistant.

**Spotify Connect status:** ~~Not possible on macOS Docker Desktop.~~ Docker Desktop runs containers in a Linux VM, so mDNS multicast (required for Spotify Connect device discovery) cannot reach the local network. Neither `network_mode: host` nor `macvlan` work on macOS Docker Desktop. Spotify Connect plugin has been removed.

**What works now (voice intents added):**
- ✅ `PlaySong` — "play the song Bohemian Rhapsody" → `music_assistant.play_media` with `media_type: track`
- ✅ `PlayPodcast` — "play the podcast Serial" → RadioBrowser/TuneIn search
- ✅ `PlayLikedSongs` — "play my liked songs"
- ✅ `StopMusic` — "stop the music"
- ✅ `WhatsPlaying` — "what's playing right now?"
- ✅ `AddToQueue` — "add the song X to the queue"
- ✅ `PlayMusic` / `PlayAlbum` / `PlayPlaylist` / `PlayGenre` / `PlayRadio` (existing)

**Optional future enhancement:**
- Install SpotifyPlus via HACS for advanced features (queue management, complex search) if MA's search isn't good enough
- If you move to a Linux host (Raspberry Pi, NAS), Spotify Connect will work immediately

---

## Frigate: Optimize for Brooklyn Street Camera

**Goal:** Stop parked cars from triggering events. Only detect people + moving cars.

**The problem:** Parked cars sit in frame and constantly trigger detection events, filling storage (217GB+).

**Multi-layered fix:**

### Layer 1: Stationary object timeout (biggest impact)
```yaml
# Add to frigate/config.yml under objects:
stationary:
  threshold: 30        # Frames until "stationary" (6 sec at 5 FPS)
  interval: 50         # Re-check every 10 sec
  max_frames:
    default: 500
    person: 1000       # People can stand still
    car: 150           # Cars stop tracking after 30 sec — THE KEY SETTING
```

### Layer 2: Stricter car detection filters
```yaml
objects:
  filters:
    person:
      min_area: 2000     # Up from 1500 (skip distant noise)
      min_score: 0.55
      threshold: 0.7
    car:
      min_area: 8000     # Only detect cars that are close/large
      min_score: 0.65    # Higher confidence
      threshold: 0.8     # Much stricter
```

### Layer 3: Zone-based event filtering
- Define `active_street` and `parking_area` zones using coordinates
- Set `required_zones: [active_street]` on alerts and detections
- Parked cars in `parking_area` won't generate event clips

### Layer 4: Recording retention optimization
```yaml
record:
  retain:
    days: 1
    mode: active_objects   # Only save segments with moving objects (vs "all")
  alerts:
    required_zones: [active_street]
    retain:
      days: 14
  detections:
    required_zones: [active_street]
    retain:
      days: 14
```

**Expected result:** ~65% storage reduction, dramatically fewer false events.

**Implementation approach:** Take a screenshot of the camera view, define zone coordinates using Frigate's UI zone editor, then apply the config changes.

---

## Wyze Plugs: Light + Speaker + Goodnight Routine

**Goal:** Voice control two Wyze plugs (light + speaker), plus a "goodnight" command that turns both off.

**Setup plan:**

### Step 1: Install ha-wyzeapi via HACS
- HACS → Custom Repositories → add `https://github.com/SecKatie/ha-wyzeapi`
- Install, restart HA
- Configure with Wyze account credentials
- **Note:** 2FA must be disabled on your Wyze account
- Creates entities like `switch.bedroom_light` and `switch.speaker`

### Step 2: Built-in voice commands work automatically
Once entities are exposed to Assist, HA's built-in intents handle:
- "Turn on the light" → `HassTurnOn`
- "Turn off the speaker" → `HassTurnOff`
No custom sentences needed for basic on/off.

### Step 3: Create "goodnight" voice routine
Add to `custom_sentences/en/routines.yaml`:
```yaml
language: "en"
intents:
  GoodNight:
    data:
      - sentences:
          - "goodnight"
          - "good night"
          - "night night"
          - "bedtime"
```

Add to `configuration.yaml` intent_script:
```yaml
GoodNight:
  speech:
    text: "Good night, Paul. Turning everything off."
  action:
    - action: switch.turn_off
      target:
        entity_id:
          - switch.bedroom_light
          - switch.speaker
    - action: media_player.media_stop
      target:
        entity_id: media_player.naboo_media_player
```

### Step 4: (Optional) "Good morning" routine
Could turn things back on, announce weather, play music, etc.

**Gotchas:**
- ha-wyzeapi requires Wyze 2FA disabled
- Cloud-dependent (no local control unless you flash firmware)
- Entity names must match voice commands exactly
- API may break if Wyze changes their backend

---

## Future / Lower Priority

- [ ] Enable Frigate CoreML detection (Apple Neural Engine) for faster detection
- [ ] Centralized logging with Loki/Promtail
- [ ] Reverse proxy (Nginx) for TLS on all UIs
- [ ] Add cron jobs for monitoring scripts (`monitoring/health-check.sh`, `monitoring/frigate-disk-check.sh`)
- [ ] HA System Monitor integration for CPU/memory dashboard
