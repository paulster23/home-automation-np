#!/usr/bin/env python3
"""
np_porch_page.py -- page Paul when the New Paltz porch camera sees a person
while the house is marked empty.

Called by HA as:  shell_command.np_porch_page  ->  python3 /config/scripts/np_porch_page.py <frigate_event_id>
Re-sent by:       shell_command.np_porch_flush ->  python3 /config/scripts/np_porch_page.py --flush
Porch note:       shell_command.np_porch_page with event_id "--note <id>" (np_porch_info)

WHY A SCRIPT AND NOT rest_command.ntfy
--------------------------------------
Two things a template cannot do:

1. The page carries the snapshot as an ntfy ATTACHMENT. That means pulling
   binary from Frigate and PUTting it to ntfy. HA's rest_command templates
   text bodies only. The alternative -- an `Attach:` header pointing at a
   Frigate URL -- fails because Frigate has auth on, so the phone would get
   a 401 where the picture should be.

2. ntfy lives on woodhull, in BROOKLYN. New Paltz's WAN drops for a few
   minutes most nights (and once for 2h36m on 2026-09-17), and notify.sh
   fails SILENTLY by design. A person alert sent during an outage is simply
   lost. So every failure here is appended to QUEUE and re-sent later by
   --flush. The event itself is always safe -- Frigate recorded it locally --
   only the notification is at risk, and this is what closes that.

The snapshot is fetched from http://frigate:5000, the in-container API, which
needs no auth. HA and Frigate share the `home-automation` docker network.
"""
import json, os, re, sys, time, urllib.request, urllib.error

