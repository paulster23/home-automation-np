# Home Automation Stack — Context

*Deep reference for this stack. Read alongside root `SYSTEM_CONTEXT.md` and `OPS_RUNBOOK.md`.*

*(No manual "last updated" stamp — see `git log` for history.)*

---

## Containers

| Container | Port | Purpose |
|---|---|---|
| mosquitto | 1883 (internal) | MQTT broker (Frigate ↔ HA) |
| frigate | 8971/8554 | NVR — 2 cameras: front_window @ 192.168.1.33 (wired) + backyard @ 192.168.1.248 (RLC-510WA WiFi, added 2026-06-13, sub-stream detect only). Apple Silicon ZMQ detection, 5fps. **Frigate 0.17.1.** Requires FrigateDetector.app running on host (Login Item, port 5555). Model: `/config/model_cache/yolo.onnx` (YOLOv9-t-320). Healthcheck: `curl -sf http://localhost:5000/api/version` (internal FastAPI, not nginx port 8971 — bare TCP probe caused 421 HTTP 400s/week). |
| homeassistant | 8123/6053 | Central automation hub + voice intents. **Version: 2026.6.2** (updated 2026-06-10). **Known bug:** Spotify coordinator throws `MissingField: Field "items" of type PlaylistTracks is missing` on every poll cycle (~every 10–20s) — caused by Spotify's Feb 2026 API change removing `/playlists/{id}/tracks`. Causes playback lag (error loop hammers API). No fix as of 2026.6.2 (upstream issue #166884 still open). Workaround: avoid Spotify algorithmic playlists (Daily Mix, Radio, Discover Weekly). **Trusted proxies:** `configuration.yaml` `http:` block includes `192.168.65.1` (Docker Desktop macOS host gateway) — required since 2026.6 hardened X-Forwarded-For enforcement; without it Tailscale-proxied requests return HTTP 400. |
| ~~music-assistant~~ | 8095/8097 | **REMOVED 2026-05-03.** Was radio-only after Spotify removed 2026-03-28. Radio now uses direct MP3 streams via `script.radio_play_station`; Spotify via librespot → ESPHome direct path. Was consuming ~460m RAM. To restore: `git show HEAD~1:home-automation/docker-compose.yml \| grep -A40 'music-assistant:'` |
| ~~whisper~~ | 10300 (internal) | **REMOVED 2026-04-22.** Replaced by native wyoming-whisperkit (port 7892) and wyoming-mlx-whisper (port 7891). To restore: `git show HEAD~1:home-automation/docker-compose.yml \| grep -A40 'whisper:'` |

---

## Native macOS Services

These run via LaunchAgents, not Docker. All logs tailed to `infra/log-reports/` by log-tailer-native.

| Service | Port | Location |
|---|---|---|
| ~~wyoming-mlx-whisper~~ | ~~7891~~ | **RETIRED 2026-06-02** (STT fallback, unused). Files kept at `home-automation/wyoming-mlx-whisper`. To restore: re-enable LaunchAgent + re-add Wyoming entry on 7891. |
| wyoming-whisperkit | 7892 | `home-automation/wyoming-whisperkit` |
| librespot | 8765 (HTTP out) | `home-automation/librespot` |
| voice-bench | 7700 | `home-automation/voice-bench` |

### wyoming-mlx-whisper — RETIRED 2026-06-02
Was the STT fallback (port 7891). Retired because the active pipeline only ever used WhisperKit (7892); the fallback was never routed to in normal operation, and it was crash-looping (model drift to `distil-whisper-large-v3` + a since-fixed `NameError` in `__main__.py`) while idle. Freed RAM on the 8 GB box.

LaunchAgent `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist` unloaded + disabled. HA Wyoming entry `whisper-cpp` (host.docker.internal:7891) removed. Repo files retained for reference.

Restore: re-enable the LaunchAgent (`launchctl load -w ...`) and re-add a Wyoming integration pointing at port 7891.

