#!/usr/bin/env python3
"""
np_notify.py -- every New Paltz HA notification except the porch camera
(the porch person page and porch note stay in np_porch_page.py).

Called by HA as:  shell_command.np_notify        (ONE arg: base64 of a JSON object)
Re-sent by:       shell_command.np_notify_flush  (automation np_porch_flush, every 5 min + HA start)

    data: {title, message, priority, tags, [topic]}
      priority  min|low|default|high|urgent or 1-5   (default: default)
      tags      "a,b" or ["a", "b"]                  (default: house)
      topic     optional; default ntfy_topic_page -- the same topic the old
                rest_command.ntfy always posted to, so routing is unchanged.

WHY (2026-10-06)
----------------
ntfy lives on woodhull, in BROOKLYN, and Paul's standing call is that the BK
WAN WILL keep dropping. rest_command.ntfy / rest_command.np_ntfy posted to
woodhull only, with no fallback and no retry, so during a Brooklyn outage NP's
FREEZE RISK (urgent) and HVAC-offline / camera-offline (high) pages were simply
lost. This script gives every one of them the two properties np_porch_page.py
already had:

1. MIRROR: anything on the page topic is ALSO posted to ntfy_mirror (ntfy.sh,
   the same topic as notify.sh's NTFY_FALLBACK_TOPIC). That path does not touch
   Brooklyn, and its content is readable on bare cellular.
2. QUEUE: a failed post (either target) goes to np_notify_queue.jsonl and is
   re-sent by --flush, marked late, for up to 24 h. Separate from the porch
   queue on purpose: np_porch_page.py's flush expects Frigate event ids.

JSON publish (POST to the server root, topic in the body) rather than headers:
titles carry "—" and bodies "°F", and urllib refuses non-latin-1 header values.

Never fails into HA: always exits 0. Heat automations act on the hardware
first and notify second regardless.
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


def _secret(key, default):
    try:
        for line in open("/config/secrets.yaml"):
            m = re.match(rf'^{key}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return default


# NP_NOTIFY_* env overrides exist for testing (e.g. SERVER=http://192.0.2.1:8111
# simulates a Brooklyn outage); HA never sets them.
SERVER     = (os.environ.get("NP_NOTIFY_SERVER") or _secret("ntfy_server", "http://192.168.1.71:8111")).rstrip("/")
PAGE_TOPIC = _secret("ntfy_topic_page", "homelab")
MIRROR     = os.environ.get("NP_NOTIFY_MIRROR", _secret("ntfy_mirror", ""))   # full https://ntfy.sh/<topic>
QUEUE      = os.environ.get("NP_NOTIFY_QUEUE", "/config/np_notify_queue.jsonl")
LOG        = "/config/np_alerts.log"
MAX_AGE    = 24 * 3600
TIMEOUT    = 8          # x up to ~4 posts per call stays well inside HA's 60 s shell_command limit
PRIO       = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5, "max": 5}


def log(line):
    try:
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | NOTIFY {line}\n")
    except OSError:
        pass


def normalise(n):
    p = str(n.get("priority") or "default").strip().lower()
    prio = int(p) if p.isdigit() else PRIO.get(p, 3)
    tags = n.get("tags") or "house"
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return {
        "title": str(n.get("title") or "New Paltz"),
        "message": str(n.get("message") or ""),
        "priority": max(1, min(5, prio)),
        "tags": tags,
        "topic": str(n.get("topic") or PAGE_TOPIC),
    }


def post(target, n, late_from=None):
    if target == "mirror":
        root, topic = MIRROR.rstrip("/").rsplit("/", 1)
    else:
        root, topic = SERVER, n["topic"]
    title = n["title"]
    if late_from:
        title += f" [late, queued {time.strftime('%H:%M', time.localtime(late_from))}]"
    body = json.dumps({"topic": topic, "title": title, "message": n["message"],
                       "priority": n["priority"], "tags": n["tags"]}).encode("utf-8")
    req = urllib.request.Request(root + "/", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=TIMEOUT).read()


def enqueue(target, n, err):
    with open(QUEUE, "a") as f:
        f.write(json.dumps({"target": target, "queued_at": time.time(), "n": n}) + "\n")
    log(f"QUEUED [{target}] p{n['priority']} {n['title']} ({err})")


def flush():
    if not os.path.exists(QUEUE):
        return
    try:
        rows = [json.loads(l) for l in open(QUEUE) if l.strip()]
    except Exception as e:
        log(f"FLUSH-PARSE-FAIL {e!r}")
        return
    if not rows:
        return
    now, keep, sent, dropped, down = time.time(), [], 0, 0, set()
    for row in rows:
        target, n = row.get("target", "primary"), row.get("n") or {}
        if now - row.get("queued_at", 0) > MAX_AGE or (target == "mirror" and not MIRROR):
            dropped += 1
            continue
        if target in down:                 # one timeout per target per flush, not one per row
            keep.append(row)
            continue
        try:
            post(target, n, late_from=row.get("queued_at"))
            sent += 1
        except Exception:
            down.add(target)
            keep.append(row)
    with open(QUEUE, "w") as f:
        for row in keep:
            f.write(json.dumps(row) + "\n")
    if sent or dropped:
        log(f"FLUSH sent={sent} dropped={dropped} still_queued={len(keep)}")


def main():
    if len(sys.argv) < 2:
        log("NO-ARG")
        return 0
    if sys.argv[1] == "--flush":
        flush()
        return 0
    try:
        n = normalise(json.loads(base64.b64decode(sys.argv[1])))
    except Exception as e:
        log(f"BAD-ARG {e!r} {sys.argv[1][:80]!r}")
        return 0
    primary_ok = True
    try:
        post("primary", n)
        log(f"SENT p{n['priority']} ({n['topic']}) {n['title']}")
    except Exception as e:
        primary_ok = False
        enqueue("primary", n, repr(e)[:120])
    if MIRROR and n["topic"] == PAGE_TOPIC:
        try:
            post("mirror", n)
            log(f"SENT [mirror] p{n['priority']} {n['title']}")
        except Exception as e:
            enqueue("mirror", n, repr(e)[:120])
    if primary_ok:
        try:
            flush()
        except Exception as e:
            log(f"FLUSH-FAIL {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
