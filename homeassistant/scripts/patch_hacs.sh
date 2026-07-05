#!/usr/bin/env bash
# patch_hacs.sh — Reapplies the HACS startup-timeout patch before HA starts.
#
# Problem: HACS self-updates overwrite custom_components/hacs/base.py, losing
# the asyncio.wait_for() wrapper that prevents DNS failures from blocking HA
# startup indefinitely.
#
# This script is called by the homeassistant container's entrypoint override in
# docker-compose.yml before /init runs. It re-checks and reapplies the patch on
# every container start so the fix survives HACS updates automatically.
#
# See: home-automation/homeassistant/scripts/patch_hacs.py for patch logic.
# Added 2026-04-30.

set -eo pipefail

# ── SSL CA patch (2026-07-04) ─────────────────────────────────────────────────
# HA 2026.7 / Python 3.14 base image (Alpine) is missing DigiCert Global Root CA
# from its system trust store, breaking SSL verification for api.wyzecam.com.
# Append the cert to the system bundle before s6/HA starts. Idempotent: checks
# for the marker before appending so repeated restarts don't bloat the file.
python3 - <<'PYEOF' > /config/ssl/cert_patch.log 2>&1 || true
import ssl, os

cert_file = "/config/ssl/DigiCertGlobalRootCA.pem"
paths = ssl.get_default_verify_paths()
print("openssl_cafile:", paths.openssl_cafile)
print("openssl_cafile_env:", paths.openssl_cafile_env)
print("cafile:", paths.cafile)
print("capath:", paths.capath)
print("cert_file exists:", os.path.exists(cert_file))

# Inject into whatever file Python actually reads
target = paths.cafile or paths.openssl_cafile
if target and os.path.exists(target) and os.path.exists(cert_file):
    content = open(target).read()
    marker = "DigiCert Global Root CA"
    if marker not in content:
        with open(target, "a") as f:
            f.write("\n" + open(cert_file).read())
        print("INJECTED:", target)
    else:
        print("ALREADY PRESENT:", target)
elif not target:
    print("ERROR: no CA file found to inject into")
else:
    print("ERROR: target or cert missing — target:", target)
PYEOF
# ─────────────────────────────────────────────────────────────────────────────

BASE_PY="/config/custom_components/hacs/base.py"
MARKER="asyncio.wait_for(self.async_load_hacs_from_github(), timeout=30)"

if [ ! -f "$BASE_PY" ]; then
    echo "[patch_hacs] base.py not found — HACS not installed, nothing to patch"
    exit 0
fi

if grep -qF "$MARKER" "$BASE_PY"; then
    echo "[patch_hacs] patch present — nothing to do"
    exit 0
fi

echo "[patch_hacs] patch missing (HACS likely updated itself) — reapplying..."
python3 /config/scripts/patch_hacs.py || {
    echo "[patch_hacs] WARNING: patcher failed — HA will start without the patch"
    exit 0  # Never block HA startup
}
