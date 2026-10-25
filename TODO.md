# Home Automation — To-Do List

*Last updated: 2026-10-24 (fix-high-issues)*

> **Structure rule (2026-07-28):** sections in order — Pending → Watching/deferred → Future → Completed (newest first, max ~10; older items go to `archive/TODO-completed.md` in this repo). **Scheduled-task appends must be ≤300 chars + a pointer** to the full report/TROUBLESHOOTING entry — no inline essays.
>
> **Trimmed 2026-10-01 (Paul's call, after quarterly-doc-audit):** done items moved verbatim to `archive/TODO-completed.md`; open items over 500 chars are one-line summaries here, full text verbatim in `archive/TODO-detail.md` under the § ID. Keep new items ≤300 chars + pointer.

---

- [ ] **NP pipe heat cable (Paul, 2026-10-20; was "heat pads" 10-18).** BOUGHT 2026-10-23: HEATIT JHSF 24 ft (on 37 F / off 50 F, self-regulating, own thermostat). **2026-10-25 (Paul): no smart plug — it switches itself.** Plug 0x...2796 became np_lamp_2; packages/np_heat_cable.yaml and the plug step in np_freeze_protection removed (db2edd1). Remaining: install on the wall-entry -> tank tee -> filter run (GFCI outlet), ice-pack test. Plan: project doc `claude/NP_WINTER_FREEZE_PLAN.md`.
- [ ] **NP winter physical checks - visit Thu 2026-10-22 (Paul).** (a) unused hydronic baseboard loop + boiler: drained or glycol? (b) hose bibs: close interior valve, drain, disconnect hoses; (c) bulkhead + basement window weatherstrip; (d) outdoor split units clear of snow line, drip cannot ice under them; (e) water heater type; (f) photo of the wall-entry -> pump -> filter run for heat-cable sizing. Plan: `claude/NP_WINTER_FREEZE_PLAN.md`.
- [ ] **Buy 3+ SNZB-02P for freeze spots:** wall entry (separate from pump/valve), kitchen-sink cabinet, bathroom exterior wall. Add each to `np_freeze_protection` trigger + device watchdog. (Paul, 2026-10-20)
- [ ] **NP music, next visit (Paul, 2026-10-20): Music Assistant on brookside + an ESP32 squeezelite-esp32 bridge per BT speaker** (I2S DAC + line-in for receivers). Before: list speaker/receiver models + rooms, buy ESP32s, add-service resource estimate. On site: flash, pair, expose to HA. Control: phone (MA panel in HA app) now, touchscreen later; no Zigbee remote needed. Paul rejected Naboo for this.

## Pending

- [ ] **brookside frigate: `back` record role 404s.** 25× `Error opening input file rtsp://...h264Preview_01_main` + 13× `Server returned 404 Not Found`; main stream was dropped 06-15. Point record at the sub stream. See weekly-report-2026-10-22.html §M4.
- [ ] **brookside adguardhome-dns2 missed the 10-07 hardening.** Still 2 dead IPv6 bootstrap entries + `upstream_timeout: 10s` vs woodhull's IPv4-only/15s. 0 errors today; latent flap-amplifier on NP's primary resolver. Keep file root:root 600. See weekly-report-2026-10-22.html §M3.
- [ ] **brookside HA: 29 `'value_json' is undefined` template errors** from an empty MQTT payload (zigbee2mqtt topic named in a 3rd warning). Guard the value_template. New since Z2M landed 10-16. See weekly-report-2026-10-22.html §M8.
- [ ] **NP leak shutoff — BUILT 2026-10-23, end-to-end wet test pending (Paul at NP).** `packages/np_leak_shutoff.yaml`: wet → close main (1 retry, low 'confirmed' note / urgent 'did not confirm'), lockout + no auto-reopen (`script.np_valve_reopen`), startup re-check, 2 h bypass, device watchdog (`sensor.np_leak_system_problems`, Z2M last_seen enabled), monthly exercise 1st Sat 10:00 when occupied. Valve is tight and the T1 can twist on the pipe — Paul may back the exercise off. Test: open a tap, wet one sensor → valve closes, tap stops, pages arrive; dry, run `script.np_valve_reopen`. Deferred (Paul): pump-side leaks (upstream of the T1) are page-only. Plan: project doc `claude/NP_LEAK_AUTOMATIONS_PLAN.md`.
- [ ] **Zigbee: can basement devices reach the coordinator directly?** Coordinator (SLZB-06MU) sits on the floor of the closet directly above the basement; the floor is thin. 10-19 all 4 leak sensors + valve parent on basement plugs (map: zigbee2mqtt/data/networkmap-2026-10-19-post-unplug.json). Test on a visit: unplug BOTH basement plugs, wait ~10 min, confirm every leak sensor + np_valve_main re-announces, keeps checking in (~2 min) and that a valve OFF/ON command acks; take a network map for direct-link LQIs; replug. Decides whether the basement plugs are redundancy or a single point of failure. (Paul 2026-10-19)
- [x] ~~Z2M: leak sensors report powerSource Mains → falsely offline~~ — resolved 10-16 by fw v73 on all four (Battery, passive availability). (closed 2026-10-19)
- [ ] **Z2M: decide coordinator location from the network map once devices are in final spots** (Ethernet run to the house centre/basement vs keep the closet). Valve currently routes via plug …1765, LQI 122. 
- [ ] **Buy remaining sensors:** 4 leak (kitchen sink, dishwasher, each bathroom) + 5 temp. Sinopé TH1300ZB floor-heat thermostat still waiting for restock. See `claude/NP_SAFETY_SENSORS_PLAN.md`.


- [ ] **Watch brookside frigate drift — 46%/67% of 3 GiB, +11.6 half-over-half (young series).** No restart cron here; if it climbs toward cap over 1–2 wk add woodhull's weekly `docker restart frigate`. See budget-report-2026-10-12.md §6 — (via weekly-resource-budget 2026-10-12) — carried over 1x (2026-10-19: avg 50%/peak 57% of 3 GiB, +6.1 — peak down from 67%, slope halved, not climbing to cap; see budget-report-2026-10-19.md §2)

- [ ] **`np_porch_camera_back_online_page` timed out 86× (+18 `np_kuma_heartbeat`) during the porch outage; now 3–5/day.** If it climbs, add `continue_on_error: true`. See weekly-report-2026-10-08.html — (via weekly-docker-log-report 2026-10-08) — **carried over 1× (2026-10-15): NOT improving. Kuma #36 `NP · HA · heartbeat` went Pending on all 8 days, 26–54/day (275 Pending + 9 Failing). `continue_on_error: true` still unapplied; also widen #36's window 300→600 s. See weekly-report-2026-10-15.html §M1.** — **2026-10-21 (advisor): paging now mitigated by kuma-np-gate (infra 98ea391, 10-18) — NP Kuma group held in maintenance during BK WAN down, so #36/#46 stop paging on blips. continue_on_error + 300→600 s window still open (trims the Pending noise itself). See advisor-2026-10-21.html §M1.** — **carried 2× (2026-10-22): neither half applied — kuma.db monitor 36 still `interval=300/retry=300`, `continue_on_error` only in the 09-14 backup clone. 266 Pending + 8 Failing; noise only now. See weekly-report-2026-10-22.html §M6.**

- [ ] **🟡 NP morning schedule — first live run 2026-10-10 08:00/09:00 (added 2026-10-09, Cowork).** Check the automation trace: both units heat ~69.8/high/both at 08:00, ~67.1/low/both at 09:00, no CHECK UNITS page. Kitchen Wi-Fi is the likely failure. See CONTEXT.md → NP morning schedule.

- [ ] **🟡 NP "Heading to NP" — first real test 10-10/11 (added 2026-10-05, Cowork).** Note when the iPhone Arrive prompt fires vs arrival time; confirm `np_heading_arrived` cancelled `timer.np_heading_window` (trace) and units held 68/high/both; tune the ~40 mi geofence radius. Open: summer behaviour (cool to 68?). See CONTEXT.md → NP "Heading to NP".

- [ ] **🟡 NEW 2026-10-04 — Face recognition — measure, train, then decide on detect resolution.** Live on front_window (see CONTEXT.md → Frigate). (1) Train Michelle + Broomhilda in Face Library → aim 20–30 images each, daylight, no IR. (2) After ~1 week read face sizes/scores in Recent Recognitions: if most faces < ~25 px, move `detect` to the main stream (scale person/car `min_area` ×4.5, check iGPU + 4 GiB cap) — record already pulls main, so no extra Wi-Fi. (3) Re-measure frigate mem vs new 4096m cap and `inference_speed` (14 ms right after enable vs 7–9 before). (4) Broomhilda high path not yet fired for real (low path + MQTT trigger verified with a test name).
- [x] **✅ CLOSED 2026-10-21 (homelab-advisor): NP `back` (.35) healthy + streaming — live /api/stats 5.0 cam fps, clean since the 10-11 restart (10 d). brookside Frigate runs 2 cameras, both folded into the 3 GiB mem watch (50%/57% §2 budget-10-19) + root-disk watch (settled, disk-health-10-20). The 10-09/10 back blackout that nothing paged is the separate camera-probe item below, still open. See advisor-2026-10-21.html §4.** — (via homelab-advisor 2026-10-14)

  - **2026-10-14 (homelab-advisor):** re-spiked during the 10-09/11 NP visit (5,930→1,965→128 crashes/day) then clean since 10-11, porch 3.1 fps — visit churn, not a regression. Confirm 1 more clean week then CLOSE. See advisor-2026-10-14.html §4.
  - **2026-10-05 (Cowork):** brookside-era crash loop was a different cause — VAAPI `hwdownload` failures, 2,180 crashes 10-03→10-05. Fixed with porch `hwaccel_args: []` (home-automation-np `1386af0`). The 10-01 Mac-era `192.168.2.34:554 refused` cause was not seen on brookside. Close this item once 48 h of porch logs show no crash loop. See TROUBLESHOOTING 2026-10-05.
- [x] **✅ DONE 2026-10-08: token in `secrets/ha-np.env` (HA_URL + HA_TOKEN, 600, gitignored); /api/ → 200.** ~~NP HA long-lived token missing on brookside~~ — `secrets/ha.env` there is Brooklyn's (`192.168.1.71`), so NP HA's API returns 401 and automation reloads need a container restart. Create a token in NP HA and write a separate `ha-np.env`. — (via Cowork 2026-10-05)
- [x] **✅ CLOSED 2026-10-06 (Cowork): not stale — an MCP quirk.** `unifi_list_clients` live (no `include_offline`) shows Porch online, -44 dBm, sinola 2.4, last_seen now; `search` + `include_offline=true` returns the historical /rest/user record whose status is computed from an old last_seen. Use the live list. ~~**`unifi-brookside` looks stale** — lists Porch offline since 10-04 02:00 ET and returns 0 events in 24 h while the camera streams at 3 fps. Check the MCP's controller/site config. — (via Cowork 2026-10-05)~~


- [x] **✅ DONE 2026-10-08: 32m on both hosts — brookside 742bbab, woodhull home-automation 2e10d22 (recreated 18:55, healthy, MQTT clients back).** ~~woodhull mosquitto cap 8->16 MiB — `OOMKilled=true`, now `RestartCount=1` (killed 10-01 03:14 UTC; cap still 8388608).** Set `mem_limit: 16m` and recreate on BOTH hosts — brookside carries the same 8 MiB cap. See weekly-report-2026-10-08.html — (via homelab-advisor 2026-09-30) (via weekly-docker-log-report 2026-10-08) → full text: `archive/TODO-detail.md` §H-001

- [ ] **NP porch: tighten the `yard` polygon above the porch rail.** Its lower edge IS the rail top, so a person standing at the rail (legs hidden) reads as in `yard`. Paging keys on the *first* zone so this is harmless today, but anything that later reads `yard` membership will misfire. Known gap either way: someone climbing the steps from out of frame enters `frontporch` first → note, not page. See TROUBLESHOOTING 2026-09-26. — (via Cowork 2026-09-26)

- [ ] **NP Serin dongles — weak Wi-Fi at the kitchen, marginal Govee in the living room (added 2026-09-25, Cowork; accepted by Paul until the NP network audit/upgrade, "a few weeks").** → full text: `archive/TODO-detail.md` §H-002

- [ ] **🔴 Frigate per-day recording volume jumped ~6× at the 0.18.0 upgrade (09-16).** — (via weekly-disk-health 2026-09-22) → full text: `archive/TODO-detail.md` §H-003 — carried (2026-10-20, no change)

- [ ] **🟡 MEASURE `car.min_area` on the NP porch camera — the value in place is a PLACEHOLDER.** — (via Cowork 2026-09-20) → full text: `archive/TODO-detail.md` §H-004
  - **2026-10-05 readout (Cowork, brookside Frigate, events since 10-02 clean start; 09-28→10-01 only in the Mac archive):** 39 porch `car` events. **2 real** — a car on the gravel patch, zone `yard`, box ≈ x0.71 y0.33 w0.21 h0.17: area **9750** (10-02 04:35, score 0.70) and **11484** (10-02 15:41, 0.99, 16 min, snapshot confirms SUV). **37 false** — the porch pillar/rail corner read as a car, box centred ~(0.5,0.5), area **28,420–77,924**, score 0.70–0.84, no zone, mostly at night under IR (snapshots 10-04 12:36 and 23:48 confirm). No car pages found in ntfy over 96 h. **APPLIED 2026-10-05 10:17 on Paul's call (home-automation-np 073c6d2, Frigate restarted healthy, /api/config reads min 7500 / max 25000, HA receiving Frigate MQTT again by 10:17:51):** porch `car` `min_area: 7500` (≈20% under 9750) **and** `max_area: 25000` — removes all 37 rail false positives, keeps both real cars. Alternative: an object mask over the pillar/rail for `car`. Snapshots: infra/log-reports/np-car-snaps-20261005/.


- [ ] **🟡 NEW 2026-09-14 — no UPS at New Paltz.** `pmset -g ps` = AC only. A flicker is survivable (`autorestart 1`), but a brownout can wedge the engine mid-write, and when the UX7/ONT drop with it the ntfy page saying so never leaves the house. Small UPS on Mac + UX7 + ONT; USB signalling so macOS can shut down cleanly. On-site purchase/install; size for ~15 min.

- [ ] **Frigate records to `/srv/frigate` — woodhull's boot NVMe, not the 3.7 T `/srv/media`.** — (via weekly-disk-health 2026-09-15) → full text: `archive/TODO-detail.md` §H-006 — carried (2026-10-20, no change)

- [ ] **🟡 Rebuild `voice-bench` on woodhull with a new `config_tag` — it has been dark since 2026-09-03 and its LaunchAgent was retired 09-04.** — (via Cowork 2026-09-04) → full text: `archive/TODO-detail.md` §H-007

- [ ] **🔵 Home-automation migration — Phase 3/4/5 remain. §10 #18 reboot survival: ✅ PASS 2026-09-04 13:42 ET.** — (via `infra/scripts/phase34-mac.sh` + `phase34-mac2.sh`, run by Paul; Cowork has no route to the Mac) (via Cowork 2026-09-04) → full text: `archive/TODO-detail.md` §H-008

- [ ] **🔴 ACTIVE — Naboo Spotify Connect / play_media investigation. READ THIS FIRST if starting a new session on this.** — (Settings → Devices & services → the Naboo device → Logs, or via the "..." menu — note: no "Enable debug logging" option was found on this HA version's device page, worth checking the ESPHome integration's own page instead) (via Cowork 2026-09-04, handoff written for a fresh session) → full text: `archive/TODO-detail.md` §H-009

- [ ] **`infra/log-reports/go-librespot*.log` stale since the 08-31 infra migration (log-tailer moved to woodhull, lost its mount into the Mac-local librespot log dir).** Use `home-automation/librespot/log/{librespot,stream,events,watchdog,run}.log` directly until re-wired (candidate: extend `log-tailer-native` on the Mac, same pattern already used for homeassistant/frigate/mosquitto). See TROUBLESHOOTING.md 2026-09-01. — (via Cowork 2026-09-01)

- [ ] **🔵 Migrate the home-automation stack (`homeassistant`, `mosquitto`, `frigate`) from `media` to `woodhull`.** — (via Cowork 2026-08-30, planned 2026-08-31, Phase 1 executed 2026-08-31, pre-cutover prep 2026-09-02, STT verdict + Phase 2 cutover 2026-09-03) → full text: `archive/TODO-detail.md` §H-010

- [ ] **switch.plug_1 (Wyze) still `unavailable` since 08-23 07:01 — deferred by Paul.** Confirmed offline in the Wyze app (physical/Wi-Fi, not HA/DNS). `switch.speaker` had the same issue and was fixed same day (power-cycled, back `on` 08-27 23:17 UTC) — plug_1 needs the same physical power-cycle whenever Paul wants that plug back; not urgent. See TROUBLESHOOTING.md 2026-08-27. — (via Cowork 2026-08-27)


- [x] **Rotate credentials left in git history — ✅ CLOSED 2026-10-13.** Both HA long-lived tokens (voice_performance, speech-to-phrase — still valid on woodhull's BK HA until then) deleted by Paul; refresh-token ids verified gone from `.storage/auth`. The leaked mkcert privkey was already replaced and nothing mounts `certs/`. No history rewrite. Originally: found 2026-08-09 by the repo's first full-history `gitleaks git` scan (4 findings). → full text: `archive/TODO-detail.md` §H-012

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

- [x] **✅ CLOSED 2026-10-24 (Cowork) — REPORTED IN ERROR, correcting the 10-22 run. 0 `IllegalInstruction` crashes in the 7-day window: the 3 such events were 10-13, outside it. The '8 lines on 10-21' were ONE event at 10-20 21:17 ET that the 10-22 run's `docker logs -t` grep bucketed by UTC date, and its reason was `Fault - Unknown` (PC 0x4038280E), a different signature. `speaker_source_media_player` appears 0× in 10 d — the fault attribution carried here for weeks is stale. Firmware already current (installed 26.9.0 = latest 26.9.0, update entity off), so there was nothing to reflash. Crash rate is ~1 unexplained event/week; reopen only if a signature recurs.** ~~**Voice PE `0a3a76` esp32 crash — `Fault - IllegalInstruction` at `speaker_source_media_player:222`.** 2026-10-08: quiet — 27 lines/7 d (vs 4,320 on 09-29); still not reflashed. — (via homelab-advisor 2026-09-02) (via weekly-docker-log-report 2026-10-08) → full text: `archive/TODO-detail.md` §H-011 — **carried over 2× (2026-10-15): REGRESSED — 71 crash lines / 5 events (11 on 10-08, 15 on 10-13, 45 on 10-14) vs 27 lines last week. Same `speaker_source_media_player:222` fault; never reflashed. See weekly-report-2026-10-15.html §H3.** — **carried 3× (2026-10-21, homelab-advisor): still not reflashed (no ESPHome build commit since tag); stale-and-blocking. No new HA-log run since 10-15 for fresh counts. See advisor-2026-10-21.html §Actions.** — **carried 4× (2026-10-22): 8 crash lines, all 10-21, same `speaker_source_media_player:222` fault; still not reflashed. Volume down 71→8. Ship the reflash or downgrade to Watching. See weekly-report-2026-10-22.html §H4.**~~
- [x] **✅ DONE 2026-10-22 (weekly-docker-log-report): `np_porch_camera_health.yaml` + `np_back_camera_health.yaml` live on brookside (10-06/10-09), both alerting off MQTT `cameras.<cam>.camera_fps > 0` — the requested signal. Tag was raised after the fix shipped.** ~~**Camera-level health probe at NP — container health is blind to dead cameras.** `back` (.35) crash-looped 2 d, 8,864 watchdog restarts, while service-watchdog and Kuma #44 read `frigate=healthy`. Alert on camera_fps=0 or no new mp4 in 10 min. §M4 — (via weekly-docker-log-report 2026-10-15)~~
- [x] **✅ DONE 2026-10-22 (weekly-docker-log-report): 0 occurrences of `token=` in 7 d of woodhull HA logs (was 179×). The 14 remaining `windmill` lines are benign automation INFO.** ~~**🔑 Rotate the Windmill dashboard token; stop HA logging it.** `custom_components.windmillac` printed the full URL incl. `token=` 179× in 7 d into `log-reports/homeassistant.log`. Redact the query string or filter `token=`. §M3 — (via weekly-docker-log-report 2026-10-15)~~
- [x] **✅ DONE 2026-10-20 (weekly-disk-health): plateaued — root 44.7 GB (21%), peak 87.0 GB 10-12, 7d range 39–57 GB, well under 110 flag. See disk-health-2026-10-20.md §3.** Watch brookside root: Frigate spiked it 21→94 GB (10-09→10-12), now 58 GB falling; confirm plateau (~41 GB Frigate) by 10-20; flag >110 GB.** See infra/disk_reports/disk-health-2026-10-13.md §3 — (via weekly-disk-health 2026-10-13) — **2026-10-15 (weekly-docker-log-report): plateauing — root 51 GB / 24% of 221 G (160 GB free), 33 GB of it Frigate. Both cams recording (porch 720 + back 396 segments / 2 h). 14-d alert / 2-d detection retention, no continuous; steady state ~70–80 GB (~36%) by 10-23. See weekly-report-2026-10-15.html §M8.**
- [x] **🔴 NP porch cam RTSP down — Frigate ffmpeg crash loop, 5,132 crashes on 10-01** (132 on 09-27, 1,165 on 09-30); `192.168.2.34:554` refused. Paging is blind. Fix the lease/RTSP in NP UniFi, or set `enabled: false`. See weekly-report-2026-10-01.html — (via weekly-docker-log-report 2026-10-01) **2026-10-06 (Cowork): recurred** — ffmpeg exit/refused loop ran continuously 10-03→10-05 (~3,800 lines/day, 110-210/h) and stopped when the frigate container was recreated 10-05 22:23 ET; 0 errors in the 17 h since, porch 3.1 fps. A Frigate restart clears it; cause still unknown (camera RTSP server wedging?). Watch the next weekly log report before building an auto-restart. — **2026-10-08: NEAR-RESOLVED, and it was not just the restart.** Errors/day 5,529 (10-03) → 3,808 → 3,782 → 446 (10-06) → 17 (10-07) → 1 (10-08); clean 17 h, porch 3.0 fps. Two real fixes landed: `hwaccel_args: []` (CPU decode) on 10-05 and the 10-07 15:25 UTC restart carrying the YOLOv9-t/OpenVINO swap (`f710785`). No auto-restart needed — confirm clean next week, then CLOSE. See weekly-report-2026-10-08.html — (via weekly-docker-log-report 2026-10-08)** — **✅ CLOSED 2026-10-15 (weekly-docker-log-report): confirmed clean as the 10-08 note asked. brookside Frigate logged 0 errors since the 10-11 18:00 ET restart (3.5 d); porch wrote 720 segments in 2 h, .34:554 answers. The `hwaccel_args: []` + YOLOv9-t/OpenVINO fixes held; no auto-restart needed. See weekly-report-2026-10-15.html.**

- [x] **brookside mosquitto restarted ~10× in 7 d — ✅ RESOLVED by evidence 2026-10-14 (homelab-advisor).** 0 restarts since the 10-10 closet-move reboot (RestartCount=0, stable 4 d); cap now 32 m (10-08). The 10-01→08 cluster (4 on 10-07) was visit-prep/migration churn — caller never confirmed, symptom gone. Reopen if Frigate MQTT drops recur. See advisor-2026-10-14.html §1.

- [x] **HA windmillac errors — ✅ CLOSED 2026-10-13: durable year-round setup (BK home-automation d8abad1).** Off/unplugged never caused errors (Blynk returns last values); all errors were the cloud unreachable during BK WAN drops. Integration stays enabled; `binary_sensor.windmill_ac_connected` (Blynk isHardwareConnected, 5 min, !secret windmill_token) gates the 7am/1am schedule so removing the unit in fall stops it and reinstalling resumes it; logger filters drop only cloud-unreachable lines (255/255 of last week). Nothing to do each season. Filed in the NP repo but it is a Brooklyn item.

- [x] **Size the NP box before NP Frigate comes back — ✅ DONE 2026-10-08.** NP Frigate is live on brookside (porch 3.0 fps / 6.4 detect fps) on a 16 GB / 221 GB host sitting at 11% disk with 12.5 GB RAM available, up 5 d. Sizing is comfortable. (was §H-005) — (via weekly-docker-log-report 2026-10-08)


- [x] **Deploy stats-collector on brookside — ✅ DONE 2026-10-05.** Native cron `5 * * * *` runs infra/stats-collector.sh → memory_reports/hourly_stats.csv (verified, 5 containers). Mac collector already retired. See budget-report-2026-10-05.md §6 — (via weekly-resource-budget 2026-10-05)

- [x] **Trim TODO.md — ✅ DONE 2026-10-01 (Cowork).** 110→19 KB: done items moved verbatim to `archive/TODO-completed.md`, long open items summarized with full text in `archive/TODO-detail.md`; line-preservation check passed. — (via quarterly-doc-audit 2026-10-01)









Older completed items: `archive/TODO-completed.md`.
