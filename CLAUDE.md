# Home Automation Stack

Containers: mosquitto, frigate, homeassistant (see `CONTEXT.md` for the deep reference: voice pipeline, automations, ESPHome, Frigate). Work tracking: `TODO.md`.

Root context (hard rules, port map, repo layout) auto-loads from `../CLAUDE.md`.

## Music system (Naboo / Spotify / Stream Deck)

All of it lives in this repo: `streamdeck/` (button scripts — **read `streamdeck/CLAUDE.md` before touching anything there**) and `librespot/` (Spotify Connect receiver "Naboo" + watchdog + HA webhook event hook). Native macOS processes, not Docker. `~/streamdeck` is a symlink here — launchd plists and .app bundles depend on it; never delete it.

## Repo gotchas

- `homeassistant/` is gitignored; key config files are force-tracked (`git add -f`): `automations.yaml`, `configuration.yaml`, `custom_sentences/`.
- `.claude/settings.json` denies reads into frigate storage/DBs, whisper models, voice-bench, and HA's runtime DB — that's the fix for Claude timing out on this repo's 35 GB. If you legitimately need one of those paths, ask Paul rather than editing the deny list.
- `voice-bench/` is a separate project (964 files) that happens to live here; candidate for its own repo.
- Runtime logs (`librespot/log/`, `voice-bench/log+data/`, `wyoming-whisperkit/log/`, `streamdeck/*.log`) are gitignored — read them for diagnosis, never commit them.
- `streamdeck/spotify_resume.last.log` captures the last button press — check it when a button "doesn't work".