### wyoming-whisperkit (Active STT backend)
Switched 2026-03-29. LaunchAgent `~/Library/LaunchAgents/com.wyoming.whisperkit.plist` — WhisperKit Swift bridge (CoreML + Apple Neural Engine). Port **7892**. Model: small (benchmarked 0.85s avg / 0.52s warm; real-world ~1.1s). Calls `mac-whisper-speedtest/tools/whisperkit-bridge/.build/release/whisperkit-bridge` as subprocess. Silero-VAD enabled. VAD silence threshold: **700ms** (increased from 450ms on 2026-04-02; reduced from 900ms → 700ms on 2026-04-29 after tuning). If clipped transcripts appear on short commands ("Stop", "Off"), raise to 800ms.

voice-bench config tag: `whisperkit-small-esphome-direct`. HA Wyoming integration → port 7892. (mlx-whisper fallback on 7891 retired 2026-06-02 — see above.)

Logs → `wyoming-whisperkit/log/whisper.log` + `whisper.err`.

Reload:
```bash
cp ~/containers/home-automation/wyoming-whisperkit/com.wyoming.whisperkit.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.wyoming.whisperkit.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.wyoming.whisperkit.plist
# Wait 30s (ThrottleInterval) before testing
```

**Log ordering note:** wyoming-whisperkit writes the timing line (`WhisperKit internal time:`) *before* the transcription text — opposite of mlx-whisper. The voice-bench correlator buffers the timing in `pending_whisperkit_ms` and emits the entry when text arrives. Bracket-noise tokens (`[water running]`, `[music]`, etc.) treated as non-speech.

### voice-bench
Benchmarking daemon. LaunchAgent `~/Library/LaunchAgents/com.voice-bench.plist`. Logs every voice command to `voice-bench/data/voice_bench.csv` with per-hop timing (listening, STT, HA processing, TTS). Dashboard at `http://localhost:7700`.

Config: `voice-bench/config.yaml` — `tag` field sets the config_tag written to CSV (current: `whisperkit-small-esphome-direct`). `ha_websocket_url`: **`ws://192.168.1.70:8123/api/websocket`** (changed from localhost 2026-05-06 — localhost:8123 no longer binds after port binding migration).

Correlator sleep: **1.5s** (bumped from 0.5s on 2026-05-02 — direct ESPHome path completes faster than old MA-proxied path).

**StreamMonitor (2026-05-03):** asyncio coroutine tracking Spotify/radio stream health. Watches `amp_entity` state changes from HA WebSocket; tails `librespot/log/stream.log` for pipe stall events. Logs to `voice-bench/data/stream_health.csv`. `correlated_stall_ms` non-null = dropout preceded by a pipe stall (Mode A — ffmpeg/librespot gap); null = HA-induced stop (Mode B). Dashboard "Stream Health" tab at port 7700.

Reload: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.voice-bench.plist && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.voice-bench.plist`

If port 7700 stuck: `lsof -ti :7700 | xargs kill -9` first.

### librespot
Spotify Connect receiver registered as "Naboo" via macOS Bonjour/mDNS. LaunchAgent `~/Library/LaunchAgents/com.librespot.naboo.plist`.

**Pipeline:** `librespot (PCM stdout) | ffmpeg (MP3 192k, pipe:1) | serve_http.py (port 8765)`

Key implementation details:
- `serve_http.py` uses `select()` to monitor stdin (audio from ffmpeg) and server socket simultaneously
- **Rate-limiting:** 1.05× real-time rate-limiter (25200 bytes/sec) prevents runaway decode; caps ESPHome's greedy localhost reads
- **SO_SNDBUF=8192** limits kernel TCP send buffer to ~170ms — keeps skip/pause latency low
- **Rate counters reset on new client connection** (2026-05-02) — prevents burst send after pause/resume
- **`--zeroconf-port 5354`** — fixed port for Spotify Connect handshake (random port caused phone discovery failures on mixed wired/WiFi)
- **Audio path (2026-05-02):** HA `librespot_playing` webhook plays `http://192.168.1.70:8765` directly on `media_player.home_assistant_voice_0a3a76_media_player` (ESPHome entity) — bypasses Music Assistant entirely

**on_event.sh:** PID-based debounce; only fires `librespot_playing` webhook on first play/resume (not track changes); ignores `play_request_id_changed` while stream is live.

