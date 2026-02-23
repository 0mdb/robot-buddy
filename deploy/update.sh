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

info() { echo "[update] $*"; }
ok()   { echo "[update] ✓ $*"; }
die()  { echo "[update] ERROR: $*" >&2; exit 1; }

# ── Paths ─────────────────────────────────────────────────────────────────────
SUPERVISOR_DIR="$REPO_ROOT/supervisor_v2"
SERVICE_NAME="robot-buddy-supervisor-v2"
MODULE_NAME="supervisor_v2"

info "Updating $MODULE_NAME..."

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
uv pip install --python "$SUPERVISOR_DIR/.venv/bin/python" -e .  # base deps only; no extras
ok "dependencies up to date"

# ── 3. Sync tools dependencies ───────────────────────────────────────────────
TOOLS_DIR="$REPO_ROOT/tools"
if [[ -d "$TOOLS_DIR/.venv" ]]; then
    info "Syncing tools dependencies..."
    uv pip install --python "$TOOLS_DIR/.venv/bin/python" -e "$TOOLS_DIR"
    ok "tools dependencies up to date"
fi

# ── 4. Restart the supervisor service ─────────────────────────────────────────
info "Restarting $SERVICE_NAME..."
sudo systemctl restart "$SERVICE_NAME"
sleep 2  # brief pause so the service has time to crash if something is wrong

# ── 5. Show status ────────────────────────────────────────────────────────────
echo ""
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
echo ""
ok "Done. Tail logs with:  journalctl -fu $SERVICE_NAME"
