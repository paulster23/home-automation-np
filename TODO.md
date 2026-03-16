# Home Automation — To-Do List

*Last updated: 2026-03-16*

---

## ✅ Completed

- **Piper TTS removed** — No longer in docker-compose.yml. Stack restarted, piper-data volume cleaned up. Google Translate (cloud) used for TTS.
- **Wyze plugs** — Working via ha-wyzeapi. GoodNight routine active (`good night`, `bedtime`, etc.).
- **Spotify Developer App** — Created at developer.spotify.com. Client ID + Client Secret in MA's Spotify provider settings. Faster search via dev token.
- **PlayArtistRadio intent** — Voice command e.g. "play Breeders radio" → MA radio_mode with continuous queue. Added to `custom_sentences/en/music.yaml` + `configuration.yaml`.
- **PlayRadio disambiguation** — Fixed collision: PlayRadio now requires "station" keyword; PlayArtistRadio catches `{artist} radio`.
- **MLX Whisper (native STT)** — Installed at `/Users/media/containers/home-automation/wyoming-mlx-whisper`. Model: `mlx-community/whisper-large-v3-turbo`. Port 7891. M1 GPU/Neural Engine. ~2s transcription in quiet (was 13-22s with Docker). Launch Agent: `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist`.
- **Docker Whisper container stopped** — `whisper` container stopped, freeing ~768 MB RAM + 2 CPUs. Moved to `profiles: [stt]`; restart with `docker compose --profile stt up -d whisper`.
- **Voice pipeline auto-pause automation** — Two automations in `automations.yaml`: pauses `media_player.naboo_media_player` when wake word fires, resumes after pipeline completes. Uses `input_boolean.voice_paused_music` helper to track state.
- **whisper-small.en tested and rejected** — Tested `mlx-community/whisper-small.en` (2026-03-15). Transcription accuracy not acceptable. Reverted to `whisper-large-v3-turbo`.
- **FrigateDetector.app** — Added to macOS Login Items. Auto-starts on reboot.
- **Frigate car filters tightened** — `min_area: 8000`, `min_score: 0.65`, `threshold: 0.8` in `frigate/config.yml`.
- **Frigate stationary filtering** — `threshold: 50`, `interval: 50`, `max_frames.default: 3000` in place.
- **Frigate zones** — `entrance`, `sidewalk`, `active_street` zones defined. `required_zones` set on alerts + detections.

---

## 🔲 Pending

### Frigate: per-object max_frames for car
Frigate 0.17 only supports the `default` key under `max_frames` — per-object keys (e.g. `car: 150`) cause a schema validation error. Options:
- **Wait:** Check if Frigate 0.18+ restores per-object support
- **Workaround:** Set `max_frames.default` to a lower value (e.g. 500) to affect all objects — trade-off is people also stop tracking sooner

### Spotify voice: optional SpotifyPlus
SpotifyPlus via HACS would unlock advanced queue management and richer search. Low priority — current MA + radio_mode setup is working well.

### Voice pipeline latency optimization
Profiling results (2026-03-15, model: `whisper-large-v3-turbo`):
- "What time is it" (quiet): **8.4s total**, Whisper 2.44s
- "Play the Replacements" (KEXP playing): **20.4s total**, Whisper 9.88s
- "Play KCRW radio station" (music starting): **13.3s total**, Whisper 1.98s
- "Stop" (KCRW blasting): **54.5s total**, Whisper 47.8s, WRONG transcription

Remaining optimizations to try:
- [x] **Tune VAD silence detection threshold** — ✅ Set `select.home_assistant_voice_0a3a76_finished_speaking_detection` to **aggressive** in HA UI (2026-03-16). Options: default/relaxed/aggressive. Aggressive cuts ~0.5-1s off each command. Revert to "default" if it clips mid-sentence.
- [ ] **Try other Whisper models** — `whisper-small.en` already rejected. Consider `whisper-medium.en` or `distil-whisper-large-v3` as middle ground between speed and accuracy.
- [x] **Fix MLX Whisper LaunchAgent plist** — ✅ Fixed model (`whisper-small.en-mlx` → `whisper-large-v3-turbo`) and log paths (`/tmp/` → `wyoming-mlx-whisper/log/`) in `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist` (2026-03-16). Reload with `launchctl unload && launchctl load` to apply.
- [x] **Test auto-pause automation** — ✅ Confirmed working 2026-03-16. Music pauses on wake word, resumes after pipeline completes.
- [x] **Add "Stop" as a standalone voice command** — ✅ Added bare "stop" + "shut it off" to `custom_sentences/en/music.yaml` StopMusic intent (2026-03-16).
- [x] **Remove debug logging from HA** — ✅ Removed `logger:` block from `configuration.yaml` (2026-03-16).
- [x] **Disable wake sound** — ✅ Toggle off `switch.home_assistant_voice_0a3a76_wake_sound` in HA UI (2026-03-16). Saves ~0.7s per interaction.

---

## 🔮 Future / Lower Priority

- [ ] Reverse proxy (Caddy/Nginx) — HTTPS + friendly names (e.g. `emby.local`) for all UIs
- [ ] Centralized logging (Loki/Promtail) — only if log-tailer + direct file reads aren't enough
- [ ] HA System Monitor integration — CPU/memory dashboard in HA
- [ ] Network isolation for media stack — separate `download-net` and `media-net` bridge networks
- [ ] Move speedtest-tracker APP_KEY to secrets file
- [ ] Tailscale for remote access — access services away from home without port forwarding
- [ ] Frigate CoreML detection — Apple Neural Engine path (currently using ZMQ via FrigateDetector.app)
