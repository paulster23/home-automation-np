#!/usr/bin/env python3
"""
voice_bench.py — Voice pipeline benchmarking daemon

Subscribes to Home Assistant's WebSocket API to track satellite state
transitions, tails the wyoming-mlx-whisper log for STT timing, and
correlates both into per-command rows written to a CSV file.

Also serves a lightweight HTTP dashboard at http://localhost:7700

Stream health monitoring (StreamMonitor)
────────────────────────────────────────
In parallel with voice benchmarking, StreamMonitor tracks audio stream
health for all active streams (Spotify Connect via librespot, or radio).

It watches two data sources:
  1. HA state_changed events on the amp entity — detects dropouts (playing
     → not-playing → playing within dropout_window_secs) vs. real stops.
  2. librespot/log/stream.log written by serve_http.py — detects pipe stalls
     (ffmpeg stdin going dry) and correlates them with dropout events.

Events are written to data/stream_health.csv and exposed via:
  GET /api/stream/status   — live stream state + 24h stats
  GET /api/stream/events   — last 200 stream_health.csv rows
"""

import argparse
import asyncio
import csv
import json
import os
import plistlib
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from aiohttp import web
import websockets  # type: ignore

# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR   = SCRIPT_DIR / "data"
CSV_FILE   = DATA_DIR / "voice_bench.csv"
RATINGS_FILE = DATA_DIR / "ratings.json"

CSV_COLUMNS = [
    "id", "timestamp", "transcribed_text", "command_type",
    "listening_ms", "stt_ms", "processing_ms", "responding_ms", "total_ms",
    "amp_muted_at_wake", "music_was_playing",
    "config_tag", "whisper_model",
]