**Stream health log (2026-05-03):** `serve_http.py` writes `librespot/log/stream.log` with events: `CLIENT_CONNECT`, `CLIENT_DISCONNECT`, `STALL_START`, `STALL_END`, `THROUGHPUT`, `STDIN_EOF`. Select timeout: 0.2s for fast stall detection.

**Reboot persistence (2026-05-09):** `launchctl enable gui/$(id -u)/com.librespot.naboo` must be run once — without it, macOS launchd doesn't auto-register the LaunchAgent after reboot. If librespot is missing after a reboot: `launchctl enable gui/$(id -u)/com.librespot.naboo` then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo.plist`.

**Watchdog:** LaunchAgent `~/Library/LaunchAgents/com.librespot.naboo-watchdog.plist`. Runs every 5 minutes. Checks: (1) librespot process alive via `pgrep`, (2) port 8765 open via `nc -z`, (3) ffmpeg process alive via `pgrep` — **critical**: serve_http.py stays alive on port 8765 even after ffmpeg dies, so the port check alone misses this failure mode. Restarts via `launchctl kickstart -k`.

**Known watchdog limitation:** If launchd's ThrottleInterval deregisters the service after crash cycles, `kickstart` fails with "Could not find service". The watchdog does not fall back to `bootstrap`. Tracked as future hardening item.

Logs → `librespot/log/` (`librespot.err`, `stream.err`, `http.log`, `events.log`, `run.log`, `watchdog.log`).

**ALWAYS copy plists from containers before reloading:**
```bash
cp ~/containers/home-automation/librespot/com.librespot.naboo.plist ~/Library/LaunchAgents/
cp ~/containers/home-automation/librespot/com.librespot.naboo-watchdog.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo.plist 2>/dev/null || true
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo-watchdog.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo-watchdog.plist
sleep 5 && ps aux | grep -E "librespot|ffmpeg|serve_http" | grep -v grep
```

**⚠️ Architecture note:** A FIFO-based decoupled architecture was attempted (2026-04-02) and removed — failed due to ffmpeg blocking behavior with FIFOs. **Stick with the single pipe chain (`librespot | ffmpeg (pipe:1) | serve_http.py`). Do NOT use ffmpeg `-listen 1` mode.**

---

## Voice Pipeline

### Architecture
```
Wake word → ESPHome mic → wyoming-whisperkit (STT, port 7892, Silero-VAD 700ms)
  → HA intent matching → spotify_voice_assistant.search (Spotify API)
  → spotify_voice_assistant.play (start_playback on device "Naboo")
  → librespot receives stream → ffmpeg (pipe:1) → serve_http.py :8765
  → on_event.sh fires HA webhook → media_player.home_assistant_voice_0a3a76_media_player (ESPHome direct)
  → librespot_playing automation: wait for naboo "playing", delay 2s, unmute amp
```

### Voice Command Flows

**Spotify music:**
`PlayMusic` / `PlayAlbum` / `PlaySong` / `PlayPlaylist` / `PlayLikedSongs` / `PlayGenre` →
`spotify_voice_assistant.search` → URI → `spotify_voice_assistant.play(device_name="Naboo")` →
Spotify Web API `start_playback` → librespot → HTTP stream → ESPHome direct

**Podcast:**
`PlayPodcast` / `PlayEpisode` → `spotify_voice_assistant.podcast_play` →
iTunes Search API → RSS feed → latest episode MP3 URL → `media_player.play_media` on ESPHome directly.
**Bypasses librespot entirely** — librespot cannot decode `spotify:episode:` audio keys.

**Spotify "radio":**
`PlayArtistRadio` / `PlaySongRadio` — no true radio seeding; plays artist/track directly.

**Broadcast radio (direct streams, 2026-05-02):**
`PlayCallSign` / `PlayRadio` / `PlayMusic` (call sign redirect) → `media_player.play_media` with hardcoded direct MP3 stream URLs. No MA/RadioBrowser.

