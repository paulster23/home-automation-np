# Streamdeck Scripts

## Rules

- Each time a `.sh` file is updated, create a new corresponding `.app` file using `osacompile`.
- Example: `osacompile -o kcrw.app -e 'do shell script "/Users/media/streamdeck/kcrw.sh"'`
- Must be run on the Mac (osacompile is macOS-only, not available in the Linux sandbox).
- Use `rebuild_apps.sh` to rebuild all `.app` files at once.

## Architecture

Stream Deck buttons trigger `.app` files (built with osacompile) which call `.sh` scripts in `/Users/media/streamdeck/`. Scripts source `~/.streamdeck_env` for credentials.

**`~/.streamdeck_env` contains:**
- `HA_URL=http://192.168.1.70:8123`
- `HA_TOKEN`
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`

**Naboo** is a Home Assistant Voice PE device used as a Spotify Connect speaker.
- HA media player entity: `media_player.home_assistant_voice_0a3a76_media_player`
- Spotify entity: `media_player.spotify_paulster23`
- Spotify Connect device ID: `0596f720dd52a9e2e2d0020d00931a1b91014e64`
- Spotify Connect device name: `Naboo`, type: `Speaker`

**Librespot** runs on the Mac Mini as three native macOS processes (NOT in Docker):
- `run.sh` — watchdog launcher: `/Users/media/containers/home-automation/librespot/run.sh`
- `librespot` binary — Spotify Connect receiver, registered as "Naboo"
- `serve_http.py` — pipes librespot audio out as HTTP stream on port 8765
- Full command: `librespot --name Naboo --device-type speaker --bitrate 320 --backend pipe --format S16 --onevent .../on_event.sh --disable-audio-cache --cache ~/.config/librespot --initial-volume 100 --zeroconf-port 5354`
- launchd labels: `com.librespot.naboo` (main), `com.librespot.naboo-watchdog`
- Restart safely with: `bash /Users/media/streamdeck/librespot_heal.sh` (kills process, watchdog auto-restarts)
- Config/scripts in: `/Users/media/containers/home-automation/librespot/`

**Speaker** is controlled via `switch.speaker` in HA. All scripts check speaker state and turn it on if off before playing.

## Scripts

### Radio stations (k* and w*)
`kcrw.sh`, `kexp.sh`, `wbgo.sh`, `wfmu.sh`, `wnyc.sh`, `wqxr.sh`
- POST to HA `media_player/play_media` with stream URL
- Check `switch.speaker` state, turn on if off
- Use `$HA_URL` and `$HA_TOKEN` from env

### Spotify
**`spotify_resume.sh` / `spotify_resume.py`**
- Refreshes Spotify token via refresh_token grant
- Fetches top 50 tracks (`/me/top/tracks?time_range=medium_term`), dedupes by artist
- Cycles through artists using `~/.streamdeck_spotify_idx` (index file, persists between runs)
- Turns on speaker immediately; starts Deezer playlist build in a background thread simultaneously
- Retries `PUT /me/player/play` up to 8 times (2s delay) waiting for Naboo to register
- On `NO_ACTIVE_DEVICE`: calls `PUT /me/player` (transfer) to activate Naboo, then retries play
- If playlist thread finishes before device comes online, plays full list in one shot (no stutter)
- If device comes online before playlist is ready, plays seed track first, then replaces queue with `PUT /me/player/play` using `position_ms` to resume without restarting the song
- Deezer: exact name match only; gets 25 artist radio tracks; parallel-matches to Spotify URIs (ThreadPoolExecutor, 8 workers)
- Final play call uses `PUT /me/player/play` with full `uris` list — atomically replaces queue (never use `POST /me/player/queue`, it appends and accumulates across button presses)

**`spotify_skip.sh` / `spotify_skip.py`**
- Refreshes token
- `POST /me/player/next?device_id=NABOO_DEVICE_ID`
- sleep 1
- HA `media_player/media_play` on `media_player.spotify_paulster23`

**`librespot_heal.sh`**
- Kills the librespot process by PID; watchdog (`com.librespot.naboo-watchdog`) auto-restarts it
- Waits up to 20s for a new PID to confirm restart
- Use when librespot is running but degraded (registered with Spotify but unresponsive)
- Do NOT use `launchctl kickstart -k` — requires elevated permissions and may silently fail

**`librespot_monitor.py`**
- Health check: detects when librespot is running but Spotify can't see Naboo in device list
- Skips restart if music is actively playing on Naboo (avoids interruption)
- Calls `librespot_heal.sh` when degradation is detected
- Installed as launchd agent: `com.streamdeck.librespot-monitor` (plist in streamdeck folder)
- Runs every 5 minutes via launchd (NOT via Cowork scheduled tasks — too much overhead)
- Logs to `/tmp/librespot-monitor.log`

### Celtics
`/Users/media/containers/playball/celtics.sh` — calls `playball.py --team Celtics` directly

## Known Issues / Notes

- Librespot streaming latency is 10-15 seconds (hardware/pipe backend, was 30+). Startup stutter may come from `serve_http.py` buffer filling — look at buffer size there if it needs improvement.
- Librespot degrades over time (loses Spotify Connect registration after repeated use). `librespot_monitor.py` heals this in the background every 5 minutes.
- `PUT /me/player/play` with `uris` list replaces queue atomically. Do NOT use `POST /me/player/queue` — it appends and persists across button presses.
- `PUT /me/player/play` returns `NO_ACTIVE_DEVICE` (404) when no Spotify session is active anywhere, even if the device is visible in `/me/player/devices`. Fix: call `PUT /me/player` (transfer) first to activate Naboo, then retry play.
- Both devices visible to Spotify: Naboo (`0596f720...`) and PS Macbook (`e9b2419431c77ba3699cf2ec8eb476db1f66f1c5`).
- Spotify `/recommendations` endpoint is deprecated for new apps (post Nov 2024) — use Deezer radio instead.
- Deezer exact-match required for artist search — fuzzy match returns wrong artists.
- osacompile requires macOS; cannot be run in Linux sandbox.
- POSIX ACLs can block script execution — fix with `chmod -N ~/streamdeck/*.sh && chmod +x ~/streamdeck/*.sh`.

## Music Recommendation Options (evaluated, not yet implemented)
- **Last.fm `artist.getSimilar`** — recommended drop-in for Deezer, free, no auth, better quality
- **Troi** (PyPI) — ListenBrainz-backed, best long-term option, requires scrobbling setup
- **Deej-A.I** — neural net, best for local audio files, less useful for Spotify streaming
- **LMS DSTM** — full playback server, doesn't fit current architecture