FRIGATE = os.environ.get("FRIGATE_URL", "http://frigate:5000")
def _secret(key, default):
    """Read a plain `key: "value"` line from HA's secrets.yaml -- the same
    ntfy_server / ntfy_topic_page the packages use, so the page topic is set
    in exactly one place."""
    try:
        for line in open("/config/secrets.yaml"):
            m = re.match(rf'^{key}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return default


NTFY    = os.environ.get("NTFY_URL") or (
    _secret("ntfy_server", "http://192.168.1.71:8111").rstrip("/") + "/"
    + _secret("ntfy_topic_page", "homelab"))
# 2026-09-26: urgent -> high. A yard entry at an empty house is worth a page,
# not a max-priority alarm that overrides Do Not Disturb.
PAGE_PRIORITY = "high"
# Tailnet URL for the "open it" tap target. Tailnet-only on purpose -- see
# infra/ntfy/README.md; the phone needs Tailscale up to follow it.
UI      = os.environ.get("NP_FRIGATE_UI", "https://brookside.tail317990.ts.net:18971")  # 2026-10-06: Frigate moved off the Mac; unused since the Click header went (09-26)
# 2026-09-29 -- pager MIRROR. The self-hosted ntfy relays only a poll request to
# ntfy.sh, so off the tailnet the phone buzzes but opens EMPTY (tested
# 2026-09-20). ntfy_mirror in secrets.yaml is a full https://ntfy.sh/<topic>
# URL -- the same topic as notify.sh's NTFY_FALLBACK_TOPIC -- where the body
# and the photo are readable on cellular. Pages only; porch notes are not
# mirrored. Unset -> no mirror. Mirror failures queue independently of the
# primary (row "target": "mirror") so neither blocks the other.
MIRROR  = os.environ.get("NTFY_MIRROR_URL") or _secret("ntfy_mirror", "")
QUEUE   = "/config/np_alert_queue.jsonl"
LOG     = "/config/np_alerts.log"
MAX_AGE = 24 * 3600          # drop a queued page older than this; it is news no longer
TIMEOUT = 10

ZONE_WORDS = {"yard": "the driveway", "frontporch": "the front porch"}


def log(line):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")


def get_event(eid, tries=4):
    # A page fires on an in-progress object, and Frigate may not have written
    # the event row yet: 404 for a second or two. Retry briefly here rather
    # than dropping to the WAN queue, whose flush runs only every 5 minutes.
    # (2026-09-25 19:40:29: ku2slf queued on 404, sent 76 s later by flush.)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(f"{FRIGATE}/api/events/{eid}", timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 404 or attempt == tries - 1:
                raise
            time.sleep(2)


def get_snapshot(eid):
    """Best effort. A page with no picture still beats no page."""
    try:
        url = f"{FRIGATE}/api/events/{eid}/snapshot.jpg?bbox=1&quality=70"
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.read()
    except Exception as e:
        log(f"SNAPSHOT-FAIL {eid} {e}")
        return None


def compose(ev):
    label = (ev.get("label") or "object").replace("_", " ")
    zones = [z for z in (ev.get("zones") or []) if z]
    if zones:
        where = " and ".join(ZONE_WORDS.get(z, z) for z in zones)
    else:
        # Today's 12:47 and 12:54 events looked exactly like this: a real
        # person, in frame, inside neither zone. Frigate calls that a
        # detection rather than an alert. For an empty house it is still
        # worth knowing about, so it pages -- just without a place name.
        where = "frame, outside both zones"
    when = time.strftime("%-I:%M %p", time.localtime(ev.get("start_time", time.time())))
    # Frigate 0.17 moved the scores under `data`. The old top-level
    # ev["top_score"] is still present but always None, so reading it
    # silently produced "0% confidence" on the first real page.
    data = ev.get("data") or {}
    score = data.get("top_score") or data.get("score") or 0
    title = f"NP: {label} at {ZONE_WORDS.get(zones[0], zones[0]) if zones else 'the house'}"
    conf = f"{round(score * 100)}% confidence" if score else "confidence unknown"
    body = (f"{label.capitalize()} detected in {where} at {when}, "
            f"{conf}. House is empty (binary_sensor.np_occupied off).")
    return title, body


def send(eid, tries=4, url=None):
    url = url or NTFY
    tag = "" if url == NTFY else " [mirror]"
    ev = get_event(eid, tries)
    title, body = compose(ev)
    img = get_snapshot(eid)
    headers = {
        "Title": title,
        "Priority": PAGE_PRIORITY,
        "Tags": "rotating_light,house",
        # No "Click" header (removed 2026-09-26, Paul): tapping the alert should
        # open it in ntfy, where the attached snapshot is shown -- not a Frigate
        # login in a browser he does not otherwise use. The event is still in
        # Frigate (explore?event_id=<id>) for the clip.
    }
    def post_text():
        req = urllib.request.Request(url, data=body.encode("utf-8"),
                                     headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=TIMEOUT).read()

    if img:
        h = dict(headers, Filename="porch.jpg", Message=body)
        req = urllib.request.Request(url, data=img, headers=h, method="PUT")
        try:
            urllib.request.urlopen(req, timeout=TIMEOUT).read()
            log(f"SENT{tag} {eid} img=yes | {title} | {body}")
            return
        except urllib.error.HTTPError as e:
            # ntfy 40014 "attachments not allowed" -- the server has no
            # attachment-cache-dir configured. A picture is a nice-to-have;
            # the page is not. Never let a rejected image swallow the alert.
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            log(f"ATTACH-REJECTED{tag} {eid} HTTP {e.code} {detail} -- falling back to text")
    post_text()
    log(f"SENT{tag} {eid} img=no | {title} | {body}")


def enqueue(eid, err, target="primary"):
    with open(QUEUE, "a") as f:
        f.write(json.dumps({"id": eid, "queued_at": time.time(), "target": target}) + "\n")
    log(f"QUEUED{'' if target == 'primary' else ' [mirror]'} {eid} ({err})")


def flush():
    if not os.path.exists(QUEUE):
        return
    try:
        rows = [json.loads(l) for l in open(QUEUE) if l.strip()]
    except Exception as e:
        log(f"FLUSH-PARSE-FAIL {e}")
        return
    if not rows:
        return
    now, keep, sent, dropped = time.time(), [], 0, 0
    late = {}                             # target url -> count delivered late
    for row in rows:
        if now - row.get("queued_at", 0) > MAX_AGE:
            dropped += 1
            continue
        target = row.get("target", "primary")
        if target == "mirror" and not MIRROR:
            dropped += 1                  # mirror switched off since queueing
            continue
        url = MIRROR if target == "mirror" else NTFY
        try:
            send(row["id"], tries=1, url=url)  # no 404 retry here: 70 rows x 6 s blew HA's 60 s limit
            sent += 1
            late[url] = late.get(url, 0) + 1
        except urllib.error.HTTPError as e:
            # 404 long after queueing = Frigate discarded the event (short-lived
            # false positive). It will never send; retrying it every 5 min for
            # 24 h is noise. A fresh 404 is the write race -- keep it.
            if e.code == 404 and now - row.get("queued_at", 0) > 300:
                dropped += 1
                log(f"DROP-404 {row['id']} (Frigate no longer has this event)")
            else:
                keep.append(row)
        except Exception:
            keep.append(row)
    with open(QUEUE, "w") as f:
        for row in keep:
            f.write(json.dumps(row) + "\n")
    if sent or dropped:
        log(f"FLUSH sent={sent} dropped={dropped} still_queued={len(keep)}")
        # Say plainly that these are late. A 3am page arriving at 7am
        # without that context reads as something happening right now.
        for url, n in late.items():
            try:
                urllib.request.urlopen(urllib.request.Request(
                    url, data=f"{n} New Paltz alert(s) from during the outage were just delivered.".encode(),
                    headers={"Title": "NP alerts delivered late", "Priority": "default",
                             "Tags": "clock"}, method="POST"), timeout=TIMEOUT)
            except Exception:
                pass



def note(eid):
    """Low-priority porch note (automation np_porch_info), sent only if Frigate
    actually KEPT the event.

    WHY (2026-09-28): Frigate publishes new/end on frigate_np/events for tracks
    it later discards as false positives -- no event row, no timeline, no
    review item, API 404. The page path already survives this (send() 404s,
    the queue drops it), but np_porch_info posted straight from the MQTT
    payload, so a ghost track told Paul "someone on the porch" at 06:01 and
    07:02 with nobody there and nothing in Frigate. Same signature as the 70
    DROP-404 rows on 2026-09-26. Checking the API at end-time is the one test
    that matches what Paul sees in Frigate.
    """
    try:
        ev = get_event(eid, tries=4)          # ~6 s of 404 grace for the write race
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log(f"NOTE-SKIP-404 {eid} (Frigate discarded this track -- false positive, no note sent)")
            return
        log(f"NOTE-FAIL {eid} frigate HTTP {e.code}")
        return
    except Exception as e:
        log(f"NOTE-FAIL {eid} frigate {e!r}")
        return
    zones = [z for z in (ev.get("zones") or []) if z]
    title = "NP: someone on the porch" if "frontporch" in zones else "NP: person in frame"
    where = "on the front porch" if "frontporch" in zones else "outside both zones"
    when = time.strftime("%-I:%M %p", time.localtime(ev.get("start_time", time.time())))
    data = ev.get("data") or {}
    score = data.get("top_score") or data.get("score") or 0
    conf = f", {round(score * 100)}% confidence" if score else ""
    body = (f"Porch camera saw a person {where} at {when}{conf}. They did not arrive "
            f"through the yard, so this is a note, not a page. House is empty.")
    url = _secret("ntfy_server", "http://192.168.1.71:8111").rstrip("/") + "/" + _secret("ntfy_topic_info", "np-info")
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST",
                                 headers={"Title": title, "Priority": "low",
                                          "Tags": "bust_in_silhouette"})
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
        log(f"NOTE-SENT {eid} | {title} | {body}")
        print("NOTE-SENT")                    # np_porch_info starts its cooldown only on this
    except Exception as e:
        # Not queued: a stale porch note is worth less than the noise of a late one.
        log(f"NOTE-FAIL {eid} ntfy {e!r}")


def main():
    if len(sys.argv) < 2:
        log("NO-ARG")
        return 1
    if sys.argv[1] == "--flush":
        flush()
        return 0
    if sys.argv[1] == "--note":
        eid = sys.argv[2].strip() if len(sys.argv) > 2 else ""
        if not re.fullmatch(r"[0-9]+\.[0-9]+-[A-Za-z0-9]+", eid):
            log(f"BAD-ID note {eid!r}")
            return 1
        note(eid)
        return 0
    eid = sys.argv[1].strip()
    # Frigate ids are "<epoch>.<frac>-<slug>". Anything else is not ours.
    if not re.fullmatch(r"[0-9]+\.[0-9]+-[A-Za-z0-9]+", eid):
        log(f"BAD-ID {eid!r}")
        return 1
    primary_ok = True
    try:
        send(eid)
    except Exception as e:
        enqueue(eid, repr(e))
        primary_ok = False  # never fail loudly into HA; the queue is the recovery
    if MIRROR:
        try:
            send(eid, tries=1, url=MIRROR)   # the event row exists by now
        except Exception as e:
            enqueue(eid, repr(e), target="mirror")
    if not primary_ok:
        return 0
    # A successful send is also the moment to try anything stranded earlier.
    try:
        flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
