#!/usr/bin/env python3
"""patch_hacs.py — Reapplies the startup-timeout patch to HACS base.py.

Wraps async_load_hacs_from_github() in asyncio.wait_for(timeout=30) inside
startup_tasks() so a broken DNS resolver can't block HA startup indefinitely.
HACS self-updates overwrite base.py; this script restores the patch.

Called by homeassistant/scripts/patch_hacs.sh on every container start.
Added 2026-04-30.
"""

import re
import sys
import pathlib

BASE_PY = pathlib.Path("/config/custom_components/hacs/base.py")

# If this string is present the patch is already applied — nothing to do.
MARKER = "asyncio.wait_for(self.async_load_hacs_from_github(), timeout=30)"

# Match the bare await call as it appears in upstream HACS (8-space indent,
# own line). The \1 back-reference preserves the indent in case upstream ever
# changes from 8 to a different depth.
PATTERN = r'^( {8})await self\.async_load_hacs_from_github\(\)\n'

REPLACEMENT = (
    r"\1# Wrap the initial GitHub fetch in a 30-second timeout so a broken DNS\n"
    r"\1# resolver (e.g. gluetun DoT proxy failure) can't block HA startup\n"
    r"\1# indefinitely. If the fetch times out, HACS logs the failure, marks\n"
    r"\1# startup complete, and the 48h recurring task will retry automatically.\n"
    r"\1# NOTE: applied by /config/scripts/patch_hacs.py on every HA start.\n"
    r"\1# Added 2026-04-30.\n"
    r"\1try:\n"
    r"\1    await asyncio.wait_for(self.async_load_hacs_from_github(), timeout=30)\n"
    r"\1except asyncio.TimeoutError:\n"
    r"\1    self.log.error(\n"
    r'\1        "HACS: Timed out loading from GitHub during startup (30s). "\n'
    r'\1        "DNS may be unavailable. Startup will proceed without HACS data; "\n'
    r'\1        "the 48h recurring task will retry when connectivity is restored."\n'
    r"\1    )\n"
    r"\1    self.status.startup = False\n"
    r"\1    self.async_dispatch(HacsDispatchEvent.STATUS, {})\n"
    r"\1    self.set_stage(HacsStage.RUNNING)\n"
    r"\1    return\n"
)


def main() -> int:
    if not BASE_PY.exists():
        print("[patch_hacs] base.py not found — skipping")
        return 0

    src = BASE_PY.read_text()

    if MARKER in src:
        print("[patch_hacs] already patched — nothing to do")
        return 0

    new_src, count = re.subn(PATTERN, REPLACEMENT, src, flags=re.MULTILINE)

    if count == 0:
        print(
            "[patch_hacs] ERROR: target line not found — HACS structure may have "
            "changed. Check base.py manually and update patch_hacs.py if needed.",
            file=sys.stderr,
        )
        # Return 0 so patch_hacs.sh doesn't block HA startup
        return 0

    if count > 1:
        print(
            f"[patch_hacs] WARNING: matched {count} sites (expected 1). "
            "Check base.py to confirm correctness.",
            file=sys.stderr,
        )

    BASE_PY.write_text(new_src)
    print(f"[patch_hacs] patch applied ({count} substitution)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
