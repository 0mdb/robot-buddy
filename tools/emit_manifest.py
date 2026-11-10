#!/usr/bin/env python3
"""Emit Buddy's Vantage capability manifest from this repo's real configuration.

`~/vantage` is a ground control station that renders a HUD from a manifest the
vehicle serves at connect. The manifest must describe what *this* robot actually
enforces — a HUD showing a limit the vehicle does not honour is the worst kind of
instrument error, and `manifest_crc` exists to catch exactly that at runtime.

So the manifest is **generated, never hand-written**. Every value below is read
from the file that owns it:

  esp32-reflex/main/config.h   chassis caps, command TTL, soft-stop ramp, hard stop
  supervisor/config.py         governor thresholds, tick rate
  supervisor/core/state.py     the mode table
  supervisor/core/tick_loop.py teleop TTL
  supervisor/workers/vision_worker.py
                               the camera's capture size, which is what Vantage's
                               video carries (the worker writes the full-res picture)
  docs/power.md                pack configuration, cross-checked against the
                               UPS monitor's discharge curve in code

Buddy differs from Scout in ways that are pure data, which is the point — it has a
face and voice AI where Scout has a camera and gimbal, its range governor is stepped
rather than a linear ramp, and its reflex MCU *ramps* to zero on command timeout
where Scout stops flat.

The teleop TTL is read from `TickLoop.__init__`'s own signature rather than copied,
so it cannot drift. (It was missing entirely until 2026-08-07 — a client that stopped
sending left the last twist latched — and this script refused to emit a `ttl_ms` it
could not honour. Keep that behaviour: never invent a failsafe number.)

Usage:
    just emit-manifest                  # to stdout
    just emit-manifest --out buddy.toml
    just emit-manifest --check <path>   # non-zero exit if <path> is stale
"""

from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REFLEX_CONFIG = REPO_ROOT / "esp32-reflex" / "main" / "config.h"

# Buddy's MCU defaults live in a designated-initializer struct:
#     .max_v_mm_s = 500,
# rather than Scout's `constexpr` constants. Same job, different shape.
DESIGNATED_RE = re.compile(r"^\s*\.([a-zA-Z_]\w*)\s*=\s*([^,]+),", re.MULTILINE)

# Design-token colour per mode. Tokens are defined in vantage's docs/DESIGN.md.
MODE_COLORS = {
    "BOOT": "text_label",
    "IDLE": "text_label",
    "TELEOP": "text_primary",
    "WANDER": "accent",
    "ERROR": "warn",
}

# The pack is parsed from docs/power.md, not copied. The copy that was here said
# "2S LiPo" (from the README) while power.md and the UPS monitor both say 2S 18650
# Li-ion — the same drift that hit Scout's generator, invisible to --check.
POWER_DOC = REPO_ROOT / "docs" / "power.md"
# "2× 18650 Li-ion in series (2S, ..." in the Battery section, and
# "2× 18650 Li-ion (2S, 7.4 V nom)" in the topology diagram.
CELLS_RE = re.compile(r"(\d+)×\s*\d{5}\s+(Li-ion|LiPo|LiFePO4)\b[^(\n]*\((\d+)S\b")
# Full-charge cell voltage per chemistry, for the cross-check against code.
FULL_CELL_MV = {"li-ion": 4200, "lipo": 4200, "lifepo4": 3650}

# The capture size the vision worker configures the camera with, and the size of the picture
# it writes into the Vantage frame slot. Read from the worker's source rather than importing
# it, which would pull in cv2 and picamera2. (VisionConfig.capture_width in config.py is a
# duplicate nothing reads; the worker's literal is what the camera actually gets.)
VISION_WORKER = REPO_ROOT / "supervisor" / "workers" / "vision_worker.py"
CAPTURE_RE = re.compile(r"self\._capture_size\s*=\s*\((\d+),\s*(\d+)\)")

# The media worker's encode clock: Vantage's bridge starts it with VANTAGE_MEDIA_FPS, default
# 30 (~/vantage supervisor/bridge.py, MediaRelay). It repeats the latest picture when the camera
# is slower, so this is the stream's rate, not the camera's (10-20 Hz on the Pi).
VIDEO_FPS = 30
# WireGuard leaves a 1420 MTU; RTP payloads stay at or under 1372 (Vantage CLAUDE.md).
VIDEO_MAX_PAYLOAD = 1372

# Client-side display threshold before the HUD says LINK_DEGRADED. Display only.
WARN_MS = 150


def _parse_designated(path: Path) -> dict[str, float]:
    """Extract numeric fields from a C designated-initializer block."""
    if not path.is_file():
        sys.exit(f"missing config header: {path}")
    out: dict[str, float] = {}
    for name, raw in DESIGNATED_RE.findall(path.read_text()):
        value = raw.split("//")[0].strip().replace("'", "").rstrip("fF")
        value = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)([uUlL]+)\b", r"\1", value)
        try:
            out[name] = float(value) if "." in value else int(value, 0)
        except ValueError:
            continue  # non-numeric initializer — not needed here
    return out


