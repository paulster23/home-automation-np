#!/usr/bin/env python3
"""
seed_from_log.py — One-time import of historical whisper.err into voice_bench.csv

Run once to populate the CSV with your existing log history.
Only captures STT timing and transcribed text — HA-side timings
(listening, processing, responding) won't be available for historical data.

Usage:
    python3 seed_from_log.py
    python3 seed_from_log.py --log /path/to/whisper.err
"""

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR   = SCRIPT_DIR / "data"
CSV_FILE   = DATA_DIR / "voice_bench.csv"

CSV_COLUMNS = [
    "id", "timestamp", "transcribed_text", "command_type",
    "listening_ms", "stt_ms", "processing_ms", "responding_ms", "total_ms",
    "amp_muted_at_wake", "music_was_playing",
    "config_tag", "whisper_model",
]

TYPE_MAP = {
    "radio":   ["radio", "wfmu", "kexp", "kcrw", "wqxr", "wnyc", "call sign", "callsign"],
    "music":   ["play ", "song", "album", "artist", "playlist", "genre", "podcast",
                "spotify", "music", "add to queue", "liked songs",
                "stop music", "stop playing"],
    "time":    ["what time", "time is it", "what's the time"],
    "weather": ["weather", "forecast", "temperature", "rain", "snow", "sunny", "humid"],
    "home":    ["good night", "goodnight", "lights", "turn on the light",
                "turn off the light", "dim", "bright",
                "turn on the speaker", "turn off the speaker"],
}

def detect_type(text: str) -> str:
    t = text.lower()
    for cmd_type, keywords in TYPE_MAP.items():
        if any(k in t for k in keywords):
            return cmd_type
    return "other"


def parse_log(log_path: Path):
    """Parse whisper.err and yield (text, duration_ms) pairs in order."""
    pending_text = None
    entries = []

    with open(log_path) as f:
        for line in f:
            line = line.strip()

            m = re.match(r"INFO:wyoming_mlx_whisper\.handler:\s*(.+)", line)
            if m:
                pending_text = m.group(1).strip()
                continue

            m = re.match(r"WARNING:asyncio:Executing .+? took ([\d.]+) seconds", line)
            if m:
                duration_ms = int(float(m.group(1)) * 1000)
                entries.append((pending_text, duration_ms))
                pending_text = None

    return entries


def main():
    parser = argparse.ArgumentParser(description="Seed voice_bench.csv from whisper.err history")
    parser.add_argument(
        "--log",
        default="/Users/media/containers/home-automation/wyoming-mlx-whisper/log/whisper.err",
        help="Path to whisper.err log file"
    )
    parser.add_argument(
        "--tag", default="pre-bench-history",
        help="Config tag to assign to historical entries (default: pre-bench-history)"
    )
    parser.add_argument(
        "--model", default="distil-whisper-large-v3",
        help="Whisper model name to stamp on rows (default: distil-whisper-large-v3)"
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"ERROR: Log file not found: {log_path}")
        sys.exit(1)

    print(f"Parsing {log_path}…")
    entries = parse_log(log_path)
    print(f"Found {len(entries)} entries in log")

    # Check for existing CSV so we don't duplicate
    existing_ids = set()
    if CSV_FILE.exists():
        with open(CSV_FILE, newline="") as f:
            for row in csv.DictReader(f):
                existing_ids.add(row.get("id", ""))
        print(f"Existing CSV has {len(existing_ids)} entries — will skip duplicates by position")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not CSV_FILE.exists()

    written = 0
    # Use a fake start time going back from now so entries are spread out
    # Use sequential IDs based on position in log (not real timestamps)
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if is_new:
            writer.writeheader()

        for i, (text, stt_ms) in enumerate(entries):
            entry_id = f"seed_{i:04d}"
            if entry_id in existing_ids:
                continue

            cmd_type = detect_type(text or "")
            row = {
                "id":                entry_id,
                "timestamp":         "",        # no real timestamp available
                "transcribed_text":  text or "",
                "command_type":      cmd_type,
                "listening_ms":      "",        # not available from log alone
                "stt_ms":            stt_ms,
                "processing_ms":     "",
                "responding_ms":     "",
                "total_ms":          stt_ms,    # best estimate: stt ≈ total for historical
                "amp_muted_at_wake": "",
                "music_was_playing": "",
                "config_tag":        args.tag,
                "whisper_model":     args.model,
            }
            writer.writerow(row)
            written += 1

    print(f"Wrote {written} historical entries to {CSV_FILE}")
    print("Done. Open http://localhost:7700 to see them (after starting voice_bench.py).")


if __name__ == "__main__":
    main()