STREAM_CSV_FILE    = DATA_DIR / "stream_health.csv"
STREAM_CSV_COLUMNS = [
    "id", "timestamp", "stream_type", "source_detail",
    "event", "duration_ms", "correlated_stall_ms", "notes",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    # Allow token to live in a separate secrets file (keeps it out of git).
    # If ha_token_file is set, read the token from that file and override ha_token.
    token_file = cfg.get("ha_token_file")
    if token_file:
        cfg["ha_token"] = Path(token_file).expanduser().read_text().strip()
    return cfg


def detect_whisper_model(plist_path: str) -> str:
    """Read the --model argument from the wyoming LaunchAgent plist."""
    try:
        p = Path(plist_path).expanduser()
        with open(p, "rb") as f:
            plist = plistlib.load(f)
        args = plist.get("ProgramArguments", [])
        for i, arg in enumerate(args):
            if arg in ("--model", "-m") and i + 1 < len(args):
                return args[i + 1].split("/")[-1]
    except Exception:
        pass
    return "unknown"


def detect_command_type(text: Optional[str]) -> str:
    if not text:
        return "other"
    t = text.lower()
    if any(x in t for x in ["radio", "wfmu", "kexp", "kcrw", "wqxr", "wnyc", "call sign", "callsign"]):
        return "radio"
    if any(x in t for x in ["play ", "song", "album", "artist", "playlist", "genre", "podcast",
                              "spotify", "music", "add to queue", "liked songs"]):
        return "music"
    if any(x in t for x in ["stop music", "stop playing", "stop the music"]):
        return "music"
    if any(x in t for x in ["what time", "time is it", "what's the time"]):
        return "time"
    if any(x in t for x in ["weather", "forecast", "temperature", "rain", "snow", "sunny", "humid"]):
        return "weather"
    if any(x in t for x in ["good night", "goodnight", "lights", "turn on the light", "turn off the light",
                              "dim", "bright", "turn on the speaker", "turn off the speaker"]):
        return "home"
    return "other"


def ms_between(t1: Optional[datetime], t2: Optional[datetime]) -> Optional[int]:
    if t1 and t2:
        return max(0, int((t2 - t1).total_seconds() * 1000))
    return None


# ── StreamMonitor ─────────────────────────────────────────────────────────────

class StreamMonitor:
    """
    Tracks audio stream health for Spotify Connect (librespot) and radio.

    Integrates two data sources:
      - HA amp entity state changes (fed in via on_amp_state from watch_ha)
      - serve_http.py stream.log (tailed for pipe stall events)

    Detects:
      play_start  — amp transitioned to playing
      play_stop   — amp was playing, stopped, did not recover within dropout_window
      dropout     — amp was playing, brief gap, then recovered within dropout_window
      pipe_stall  — serve_http.py stdin went dry (from stream.log tail)
    """

    # Known station name fragments → display name
    _STATION_NAMES = {
        "kexp": "KEXP", "wfmu": "WFMU", "kcrw": "KCRW",
        "wqxr": "WQXR", "wnyc": "WNYC", "wbgo": "WBGO",
    }

    def __init__(self, config: dict, entity_states: Dict[str, str],
                 entity_attrs: Dict[str, dict]):
        self.amp_entity      = config.get("amp_entity", "")
        self.radio_entity    = config.get("radio_active_entity",
                                          "input_boolean.radio_active")
        self.stream_log_path = config.get("librespot_stream_log", "")
        self.dropout_window  = float(config.get("dropout_window_secs", 30))

        # Shared references to VoiceBench's entity state mirrors — always current
        self._entity_states = entity_states
        self._entity_attrs  = entity_attrs

        # Current play-session state machine
        self._play_start:    Optional[datetime] = None
        self._play_stop:     Optional[datetime] = None   # set on playing→stopped
        self._stream_type:   str = "unknown"
        self._source_detail: str = ""
        self._dropout_task:  Optional[asyncio.Task] = None

        # Stall correlation: most recent STALL_END from stream.log
        self._last_stall_end_mono: float = 0.0
        self._last_stall_end_ms:   int   = 0
        self._stalls_this_session: int   = 0

        # In-memory event cache for the API (last 2000 rows)
        self._events_cache: List[dict] = []
        self._load_csv()

        print(f"[stream-monitor] Initialized  amp={self.amp_entity}"
              f"  dropout_window={self.dropout_window}s"
              f"  stream_log={self.stream_log_path or '(none)'}")

    # ── CSV ───────────────────────────────────────────────────────────────────

    def _load_csv(self):
        if STREAM_CSV_FILE.exists():
            with open(STREAM_CSV_FILE, newline="") as f:
                self._events_cache = list(csv.DictReader(f))
        print(f"[stream-monitor] Loaded {len(self._events_cache)} existing stream events")

    def _append_csv(self, row: dict):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        is_new = not STREAM_CSV_FILE.exists()
        with open(STREAM_CSV_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=STREAM_CSV_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in STREAM_CSV_COLUMNS})
        self._events_cache.append(row)
        if len(self._events_cache) > 2000:
            self._events_cache = self._events_cache[-2000:]

    def _log_event(self, event: str, ts: datetime, *,
                   duration_ms: Optional[int] = None,
                   correlated_stall_ms: Optional[int] = None,
                   notes: str = "") -> None:
        row = {
            "id":                  ts.strftime("%Y%m%d_%H%M%S_%f")[:-3],
            "timestamp":           ts.isoformat(),
            "stream_type":         self._stream_type,
            "source_detail":       self._source_detail,
            "event":               event,
            "duration_ms":         duration_ms if duration_ms is not None else "",
            "correlated_stall_ms": correlated_stall_ms if correlated_stall_ms is not None else "",
            "notes":               notes,
        }
        self._append_csv(row)
        corr = f"  stall={correlated_stall_ms}ms" if correlated_stall_ms else ""
        dur  = f"  {duration_ms}ms" if duration_ms is not None else ""
        print(f"[stream-monitor] {event:12s} {self._stream_type:8s}"
              f"  {self._source_detail[:20]}{dur}{corr}")

    # ── Stream type detection ─────────────────────────────────────────────────

    def _refresh_stream_type(self) -> None:
        """Determine current stream type from shared HA entity state."""
        radio_state = self._entity_states.get(self.radio_entity, "off")
        if radio_state == "on":
            self._stream_type = "radio"
            attrs = self._entity_attrs.get(self.amp_entity, {})
            url   = attrs.get("media_content_id", "")
            self._source_detail = self._station_from_url(url) or url[:40] or "radio"
        else:
            self._stream_type   = "spotify"
            self._source_detail = "librespot"

    @classmethod
    def _station_from_url(cls, url: str) -> str:
        url_lower = url.lower()
        for fragment, name in cls._STATION_NAMES.items():
            if fragment in url_lower:
                return name
        return ""

    # ── HA amp state handler (called from VoiceBench.watch_ha) ───────────────

    async def on_amp_state(self, old_state: str, new_state: str,
                           ts: datetime) -> None:
        """
        Called whenever the amp entity changes state.

        State machine:
          * → playing      : play_start (or dropout recovery)
          playing → other  : start dropout_window timer
          timer fires      : play_stop (no recovery within window)
        """
        if new_state == "playing":
            if self._play_stop is not None:
                # ── Dropout recovery ──────────────────────────────────────────
                dropout_ms = int((ts - self._play_stop).total_seconds() * 1000)

                # Correlate: was there a pipe stall logged in the last dropout_window?
                corr_stall: Optional[int] = None
                if self._last_stall_end_mono > 0:
                    age_s = time.monotonic() - self._last_stall_end_mono
                    if age_s < self.dropout_window:
                        corr_stall = self._last_stall_end_ms

                self._log_event("dropout", self._play_stop,
                                duration_ms=dropout_ms,
                                correlated_stall_ms=corr_stall)

                # Cancel the play_stop timer — we recovered before it fired
                if self._dropout_task and not self._dropout_task.done():
                    self._dropout_task.cancel()
                    self._dropout_task = None

                self._play_stop         = None
                self._last_stall_end_ms = 0
                # Keep _play_start and session — still in the same play session

            elif self._play_start is None:
                # ── Fresh play start ──────────────────────────────────────────
                self._refresh_stream_type()
                self._play_start          = ts
                self._stalls_this_session = 0
                self._last_stall_end_ms   = 0
                self._log_event("play_start", ts)

        elif old_state == "playing" and new_state in ("idle", "paused", "off", "unavailable"):
            # ── Playing stopped — may be dropout or real stop ─────────────────
            self._play_stop = ts

            # Cancel any existing timer before starting a fresh one
            if self._dropout_task and not self._dropout_task.done():
                self._dropout_task.cancel()
            self._dropout_task = asyncio.create_task(self._dropout_timer(ts))

    async def _dropout_timer(self, stop_ts: datetime) -> None:
        """
        Wait dropout_window seconds. If amp still not playing, it's a real
        stop — log play_stop and reset session state.
        """
        await asyncio.sleep(self.dropout_window)

        # _play_stop still set means no recovery arrived during the window
        if self._play_stop is not None and self._play_start is not None:
            session_ms = int((stop_ts - self._play_start).total_seconds() * 1000)
            self._log_event("play_stop", stop_ts,
                            duration_ms=session_ms,
                            notes=f"session {session_ms // 1000}s")

        # Reset session state regardless
        self._play_start          = None
        self._play_stop           = None
        self._stalls_this_session = 0
        self._dropout_task        = None

    # ── serve_http.py stream.log tail ─────────────────────────────────────────

    async def tail_stream_log(self) -> None:
        """
        Tail librespot/log/stream.log for STALL_* and CLIENT_* events.
        STALL_END events update the stall correlation state used by on_amp_state.
        """
        log_path = Path(self.stream_log_path).expanduser()

        # Start at current EOF so we don't replay history on startup
        last_pos = log_path.stat().st_size if log_path.exists() else 0
        print(f"[stream-monitor] Tailing stream log: {log_path}  (offset={last_pos})")

        while True:
            await asyncio.sleep(0.25)
            try:
                if not log_path.exists():
                    continue

                current_size = log_path.stat().st_size
                if current_size < last_pos:
                    last_pos = 0   # file rotated or truncated
                if current_size <= last_pos:
                    continue

                with open(log_path) as f:
                    f.seek(last_pos)
                    new_text = f.read()
                last_pos = current_size

                for line in new_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    await self._parse_stream_log_line(line)

            except Exception as e:
                print(f"[stream-monitor] stream.log tail error: {e!r}")
                await asyncio.sleep(2)

    async def _parse_stream_log_line(self, line: str) -> None:
        # Format: 2026-05-03T05:24:17.123Z <EVENT_TOKEN> [rest]
        parts = line.split(" ", 2)
        if len(parts) < 2:
            return
        ts_str, event_token = parts[0], parts[1]
        rest = parts[2] if len(parts) > 2 else ""

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone()
        except ValueError:
            ts = datetime.now().astimezone()

        if event_token == "STALL_END":
            # STALL_END <ms>ms — record for correlation and log to CSV
            m = re.match(r"(\d+)ms", rest)
            stall_ms = int(m.group(1)) if m else 0
            self._last_stall_end_mono  = time.monotonic()
            self._last_stall_end_ms    = stall_ms
            self._stalls_this_session += 1
            # Log pipe_stall to stream_health.csv only during an active session
            if self._play_start is not None:
                self._log_event("pipe_stall", ts, duration_ms=stall_ms)

        elif event_token == "CLIENT_CONNECT":
            print(f"[stream-monitor] ESPHome connected  {rest}")

        elif event_token == "CLIENT_DISCONNECT":
            print(f"[stream-monitor] ESPHome disconnected  {rest}")

    # ── API handlers ──────────────────────────────────────────────────────────

    async def api_status(self, _req: web.Request) -> web.Response:
        now        = datetime.now(timezone.utc)
        cutoff_24h = (now - timedelta(hours=24)).isoformat()

        recent   = [e for e in self._events_cache if e.get("timestamp", "") >= cutoff_24h]
        dropouts = [e for e in recent if e["event"] == "dropout"]
        stalls   = [e for e in recent if e["event"] == "pipe_stall"]
        dropout_durations = [int(e["duration_ms"]) for e in dropouts if e.get("duration_ms")]
        correlated        = [e for e in dropouts if e.get("correlated_stall_ms")]

        # Dropouts per hour over the observed window
        if recent:
            oldest_ts = datetime.fromisoformat(recent[0]["timestamp"])
            if oldest_ts.tzinfo is None:
                oldest_ts = oldest_ts.replace(tzinfo=timezone.utc)
            hours_window = max(
                (now - oldest_ts.astimezone(timezone.utc)).total_seconds() / 3600,
                0.1
            )
        else:
            hours_window = 1.0
        dropouts_per_hr = round(len(dropouts) / hours_window, 1)

        mean_dropout = (round(sum(dropout_durations) / len(dropout_durations))
                        if dropout_durations else None)
        max_dropout  = max(dropout_durations) if dropout_durations else None
        corr_pct     = (round(len(correlated) / len(dropouts) * 100)
                        if dropouts else None)

        # Current playing duration
        playing_duration_s = None
        if self._play_start is not None and self._play_stop is None:
            playing_duration_s = int(
                (datetime.now().astimezone() - self._play_start).total_seconds()
            )

        # Last dropout for the status card
        last_dropout = next(
            (e for e in reversed(self._events_cache) if e["event"] == "dropout"),
            None
        )

        amp_state = self._entity_states.get(self.amp_entity, "")
        if amp_state == "playing":
            state = "playing"
        elif amp_state in ("idle", "paused", "off"):
            state = "stopped"
        else:
            state = "unknown"

        return web.json_response({
            "state":                  state,
            "stream_type":            self._stream_type,
            "source_detail":          self._source_detail,
            "playing_since_iso":      self._play_start.isoformat() if self._play_start else None,
            "playing_duration_s":     playing_duration_s,
            "stalls_this_session":    self._stalls_this_session,
            "last_dropout_ms":        int(last_dropout["duration_ms"]) if last_dropout and last_dropout.get("duration_ms") else None,
            "last_dropout_iso":       last_dropout["timestamp"] if last_dropout else None,
            "dropouts_24h":           len(dropouts),
            "dropouts_per_hr":        dropouts_per_hr,
            "mean_dropout_ms":        mean_dropout,
            "max_dropout_ms":         max_dropout,
            "stalls_24h":             len(stalls),
            "stall_correlated_count": len(correlated),
            "stall_correlation_pct":  corr_pct,
        })

    async def api_events(self, _req: web.Request) -> web.Response:
        return web.json_response(list(reversed(self._events_cache[-200:])))

    # ── Main coroutine ────────────────────────────────────────────────────────

    async def run(self) -> None:
        if self.stream_log_path:
            await self.tail_stream_log()
        else:
            # No stream log configured — on_amp_state is still called externally.
            # Keep the coroutine alive so asyncio.gather doesn't drop it.
            while True:
                await asyncio.sleep(3600)