Supported stations:
- KEXP: `https://kexp-mp3-128.streamguys1.com/kexp128.mp3`
- WFMU: `http://stream2.wfmu.org/freeform-128k`
- KCRW: `https://streams.kcrw.com/kcrw_mp3`
- WQXR: `http://stream.wqxr.org/wqxr`
- WNYC: `https://fm939.wnyc.org/wnycfm-web`
- WBGO: `https://ais-sa8.cdnstream1.com/3629_128.mp3`

Whisper mishearing corrections: `wsmu`/`wsnu`/`wbmu`/`wfmyou` → WFMU (in `custom_sentences/en/music.yaml` and correction maps in all three intent scripts). `please` accepted alongside `play` in PlayCallSign pattern.

**Stop:** `StopMusic` → clears `voice_paused_music` boolean + `media_player.media_stop` on ESPHome entity.

### Custom Components
- `spotify_voice_assistant` — search + play + podcast_play services
- ~~spotcast~~ **removed** (v4 broken — Spotify killed `/server-time` endpoint 2025)

**Code fix 2026-05-09:** `play` (line 438) and `podcast_play` (line 618) in `spotify_voice_assistant/__init__.py` were hardcoded to `media_player.naboo_media_player` (dead MA entity). Corrected to `media_player.home_assistant_voice_0a3a76_media_player`.

### Amp Mute/Unmute Architecture (critical — read before changing)
The ESPHome amp (`media_player.home_assistant_voice_0a3a76_media_player`) is muted/unmuted by HA automations, NOT by ESPHome firmware. **MA Mute Control must be set to "None"** in MA player settings — if set to "Native mute control", MA races with HA automations.

Six automations govern muting:
1. `voice_pause_media_on_wake` — mutes on wake word
2. `voice_unmute_after_listening` — unmutes when speech recording ends (listening→*)
3. `voice_resume_media_on_done` — belt-and-suspenders unmute + resume on pipeline complete
4. `voice_premute_when_idle` — mutes when naboo stays idle/paused/off for **15 seconds** (delay intentional — RadioBrowser lookups take 2–15s; immediate mute raced against stream start)
5. `naboo_unmute_on_play` — unconditionally unmutes whenever naboo transitions to "playing" (safety net for all play paths)
6. `voice_listening_timeout` — fires `persistent_notification` at 15s (warn) and 60s (urgent) if satellite stays in "listening" too long. Worst observed hang: 461s (water splashing).

The `librespot_playing` automation unmutes after naboo reaches "playing" with a **2-second delay** — ensures it fires after `voice_premute_when_idle` settles.

**`assist_satellite.abort` does not exist** — confirmed via Developer Tools. Hard restart requires ESPHome firmware action (not present as of 2026-04-15).

### Voice PE Settings
- **Firmware: `26.6.0`** (ESPHome 2026.6.0) — updated 2026-07-29 from 26.4.0 via **USB-C web-installer reflash** (WiFi OTA repeatedly failed mid-download, low heap `Error reading data: -28679`). After flashing, **power from a USB wall adapter, not a laptop** — tethered to a computer it boot-loops (`rst:0x15 USB_UART_CHIP_RESET` / `Reset Reason: USB peripheral`). See TROUBLESHOOTING 2026-07-29.
- Wake sound: OFF (`switch.home_assistant_voice_0a3a76_wake_sound`)
- Device IP: `192.168.1.47` (DHCP reserved)
- API encryption: **Noise ENABLED** as of the 26.6.0 reflash (`Noise encryption: YES`, saved PSK; HA 2026.7.4 connects fine). Supersedes the 2026-04-29 "encryption removed" state — the production-firmware reflash restored it.
- Finished speaking detection: **relaxed** (set via `naboo_vad_relaxed` automation on HA start)
- Silero-VAD silence threshold in wyoming-whisperkit: **700ms** (`VAD_SILENCE_MS` in `handler.py` — verified 2026-07-28)
- **Once-a-minute `errno=128` in device/HA logs is NOT instability** — it's the uptime-kuma `Naboo Voice PE (ESPHome API)` TCP port monitor probing `:6053` every 60s (bare connect, no noise handshake → `Accept 192.168.1.70` + `CONNECTION_CLOSED errno=128`). Redundant ping monitor dropped + port monitor slowed 60s→300s on 2026-07-29. See TROUBLESHOOTING 2026-07-29.

