# Home Automation — To-Do List

*Last updated: 2026-10-08 (weekly-docker-log-report)*

> **Structure rule (2026-07-28):** sections in order — Pending → Watching/deferred → Future → Completed (newest first, max ~10; older items go to `archive/TODO-completed.md` in this repo). **Scheduled-task appends must be ≤300 chars + a pointer** to the full report/TROUBLESHOOTING entry — no inline essays.
>
> **Trimmed 2026-10-01 (Paul's call, after quarterly-doc-audit):** done items moved verbatim to `archive/TODO-completed.md`; open items over 500 chars are one-line summaries here, full text verbatim in `archive/TODO-detail.md` under the § ID. Keep new items ≤300 chars + pointer.

---

## Pending

- [ ] **brookside mosquitto restarted ~10× in 7 d (4 on 10-07), exit 0, no watchdog heal — each one drops Frigate's MQTT.** Find the caller. See weekly-report-2026-10-08.html — (via weekly-docker-log-report 2026-10-08)
- [ ] **`np_porch_camera_back_online_page` timed out 86× (+18 `np_kuma_heartbeat`) during the porch outage; now 3–5/day.** If it climbs, add `continue_on_error: true`. See weekly-report-2026-10-08.html — (via weekly-docker-log-report 2026-10-08)

- [ ] **🟡 NP morning schedule — first live run 2026-10-10 08:00/09:00 (added 2026-10-09, Cowork).** Check the automation trace: both units heat ~69.8/high/both at 08:00, ~67.1/low/both at 09:00, no CHECK UNITS page. Kitchen Wi-Fi is the likely failure. See CONTEXT.md → NP morning schedule.

- [ ] **🟡 NP "Heading to NP" — first real test 10-10/11 (added 2026-10-05, Cowork).** Note when the iPhone Arrive prompt fires vs arrival time; confirm `np_heading_arrived` cancelled `timer.np_heading_window` (trace) and units held 68/high/both; tune the ~40 mi geofence radius. Open: summer behaviour (cool to 68?). See CONTEXT.md → NP "Heading to NP".

- [ ] **🟡 NEW 2026-10-04 — Face recognition — measure, train, then decide on detect resolution.** Live on front_window (see CONTEXT.md → Frigate). (1) Train Michelle + Broomhilda in Face Library → aim 20–30 images each, daylight, no IR. (2) After ~1 week read face sizes/scores in Recent Recognitions: if most faces < ~25 px, move `detect` to the main stream (scale person/car `min_area` ×4.5, check iGPU + 4 GiB cap) — record already pulls main, so no extra Wi-Fi. (3) Re-measure frigate mem vs new 4096m cap and `inference_speed` (14 ms right after enable vs 7–9 before). (4) Broomhilda high path not yet fired for real (low path + MQTT trigger verified with a test name).
- [ ] **🔴 NP porch cam RTSP down — Frigate ffmpeg crash loop, 5,132 crashes on 10-01** (132 on 09-27, 1,165 on 09-30); `192.168.2.34:554` refused. Paging is blind. Fix the lease/RTSP in NP UniFi, or set `enabled: false`. See weekly-report-2026-10-01.html — (via weekly-docker-log-report 2026-10-01) **2026-10-06 (Cowork): recurred** — ffmpeg exit/refused loop ran continuously 10-03→10-05 (~3,800 lines/day, 110-210/h) and stopped when the frigate container was recreated 10-05 22:23 ET; 0 errors in the 17 h since, porch 3.1 fps. A Frigate restart clears it; cause still unknown (camera RTSP server wedging?). Watch the next weekly log report before building an auto-restart. — **2026-10-08: NEAR-RESOLVED, and it was not just the restart.** Errors/day 5,529 (10-03) → 3,808 → 3,782 → 446 (10-06) → 17 (10-07) → 1 (10-08); clean 17 h, porch 3.0 fps. Two real fixes landed: `hwaccel_args: []` (CPU decode) on 10-05 and the 10-07 15:25 UTC restart carrying the YOLOv9-t/OpenVINO swap (`f710785`). No auto-restart needed — confirm clean next week, then CLOSE. See weekly-report-2026-10-08.html — (via weekly-docker-log-report 2026-10-08)**
  - **2026-10-05 (Cowork):** brookside-era crash loop was a different cause — VAAPI `hwdownload` failures, 2,180 crashes 10-03→10-05. Fixed with porch `hwaccel_args: []` (home-automation-np `1386af0`). The 10-01 Mac-era `192.168.2.34:554 refused` cause was not seen on brookside. Close this item once 48 h of porch logs show no crash loop. See TROUBLESHOOTING 2026-10-05.
- [x] **✅ DONE 2026-10-08: token in `secrets/ha-np.env` (HA_URL + HA_TOKEN, 600, gitignored); /api/ → 200.** ~~NP HA long-lived token missing on brookside~~ — `secrets/ha.env` there is Brooklyn's (`192.168.1.71`), so NP HA's API returns 401 and automation reloads need a container restart. Create a token in NP HA and write a separate `ha-np.env`. — (via Cowork 2026-10-05)
- [x] **✅ CLOSED 2026-10-06 (Cowork): not stale — an MCP quirk.** `unifi_list_clients` live (no `include_offline`) shows Porch online, -44 dBm, sinola 2.4, last_seen now; `search` + `include_offline=true` returns the historical /rest/user record whose status is computed from an old last_seen. Use the live list. ~~**`unifi-brookside` looks stale** — lists Porch offline since 10-04 02:00 ET and returns 0 events in 24 h while the camera streams at 3 fps. Check the MCP's controller/site config. — (via Cowork 2026-10-05)~~

- [ ] **HA windmillac integration failing and climbing — 120 errors/7 d** (`dashboard.windmillair.com` max retries), 15→30→35 a day 09-28→09-30, after the WAN settled. Re-auth or remove the component. — **2026-10-08: WORSE — 175 error lines/7 d (84+82+9) vs 120 at tagging; two unbroken weeks of `Max retries exceeded`, ~1/10th of this host's HA error volume. Re-auth, or remove the component if the vendor API is gone. See weekly-report-2026-10-08.html** — (via weekly-docker-log-report 2026-10-08)

- [x] **✅ DONE 2026-10-08: 32m on both hosts — brookside 742bbab, woodhull home-automation 2e10d22 (recreated 18:55, healthy, MQTT clients back).** ~~woodhull mosquitto cap 8->16 MiB — `OOMKilled=true`, now `RestartCount=1` (killed 10-01 03:14 UTC; cap still 8388608).** Set `mem_limit: 16m` and recreate on BOTH hosts — brookside carries the same 8 MiB cap. See weekly-report-2026-10-08.html — (via homelab-advisor 2026-09-30) (via weekly-docker-log-report 2026-10-08) → full text: `archive/TODO-detail.md` §H-001

- [ ] **NP porch: tighten the `yard` polygon above the porch rail.** Its lower edge IS the rail top, so a person standing at the rail (legs hidden) reads as in `yard`. Paging keys on the *first* zone so this is harmless today, but anything that later reads `yard` membership will misfire. Known gap either way: someone climbing the steps from out of frame enters `frontporch` first → note, not page. See TROUBLESHOOTING 2026-09-26. — (via Cowork 2026-09-26)

- [ ] **NP Serin dongles — weak Wi-Fi at the kitchen, marginal Govee in the living room (added 2026-09-25, Cowork; accepted by Paul until the NP network audit/upgrade, "a few weeks").** → full text: `archive/TODO-detail.md` §H-002

- [ ] **🔴 Frigate per-day recording volume jumped ~6× at the 0.18.0 upgrade (09-16).** — (via weekly-disk-health 2026-09-22) → full text: `archive/TODO-detail.md` §H-003

- [ ] **🟡 MEASURE `car.min_area` on the NP porch camera — the value in place is a PLACEHOLDER.** — (via Cowork 2026-09-20) → full text: `archive/TODO-detail.md` §H-004
  - **2026-10-05 readout (Cowork, brookside Frigate, events since 10-02 clean start; 09-28→10-01 only in the Mac archive):** 39 porch `car` events. **2 real** — a car on the gravel patch, zone `yard`, box ≈ x0.71 y0.33 w0.21 h0.17: area **9750** (10-02 04:35, score 0.70) and **11484** (10-02 15:41, 0.99, 16 min, snapshot confirms SUV). **37 false** — the porch pillar/rail corner read as a car, box centred ~(0.5,0.5), area **28,420–77,924**, score 0.70–0.84, no zone, mostly at night under IR (snapshots 10-04 12:36 and 23:48 confirm). No car pages found in ntfy over 96 h. **APPLIED 2026-10-05 10:17 on Paul's call (home-automation-np 073c6d2, Frigate restarted healthy, /api/config reads min 7500 / max 25000, HA receiving Frigate MQTT again by 10:17:51):** porch `car` `min_area: 7500` (≈20% under 9750) **and** `max_area: 25000` — removes all 37 rail false positives, keeps both real cars. Alternative: an object mask over the pillar/rail for `car`. Snapshots: infra/log-reports/np-car-snaps-20261005/.


- [ ] **🟡 NEW 2026-09-14 — no UPS at New Paltz.** `pmset -g ps` = AC only. A flicker is survivable (`autorestart 1`), but a brownout can wedge the engine mid-write, and when the UX7/ONT drop with it the ntfy page saying so never leaves the house. Small UPS on Mac + UX7 + ONT; USB signalling so macOS can shut down cleanly. On-site purchase/install; size for ~15 min.

- [ ] **Frigate records to `/srv/frigate` — woodhull's boot NVMe, not the 3.7 T `/srv/media`.** — (via weekly-disk-health 2026-09-15) → full text: `archive/TODO-detail.md` §H-006

- [ ] **🟡 Rebuild `voice-bench` on woodhull with a new `config_tag` — it has been dark since 2026-09-03 and its LaunchAgent was retired 09-04.** — (via Cowork 2026-09-04) → full text: `archive/TODO-detail.md` §H-007

- [ ] **🔵 Home-automation migration — Phase 3/4/5 remain. §10 #18 reboot survival: ✅ PASS 2026-09-04 13:42 ET.** — (via `infra/scripts/phase34-mac.sh` + `phase34-mac2.sh`, run by Paul; Cowork has no route to the Mac) (via Cowork 2026-09-04) → full text: `archive/TODO-detail.md` §H-008

- [ ] **🔴 ACTIVE — Naboo Spotify Connect / play_media investigation. READ THIS FIRST if starting a new session on this.** — (Settings → Devices & services → the Naboo device → Logs, or via the "..." menu — note: no "Enable debug logging" option was found on this HA version's device page, worth checking the ESPHome integration's own page instead) (via Cowork 2026-09-04, handoff written for a fresh session) → full text: `archive/TODO-detail.md` §H-009

- [ ] **`infra/log-reports/go-librespot*.log` stale since the 08-31 infra migration (log-tailer moved to woodhull, lost its mount into the Mac-local librespot log dir).** Use `home-automation/librespot/log/{librespot,stream,events,watchdog,run}.log` directly until re-wired (candidate: extend `log-tailer-native` on the Mac, same pattern already used for homeassistant/frigate/mosquitto). See TROUBLESHOOTING.md 2026-09-01. — (via Cowork 2026-09-01)

- [ ] **🔵 Migrate the home-automation stack (`homeassistant`, `mosquitto`, `frigate`) from `media` to `woodhull`.** — (via Cowork 2026-08-30, planned 2026-08-31, Phase 1 executed 2026-08-31, pre-cutover prep 2026-09-02, STT verdict + Phase 2 cutover 2026-09-03) → full text: `archive/TODO-detail.md` §H-010

- [ ] **switch.plug_1 (Wyze) still `unavailable` since 08-23 07:01 — deferred by Paul.** Confirmed offline in the Wyze app (physical/Wi-Fi, not HA/DNS). `switch.speaker` had the same issue and was fixed same day (power-cycled, back `on` 08-27 23:17 UTC) — plug_1 needs the same physical power-cycle whenever Paul wants that plug back; not urgent. See TROUBLESHOOTING.md 2026-08-27. — (via Cowork 2026-08-27)

- [ ] **Voice PE `0a3a76` esp32 crash — `Fault - IllegalInstruction` at `speaker_source_media_player:222`.** 2026-10-08: quiet — 27 lines/7 d (vs 4,320 on 09-29); still not reflashed. — (via homelab-advisor 2026-09-02) (via weekly-docker-log-report 2026-10-08) → full text: `archive/TODO-detail.md` §H-011

- [ ] **Rotate credentials left in git history — found 2026-08-09 by the repo's first full-history `gitleaks git` scan (4 findings).** → full text: `archive/TODO-detail.md` §H-012

- [ ] **stream_health logger writes bogus pipe_stall duration.** — (via homelab-advisor 2026-08-19) (via homelab-advisor 2026-09-02) → full text: `archive/TODO-detail.md` §H-013

- **Instrument the Naboo Voice PE for Wi-Fi drops (added 2026-07-22):** — (via Cowork) (closed via Cowork 2026-08-05) → full text: `archive/TODO-detail.md` §H-014

- **Reconnect Stream Deck to the relocated server (added 2026-07-14):** → full text: `archive/TODO-detail.md` §H-015

---

---

## 🔲 Pending  *(older / deferred)*

- [ ] **VAD end-of-speech / listening-timeout hangs skew voice latency (recurring 3rd week).** — (via homelab-advisor 2026-07-22) (via homelab-advisor 2026-09-02) → full text: `archive/TODO-detail.md` §H-016
- [ ] **stream_health correlator under-tags Mode A (pipe_stall → dropout).** — (via homelab-advisor 2026-07-22) (via homelab-advisor 2026-09-02) → full text: `archive/TODO-detail.md` §H-017
**Fix applied — Option 1 (2026-06-26, Cowork):** added `dns_opt: [timeout:2, attempts:5, rotate]` to the HA compose block (hardens c-ares retries/rotation; no new dependency, preserves the 2026-04-09 independent-DNS decision). ✅ Recreated via `./crestart -home` 14:27 ET — HA init 11.16s, wyzeapi/spotify clean, zero post-restart errors. **Still open:** confirm the aiodns timeout bursts actually drop over a full week (verification window short at apply time). See TROUBLESHOOTING 2026-06-26.
**Escalation if still bursting (Option 2):** point HA primary at the now-redundant AdGuard (`192.168.1.70`, keep 8.8.8.8 secondary) for caching — but also set AdGuard `cache_ttl_min` floor (~60–300s), since current `cache_ttl_min: 0` honors short Wyze/Spotify TTLs and blunts the cache benefit. Accepts a soft HA→AdGuard dependency. **UPDATE 2026-07-01 (via homelab-advisor): Jul 1 00:51, 07:51, 14:33 UTC cluster failures CONFIRMED — all three external upstreams (1.1.1.1, 8.8.8.8, 9.9.9.10) timed out simultaneously, which means Option 1's c-ares hardening is insufficient when Docker Desktop's network layer (vpnkit/gvisor) itself fails. Escalate to Option 2: point HA dns to AdGuard (192.168.1.70) + set AdGuard cache_ttl_min 60–300s. Claude Code/Cowork task.** **UPDATE 2026-07-02 (via weekly-docker-log-report): 3rd confirmed recurrence, 17:10–17:16 ET — AdGuard 100% upstream timeout (all of 1.1.1.1/8.8.8.8/9.9.9.10/149.112.112.10/9.9.9.9), gluetun VPN cycling ("VPN server crashed"), Sonarr/Radarr/Prowlarr connection-refused to gluetun, HA Wyze/WindmillAC DNS failures — all self-healed within ~5–6 min. Still on Option 1 only. Option 2 escalation still not applied.** **UPDATE 2026-07-02 (Cowork, later same session): Paul confirmed the recurring outages line up with his ISP dropping yesterday, not a Docker-layer bug — reframes root cause but the mitigation is the same. Applied the caching half of Option 2: `infra/adguard_conf/AdGuardHome.yaml` `dns.cache_ttl_min` 0 → 300 (5 min floor on all cached records, incl. short-TTL Wyze/Spotify), edited via Cowork (no Docker access in that session to restart). **UPDATE 2026-07-03 (Cowork): Paul restarted adguardhome. Verified via `infra/log-reports/adguardhome.log` — clean restart 19:13:35 ET, `dnsproxy: cache ttl override is enabled min=300 max=0` confirms the 300s floor is live, zero errors since. Caching half of Option 2 is DONE.** **UPDATE 2026-07-03 (Cowork, same session): applied the HA-side half too — `home-automation/docker-compose.yml` homeassistant `dns:` changed from `[1.1.1.1, 8.8.8.8]` to `[192.168.1.70 (AdGuard), 8.8.8.8 fallback]`; `dns_opt` (timeout:2/attempts:5/rotate) left as-is. Accepts the soft HA→AdGuard dependency already called out in the infra reverse-proxy lessons-learned notes. Option 2 escalation is now fully applied in config. **UPDATE 2026-07-03 (Cowork, same session): Paul recreated homeassistant. Verified via `infra/log-reports/homeassistant.log` — clean restart 19:21:05 ET, wyzeapy/windmillac coordinators set up with zero errors, zero `aiodns`/`ClientConnectorDNSError`/`NameResolutionError` in ~4 min post-restart (previously immediate on every restart). Two brief self-recovering Spotify API errors (19:22/19:23 ET, no DNS traceback) look like normal post-restart auth settling, not related to this change — quiet since 19:24:35. Option 2 (both halves — AdGuard cache floor + HA routed through AdGuard) is now fully applied and verified. Real test is the next actual ISP blip — watch the next weekly report for whether Wyze/Spotify/WindmillAC survive it without the aiodns timeout signature.** **UPDATE 2026-07-09 (via weekly-docker-log-report): ✅ CLOSED.** Verified through a week containing real ISP blips: aiodns/DNS errors now appear ONLY in 4 short clusters (Jul 7 ~01Z + 18Z, Jul 8 23Z, Jul 9 17Z — 56 lines total), each coinciding with a confirmed whole-upstream outage (AdGuard simultaneously lost ALL upstream types incl. bootstrap UDP; gluetun VPN crashed inside two of the same windows) and self-healing in minutes — vs constant bursty firing before. No standalone HA-side resolver issue remains; residual errors track genuine ISP outages (tracked as an infra item). — (via weekly-docker-log-report 2026-06-26; closed 2026-07-09)
- [ ] **MOVED TO NEW PALTZ 2026-09-08** — (2026-06-13, via Cowork) → full text: `archive/TODO-detail.md` §H-018
- [ ] **MOVED TO NEW PALTZ 2026-09-08** — (2026-06-13, via Cowork) → full text: `archive/TODO-detail.md` §H-019
- [ ] **MOVED TO NEW PALTZ 2026-09-08** — (2026-06-13, via Cowork) → full text: `archive/TODO-detail.md` §H-020
- [ ] **streamdeck librespot-monitor needs fixing or retiring (2026-06-13, NEW)** → full text: `archive/TODO-detail.md` §H-021
- [ ] **MOVED TO NEW PALTZ 2026-09-08** — (2026-06-15, via Cowork) → full text: `archive/TODO-detail.md` §H-022
- [ ] **go-librespot migration follow-ups (2026-06-11, via Cowork)** — (2026-06-11, via Cowork) → full text: `archive/TODO-detail.md` §H-023

---

---

## 🔲 Open Bugs (waiting on upstream)

- [ ] **Spotify coordinator MissingField crash loop** → full text: `archive/TODO-detail.md` §H-024

---

---

## 🔮 Future / Lower Priority

- [ ] **🔵 NP/BK decoupling — low priority (raised 2026-09-23, filed 2026-09-26).** — (via Claude Code 2026-09-26) → full text: `archive/TODO-detail.md` §H-025
- [ ] **🔵 NP option 6 has a single resolver.** If AdGuard on `media` dies, **all NP DNS fails**. Decide on a secondary (e.g. the gateway `192.168.2.1` or Quad9), knowing it would **bypass filtering whenever it wins**: clients race resolvers rather than fail over, as 2026-09-26 just demonstrated for Tailscale. The mirror of Brooklyn's accepted single-`.71` decision (`CLAUDE.md` rule 5). Revisit when the NP IT12 lands. — (via Claude Code 2026-09-26)
- [ ] **Investigate go-librespot as librespot replacement** — Go rewrite of the Spotify Connect protocol; ARM64 binary available; built-in HTTP control API (could replace serve_http.py); reports better long-term stability than C++ librespot. Goal: eliminate the heal loop, watchdog, and retry logic in spotify_resume.py.
- [ ] **Monitor small model accuracy (ongoing)** — `whisper-small-mlx-4bit` / WhisperKit small benchmarked well but needs real-world validation across voice diversity, proper nouns (WFMU, KEXP), and noisy conditions. Watch voice-bench dashboard for transcription errors.
- [ ] **voice-bench (no transcription) for radio commands** — P8/low. VAD early-trigger path produces two WhisperKit transcriptions per command; session finalizer races the slower result. Deferred — latency and hang tracking still work, transcription text unreliable for radio commands. Candidate for deprecation.
- [ ] **Frigate CoreML detection** — Apple Neural Engine path (currently using ZMQ via FrigateDetector.app)
- [ ] **HA System Monitor integration** — CPU/memory dashboard in HA
- [ ] **Centralized logging (Loki/Promtail)** — only if log-tailer + direct file reads become insufficient

---

## ✅ Completed

- [x] **Size the NP box before NP Frigate comes back — ✅ DONE 2026-10-08.** NP Frigate is live on brookside (porch 3.0 fps / 6.4 detect fps) on a 16 GB / 221 GB host sitting at 11% disk with 12.5 GB RAM available, up 5 d. Sizing is comfortable. (was §H-005) — (via weekly-docker-log-report 2026-10-08)


- [x] **Deploy stats-collector on brookside — ✅ DONE 2026-10-05.** Native cron `5 * * * *` runs infra/stats-collector.sh → memory_reports/hourly_stats.csv (verified, 5 containers). Mac collector already retired. See budget-report-2026-10-05.md §6 — (via weekly-resource-budget 2026-10-05)

- [x] **Trim TODO.md — ✅ DONE 2026-10-01 (Cowork).** 110→19 KB: done items moved verbatim to `archive/TODO-completed.md`, long open items summarized with full text in `archive/TODO-detail.md`; line-preservation check passed. — (via quarterly-doc-audit 2026-10-01)

- [x] **✅ DONE 2026-10-01 — front_window iGPU hwaccel decode errors resolved.** 0 `Failed to sync surface` / `hwdownload Failed to download frame` across the full 7-day window. See weekly-report-2026-10-01.html

- [x] **✅ DONE 2026-10-01 — NP np_kuma_heartbeat timeouts fixed.** Failures/day 5/4/5/0/1/0/0/0 (09-24→10-01) over 2,027 runs — 0 in the last 3 days vs 116/7 d before the 09-28 timeout 10→30 s + continue_on_error change. See weekly-report-2026-10-01.html

- [x] **✅ DONE 2026-10-01 — front_window ffmpeg crashes resolved.** 26 crashes in 7 d, all inside 02:00:03–02:00:43 ET on 09-27 (the weekly restart cron), 0 `No route to host`, 192.168.1.33 pings clean at 35 ms. See weekly-report-2026-10-01.html

- [x] **Frigate drift — weekly restart cron is now the durable fix. ✅ DONE 2026-09-28.** woodhull crontab `30 3 * * 0 docker restart frigate` is live and fired Sun 09-27 (frigate 99.1% → 48.6% of 3 GiB, on 0.18.0, oom_kill=0). Carried 3+ / featured. See budget-report-2026-09-28.md — (via weekly-resource-budget 2026-09-28)

- **✅ DONE 2026-09-26 (Claude Code) — NP DNS off the BK resolver.** Tailscale admin → DNS → *Override DNS servers* → **off**. NP now resolves through its own AdGuard via option 6 (`192.168.2.70`); verified on `PS-Macbook` at NP: default resolver `192.168.2.70`, `doubleclick.net` → `0.0.0.0`, MagicDNS still answers. `TROUBLESHOOTING.md` 2026-09-26.

- **✅ DONE 2026-09-24 — Brooklyn HA no longer references the missing `switch.plug_2`.** Zero occurrences in 7 days of woodhull `homeassistant` logs (was 4). Closed by weekly-docker-log-report 2026-09-24.
- **✅ DONE 2026-09-23 — Frigate upgraded to 0.18.0 stable (09-16), the release with per-object `max_frames`.** 0.18-stable-watch item closed; `ghcr.io/blakeblackshear/frigate:0.18.0` running healthy on woodhull. Caveat: per-day recording volume jumped ~6× at the upgrade — tracked separately as the open Pending item. (via homelab-advisor 2026-09-23; orig homelab-advisor 2026-08-26)
- **✅ DONE 2026-09-23 — Brooklyn HA upgraded past 2026.8 to 2026.9.0.** 2026.8-evaluation item closed; woodhull `homeassistant` reports 2026.9.0, healthy. (via homelab-advisor 2026-09-23; orig homelab-advisor 2026-09-02)

- **✅ DONE 2026-09-14 (Cowork) — NP Home Assistant liveness heartbeat → Uptime Kuma.** Closes the gap where a dead HA read as healthy: Kuma monitor 35 pings the *host*, and the Mac stays green while the container is stopped or wedged — which is exactly when freeze protection is not running. `np_climate_entity_unavailable` cannot cover it; a dead HA runs no automations. **Built:** Kuma push monitor **36 `NP · Home Assistant · heartbeat`** in group 34 `! New Paltz`, interval 300 / retry 300 / maxretries 1 → DOWN after ~10 min of silence, notification 3 (`ntfy · homelab`) bound. Created by direct sqlite insert with Kuma stopped (no REST API for monitor creation), row cloned from push monitor 33; backup `uptime-kuma_data/kuma.db.bak-20260914-hb`. HA side: `rest_command.kuma_heartbeat` in `configuration.np.yml` (copied to `configuration.yaml`) + automation `np_kuma_heartbeat` in `automations.yaml` — `time_pattern` `/5` **plus** an `homeassistant.start` trigger so the monitor recovers in seconds after a restart instead of waiting out the cycle. Uses `http://192.168.1.71:3001` — the same LAN path `rest_command.ntfy` uses, so **no `tailscale serve` and no `RouteAll` change were needed**. Deliberately unconditional: it reports HA is *alive*, never that HA is *happy* — gating it on another automation's state would give one alert two meanings. `msg` carries `freeze=<state> units=<count>` as context only. **Verified:** manual push `{"ok":true}`; beats unbroken at :30 :35 :40 :45 through three later Kuma restarts; HA restart clean, **0 ERROR**, `Initialized trigger NP · Kuma heartbeat`; start-trigger beat at 15:20:12 and the first scheduled beat at **15:25:00 exactly**, both `freeze=on units=0` (`units=0` is correct — the Serin dongles are not flashed yet). ⚠️ **Its paging path was dead until the same day:** every push/ping/port monitor had an empty `url`, which made ntfy reject the whole notification — see the ntfy empty-url entry in `infra/TODO.md`.

- **HA Voice PE (0a3a76) firmware updated 26.4.0 → 26.6.0 — ✅ DONE 2026-07-29 (Cowork, with Paul).** The recurring errno=128 flapping + esp32 crash traced to old firmware; repeated WiFi OTAs to 26.6.0 kept failing mid-download (low heap). Fixed by USB-C reflash to 26.6.0 (ESPHome 2026.6.0). One gotcha: it boot-looped while still on the laptop (`rst:0x15 USB_UART_CHIP_RESET` / `Reset Reason: USB peripheral`) — moving it to a wall USB adapter cleared it. Post-move: 25+ min stable, no resets, boot-attempt counter reset, no reconnect churn; voice verified ("What time is it?" → correct). Note HA is already on 2026.7.4. **Residual (cosmetic, not this bug):** the once-a-minute errno=128 socket-close is the uptime-kuma `Naboo Voice PE (ESPHome API)` TCP port monitor probing 192.168.1.47:6053 every 60s (bare TCP connect, no noise handshake → device logs Accept+CONNECTION_CLOSED). Harmless. Plan: drop redundant ping monitor `Voice PE (Naboo satellite)`, slow the port monitor 60s→300s (do via Kuma UI). — (via Cowork 2026-07-29)

Older completed items: `archive/TODO-completed.md`.
