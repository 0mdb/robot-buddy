#!/usr/bin/env bash
# deploy/update.sh — Pull latest code, sync deps, restart the service.
#
# Usage:
#   cd ~/robot-buddy
#   bash deploy/update.sh
#
# Run this whenever you push new commits from your dev machine.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISOR_DIR="$REPO_ROOT/supervisor"
SERVICE_NAME="robot-buddy-supervisor"

info() { echo "[update] $*"; }
ok()   { echo "[update] ✓ $*"; }
die()  { echo "[update] ERROR: $*" >&2; exit 1; }

cd "$REPO_ROOT"

# ── 1. Pull latest changes ────────────────────────────────────────────────────
info "Fetching latest from origin..."
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git pull origin "$BRANCH"
ok "pulled branch '$BRANCH'"

# ── 2. Sync Python dependencies (in case pyproject.toml changed) ──────────────
info "Syncing dependencies..."
export PATH="$HOME/.local/bin:$PATH"
cd "$SUPERVISOR_DIR"
uv sync --extra rpi
ok "dependencies up to date"

# ── 3. Restart the supervisor service ─────────────────────────────────────────
info "Restarting $SERVICE_NAME..."
sudo systemctl restart "$SERVICE_NAME"
sleep 2  # brief pause so the service has time to crash if something is wrong

# ── 4. Show status ────────────────────────────────────────────────────────────
echo ""
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
echo ""
ok "Done. Tail logs with:  journalctl -fu $SERVICE_NAME"