# ── Pipeline Session ─────────────────────────────────────────────────────────

class PipelineSession:
    """Tracks one complete voice command pipeline run."""

    def __init__(self, listening_start: datetime):
        self.id = listening_start.strftime("%Y%m%d_%H%M%S_%f")[:-3]
        self.listening_start: datetime              = listening_start
        self.listening_end:   Optional[datetime]   = None
        self.processing_start: Optional[datetime]  = None
        self.responding_start: Optional[datetime]  = None
        self.pipeline_end:    Optional[datetime]   = None
        self.transcribed_text: Optional[str]       = None
        self.stt_ms:          Optional[int]        = None
        self.amp_muted_at_wake: Optional[bool]     = None
        self.music_was_playing: Optional[bool]     = None

    def to_row(self, config_tag: str, whisper_model: str) -> dict:
        listening = ms_between(self.listening_start, self.listening_end)

        # processing_ms: listening-end → responding-start
        proc = None
        if self.processing_start and self.responding_start:
            proc = ms_between(self.processing_start, self.responding_start)
        elif self.listening_end and self.responding_start:
            proc = ms_between(self.listening_end, self.responding_start)

        resp  = ms_between(self.responding_start, self.pipeline_end)
        total = ms_between(self.listening_start, self.pipeline_end)

        def b2s(v: Optional[bool]) -> str:
            if v is None:
                return ""
            return "true" if v else "false"

        return {
            "id":                self.id,
            "timestamp":         self.listening_start.isoformat(),
            "transcribed_text":  self.transcribed_text or "",
            "command_type":      detect_command_type(self.transcribed_text),
            "listening_ms":      listening or "",
            "stt_ms":            self.stt_ms or "",
            "processing_ms":     proc or "",
            "responding_ms":     resp or "",
            "total_ms":          total or "",
            "amp_muted_at_wake": b2s(self.amp_muted_at_wake),
            "music_was_playing": b2s(self.music_was_playing),
            "config_tag":        config_tag,
            "whisper_model":     whisper_model,
        }