def _require(consts: dict[str, float], name: str) -> float:
    if name not in consts:
        sys.exit(
            f"{REFLEX_CONFIG.name} no longer defines .{name} — update tools/emit_manifest.py"
        )
    return consts[name]


def _section(text: str, heading: str) -> str:
    m = re.search(
        rf"^## {re.escape(heading)}\b.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    if m is None:
        sys.exit(
            f"{POWER_DOC.name} has no '## {heading}' section — update tools/emit_manifest.py"
        )
    return m.group(0)


def _pack() -> dict[str, int | str]:
    """Read the pack from docs/power.md and check it against the code that depends on it.

    The Battery section is authoritative; the topology diagram must agree. power.md also
    says the cell count is "a software-visible fact": `WaveshareUpsBMonitor`'s SoC curve
    is calibrated to it. So the curve's full-charge point must equal series × full-cell
    voltage — changing the doc without re-deriving the curve fails here.
    """
    if not POWER_DOC.is_file():
        sys.exit(f"missing power doc: {POWER_DOC}")
    text = POWER_DOC.read_text()
    found = CELLS_RE.findall(_section(text, "Battery"))
    if len(found) != 1:
        sys.exit(
            f"{POWER_DOC.name} Battery section: expected one '<N>× <cell> <chem> ... (<S>S' "
            f"statement, found {len(found)} — update tools/emit_manifest.py"
        )
    count, chem, series = int(found[0][0]), found[0][1].lower(), int(found[0][2])
    topo = CELLS_RE.findall(_section(text, "Topology"))
    if not topo or (int(topo[0][0]), topo[0][1].lower(), int(topo[0][2])) != (
        count,
        chem,
        series,
    ):
        sys.exit(
            f"{POWER_DOC.name} disagrees with itself: Battery says {count}× {chem} {series}S, "
            f"topology says {topo[0] if topo else 'nothing'}. Reconcile before emitting."
        )
    if series < 1 or count % series:
        sys.exit(f"{POWER_DOC.name}: {count} cells do not divide into {series}S")

    from supervisor.devices.power_monitor import _SOC_CURVE

    full_mv = _SOC_CURVE[0][0]
    want = series * FULL_CELL_MV[chem]
    if full_mv != want:
        sys.exit(
            f"power_monitor._SOC_CURVE starts at {full_mv} mV but {series}S {chem} is full at "
            f"{want} mV. power.md and the SoC curve disagree — re-derive the curve."
        )
    return {"series": series, "parallel": count // series, "chem": chem}


def _capture_size() -> tuple[int, int]:
    """The vision worker's camera capture size, from its own source."""
    found = CAPTURE_RE.findall(VISION_WORKER.read_text())
    if len(found) != 1:
        sys.exit(
            f"expected one `self._capture_size = (w, h)` in {VISION_WORKER}, found {len(found)}"
            " — read the capture size properly"
        )
    w, h = found[0]
    return int(w), int(h)


def _teleop_ttl_s() -> float:
    """Read the tick loop's teleop TTL from its own signature, not a copy."""
    from supervisor.core.tick_loop import TickLoop

    default = inspect.signature(TickLoop.__init__).parameters["teleop_ttl_s"].default
    if not isinstance(default, (int, float)):
        sys.exit(
            "TickLoop.teleop_ttl_s is no longer a literal default — read it properly"
        )
    return float(default)


def build() -> tuple[str, list[str]]:
    """Return (manifest_toml, warnings)."""
    from supervisor.config import ControlConfig, SafetyConfig
    from supervisor.core.state import MOTION_MODES, Mode

    reflex = _parse_designated(REFLEX_CONFIG)
    safety = SafetyConfig()
    control = ControlConfig()
    pack = _pack()
    warnings: list[str] = []

    mcu_v = int(_require(reflex, "max_v_mm_s"))
    mcu_w = int(_require(reflex, "max_w_mrad_s"))
    mcu_timeout = int(_require(reflex, "cmd_timeout_ms"))
    ramp_ms = int(_require(reflex, "soft_stop_ramp_ms"))
    ttl_ms = round(_teleop_ttl_s() * 1000)
    tick_ms = round(1000 / control.tick_hz)

    lines: list[str] = []
    add = lines.append

    add("# GENERATED by tools/emit_manifest.py — do not edit by hand.")
    add(
        "# Regenerate with `just emit-manifest`. Values trace to this repo's own config;"
    )
    add("# see the module docstring for which file owns which number.")
    add("")
    add("[robot]")
    add('id                = "buddy"')
    add('name              = "Buddy"')
    add('class             = "ground"')
    add('control_authority = "primary"')
    add('kinematics        = "differential"')
    add("")
    add("[streams]")
    add(f"telemetry = {{ port = 5601, fast_hz = {control.tick_hz} }}")
    add('status    = { datachannel = "status", hz = 1 }')
    add("control   = { port = 5602, rate_hz = 100 }")
    # Served only with --vantage --vantage-video; without it the handshake answers "no video"
    # and the client carries on with telemetry. The picture is rotated by vision.rotate_deg,
    # so 90/270 swap these; the client sizes from the decoded picture, never from this line.
    cap_w, cap_h = _capture_size()
    add(
        f'video     = {{ webrtc = true, codec = "h264", width = {cap_w}, height = {cap_h}, '
        f"fps = {VIDEO_FPS}, max_payload = {VIDEO_MAX_PAYLOAD} }}"
    )
    add("")
    add("[channels]")
    # The adapter sends an identity quaternion: only accelerometer tilt exists, with unverified
    # axis signs (devices/vantage_adapter.py, "No attitude"). Declaring it would draw a
    # confidently level horizon. Flip to true with the adapter, once bench-verified.
    add("imu_quat       = false")
    add("track_measured = true")
    add("range_forward  = true")
    # gyro_z from the reflex IMU, forwarded as rate_body[2]; the reflex's own yaw loop relies on
    # its sign. Heading is integrated from it in TickLoop: relative to boot, drifting, no north.
    add("yaw_rate       = true")
    add('heading        = "relative"')
    add(
        'cell_voltages  = {{ series = {series}, parallel = {parallel}, chem = "{chem}" }}'.format(
            **pack
        )
    )
    add("# Buddy has these where Scout has a gimbal and a camera. No client branches:")
    add("# a widget whose channel is absent is simply not drawn.")
    add('face  = { display = "320x240", touch = true, moods = true, gestures = true }')
    add("voice = { tts = true, wake_word = true, conversation = true }")
    add("")
    add("[limits]")
    add(f"speed_max_mms      = {mcu_v}")
    add(f"yaw_rate_max_mrads = {mcu_w}")
    add(f"attitude_warn_deg  = {_require(reflex, 'tilt_thresh_deg'):g}")
    add("")
    add(
        "# Buddy's governor is stepped, not a linear ramp, and it scales angular velocity"
    )
    add(
        "# too. It also has a SoC-critical park layer Scout does not. Both surface through"
    )
    add(
        "# limit_reason / authority_scale like any other layer — no client code differs."
    )
    add("[governor]")
    add(f"range_close_mm     = {safety.speed_cap_close_mm}")
    add(f"range_close_scale  = {safety.speed_cap_close_scale}")
    add(f"range_medium_mm    = {safety.speed_cap_medium_mm}")
    add(f"range_medium_scale = {safety.speed_cap_medium_scale}")
    add(f"range_stale_scale  = {safety.speed_cap_stale_scale}")
    add(f"mcu_hard_stop_mm   = {int(_require(reflex, 'range_stop_mm'))}")
    add("")
    add("# Real timings, not display stages.")
    add("[failsafe]")
    add(f"warn_ms             = {WARN_MS}")
    add(f"ttl_ms              = {ttl_ms}")
    add(f"stopped_ms          = {ttl_ms + tick_ms}  # ESTIMATE — measure and pin")
    add(f"mcu_cmd_timeout_ms  = {mcu_timeout}")
    add(f"mcu_soft_stop_ramp_ms = {ramp_ms}")
    add(
        "# Buddy's reflex MCU RAMPS to zero over mcu_soft_stop_ramp_ms on command timeout,"
    )
    add("# then brakes. Scout stops flat. E-STOP is a hard stop on both.")
    add("")
    add("# Motion modes: " + ", ".join(sorted(m.name for m in MOTION_MODES)))
    for value, mode in enumerate(Mode):
        add("")
        add("[[modes]]")
        add(f"value = {value}")
        add(f'label = "{mode.name}"')
        add(f'color = "{MODE_COLORS.get(mode.name, "text_primary")}"')
        add(f"motion = {'true' if mode in MOTION_MODES else 'false'}")
        # The one mode a client may ask to return to: disarm, and leaving ERROR (via the
        # robot's own recovery). Vantage CONTROL.md §8a — the client never names it.
        add(f"rest = {'true' if mode is Mode.IDLE else 'false'}")

    return "\n".join(lines) + "\n", warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write to this path instead of stdout")
    ap.add_argument(
        "--check",
        type=Path,
        help="compare against this file and exit non-zero if it is stale",
    )
    args = ap.parse_args()

    manifest, warnings = build()
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    if args.check:
        if not args.check.is_file():
            print(f"missing: {args.check}", file=sys.stderr)
            return 1
        if args.check.read_text() != manifest:
            print(
                f"STALE: {args.check} does not match this repo's config.\n"
                f"Regenerate it with: just emit-manifest --out {args.check}",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {args.check} is current")
        return 0

    if args.out:
        args.out.write_text(manifest)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
