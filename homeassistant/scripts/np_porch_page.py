#!/usr/bin/env python3
"""
np_porch_page.py -- page Paul when the New Paltz porch camera sees a person
while the house is marked empty.

Called by HA as:  shell_command.np_porch_page  ->  python3 /config/scripts/np_porch_page.py <frigate_event_id>
Re-sent by:       shell_command.np_porch_flush ->  python3 /config/scripts/np_porch_page.py --flush

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
NTFY    = os.environ.get("NTFY_URL", "http://192.168.1.71:8111/homelab")
# Tailnet URL for the "open it" tap target. Tailnet-only on purpose -- see
# infra/ntfy/README.md; the phone needs Tailscale up to follow it.
UI      = os.environ.get("NP_FRIGATE_UI", "https://media.tail317990.ts.net:18971")
QUEUE   = "/config/np_alert_queue.jsonl"
LOG     = "/config/np_alerts.log"
MAX_AGE = 24 * 3600          # drop a queued page older than this; it is news no longer
TIMEOUT = 10

ZONE_WORDS = {"yard": "the driveway", "frontporch": "the front porch"}


def log(line):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")


def get_event(eid):
    with urllib.request.urlopen(f"{FRIGATE}/api/events/{eid}", timeout=TIMEOUT) as r:
        return json.load(r)


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
            f"{conf}. House is marked empty.")
    return title, body


def send(eid):
    ev = get_event(eid)
    title, body = compose(ev)
    img = get_snapshot(eid)
    headers = {
        "Title": title,
        "Priority": "urgent",
        "Tags": "rotating_light,house",
        "Click": f"{UI}/explore?event_id={eid}",
    }
    def post_text():
        req = urllib.request.Request(NTFY, data=body.encode("utf-8"),
                                     headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=TIMEOUT).read()

    if img:
        h = dict(headers, Filename="porch.jpg", Message=body)
        req = urllib.request.Request(NTFY, data=img, headers=h, method="PUT")
        try:
            urllib.request.urlopen(req, timeout=TIMEOUT).read()
            log(f"SENT {eid} img=yes | {title} | {body}")
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
            log(f"ATTACH-REJECTED {eid} HTTP {e.code} {detail} -- falling back to text")
    post_text()
    log(f"SENT {eid} img=no | {title} | {body}")


def enqueue(eid, err):
    with open(QUEUE, "a") as f:
        f.write(json.dumps({"id": eid, "queued_at": time.time()}) + "\n")
    log(f"QUEUED {eid} ({err})")


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
    for row in rows:
        if now - row.get("queued_at", 0) > MAX_AGE:
            dropped += 1
            continue
        try:
            send(row["id"])
            sent += 1
        except Exception:
            keep.append(row)
    with open(QUEUE, "w") as f:
        for row in keep:
            f.write(json.dumps(row) + "\n")
    if sent or dropped:
        log(f"FLUSH sent={sent} dropped_stale={dropped} still_queued={len(keep)}")
        if sent:
            # Say plainly that these are late. A 3am page arriving at 7am
            # without that context reads as something happening right now.
            try:
                urllib.request.urlopen(urllib.request.Request(
                    NTFY, data=f"{sent} New Paltz alert(s) from during the outage were just delivered.".encode(),
                    headers={"Title": "NP alerts delivered late", "Priority": "default",
                             "Tags": "clock"}, method="POST"), timeout=TIMEOUT)
            except Exception:
                pass


def main():
    if len(sys.argv) < 2:
        log("NO-ARG")
        return 1
    if sys.argv[1] == "--flush":
        flush()
        return 0
    eid = sys.argv[1].strip()
    # Frigate ids are "<epoch>.<frac>-<slug>". Anything else is not ours.
    if not re.fullmatch(r"[0-9]+\.[0-9]+-[A-Za-z0-9]+", eid):
        log(f"BAD-ID {eid!r}")
        return 1
    try:
        send(eid)
    except Exception as e:
        enqueue(eid, repr(e))
        return 0          # never fail loudly into HA; the queue is the recovery
    # A successful send is also the moment to try anything stranded earlier.
    try:
        flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
