# Home Automation — To-Do List

*Last updated: 2026-03-15*

---

## ✅ Completed

- **Piper TTS removed** — No longer in docker-compose.yml. Stack restarted, piper-data volume cleaned up. Google Translate (cloud) used for TTS.
- **Wyze plugs** — Working via ha-wyzeapi. GoodNight routine active (`good night`, `bedtime`, etc.).
- **Spotify Developer App** — Created at developer.spotify.com. Client ID + Client Secret in MA's Spotify provider settings. Faster search via dev token.
- **PlayArtistRadio intent** — Voice command e.g. "play Breeders radio" → MA radio_mode with continuous queue. Added to `custom_sentences/en/music.yaml` + `configuration.yaml`.
- **PlayRadio disambiguation** — Fixed collision: PlayRadio now requires "station" keyword; PlayArtistRadio catches `{artist} radio`.
- **MLX Whisper (native STT)** — Installed at `/Users/media/containers/home-automation/wyoming-mlx-whisper`. Model: `mlx-community/whisper-small.en-mlx`. Port 7891. M1 GPU/Neural Engine. ~1-2s transcription (was 13-22s). Launch Agent: `~/Library/LaunchAgents/com.wyoming.mlx-whisper.plist`.
- **Docker Whisper container stopped** — `whisper` container stopped, freeing ~768 MB RAM + 2 CPUs. Can be restarted with `docker compose up -d whisper` if needed.
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

---

## 🔮 Future / Lower Priority

- [ ] Reverse proxy (Caddy/Nginx) — HTTPS + friendly names (e.g. `emby.local`) for all UIs
- [ ] Centralized logging (Loki/Promtail) — only if log-tailer + direct file reads aren't enough
- [ ] HA System Monitor integration — CPU/memory dashboard in HA
- [ ] Network isolation for media stack — separate `download-net` and `media-net` bridge networks
- [ ] Move speedtest-tracker APP_KEY to secrets file
- [ ] Tailscale for remote access — access services away from home without port forwarding
- [ ] Frigate CoreML detection — Apple Neural Engine path (currently using ZMQ via FrigateDetector.app)
