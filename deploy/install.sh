#!/usr/bin/env bash
# deploy/install.sh — One-time setup for robot-buddy supervisor on Raspberry Pi OS
#
# Run as your normal user (pi).  Will prompt for sudo where needed.
#
# Usage:
#   cd ~/robot-buddy
#   bash deploy/install.sh
#
# Idempotent: safe to re-run after pulling changes.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"

# ── Helpers ────────────────────────────────────────────────────────────────────
info()  { echo "[install] $*"; }
ok()    { echo "[install] ✓ $*"; }
warn()  { echo "[install] WARNING: $*" >&2; }
die()   { echo "[install] ERROR: $*" >&2; exit 1; }

# ── Paths ─────────────────────────────────────────────────────────────────────
SUPERVISOR_DIR="$REPO_ROOT/supervisor"
SERVICE_NAME="robot-buddy-supervisor"
SERVICE_FILE="$DEPLOY_DIR/$SERVICE_NAME.service"
ENV_SOURCE="$DEPLOY_DIR/supervisor.env"
ENV_DEST="/etc/robot-buddy/supervisor.env"
MODULE_NAME="supervisor"

SYSTEMD_DEST="/etc/systemd/system/$SERVICE_NAME.service"
VENV="$SUPERVISOR_DIR/.venv"

# ── 0. Sanity checks ──────────────────────────────────────────────────────────
[[ -f "$SERVICE_FILE" ]]   || die "Service file not found: $SERVICE_FILE"
[[ -d "$SUPERVISOR_DIR" ]] || die "Supervisor directory not found: $SUPERVISOR_DIR"

# Detect the user who will own the service (must not be root)
SERVICE_USER="${SUDO_USER:-${USER}}"
[[ "$SERVICE_USER" == "root" ]] && die "Run this script as a normal user, not root."

info "Installing $MODULE_NAME as user '$SERVICE_USER'"
info "Repo root: $REPO_ROOT"

# ── 1. Install uv ─────────────────────────────────────────────────────────────
if command -v uv &>/dev/null; then
    ok "uv already installed ($(uv --version))"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Put uv on PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv installed"
fi

# ── 2. System packages needed for picamera2 ───────────────────────────────────
info "Ensuring system libcamera packages are present..."
sudo apt-get install -y --no-install-recommends \
    python3-picamera2 \
    python3-libcamera \
    libcamera-dev \
    2>/dev/null || warn "apt install skipped (non-RPi OS or no network). picamera2 may be unavailable."

# ── 3. Create venv with system-site-packages (for picamera2) ─────────────────
info "Creating/updating Python virtual environment..."
# --system-site-packages lets the venv see system-installed picamera2/libcamera.
# --seed adds pip/setuptools so uv pip install works inside the venv.
# --allow-existing skips the interactive "replace?" prompt on re-runs.
uv venv --python python3 --system-site-packages --seed --allow-existing "$VENV"
ok "venv at $VENV"

# ── 4. Install Python dependencies ────────────────────────────────────────────
info "Installing $MODULE_NAME dependencies..."
cd "$SUPERVISOR_DIR"
# Use `uv pip install -e .` rather than `uv sync`.
# `uv sync` resolves ALL extras (including [rpi]) when building the lockfile and
# ends up trying to pip-install picamera2, which pulls in python-prctl which
# needs libcap-dev headers that aren't present on RPi OS.
# picamera2 is already installed as a system package (python3-picamera2 via apt)
# and is visible in the venv via --system-site-packages; we must not pip-install it.
# `uv pip install -e .` installs only the base [project.dependencies], no extras.
uv pip install --python "$VENV/bin/python" -e .

# Ear worker deps: onnxruntime, scipy, scikit-learn (resolved normally) +
# openwakeword (--no-deps because it hard-depends on tflite-runtime which has
# no wheels for py3.12+/aarch64; we only use the onnx inference backend).
info "Installing ear worker dependencies..."
uv pip install --python "$VENV/bin/python" \
    'onnxruntime>=1.16' 'scipy>=1.3' 'scikit-learn>=1' 'tqdm' 'requests'
