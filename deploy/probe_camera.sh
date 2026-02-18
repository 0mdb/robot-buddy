#!/usr/bin/env bash
# deploy/probe_camera.sh — Verify the Pi camera is accessible before starting
#                          the full supervisor.
#
# Usage:
#   bash deploy/probe_camera.sh
#
# Exit code 0 = camera found and capture succeeded.
# Exit code 1 = camera not found or capture failed.

set -euo pipefail

VENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/supervisor/.venv"
PYTHON="${VENV}/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: venv not found at $VENV — run deploy/install.sh first"
    exit 1
fi

echo "Probing camera via picamera2..."

"$PYTHON" - <<'EOF'
import sys

try:
    from picamera2 import Picamera2
except ImportError as e:
    print(f"FAIL: cannot import picamera2 ({e})")
    print("      Is python3-picamera2 installed?  sudo apt install python3-picamera2")
    sys.exit(1)

cameras = Picamera2.global_camera_info()
if not cameras:
    print("FAIL: no cameras detected by libcamera")
    print("      Check: libcamera-hello --list-cameras")
    print("      Check: vcgencmd get_camera  (for legacy CSI)")
    sys.exit(1)

print(f"Found {len(cameras)} camera(s):")
for c in cameras:
    print(f"  [{c.get('Num', '?')}] {c.get('Model', 'unknown')}  location={c.get('Location', '?')}")

# Try a quick capture from camera 0
print("\nTesting capture from camera 0...")
try:
    cam = Picamera2(0)
    cam.configure(cam.create_still_configuration(main={"size": (320, 240), "format": "RGB888"}))
    cam.start()
    import time
    time.sleep(0.5)          # let AGC settle
    arr = cam.capture_array()
    cam.stop()
    print(f"OK: captured frame, shape={arr.shape}, dtype={arr.dtype}")
except Exception as e:
    print(f"FAIL: capture error: {e}")
    sys.exit(1)

print("\nCamera OK — supervisor vision should work.")
EOF
