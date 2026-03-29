#!/usr/bin/env bash
# Install git hooks from this directory into .git/hooks/
# Run once after cloning: bash hooks/install.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_SRC="$REPO_ROOT/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

for hook in "$HOOKS_SRC"/pre-push; do
  name="$(basename "$hook")"
  cp "$hook" "$HOOKS_DST/$name"
  chmod +x "$HOOKS_DST/$name"
  echo "Installed: .git/hooks/$name"
done

echo ""
echo "Done. Hooks will run automatically on git push."
echo "Tip: brew install gitleaks  — for more thorough secret scanning."
