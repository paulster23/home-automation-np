# Home Automation — To-Do List

*Last updated: 2026-03-17*

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
- [ ] **Fix "Stop" misheard as "Pause"** — distil-whisper-large-v3 is better but may still misfire on very short words. Option: add "pause" as a `StopMusic` alias in `custom_sentences/en/music.yaml`.

---

## 🔮 Future / Lower Priority

- [ ] Reverse proxy (Caddy/Nginx) — HTTPS + friendly names (e.g. `emby.local`) for all UIs
- [ ] Centralized logging (Loki/Promtail) — only if log-tailer + direct file reads aren't enough
- [ ] HA System Monitor integration — CPU/memory dashboard in HA
- [ ] Network isolation for media stack — separate `download-net` and `media-net` bridge networks
- [ ] Move speedtest-tracker APP_KEY to secrets file
- [ ] Tailscale for remote access — access services away from home without port forwarding
- [ ] Frigate CoreML detection — Apple Neural Engine path (currently using ZMQ via FrigateDetector.app)
