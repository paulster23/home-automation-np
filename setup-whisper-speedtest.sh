#!/bin/bash
# ── mac-whisper-speedtest setup ──────────────────────────────────────────
# Run this directly on your Mac (not inside a container/VM).
# It clones the repo, installs deps, and builds the native Swift bridges.
#
# Usage:
#   cd ~/containers/home-automation
#   chmod +x setup-whisper-speedtest.sh
#   ./setup-whisper-speedtest.sh
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$SCRIPT_DIR/mac-whisper-speedtest"

echo "═══════════════════════════════════════════════════════"
echo "  mac-whisper-speedtest setup"
echo "═══════════════════════════════════════════════════════"

# ── Check prerequisites ──────────────────────────────────────────────────
echo ""
echo "▶ Checking prerequisites..."

if ! command -v swift &>/dev/null; then
    echo "✗ Swift not found. Install Xcode Command Line Tools:"
    echo "    xcode-select --install"
    exit 1
fi
echo "  ✓ Swift $(swift --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?')"

if ! command -v uv &>/dev/null; then
    echo "  ⚠ uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "  ✓ uv $(uv --version 2>&1)"

if ! command -v python3 &>/dev/null; then
    echo "✗ Python 3 not found."
    exit 1
fi
echo "  ✓ Python $(python3 --version 2>&1 | awk '{print $2}')"

# ── Clone repo ───────────────────────────────────────────────────────────
echo ""
if [ -d "$REPO_DIR/.git" ]; then
    echo "▶ Repo already cloned — pulling latest..."
    cd "$REPO_DIR"
    git pull
else
    echo "▶ Cloning repository..."
    git clone https://github.com/anvanvan/mac-whisper-speedtest.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# ── Install Python dependencies ──────────────────────────────────────────
echo ""
echo "▶ Installing Python dependencies with uv..."
uv sync

# ── Build WhisperKit Swift bridge ────────────────────────────────────────
echo ""
echo "▶ Building WhisperKit Swift bridge (this may take a few minutes)..."
cd "$REPO_DIR/tools/whisperkit-bridge"
swift build -c release
echo "  ✓ WhisperKit bridge built"

# ── Build FluidAudio bridge (optional, may fail on some systems) ─────────
echo ""
echo "▶ Building FluidAudio CoreML bridge..."
cd "$REPO_DIR/tools/fluidaudio-bridge"
if swift build -c release 2>&1; then
    echo "  ✓ FluidAudio bridge built"
else
    echo "  ⚠ FluidAudio bridge failed (optional — other implementations will work)"
fi

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✓ Setup complete!"
echo ""
echo "  Run benchmarks with:"
echo ""
echo "  # Quick test (small model, good for home automation):"
echo "  cd $REPO_DIR"
echo "  .venv/bin/mac-whisper-speedtest --model small"
echo ""
echo "  # Test the models you're currently using:"
echo "  .venv/bin/mac-whisper-speedtest --model large-v3-turbo"
echo ""
echo "  # Full comparison with multiple runs:"
echo "  .venv/bin/mac-whisper-speedtest --model small --num-runs 5"
echo ""
echo "  # Just the MLX implementations (closest to your current setup):"
echo "  .venv/bin/mac-whisper-speedtest --model large-v3-turbo \\"
echo "    --implementations MLXWhisperImplementation,LightningWhisperMLXImplementation"
echo ""
echo "═══════════════════════════════════════════════════════"
