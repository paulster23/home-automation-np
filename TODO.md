# Home Automation — To-Do List

*Last updated: 2026-05-06*

---

## ✅ Completed

- **Piper TTS removed** — No longer in docker-compose.yml. Stack restarted, piper-data volume cleaned up. Google Translate (cloud) used for TTS.
- **Wyze plugs** — Working via ha-wyzeapi. GoodNight routine active (`good night`, `bedtime`, etc.).
- **Spotify Developer App** — Created at developer.spotify.com. Client ID + Client Secret in MA's Spotify provider settings. Faster search via dev token.
- **PlayArtistRadio intent** — Voice command e.g. "play Breeders radio" → MA radio_mode with continuous queue. Added to `custom_sentences/en/music.yaml` + `configuration.yaml`.
- **PlayRadio disambiguation** — Fixed collision: PlayRadio now requires "station" keyword; PlayArtistRadio catches `{artist} radio`.
- **MLX Whisper (native STT)** — Installed at `/Users/media/containers/home-automation/wyoming-mlx-whisper`. Model upgraded to `mlx-community/distil-whisper-large-v3`. Port 7891. M1 GPU/Neural Engine. ~1–3s transcription in quiet with pre-mute active (was 13–22s with Docker + ambient noise). Launch Agent: `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist`.
- **Docker Whisper container stopped** — `whisper` container stopped, freeing ~768 MB RAM + 2 CPUs. Moved to `profiles: [stt]`; restart with `docker compose --profile stt up -d whisper`.
- **Voice pipeline auto-mute/pause automation** — Four automations in `automations.yaml`. Always mutes the amp on wake word (cleans up mic input for Whisper VAD regardless of whether music is playing). Unmutes immediately when recording ends so TTS plays back correctly. Pauses/resumes Music Assistant only if it was actually playing. Pre-mute automation keeps amp muted whenever music is idle, eliminating the cold-start slow path. Uses `input_boolean.voice_paused_music` helper to track state.
- **whisper-small.en tested and rejected** — Tested `mlx-community/whisper-small.en` (2026-03-15). Transcription accuracy not acceptable. Reverted to `whisper-large-v3-turbo`, then upgraded to `distil-whisper-large-v3`.
- **distil-whisper-large-v3 adopted** — Faster and more accurate than large-v3-turbo for short home-automation commands. Updated in `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist` (2026-03-17).
- **whisper-large-v3-turbo-q4 adopted** — Better voice diversity (handles multiple household voices), near-identical speed to distil on clean audio. 4-bit quantised: ~450MB on disk vs ~1.5GB full model. Updated in plist (2026-03-24).
- **Silero-VAD streaming layer added** — `wyoming_mlx_whisper/handler.py` now runs Silero-VAD on each incoming 32ms audio chunk. Fires transcription immediately when 450ms of post-speech silence is detected, without waiting for ESPHome's AudioStop. Cuts the 15–20s TV-noise recording window to ~2–3s. `requirements.txt` updated with `silero-vad` + `onnxruntime`. `--vad` / `--no-vad` flag added to `__main__.py`. Enabled by default via plist (2026-03-24).
- **voice-bench installed** — Lightweight benchmarking daemon at `voice-bench/`. Logs every voice command to `voice-bench/data/voice_bench.csv` with per-hop timing (listening, STT, HA processing, TTS). Dashboard at `http://localhost:7700`. LaunchAgent: `~/Library/LaunchAgents/com.voice-bench.plist` (2026-03-17).
- **mac-whisper-speedtest installed** — Benchmarking tool at `mac-whisper-speedtest/`. Races 9 Whisper implementations against each other on local Apple Silicon hardware. Used to identify fastest backend. Results (2026-03-28): WhisperKit 0.85s avg (small model), mlx-whisper 4-bit 1.29s, whisper.cpp 1.39s — all vs current pipeline STT average of ~9.3s.
- **whisper-small-mlx-4bit adopted** — Switched from `whisper-large-v3-turbo-q4` to `mlx-community/whisper-small-mlx-4bit` (2026-03-28). Benchmark showed small model transcribes home-automation commands accurately at ~1.3s vs ~9.3s for turbo. Model updated in `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist`. voice-bench tag updated to `small-mlx-4bit-silero-vad`. Correlation bug fixed in `voice_bench.py`: small model produces fast empty STT hits from noise that previously won over real transcriptions — now prefers non-empty matches within the window.
- **whisper-small.en re-evaluation note** — Previously rejected (2026-03-15) for accuracy. `whisper-small-mlx-4bit` is the 4-bit quantised multilingual small model via MLX, which is different — benchmark transcription of all test commands was accurate.
- **FrigateDetector.app** — Added to macOS Login Items. Auto-starts on reboot.
- **Spotify rework (2026-03-28/29)** — Replaced Music Assistant's Spotify role entirely with native librespot + `spotify_voice_assistant.play` (direct Spotify Web API). MA is now radio-only (RadioBrowser, TuneIn). librespot registers as "Naboo" Spotify Connect device → streams PCM via ffmpeg (`-re`) → `serve_http.py` (port 8765) → HA webhook → naboo_media_player. Voice intents use `spotify_voice_assistant.search` + `spotify_voice_assistant.play` (calls `start_playback(device_id=...)` via spotifyaio). spotcast removed (v4 broken — Spotify killed `/server-time` endpoint). HA Spotify integration's `play_media`/`select_source` also doesn't work for cold-start — direct API is the only reliable path. `serve_http.py` replaces ffmpeg `-listen 1` to prevent pipe deadlock. `on_event.sh` uses PID-based debounce to prevent race conditions. MA memory reduced 512m→256m. LaunchAgent: `~/Library/LaunchAgents/com.librespot.naboo.plist`.
- **Frigate car filters tightened** — `min_area: 8000`, `min_score: 0.65`, `threshold: 0.8` in `frigate/config.yml`.
- **Frigate stationary filtering** — `threshold: 50`, `interval: 50`, `max_frames.default: 3000` in place.
- **Frigate zones** — `entrance`, `sidewalk`, `active_street` zones defined. `required_zones` set on alerts + detections.
- **Librespot stream failures (2026-04-09)** — Fixed stale `/tmp/librespot.fifo` + reloaded plist from repo. Pipeline running clean (librespot → ffmpeg pipe:1 → serve_http.py). Was causing 428 MA errors + 172 broken pipes per week via watchdog restart loop.
- **Frigate health check endpoint (2026-04-09)** — Changed from bare TCP `nc -z` (421 HTTP 400s/week) to `curl -sf http://localhost:5000/api/version`. Container healthy, noise eliminated.