uv pip install --python "$VENV/bin/python" --no-deps 'openwakeword>=0.6'

ok "dependencies installed"

# ── 5. Create tools venv + install dependencies ─────────────────────────────
TOOLS_DIR="$REPO_ROOT/tools"
TOOLS_VENV="$TOOLS_DIR/.venv"
info "Setting up tools environment..."
uv venv --python python3 --seed --allow-existing "$TOOLS_VENV"
uv pip install --python "$TOOLS_VENV/bin/python" -e "$TOOLS_DIR"
ok "tools environment at $TOOLS_VENV"

# ── 6. Patch service file with the actual user/home and install it ────────────
info "Installing systemd service..."
# Substitute placeholder paths if the service file uses /home/pi and the real
# user is different (e.g. ubuntu on RPi).
REAL_HOME=$(eval echo "~$SERVICE_USER")
PATCHED_SERVICE=$(sed \
    -e "s|/home/pi|$REAL_HOME|g" \
    -e "s|^User=pi|User=$SERVICE_USER|g" \
    -e "s|^Group=pi|Group=$SERVICE_USER|g" \
    "$SERVICE_FILE")
echo "$PATCHED_SERVICE" | sudo tee "$SYSTEMD_DEST" > /dev/null
sudo chmod 644 "$SYSTEMD_DEST"
ok "service file at $SYSTEMD_DEST"

# ── 7. Install environment file ───────────────────────────────────────────────
sudo mkdir -p /etc/robot-buddy
if [[ -f "$ENV_DEST" ]]; then
    info "Environment file already exists at $ENV_DEST — not overwriting."
    info "Edit it manually to change startup flags."
else
    sudo cp "$ENV_SOURCE" "$ENV_DEST"
    sudo chmod 644 "$ENV_DEST"
    ok "environment file at $ENV_DEST"
fi

# ── 8. Make sure user is in dialout + video groups ────────────────────────────
for grp in dialout video; do
    if ! groups "$SERVICE_USER" | grep -qw "$grp"; then
        sudo usermod -aG "$grp" "$SERVICE_USER"
        warn "Added $SERVICE_USER to $grp group. A re-login (or reboot) is needed for this to take effect."
    fi
done

# ── 9. Install udev rules for stable device naming ─────────────────────────────
UDEV_SRC="$DEPLOY_DIR/99-robot-buddy.rules"
UDEV_DEST="/etc/udev/rules.d/99-robot-buddy.rules"
if [[ -f "$UDEV_SRC" ]]; then
    if [[ -f "$UDEV_DEST" ]]; then
        info "udev rules already exist at $UDEV_DEST — not overwriting."
        info "To update: sudo cp $UDEV_SRC $UDEV_DEST && sudo udevadm control --reload-rules"
    else
        sudo cp "$UDEV_SRC" "$UDEV_DEST"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        ok "udev rules installed at $UDEV_DEST"
    fi
    info "To configure device symlinks, edit $UDEV_DEST and uncomment the"
    info "appropriate rules. Use 'udevadm info -a /dev/ttyACMx | grep KERNELS'"
    info "or 'python3 tools/serial_diag.py --all' to find port paths."
fi

# ── 10. Enable and (re)start the service ──────────────────────────────────────
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# ── 11. Status ────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
echo "═══════════════════════════════════════════════════════"
echo ""
ok "Done! Useful commands:"
echo "  View live logs:   journalctl -fu $SERVICE_NAME"
echo "  Stop service:     sudo systemctl stop $SERVICE_NAME"
echo "  Disable autorun:  sudo systemctl disable $SERVICE_NAME"
echo "  Edit runtime flags: sudo nano $ENV_DEST"
echo "  Update code:      bash deploy/update.sh"
