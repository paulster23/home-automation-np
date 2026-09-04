# Streamdeck Scripts

> **Location (since 2026-06-09):** canonical path is `~/containers/home-automation/streamdeck/`, part of the home-automation repo. `~/streamdeck` is a symlink here — launchd plists, .app bundles, and Stream Deck button configs all reference the symlink path, so both paths below remain valid. Never delete the symlink.

## Rules

- Each time a `.sh` file is updated, create a new corresponding `.app` file using `osacompile`.
- Example: `osacompile -o kcrw.app -e 'do shell script "/Users/media/streamdeck/kcrw.sh"'`
- Must be run on the Mac (osacompile is macOS-only, not available in the Linux sandbox).
- Use `rebuild_apps.sh` to rebuild all `.app` files at once.

## Architecture

Stream Deck buttons trigger `.app` files (built with osacompile) which call `.sh` scripts in `/Users/media/streamdeck/`. Scripts read credentials from `~/containers/home-automation/secrets/ha.env` and `secrets/spotify.env` (the older `~/.streamdeck_env` path is stale — verified 2026-09-04).

**`secrets/ha.env` + `secrets/spotify.env` contain:**
- `HA_URL=http://192.168.1.71:8123` (was `.70`; repointed 2026-09-04 when HA moved to woodhull — the Mac's HA is gone, so `.70` meant every button silently failed)
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

## Home Assistant Stream Deck plugin (AC control) — added 2026-06-26

Three buttons that control the Windmill AC (`climate.windmill_ac`) via the **cgiesche Home Assistant** Stream Deck plugin (github.com/cgiesche/streamdeck-homeassistant, v3.7.x). The plugin talks to HA directly over WebSocket — unlike the radio/Spotify buttons it does NOT call a `.sh`/`.app` script. Live temperature display is the reason for using the plugin (a script-based button can't render dynamic state on the key face).

**Location:** dedicated **page 4** of the Default Profile on the Stream Deck Mini (no folder — was a folder on page 3 until 2026-06-26, moved out via right-click Copy → Paste, which preserves full button config). Top row reads `−  72°  +`; the toggle is the middle `72°` key (shows set temp when on, `⏻` when off). Bottom-left is an auto-added "Previous page" key. Reached from home by pressing the "›" (Next page) keys through pages 2→3→4 (page 3's top-right "›" leads to page 4). Page-nav keys use Stream Deck's built-in Next page / Previous page actions, which auto-populate when a page is added.

**Plugin connection (Global Settings, shared by all keys):**
- Server URL: `http://192.168.1.71:8123`
- Access Token: HA long-lived token (same value as `secrets/ha.env` HA_TOKEN). Paste manually — never type tokens via automation.

**Plugin gotchas (learned the hard way):**
- Action type used is **Entity (generic)**.
- "Custom title" does NOT render on the key face. Use **Custom labels** (Appearance tab) — up to 4 lines, nunjucks templates — to draw text on the button.
- **Must click "Save configuration"** after editing each key's Appearance and Short Press. Unsaved per-key changes are silently discarded when you switch keys.
- Server URL only persists once focus is committed (type URL, then Tab).
- **Label size/position (to fill the key face, not just the top):** Custom labels render top-anchored and small by default. Two levers in Appearance → Custom labels: (1) **Label font size** slider — set to ~68px (max ~80px) for a single big glyph on the 80px Mini keys; (2) **vertical centering** — labels stack top→middle→bottom by line, so prefix the label text with a blank line (a leading newline) to push the glyph to the middle. All three AC buttons use a leading blank line + 68px. For the toggle, the newline goes before the `{% if %}` template.

**Button configs:**

| Key | Appearance | Short Press |
|---|---|---|
| Toggle (page 4, top-middle) | Entity `climate.windmill_ac`; Custom labels ON, **36px**. Snowflake `❄️` on line 1, then the state template on line 2: set temp (e.g. `72°`) when on, power glyph `⏻` when off. `❄️` renders in colour (blue); marks the key as the AC. | Domain `climate`, Service `set_hvac_mode`, Entity `climate.windmill_ac`, Service Data JSON toggles mode: `auto` when currently off, `off` otherwise (Jinja2 in `{% raw %}…{% endraw %}`). |
| Temp down (page 4, top-left) | Icon Source = Hide; Custom labels = leading blank line + heavy bar `━` (U+2501) at **72px** | Domain `script`, Service `windmill_temp_down` (→ `script.windmill_temp_down`) |
| Temp up (page 4, top-right) | Icon Source = Hide; Custom labels = leading blank line + heavy cross `✚` (U+271A) at **72px** | Domain `script`, Service `windmill_temp_up` (→ `script.windmill_temp_up`) |

Glyph notes: plain `+`/`−` text looked too small/thin even at max font, so the temp keys use heavy white text glyphs `✚`/`━` (big and bold). Avoid the emoji `➕`/`➖` — this plugin renders them as a dull monochrome grey (nearly invisible on the black key), whereas `❄️` does render in colour.

The temp buttons reuse existing HA scripts (`scripts.yaml`: `windmill_temp_up` / `windmill_temp_down`), which clamp to the AC's `min_temp`/`max_temp` and step ±1°. `ON = auto` hvac mode (Paul's choice). Service Data JSON left at the plugin's default placeholder on the script buttons is harmless — scripts ignore unknown variables.

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