---

## 🔲 Pending

### ~~Raise homeassistant memory limit to 768m~~ — ✅ Done 2026-04-08
Was at 640m; Apr 2 report showed 501–512m usage (78–80%, HIGH risk). Raised back to 768m in `docker-compose.yml`. Apply with `docker compose up -d homeassistant` — HA will recreate with the new limit (no data loss, config volume persists).

### ~~Fix Frigate health check endpoint~~ — ✅ Done (2026-04-09)
Changed healthcheck from `nc -z 127.0.0.1 8971` (bare TCP, caused 421 HTTP 400s/week) to `curl -sf http://localhost:5000/api/version` (Frigate's internal FastAPI endpoint). Container recreated and confirmed healthy. HTTP 400 noise eliminated.

### ~~Investigate librespot → Music Assistant stream failures~~ — ✅ Fixed (2026-04-09)
Root cause: stale `/tmp/librespot.fifo` left behind from the failed FIFO-based architecture (removed 2026-04-02), combined with the LaunchAgent plist in `~/Library/LaunchAgents/` pointing at that FIFO path instead of the correct `pipe:1 | serve_http.py` chain. ffmpeg failed on every start with "File already exists", causing the watchdog to restart every ~5 min and generating all 428 MA errors + 172 broken pipes. Fix: `rm -f /tmp/librespot.fifo` + reload plists from repo. Confirmed clean: one start at 2026-04-10T01:48:36Z, all three processes running (librespot → ffmpeg pipe:1 → serve_http.py), no subsequent watchdog restarts.

### ~~Naboo silent after pipeline recovery~~ — ✅ Fixed (2026-04-10)
ffmpeg broken pipe left serve_http.py alive (port 8765 open), so watchdog passed but pipeline was dead. Pre-mute automation fired when naboo went idle. On pipeline restart, MA radio play has no unmute path. Two fixes: (1) added ffmpeg process check to `watchdog.sh`; (2) added `naboo_unmute_on_play` automation — fires on any naboo → playing transition while amp is muted.

### ~~Fix librespot FIFO crash loop~~ — ✅ Fixed (2026-04-15, second occurrence)
`/tmp/librespot.fifo` reappeared on disk (second occurrence — first was 2026-04-09). Pipeline was in crash loop since 2026-04-10T21:26:47Z. Fix applied: `rm -f /tmp/librespot.fifo` + killed stale processes + reloaded plists. **Permanent fix:** Added `rm -f /tmp/librespot.fifo` guard (with comment) to `home-automation/librespot/run.sh` — runs on every pipeline start before ffmpeg launches, preventing recurrence regardless of cause. Committed to home-automation repo.

### ~~Verify/fix assist_satellite.abort in HA 2026.4~~ — ✅ Fixed (2026-04-15)
`assist_satellite.abort` was never a real HA action (confirmed via Developer Tools → Actions — not present). Automation `voice_listening_timeout` completely rewritten: fires `persistent_notification.create` at 15s warn and at 60s urgent alert directing manual intervention. Hard restart not implemented: `esphome.home_assistant_voice_0a3a76_restart` action doesn't exist in this firmware, and no restart button entity is exposed (confirmed via template query of all ESPHome entities). To enable hard restart: upgrade ESPHome Voice PE firmware to a version that exposes the restart action. Automation committed via `git add -f homeassistant/automations.yaml`.

### ~~Remove spotcast integration~~ — ✅ Done 2026-04-22
Removed via HACS. `configuration.yaml` spotcast block was already commented out. `secrets.yaml` spotcast keys removed. No HA restart required (no active config block). *Discovered and resolved 2026-04-22*

### ~~Investigate HA unexpected restart (Apr 20 23:17 UTC)~~ — ✅ Investigated 2026-04-22, not a bug
MA did a clean Docker restart at 23:17:04 (`shutdown requested!` in MA log — graceful). HA's MA client logged `Server disconnected` at 23:17:05; ESPHome's Naboo cascade-errored mid-stream (`Reader failed with connection error`, `Media source is in error state`). HA's s6-rc restarted at 23:17:49 in response to the ESPHome cascade, not due to OOM or crash. Unclean SQLite session (id=115, from 2026-04-18 02:08:40) was pre-existing from the Apr 18 librespot FIFO cluster, not from this event. ESPHome `Reader timed out` at 23:20 is Naboo reconnecting post-restart — expected. Recurring MA WebSocket disconnects (Apr 21 07:31, Apr 22 15:41) are MA periodic restarts, normal. No action needed.

### ~~HA restart storm caused by HACS blocking startup~~ — ✅ Mitigated 2026-04-30
Five HA crashes on Apr 29–30 traced to two root causes: (1) ESPHome HA Voice device IP change (→192.168.1.47) disrupted an HA restart, and (2) HACS `startup_tasks()` blocked HA's entire startup sequence indefinitely while waiting for a GitHub API call that DNS failure made hang forever. The gluetun DNS fix (Quad9 DoT fallback, server unpinning — committed `e6e9339`) addresses root cause. Belt-and-suspenders: patched `custom_components/hacs/base.py` to wrap `async_load_hacs_from_github()` with `asyncio.wait_for(timeout=30)` — on timeout, HACS logs an error, sets itself RUNNING, and the 48h recurring task retries automatically. **Note:** this patch lives in the config volume and survives image updates, but will be lost when HACS updates itself. Re-check `base.py` after any HACS update; reapply if the `asyncio.wait_for` wrapper is gone.

### ~~Wyze DNS timeouts still occurring post-fix~~ — ✅ Root cause fixed 2026-04-30
Wyze `api.wyzecam.com` DNS timeouts on 2026-04-29 traced to HA crash/restart cycles from HACS blocking (patched 2026-04-30). The Apr 19 correlation (12 min post-gluetun reconnect) was caused by gluetun's in-process VPN restart leaving its internal DNS proxy stuck — confirmed in 2026-04-30 logs. Root cause fixed: (1) gluetun Docker healthcheck now tests `nslookup cloudflare.com` in addition to port 9999 — DNS failure → unhealthy; (2) scheduler watchdog cron restarts gluetun within ~7 min of DNS failure. Also applied: unpinned SERVER_HOSTNAMES + DOT_PROVIDERS=cloudflare,quad9. See TROUBLESHOOTING.md 2026-04-30. Monitor for recurrence — if Wyze bursts continue clustering post-reconnect despite clean gluetun restarts, Docker bridge reconfiguration theory needs investigation.

### ~~Stop/remove idle Docker whisper container~~ — ✅ Done 2026-04-22
Service definition removed from `docker-compose.yml`. WhisperKit stable since 2026-03-29 (nearly a month). `whisper-data` volume declaration also removed. Run `docker volume rm home-automation_whisper-data` to reclaim the ~150MB disk space the model data occupies. Fallback path restored in a comment in compose.

### ~~Frigate: per-object max_frames for car~~ — ✅ Done 2026-04-29
Per-object keys under `stationary.max_frames` ARE supported in Frigate 0.17.x — confirmed in docs Apr 2026 (original TODO was wrong). Applied `car: 150` (~30s at 5fps) in `frigate/config.yml`. Container restarted, config loaded clean. People tracking unaffected (still uses `default: 3000`).

### ~~Spotify voice: optional SpotifyPlus~~
~~SpotifyPlus via HACS would unlock advanced queue management and richer search.~~ **Superseded** — MA Spotify removed entirely 2026-03-28. Spotify now runs via librespot + official HA Spotify integration. spotcast removed (v4 broken). SpotifyPlus is no longer applicable.

### ~~Fix HA Frigate integration URL~~ — ✅ Done (2026-05-05)

HA's Frigate custom integration was configured with `url: https://frigate:8971` since setup day, but Frigate's nginx serves HTTP-only on port 8971. Caused `SSL: RECORD_LAYER_FAILURE` every ~80s. Fixed by editing `url` to `http://frigate:8971` directly in `.storage/core.config_entries` and restarting HA. Confirmed clean — no Frigate errors in new HA instance.

---

### Voice pipeline latency optimization — ✅ Complete (ongoing monitoring via voice-bench)

**Root cause identified:** Whisper VAD waits for silence to detect end-of-speech. Any ambient room audio (TV, speaker bleed) extends the recording window to 15–60s. Solution: always mute the amp on wake word so Whisper hears silence within ~1s of the user stopping speaking.

**TV noise:** The in-room TV is a separate physical audio source — amp mute has no effect on it. Keep TV muted/off during voice commands.

**Round 1 profiling** (2026-03-15, pre-optimization, no auto-pause):
- "What time is it" (quiet): **8.4s total**, Whisper 2.44s
- "Play the Replacements" (KEXP playing): **20.4s total**, Whisper 9.88s
- "Stop" (KCRW blasting): **54.5s total**, Whisper 47.8s, WRONG transcription

**Round 2 profiling** (2026-03-16, distil-whisper-large-v3, pre-mute active, TV off):
- "What time is it": **2.85s total**, Whisper ~1.2s ✅
- "What's the weather?": **3.8s total** ✅
- "What time is it?" after music: **5.2s total** ✅
- Radio/music commands: **3.0–3.3s total** ✅

**All optimizations completed:**
- [x] **Upgrade to distil-whisper-large-v3** — ✅ Faster + more accurate than large-v3-turbo for this use case (2026-03-17).
- [x] **Always-mute on wake word** — ✅ Amp muted every time wake word fires, not just when music is playing. Gives Whisper clean silence on all commands (2026-03-17).
- [x] **Unmute before TTS** — ✅ Unmute fires when satellite leaves "listening" (mic done, TTS not yet started). TTS plays back correctly (2026-03-17).
- [x] **Pre-mute when music stops** — ✅ Automation fires when MA enters idle/paused/off, and when amp becomes unmuted while no music is playing. Eliminates cold-start slow path (2026-03-17).
- [x] **Tune VAD silence detection threshold** — ✅ Left at **default**. Aggressive clips user speech. Default is correct with amp muted.
- [x] **Fix MLX Whisper LaunchAgent plist** — ✅ Model and log paths corrected (2026-03-16).
- [x] **Add "Stop" as standalone voice command** — ✅ Bare "stop" + variants in `custom_sentences/en/music.yaml` (2026-03-16).
- [x] **Disable wake sound** — ✅ `switch.home_assistant_voice_0a3a76_wake_sound` off. Saves ~0.7s (2026-03-16).
- [x] **voice-bench installed** — ✅ Daemon + dashboard at `http://localhost:7700`. Logs all commands to CSV with per-hop timing. See `voice-bench/` directory (2026-03-17).

**Remaining (lower priority):**
- [x] **Radio station response latency** — ~~25s~~ No longer a significant issue. Retested 2026-03-30 with WhisperKit-small: median **11.1s** total (1.1s STT + 4.1s HA/MA RadioBrowser lookup + 2.4s TTS), worst case 16.8s. The original 25s+ times were pre-optimization STT (ambient noise, no VAD). Remaining variability (2–10s processing) is RadioBrowser lookup latency — external and not worth chasing. Hardcoding stream URLs for top stations would shave 2–4s but adds maintenance burden.
- [ ] **Fix "Stop" misheard as "Pause"** — distil-whisper-large-v3 is better but may still misfire on very short words. Option: add "pause" as a `StopMusic` alias in `custom_sentences/en/music.yaml`.
- [ ] **Monitor small model accuracy** — `whisper-small-mlx-4bit` benchmarked perfectly on test commands but needs real-world validation across voice diversity, proper nouns (WFMU, KEXP), and noisy conditions. Watch `voice-bench` dashboard for transcription errors.
- [x] **Fix voice-bench port 7700 binding** — ✅ Fixed 2026-04-10. LaunchAgent was in a broken launchd domain state (bootout/unload both returned I/O error 5). Port was already free by the time we diagnosed — previous crash loop had died. `launchctl bootstrap gui/501` brought it back up cleanly. Also fixed a related bug: VAD early-trigger log lines (INFO level, same logger as transcription) were being captured as the transcript text in the CSV. Fixed by adding `not m.group(1).startswith("VAD ")` guard in `voice_bench.py` tail_whisper_log().
- [ ] **voice-bench (no transcription) for radio commands** — P8/low. VAD early-trigger path produces two WhisperKit transcriptions per command (real text ~2s wall, blank ~1s wall). Session finalizer races the slower result. Multiple fix attempts broke MA muting. Decided to defer — latency and hang tracking still work, transcription text field unreliable for radio commands. Candidate for deprecation.
- [ ] **Investigate Apr 8 listening-phase hangs** — Discovered 2026-04-10. Four listening hangs of 120-168s clustered between 14:07-19:21 on Apr 8. Main blocker to <7s voice KPI. Possible causes: ESPHome Voice PE firmware issue, WiFi micro-disconnect, or mic driver stuck state. Check HA ESPHome logs for that timeframe.
- [x] **Add listening-phase timeout** — ✅ Fixed 2026-04-10, rewritten 2026-04-15. `voice_listening_timeout` automation fires `persistent_notification` at 15s (warn) and 60s (urgent + manual intervention instructions). Original used `assist_satellite.abort` which never existed — replaced. Hard restart not possible without ESPHome firmware exposing a restart action. Covers ambient noise hangs (worst observed: 461s).
- [x] **Switch STT backend to WhisperKit** — ✅ Complete (2026-03-29). Wyoming wrapper at `home-automation/wyoming-whisperkit/`, port 7892, Silero-VAD enabled. Active as of 2026-03-29 — voice-bench config tag `whisperkit-small-silero-vad` confirms. Benchmarked at 0.85s; real-world STT averaging ~1.1s on radio commands (vs 3–5s with mlx-whisper). Fallback: Wyoming → port 7891 (mlx-whisper still installed).
- [x] **Librespot "Naboo" watchdog + serve_http.py crash loop fix** — ✅ Complete (2026-03-30/31). Two fixes:
  1. `watchdog.sh` + `com.librespot.naboo-watchdog.plist` — checks every 5 min: (1) librespot process alive, (2) port 8765 open; restarts via `launchctl kickstart -k`. Installed and confirmed catching real failures.
  2. **Root cause:** `serve_http.py` used only `SO_REUSEADDR` which does NOT bypass `TIME_WAIT` on macOS (Linux behaviour only). Rapid restarts left port 8765 in `TIME_WAIT` → bind failure → cascade crash loop. Fixed by adding `SO_REUSEPORT` (one line). Confirmed working 2026-03-31.

---

## 🔲 Open Bugs (waiting on upstream)

- [ ] **Spotify coordinator MissingField crash loop** — HA's `spotifyaio` library fails to parse Spotify API responses since Spotify removed `GET /playlists/{id}/tracks` in Feb 2026. Error: `MissingField: Field "items" of type PlaylistTracks is missing in Playlist instance`. Fires every ~10–20s during playback, causes lag. Persists in HA 2026.4.4. Tracked at [GitHub #166884](https://github.com/home-assistant/core/issues/166884). **Workaround:** avoid Spotify algorithmic/radio playlists (Daily Mix, Discover Weekly). Watch HA 2026.5 for a fix.

---

## 🔲 Pending

- [x] **voice-bench entity state seeding on connect** — ✅ Fixed 2026-05-06. Added `get_states` API call in `watch_ha()` immediately after subscription ack. Seeds `entity_states`/`entity_attrs` with all current HA states before any events arrive. Prevents `radio_active` defaulting to "off" on a fresh WebSocket connection. Logs `Seeded N entity states (radio_active=<value>)` on connect.

- [x] **voice-bench stream type mid-session correction** — ✅ Fixed 2026-05-06. Added `StreamMonitor.on_radio_active_changed()` method. If a session is live, re-calls `_refresh_stream_type()` and logs the correction. Wired into `watch_ha()` event loop: any `state_changed` on `input_boolean.radio_active` triggers it immediately. Closes the race where `radio_active=on` arrives after `amp→playing` was already classified as spotify.

- [ ] **Fix Tailscale remote HA access** — `tailscale serve` proxies `https://media.tail317990.ts.net:8123 → http://localhost:8123`. HA's Docker port is now bound to `192.168.1.70:8123` (not localhost), so the Tailscale proxy target is broken. Fix options: (1) update `tailscale serve` to point at `http://192.168.1.70:8123` instead of `localhost`, or (2) add a second `0.0.0.0:8123` binding alongside the LAN one (but verify no Tailscale port conflict first). Triggered by 2026-05-06 force-recreate of HA container that first applied the `192.168.1.70` binding from `docker-compose.yml`.

---

## 🔮 Future / Lower Priority

- [x] ~~**Remove Music Assistant from stack**~~ — ✅ Done 2026-05-03. Service removed from `docker-compose.yml`. Frees 640 MiB RAM. Radio playback unaffected.


- [x] ~~**Check router port forwarding for port 8971**~~ — **Closed 2026-05-05.** Port confirmed not internet-accessible (canyouseeme.org test clean, no port forward rules in Linksys Velop router). The "scanner" traffic in the 2026-05-04 log was `172.18.0.4` (HA container) — the broken HA Frigate integration hammering `https://frigate:8971` every ~10s. See the HA Frigate integration URL fix TODO above.
- [ ] Reverse proxy (Caddy/Nginx) — HTTPS + friendly names (e.g. `emby.local`) for all UIs
- [ ] Centralized logging (Loki/Promtail) — only if log-tailer + direct file reads aren't enough
- [ ] HA System Monitor integration — CPU/memory dashboard in HA
- [ ] Network isolation for media stack — separate `download-net` and `media-net` bridge networks
- [x] ~~Move speedtest-tracker APP_KEY to secrets file~~ — **Done 2026-03-28** (tracked in infra/TODO.md completed section)
- [x] ~~Tailscale for remote access~~ — **Done 2026-05-04.** All services exposed via `tailscale serve --https=PORT`. No Caddy. Caddy removed entirely.
- [ ] Frigate CoreML detection — Apple Neural Engine path (currently using ZMQ via FrigateDetector.app)
- [x] ~~Tune Silero-VAD silence threshold from 900ms → 700ms~~ — **Done 2026-04-29.** Edited `VAD_SILENCE_MS` in `wyoming_whisperkit/handler.py` (line 38). LaunchAgent reloaded via `launchctl kickstart`. Monitor voice-bench for clipped transcripts on short commands ("Stop", "Off") — if seen, raise to 800ms.
- [x] ~~Add WFMU mishearing corrections~~ — ✅ Done 2026-05-02. Added `wsmu`, `wsnu`, `wbmu`, `wfmyou` to `callsign` list in `custom_sentences/en/music.yaml`; added `please` alongside `play` in PlayCallSign sentence pattern; added correction map in all three intent script templates.
