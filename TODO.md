# Home Automation — To-Do List

*Last updated: 2026-05-10*

---

## ✅ Completed

- **Piper TTS removed** — No longer in docker-compose.yml. Stack restarted, piper-data volume cleaned up. Google Translate (cloud) used for TTS.
- **Wyze plugs** — Working via ha-wyzeapi. GoodNight routine active.
- **Spotify Developer App** — Created at developer.spotify.com. Client ID + Client Secret in HA Spotify integration settings.
- **PlayArtistRadio intent** — Voice command e.g. "play Breeders radio" → RadioBrowser radio_mode with continuous queue. Added to `custom_sentences/en/music.yaml` + `configuration.yaml`.
- **PlayRadio disambiguation** — Fixed collision: PlayRadio now requires "station" keyword; PlayArtistRadio catches `{artist} radio`.
- **MLX Whisper (native STT)** — Installed at `wyoming-mlx-whisper/`. Model: `mlx-community/whisper-large-v3-turbo-q4`, port 7891. LaunchAgent: `com.wyoming.mlx-whisper.plist`. Used as STT fallback.
- **Docker Whisper container removed (2026-04-22)** — Service definition removed from `docker-compose.yml`. WhisperKit stable since 2026-03-29. Moved to `profiles: [stt]` in history for reference.
- **Voice pipeline auto-mute automation (6 automations)** — Always mutes amp on wake word; unmutes when recording ends; pauses/resumes if music was playing; pre-mute when music stops. Uses `input_boolean.voice_paused_music` helper.
- **WhisperKit native STT adopted (2026-03-29)** — Wyoming wrapper at `wyoming-whisperkit/`, port 7892, VAD_SILENCE_MS=700ms. Benchmarked 0.85s; real-world ~1.1s. Fallback: port 7891 (mlx-whisper). Config tag: `whisperkit-small-esphome-direct`.
- **voice-bench installed** — Daemon + dashboard at `http://localhost:7700`. Logs all voice commands to CSV with per-hop timing. LaunchAgent: `com.voice-bench.plist`.
- **Spotify rework (2026-03-28)** — Replaced Music Assistant's Spotify role with native librespot + `spotify_voice_assistant`. librespot registers as "Naboo" Connect device → PCM via ffmpeg → `serve_http.py` (port 8765) → naboo_media_player. spotcast removed (v4 broken). LA: `com.librespot.naboo.plist`.
- **FrigateDetector.app** — Added to macOS Login Items. Auto-starts on reboot.
- **Frigate car filters** — `min_area: 8000`, `min_score: 0.65`, `threshold: 0.8`; per-object `stationary.max_frames.car: 150` (~30s at 5fps). People: `default: 3000`.
- **Frigate zones** — `entrance`, `sidewalk`, `active_street` zones defined. `required_zones` set on alerts + detections.
- **Librespot watchdog (2026-03-30)** — `watchdog.sh` + `com.librespot.naboo-watchdog.plist` checks every 5 min: process alive + port 8765 open; restarts via `launchctl kickstart -k`. `SO_REUSEPORT` fix prevents port TIME_WAIT crash loop on rapid restarts.
- **Librespot stream failures fixed (2026-04-09)** — Stale `/tmp/librespot.fifo` artifact from removed FIFO architecture was causing crash loop. Fix: `rm -f /tmp/librespot.fifo` + plist reload. Permanent guard added to `librespot/run.sh` (runs on every pipeline start).
- **Frigate health check endpoint fixed (2026-04-09)** — Changed from bare TCP `nc -z` (421 HTTP 400s/week) to `curl -sf http://localhost:5000/api/version`. Noise eliminated.
- **Naboo silent after pipeline recovery fixed (2026-04-10)** — Added ffmpeg process check to `watchdog.sh`; added `naboo_unmute_on_play` automation for any naboo→playing transition while amp is muted.
- **voice-bench fixes (2026-04-10, 2026-05-06)** — Port 7700 LaunchAgent bootstrap fix; VAD early-trigger log lines no longer captured as transcript text; entity state seeding on WebSocket connect; stream type mid-session correction on `radio_active` state change.
- **Homeassistant memory raised to 768m (2026-04-08)** — Was 640m; Apr 2 report showed 78–80% usage. Raised to 768m.
- **Listening-phase timeout automation (2026-04-10/15)** — `voice_listening_timeout` fires persistent notification at 15s warn and 60s urgent. `assist_satellite.abort` never existed; automation fully rewritten. Hard restart deferred pending ESPHome firmware update.
- **spotcast removed (2026-04-22 / 2026-05-06)** — Removed via HACS. `custom_components/spotcast/` files manually deleted 2026-05-06 (HACS removal doesn't delete disk files). HA loads clean.
- **HA restart storm from HACS blocking (2026-04-30)** — Five HA crashes Apr 29–30. Root cause: HACS `startup_tasks()` blocked startup indefinitely on GitHub API call during DNS failure. Patched `custom_components/hacs/base.py` with `asyncio.wait_for(timeout=30)`. **Note:** recheck `base.py` after any HACS update; patch may be overwritten.
- **Gluetun DNS proxy + Wyze timeouts fixed (2026-04-30)** — Healthcheck now tests `nslookup cloudflare.com`; scheduler watchdog restarts gluetun within ~7 min on DNS failure. Unpinned `SERVER_HOSTNAMES`, added `DOT_PROVIDERS=cloudflare,quad9`. Self-healed confirmed on 2026-05-06 burst (~8 min recovery).
- **Tune VAD silence threshold (2026-04-29)** — `VAD_SILENCE_MS` reduced from 900ms → 700ms in `wyoming_whisperkit/handler.py` line 38. Monitor voice-bench; raise to 800ms if short commands ("Stop", "Off") get clipped.
- **WFMU mishearing corrections (2026-05-02)** — Added `wsmu`, `wsnu`, `wbmu`, `wfmyou` to `callsign` list in `custom_sentences/en/music.yaml`; added correction map in intent script templates.
- **Music Assistant removed (2026-05-03)** — Service removed from `docker-compose.yml`. Frees 640 MiB RAM. Radio playback unaffected (RadioBrowser via HA scripts directly).
- **Caddy → tailscale serve (2026-05-03)** — All 10 services accessible at `https://media.tail317990.ts.net:PORT`. No reverse proxy container needed.
- **Fix HA Frigate integration URL (2026-05-05)** — Was `https://frigate:8971` (HTTPS, wrong). Fixed to `http://frigate:8971` in `.storage/core.config_entries`. Eliminated `SSL: RECORD_LAYER_FAILURE` every ~80s.
- **Fix Tailscale remote HA access (2026-05-06)** — `tailscale serve` endpoints had `localhost:PORT` backends after May 5 Docker port migration. Re-ran all 10 endpoints with `--bg` + `192.168.1.70` backends. OPS_RUNBOOK updated with `--bg` warning.
- **Fix spotify_voice_assistant stale entity (2026-05-09)** — `play` and `podcast_play` in `spotify_voice_assistant/__init__.py` were hardcoded to removed MA entity. Fixed to `media_player.home_assistant_voice_0a3a76_media_player`. Committed `404cfc0`.
- **Librespot LaunchAgent enable fix (2026-05-09)** — After May 6 reboot, `com.librespot.naboo` wasn't registered with launchd. Applied `launchctl enable gui/$(id -u)/com.librespot.naboo`. Verify on next reboot.

---

## 🔲 Pending

- [ ] **Verify librespot survives Tuesday reboot (2026-05-12)** — `launchctl enable` applied 2026-05-09. After reboot: check `run.log` for a new `Starting librespot pipeline` entry. If missing, check `launchctl print gui/$(id -u)/com.librespot.naboo`.

---

## 🔲 Open Bugs (waiting on upstream)

- [ ] **Spotify coordinator MissingField crash loop** — HA's `spotifyaio` library fails to parse Spotify API responses since Spotify removed `GET /playlists/{id}/tracks` in Feb 2026. Error: `MissingField: Field "items" of type PlaylistTracks is missing in Playlist instance`. [GitHub #166884](https://github.com/home-assistant/core/issues/166884). HA 2026.5 shipped with no fix. Only triggers when browsing Spotify media via HA UI — not actively firing during voice commands. Watch HA 2026.6.

---

## 🔮 Future / Lower Priority

- [ ] **Investigate go-librespot as librespot replacement** — Go rewrite of the Spotify Connect protocol; ARM64 binary available; built-in HTTP control API (could replace serve_http.py); reports better long-term stability than C++ librespot. Goal: eliminate the heal loop, watchdog, and retry logic in spotify_resume.py.
- [ ] **Monitor small model accuracy (ongoing)** — `whisper-small-mlx-4bit` / WhisperKit small benchmarked well but needs real-world validation across voice diversity, proper nouns (WFMU, KEXP), and noisy conditions. Watch voice-bench dashboard for transcription errors.
- [ ] **voice-bench (no transcription) for radio commands** — P8/low. VAD early-trigger path produces two WhisperKit transcriptions per command; session finalizer races the slower result. Deferred — latency and hang tracking still work, transcription text unreliable for radio commands. Candidate for deprecation.
- [ ] **Frigate CoreML detection** — Apple Neural Engine path (currently using ZMQ via FrigateDetector.app)
- [ ] **HA System Monitor integration** — CPU/memory dashboard in HA
- [ ] **Centralized logging (Loki/Promtail)** — only if log-tailer + direct file reads become insufficient
