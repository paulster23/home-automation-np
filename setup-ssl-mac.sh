#!/bin/bash
# ============================================================
#  mkcert SSL Setup for Frigate — Mac
#  Run this once from the frigate-nvr/ folder:
#    chmod +x setup-ssl-mac.sh && ./setup-ssl-mac.sh
# ============================================================

set -e

echo ""
echo "🔐 Setting up trusted local SSL certificate for Frigate..."
echo ""

# ── Step 1: Install mkcert ───────────────────────────────────
if ! command -v mkcert &>/dev/null; then
  echo "📦 Installing mkcert via Homebrew..."

  # Install Homebrew if not present
  if ! command -v brew &>/dev/null; then
    echo "📦 Homebrew not found. Installing Homebrew first..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi

  brew install mkcert nss   # nss is needed for Firefox support
else
  echo "✅ mkcert already installed"
fi

# ── Step 2: Install the local CA into your system/browser ────
echo ""
echo "🔑 Installing local Certificate Authority (CA)..."
echo "   (This makes your browser trust certificates from mkcert)"
mkcert -install

# ── Step 3: Generate certificate for localhost ────────────────
# Frigate expects: fullchain.pem + privkey.pem
# mounted at:     /etc/letsencrypt/live/frigate/ inside the container
echo ""
echo "📄 Generating certificate for localhost..."
mkdir -p certs
mkcert \
  -cert-file certs/fullchain.pem \
  -key-file  certs/privkey.pem \
  localhost 127.0.0.1 ::1

echo ""
echo "✅ Done! Certificate created:"
echo "   certs/fullchain.pem"
echo "   certs/privkey.pem"
echo ""
echo "🚀 Now restart Frigate to use the new certificate:"
echo "   docker compose restart frigate"
echo ""
echo "🌐 Then open: https://localhost:8971"
echo "   No more security warnings!"