### Auto-pause Automation
Pauses `media_player.home_assistant_voice_0a3a76_media_player` when wake word fires so background audio doesn't degrade STT; resumes after pipeline completes only if the player is still in `paused` state (guards against stop/new-station commands re-triggering a resume).

---

## Frigate / Camera

- **Two cameras:** `front_window` @ 192.168.1.33 (wired; 3 zones — entrance, sidewalk, active_street; tracks person + car) and `backyard` @ 192.168.1.248 (RLC-510WA WiFi, added 2026-06-13; sub-stream detect only since 2026-06-15; powered off at times = normal)
- **Detection:** Apple Silicon ZMQ via FrigateDetector.app (Login Item, port 5555). CPU usage ~20–40% (was ~200% before ZMQ offload). If Frigate fails to detect, check FrigateDetector is running first.
- **Storage:** Retains alerts 14 days, detections 7 days. Continuous retention removed in 0.17.
- **RTSP note:** Reolink app uses proprietary P2P — app working ≠ RTSP working. Always confirm via `ping 192.168.1.33` and checking Frigate logs.

---

## Dependency Map

```
mosquitto (MQTT broker)
  └── frigate (publishes events to MQTT)
  └── homeassistant (receives frigate events via MQTT)
       ├── wyoming-whisperkit (native macOS, active STT, port 7892, Silero-VAD 700ms)
       ├── HA Spotify integration (provides spotifyaio client)
       │    └── spotify_voice_assistant custom component (search + play + podcast_play)
       │         ├── Spotify: Web API → librespot "Naboo" (native macOS)
       │         │    └── ffmpeg (PCM→MP3, pipe:1) → serve_http.py (port 8765)
       │         │         └── HA webhook → ESPHome media_player direct
       │         └── Podcasts: iTunes API → RSS → MP3 URL → ESPHome media_player directly
       └── FrigateDetector.app (native macOS, port 5555, ZMQ object detection)

NOTE: music-assistant REMOVED 2026-05-03. Radio and Spotify bypass MA entirely.
```

---

## Troubleshooting: Frigate Camera Offline

Read `infra/log-reports/frigate.log` first. `Connection refused` or `Connection timed out` on RTSP URL = almost always one of:

1. **Camera IP changed** (most common after reboot) — Reolink app will still work (P2P), RTSP won't. Confirm with `ping 192.168.1.33`. If that fails, check router connected devices.
   - Fix: Update `home-automation/frigate/config.yml` both RTSP paths to new IP. Restart Frigate. Set DHCP reservation immediately.
   ```bash
   cd ~/containers/home-automation && docker compose restart frigate
   # Also update SYSTEM_CONTEXT.md camera IP reference
   ```

2. **RTSP disabled on camera** — After firmware update, RTSP can reset to off. Check in Reolink app: Settings → Network → Advanced → Port Settings. Frigate retries every 10s — no restart needed after re-enabling.

3. **RTSP port changed** — Default 554. Update in `frigate/config.yml` if different.

---

## Troubleshooting: ESPHome Voice PE Not Connecting

**Symptom:** Blue spinning LED. HA log shows `TimeoutAPIError` to device IP.

```bash
ping 192.168.1.47   # if no response, device got a new IP
```
Check router connected devices for `home-assisant-coice-0a3a76`.

**If IP changed:** Edit `homeassistant/.storage/core.config_entries` directly — find the ESPHome entry and update `host`. Then restart HA:
```bash
cd ~/containers/home-automation && docker compose restart homeassistant
```
The HA UI reconfigure flow is unreliable for this — edit the file directly.

**If device not on network at all:**
1. Connect via USB data cable — `ls /dev/cu.*`, look for `usbmodem*`
2. Kill stale screen session: `screen -list`, `screen -X -S <session> quit`
3. Read serial log: `screen /dev/cu.usbmodem1101 115200`
4. `Not connected to network` → WiFi creds lost; open Chrome → https://www.improv-wifi.com/serial/ → provision
5. Or: connect to device hotspot in WiFi list → captive portal provisioning
6. Hold button ~5s for provisioning mode (releases early = "factory_reset_cancelled" sound, no reset)