# ── VoiceBench ───────────────────────────────────────────────────────────────

class VoiceBench:

    def __init__(self, config: dict):
        self.config       = config
        self.config_tag   = config.get("tag", "default")
        self.whisper_model = (
            config.get("whisper_model")
            or detect_whisper_model(config.get("whisper_plist", ""))
        )
        self.notes        = config.get("notes", "")

        self.current_session: Optional[PipelineSession] = None
        # Buffer of (wall_clock_ts, text, duration_ms) from whisper log
        self.recent_stt: List[Tuple[datetime, Optional[str], int]] = []
        # Local mirror of entity states for snapshot at wake time
        self.entity_states: Dict[str, str] = {}
        self.entity_attrs:  Dict[str, dict] = {}

        self.entries_cache: List[dict] = []
        self._load_csv()

        # Stream monitor — enabled if amp_entity is configured
        amp_entity = config.get("amp_entity", "")
        if amp_entity:
            self.stream_monitor: Optional[StreamMonitor] = StreamMonitor(
                config, self.entity_states, self.entity_attrs
            )
        else:
            self.stream_monitor = None

    # ── CSV ──────────────────────────────────────────────────────────────────

    def _load_csv(self):
        if CSV_FILE.exists():
            with open(CSV_FILE, newline="") as f:
                self.entries_cache = list(csv.DictReader(f))
        print(f"[voice-bench] Loaded {len(self.entries_cache)} existing entries from CSV")

    def _append_csv(self, row: dict):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        is_new = not CSV_FILE.exists()
        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
        self.entries_cache.append(row)
        if len(self.entries_cache) > 2000:
            self.entries_cache = self.entries_cache[-2000:]

    # ── Ratings ──────────────────────────────────────────────────────────────

    def load_ratings(self) -> dict:
        if RATINGS_FILE.exists():
            with open(RATINGS_FILE) as f:
                return json.load(f)
        return {}

    def save_rating(self, entry_id: str, rating: int):
        ratings = self.load_ratings()
        ratings[entry_id] = rating
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(RATINGS_FILE, "w") as f:
            json.dump(ratings, f, indent=2)

    # ── HA WebSocket ──────────────────────────────────────────────────────────

    async def watch_ha(self):
        url          = self.config["ha_websocket_url"]
        token        = self.config["ha_token"]
        satellite_id = self.config["satellite_entity"]
        amp_id       = self.config.get("amp_entity", "")
        music_id     = self.config.get("music_entity", "")

        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    # ── Auth handshake ──────────────────────────────────────
                    msg = json.loads(await ws.recv())
                    if msg.get("type") != "auth_required":
                        print(f"[voice-bench] Unexpected HA message: {msg}")
                        await asyncio.sleep(5)
                        continue

                    await ws.send(json.dumps({"type": "auth", "access_token": token}))
                    msg = json.loads(await ws.recv())
                    if msg.get("type") != "auth_ok":
                        print(f"[voice-bench] HA auth failed: {msg.get('message', msg)}")
                        await asyncio.sleep(15)
                        continue

                    # ── Subscribe to state_changed events ──────────────────
                    await ws.send(json.dumps({
                        "id": 1, "type": "subscribe_events",
                        "event_type": "state_changed"
                    }))
                    await ws.recv()  # subscription ack

                    print(f"[voice-bench] Connected to HA ✓  watching: {satellite_id}")

                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") != "event":
                            continue
                        event = msg["event"]
                        if event.get("event_type") != "state_changed":
                            continue
                        data      = event["data"]
                        entity_id = data["entity_id"]
                        new_obj   = data.get("new_state") or {}
                        old_obj   = data.get("old_state") or {}
                        new_state = new_obj.get("state", "")
                        old_state = old_obj.get("state", "")
                        attrs     = new_obj.get("attributes", {})

                        # Track all entities for snapshot at wake time
                        self.entity_states[entity_id] = new_state
                        self.entity_attrs[entity_id]  = attrs

                        if entity_id == satellite_id:
                            raw_ts = new_obj.get("last_updated", "")
                            try:
                                ts = datetime.fromisoformat(
                                    raw_ts.replace("Z", "+00:00")
                                ).astimezone()
                            except Exception:
                                ts = datetime.now().astimezone()
                            await self._on_satellite(old_state, new_state, ts, amp_id, music_id)

                        # ── Feed amp state changes to stream monitor ────────
                        elif self.stream_monitor and entity_id == amp_id and amp_id:
                            raw_ts = new_obj.get("last_updated", "")
                            try:
                                ts = datetime.fromisoformat(
                                    raw_ts.replace("Z", "+00:00")
                                ).astimezone()
                            except Exception:
                                ts = datetime.now().astimezone()
                            await self.stream_monitor.on_amp_state(old_state, new_state, ts)

            except Exception as e:
                print(f"[voice-bench] HA WebSocket error: {e!r} — reconnecting in 5s…")
                await asyncio.sleep(5)

    async def _on_satellite(self, old: str, new: str, ts: datetime,
                             amp_id: str, music_id: str):
        # ── Wake word detected ────────────────────────────────────────────
        if new == "listening" and old == "idle":
            self.current_session = PipelineSession(ts)
            s = self.current_session

            # Snapshot amp mute state
            if amp_id:
                amp_attrs = self.entity_attrs.get(amp_id, {})
                muted = amp_attrs.get("is_volume_muted")
                if muted is not None:
                    s.amp_muted_at_wake = bool(muted)

            # Snapshot music state
            if music_id:
                s.music_was_playing = (self.entity_states.get(music_id) == "playing")

            print(f"[voice-bench] [{ts.strftime('%H:%M:%S')}] ▶ Wake → listening  "
                  f"amp_muted={s.amp_muted_at_wake}  music={s.music_was_playing}")
            return

        s = self.current_session
        if not s:
            return

        # ── Listening → processing (STT done, HA processing intent) ──────
        if new == "processing" and old == "listening":
            s.listening_end    = ts
            s.processing_start = ts
            dur = ms_between(s.listening_start, ts) or 0
            print(f"[voice-bench] [{ts.strftime('%H:%M:%S')}] listening → processing  ({dur}ms)")

        # ── → responding (TTS starting) ───────────────────────────────────
        elif new == "responding":
            if not s.listening_end:
                s.listening_end    = ts
            if not s.processing_start:
                s.processing_start = ts
            s.responding_start = ts
            print(f"[voice-bench] [{ts.strftime('%H:%M:%S')}] → responding")

        # ── → idle (pipeline complete) ────────────────────────────────────
        elif new == "idle" and old != "idle":
            if not s.listening_end:
                s.listening_end = ts
            s.pipeline_end = ts

            if old == "listening":
                # No intent matched or pipeline aborted — skip logging
                print(f"[voice-bench] [{ts.strftime('%H:%M:%S')}] Command aborted (no intent matched)")
                self.current_session = None
            else:
                await self._finalize_session()

    async def _finalize_session(self):
        s = self.current_session
        if not s:
            return
        self.current_session = None

        # Wait briefly for the whisper log tail loop to catch up. The VAD
        # transcription result (slower, ~1.5-2.5s wall time) may not have been
        # written to the log file yet when the satellite hits idle. The AudioStop
        # cleanup transcription is faster and arrives first, so without this wait
        # the correlator sees only the null/blank result and logs (no transcription).
        # Bumped 0.5 → 1.5s: direct ESPHome path completes faster than the old
        # MA-proxied path, so the pipeline end now races the whisper log write
        # more aggressively.
        await asyncio.sleep(1.5)

        # ── Correlate with whisper STT entries ────────────────────────────
        if self.recent_stt and s.listening_start:
            # The STT result is logged by whisper AFTER the listening phase ends
            # (whisper runs during the HA "processing" phase), so use the full
            # pipeline end as the right boundary.
            window_end = s.pipeline_end or s.listening_end or datetime.now().astimezone()

            matched_idx = None

            # Primary: find the STT entry closest in time to window_end that
            # falls within the full pipeline window (listening_start → pipeline_end).
            # Prefer non-empty transcriptions — the small model can produce fast
            # empty hits from noise at the edges of the window that would otherwise
            # win on proximity alone.
            best_delta = None
            best_delta_nonempty = None
            matched_idx_nonempty = None
            for i, (stt_ts, text, duration_ms) in enumerate(self.recent_stt):
                if s.listening_start <= stt_ts <= window_end:
                    delta = abs((stt_ts - window_end).total_seconds())
                    if text and (best_delta_nonempty is None or delta < best_delta_nonempty):
                        best_delta_nonempty = delta
                        matched_idx_nonempty = i
                    if best_delta is None or delta < best_delta:
                        best_delta = delta
                        matched_idx = i
            # Prefer the closest non-empty match if one exists
            if matched_idx_nonempty is not None:
                matched_idx = matched_idx_nonempty

            if matched_idx is not None:
                stt_ts, text, duration_ms = self.recent_stt[matched_idx]
                s.transcribed_text = text
                s.stt_ms           = duration_ms

            # Fallback: nearest STT entry within 8s of window_end
            if not s.transcribed_text and self.recent_stt:
                best_delta = None
                for i, (stt_ts, text, duration_ms) in enumerate(self.recent_stt):
                    delta = abs((stt_ts - window_end).total_seconds())
                    if delta < 8 and (best_delta is None or delta < best_delta):
                        best_delta = delta
                        matched_idx = i
                if matched_idx is not None:
                    stt_ts, text, duration_ms = self.recent_stt[matched_idx]
                    s.transcribed_text = text
                    s.stt_ms           = duration_ms

            # Consume the matched entry so it can't pollute the next session
            if matched_idx is not None:
                self.recent_stt.pop(matched_idx)

        row = s.to_row(self.config_tag, self.whisper_model)
        self._append_csv(row)

        total_s = int(row.get("total_ms") or 0) / 1000
        stt_s   = int(row.get("stt_ms") or 0) / 1000
        print(
            f"[voice-bench] ✓  '{(row['transcribed_text'] or '?')[:50]}'  "
            f"total={total_s:.1f}s  stt={stt_s:.1f}s  "
            f"type={row['command_type']}  tag={row['config_tag']}"
        )

    # ── Whisper Log Tail ──────────────────────────────────────────────────────

    async def tail_whisper_log(self):
        log_path = Path(self.config["whisper_log"]).expanduser()
        pending_text: Optional[str] = None

        # Start at the current end of file (don't replay history)
        last_pos = log_path.stat().st_size if log_path.exists() else 0
        print(f"[voice-bench] Tailing whisper log: {log_path}  (offset={last_pos})")

        while True:
            await asyncio.sleep(0.1)
            try:
                if not log_path.exists():
                    continue

                current_size = log_path.stat().st_size
                if current_size < last_pos:
                    # File was rotated — reset to beginning
                    last_pos = 0

                if current_size <= last_pos:
                    continue

                with open(log_path) as f:
                    f.seek(last_pos)
                    new_lines = f.read()
                last_pos = current_size

                for line in new_lines.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    # Transcribed text line
                    # Matches both wyoming_mlx_whisper and wyoming_whisperkit handler loggers.
                    # Exclude VAD status lines (e.g. "VAD early trigger — ...") which are also
                    # emitted as INFO from the same logger but are not transcription output.
                    # When VAD fires early, the handler transcribes twice: once for the VAD
                    # clip (real text) and once for the trailing AudioStop audio (empty).
                    # The empty INFO line resets pending_text so the stale real text can't be
                    # re-used by the second timing line.
                    m = re.match(r"INFO:wyoming_(?:mlx_whisper|whisperkit)\.handler:(.*)", line)
                    if m:
                        text = m.group(1).strip()
                        # Reject: empty, VAD status lines, or WhisperKit blank-audio sentinel
                        if text and not text.startswith("VAD ") and text != "[BLANK_AUDIO]":
                            pending_text = text
                        else:
                            # Empty, VAD status, or [BLANK_AUDIO] — reset so the next timing
                            # line doesn't re-use a stale pending_text from a prior transcription
                            pending_text = None
                        continue

                    # Timing line — wyoming_mlx_whisper emits a WARNING:asyncio slow-callback line
                    m = re.match(r"WARNING:asyncio:Executing .+? took ([\d.]+) seconds", line)
                    if m:
                        duration_ms = int(float(m.group(1)) * 1000)
                        ts_now = datetime.now().astimezone()
                        self.recent_stt.append((ts_now, pending_text, duration_ms))
                        if len(self.recent_stt) > 20:
                            self.recent_stt = self.recent_stt[-20:]
                        print(f"[voice-bench] STT  '{(pending_text or '')[:45]}'  {duration_ms}ms")
                        pending_text = None
                        continue

                    # Timing line — wyoming_whisperkit logs "WhisperKit internal time: Xms  wall: Yms"
                    # We use the wall time so it matches the same real-world latency concept as the
                    # asyncio slow-callback figure (subprocess spawn + CoreML inference).
                    m = re.match(r"DEBUG:wyoming_whisperkit\.handler:WhisperKit internal time: [\d.]+ ms\s+wall: ([\d.]+) ms", line)
                    if m:
                        duration_ms = int(float(m.group(1)))
                        ts_now = datetime.now().astimezone()
                        self.recent_stt.append((ts_now, pending_text, duration_ms))
                        if len(self.recent_stt) > 20:
                            self.recent_stt = self.recent_stt[-20:]
                        print(f"[voice-bench] STT  '{(pending_text or '')[:45]}'  {duration_ms}ms")
                        pending_text = None

            except Exception as e:
                print(f"[voice-bench] Log tail error: {e!r}")
                await asyncio.sleep(1)

    # ── HTTP Server ───────────────────────────────────────────────────────────

    async def start_server(self):
        app = web.Application()
        app.router.add_get("/",                          self._serve_index)
        app.router.add_get("/api/entries",               self._api_entries)
        app.router.add_post("/api/ratings/{entry_id}",   self._api_set_rating)
        app.router.add_get("/api/config",                self._api_config)

        # Stream health endpoints (only if stream monitor is active)
        if self.stream_monitor:
            app.router.add_get("/api/stream/status", self.stream_monitor.api_status)
            app.router.add_get("/api/stream/events", self.stream_monitor.api_events)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        port = self.config.get("port", 7700)
        site = web.TCPSite(runner, "0.0.0.0", port)
        try:
            await site.start()
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"[voice-bench] Port {port} already in use — another instance is running. Exiting cleanly.")
                os._exit(0)  # Bypass asyncio.gather which swallows SystemExit
            raise
        print(f"[voice-bench] Dashboard →  http://localhost:{port}")

    async def _serve_index(self, _req):
        html_file = SCRIPT_DIR / "index.html"
        return web.Response(text=html_file.read_text(), content_type="text/html")

    async def _api_entries(self, _req):
        ratings = self.load_ratings()
        result  = []
        for e in self.entries_cache[-500:]:
            row = dict(e)
            row["rating"] = int(ratings.get(row.get("id", ""), 0))
            result.append(row)
        return web.json_response(list(reversed(result)))

    async def _api_set_rating(self, req):
        entry_id = req.match_info["entry_id"]
        body     = await req.json()
        self.save_rating(entry_id, int(body.get("rating", 0)))
        return web.json_response({"ok": True})

    async def _api_config(self, _req):
        return web.json_response({
            "tag":                   self.config_tag,
            "whisper_model":         self.whisper_model,
            "notes":                 self.notes,
            "stream_monitor_active": self.stream_monitor is not None,
        })

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tasks = [
            self.watch_ha(),
            self.tail_whisper_log(),
            self.start_server(),
        ]
        if self.stream_monitor:
            tasks.append(self.stream_monitor.run())
        await asyncio.gather(*tasks)


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice pipeline benchmark daemon")
    parser.add_argument(
        "--config", default=str(SCRIPT_DIR / "config.yaml"),
        help="Path to config.yaml (default: ./config.yaml)"
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[voice-bench] ERROR: config not found at {config_path}")
        print("[voice-bench] Copy config.yaml.example to config.yaml and fill in your settings.")
        sys.exit(1)

    cfg   = load_config(config_path)
    bench = VoiceBench(cfg)

    try:
        asyncio.run(bench.run())
    except KeyboardInterrupt:
        print("\n[voice-bench] Stopped.")
    except SystemExit:
        raise