**If HA shows "disabled transport encryption" error:** Button hold partially reset API encryption. Confirm removal in HA UI — device reconnects without encryption. `noise_psk` cleared from `core.config_entries`.

**Prevention:** Always set DHCP reservations for ESPHome devices immediately after adoption. Current reservation: `192.168.1.47`.

---

## Troubleshooting: Naboo Plays But No Audio (Amp Muted)

**Check first:** In MA → Settings → Players → Naboo → Player Controls → **Mute Control must be "None"**. If set to "Native mute control", MA races with HA automations. Check after every MA upgrade (if MA is ever reinstalled).

**Check second:** HA Developer Tools → States → `media_player.home_assistant_voice_0a3a76_media_player` → `is_volume_muted`. If `true` while playing, an automation race left it muted.

**Most likely cause (radio commands):** `voice_premute_when_idle` fired because naboo was still idle (RadioBrowser lookup not returned). Fixed as of 2026-04-10: premute waits 15s, `naboo_unmute_on_play` unconditionally unmutes on "playing".

**If it regresses:**
1. Confirm MA Mute Control is "None"
2. Check 15s delay is still on `voice_premute_when_idle`
3. Check `naboo_unmute_on_play` is enabled
4. Do NOT add triggers to `voice_premute_when_idle` that watch `is_volume_muted` — feedback loop risk

---

## Troubleshooting: Librespot Pipeline

**Check all three processes are running:**
```bash
ps aux | grep -E "librespot|ffmpeg|serve_http" | grep -v grep
```

**Check port 8765 is listening:**
```bash
lsof -iTCP:8765 -sTCP:LISTEN
```
Should show Python/serve_http. If nothing: pipeline is down.

**Read logs in this order:**
1. `librespot/log/http.log` — serve_http errors
2. `librespot/log/stream.err` — ffmpeg errors
3. `librespot/log/librespot.err` — librespot errors
4. `librespot/log/events.log` — webhook firing sequence
5. `librespot/log/run.log` — restart timestamps (restarting every 5min = watchdog kicking it)

**Common failure patterns:**

| Symptom | Log evidence | Fix |
|---|---|---|
| Pipeline restarts every 5 min | `run.log` entries every 5 min | Check `stream.err` / `http.log` for crash reason |
| Spotify shows playing, no audio | `events.log` shows playing→paused within 1s | ffmpeg is crashing — check `stream.err` |
| Port 8765 not listening | `http.log` has traceback | serve_http crashed — reload pipeline |
| Port 8765 up, watchdog OK, but stream silent | `pgrep -x ffmpeg` returns empty | ffmpeg died but serve_http.py stayed alive — `kill -9 $(lsof -iTCP:8765 -sTCP:LISTEN \| awk 'NR==2{print $2}')` then `pkill -x librespot` — KeepAlive restarts all three |
| launchctl kickstart fails with "Could not find service" | launchd deregistered the service after crash cycles | Run bootstrap instead: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo.plist` |

**⚠️ Do NOT use ffmpeg `-listen 1`.** It blocks waiting for a client before reading stdin — librespot fills the pipe buffer and deadlocks.

**Reload procedure:**
```bash
cp ~/containers/home-automation/librespot/com.librespot.naboo.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.librespot.naboo.plist
sleep 5 && ps aux | grep -E "librespot|ffmpeg|serve_http" | grep -v grep
```

---

## Troubleshooting: Voice Commands Cut Off (VAD Early Trigger)

**Symptom:** voice-bench shows "VAD early trigger — Xs audio collected". Commands like "play the replacements" get cut off.

**Cause:** `VAD_SILENCE_MS` in `wyoming-whisperkit/wyoming_whisperkit/handler.py`.

**Current value:** `VAD_SILENCE_MS = 700` (line 38 in `handler.py`). If clipped transcripts appear on short commands, raise to 800ms.

**If it regresses:** Check `handler.py` line ~38 for `VAD_SILENCE_MS`. After changing, reload wyoming-whisperkit (see reload commands above). Wait 30s (ThrottleInterval) before testing.
