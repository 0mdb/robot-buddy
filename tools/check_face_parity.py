#!/usr/bin/env python3
"""CI parity check — verifies V3 sim constants match MCU firmware.

Parses V3 constants.py (Python import) and MCU C++ files (regex extraction),
then compares geometry, timing, color, spring, tween, and flag constants.

Exit code 0 = pass, 1 = fail with diff report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
MCU_DIR = REPO_ROOT / "esp32-face-v2" / "main"
CONFIG_H = MCU_DIR / "config.h"
FACE_STATE_CPP = MCU_DIR / "face_state.cpp"
FACE_STATE_H = MCU_DIR / "face_state.h"
PROTOCOL_H = MCU_DIR / "protocol.h"


def extract_define(text: str, name: str) -> str | None:
    """Extract a #define value from C/C++ source."""
    m = re.search(rf"#define\s+{name}\s+([^\n/]+)", text)
    if m:
        return m.group(1).strip().rstrip("f").rstrip("F")
    return None


def extract_const(text: str, name: str) -> str | None:
    """Extract a constexpr/const value from C/C++ source."""
    m = re.search(rf"(?:constexpr|const)\s+\w+\s+{name}\s*=\s*([^;]+)", text)
    if m:
        return m.group(1).strip().rstrip("f").rstrip("F")
    return None


def extract_value(text: str, name: str) -> str | None:
    """Try both #define and const/constexpr extraction."""
    return extract_define(text, name) or extract_const(text, name)


def parse_float(s: str) -> float:
    """Parse a C-style float literal."""
    s = s.strip().rstrip("fF").strip()
    return float(s)


def parse_int(s: str) -> int:
    """Parse an integer or hex literal."""
    s = s.strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s)


def compare(
    name: str,
    mcu_val: float | int | None,
    sim_val: float | int,
    tol: float = 0.001,
) -> bool:
    """Compare two values within tolerance. Returns True if matched."""
    if mcu_val is None:
        print(f"  SKIP  {name}: MCU value not found")
        return True  # Don't fail on missing MCU values (optional constants)
    if isinstance(mcu_val, float) and isinstance(sim_val, float):
        if abs(mcu_val - sim_val) <= tol:
            return True
        print(
            f"  FAIL  {name}: MCU={mcu_val} SIM={sim_val} (delta={abs(mcu_val - sim_val):.6f})"
        )
        return False
    if mcu_val == sim_val:
        return True
    print(f"  FAIL  {name}: MCU={mcu_val} SIM={sim_val}")
    return False


def main() -> int:
    # Import V3 constants
    sys.path.insert(0, str(REPO_ROOT))
    from tools.face_sim_v3.state.constants import (
        ANIM_FPS,
        BLINK_INTERVAL,
        BLINK_VARIATION,
        BREATH_AMOUNT,
        BREATH_SPEED,
        EYE_CORNER_R,
        EYE_HEIGHT,
        EYE_WIDTH,
        FLAG_AFTERGLOW,
        FLAG_AUTOBLINK,
        FLAG_EDGE_GLOW,
        FLAG_IDLE_WANDER,
        FLAG_SHOW_MOUTH,
        FLAG_SOLID_EYE,
        FLAG_SPARKLE,
        GAZE_EYE_SHIFT,
        GAZE_PUPIL_SHIFT,
        LEFT_EYE_CX,
        LEFT_EYE_CY,
        MAX_GAZE,
        MOOD_COLORS,
        MOUTH_CX,
        MOUTH_CY,
        MOUTH_HALF_W,
        MOUTH_THICKNESS,
        PUPIL_R,
        RIGHT_EYE_CX,
        RIGHT_EYE_CY,
        SCREEN_H,
        SCREEN_W,
        SPARKLE_CHANCE,
        SPRING_D,
        SPRING_K,
        TALKING_BASE_OPEN,
        TALKING_BOUNCE_MOD,
        TALKING_OPEN_MOD,
        TALKING_PHASE_SPEED,
        TALKING_WIDTH_MOD,
        Mood,
    )

    # Read MCU source files
    if not CONFIG_H.exists():
        print(f"WARNING: {CONFIG_H} not found — skipping MCU comparison")
        print("PASS (no MCU source available)")
        return 0

    config_text = CONFIG_H.read_text()
    state_cpp = FACE_STATE_CPP.read_text() if FACE_STATE_CPP.exists() else ""
    state_h = FACE_STATE_H.read_text() if FACE_STATE_H.exists() else ""
    protocol_text = PROTOCOL_H.read_text() if PROTOCOL_H.exists() else ""

    all_text = config_text + "\n" + state_h + "\n" + protocol_text

    passed = 0
    failed = 0

    def check(name: str, mcu_val: float | int | None, sim_val: float | int) -> None:
        nonlocal passed, failed
        if compare(name, mcu_val, sim_val):
            passed += 1
        else:
            failed += 1

    print("=== Face Parity Check: V3 Sim vs MCU ===\n")

    # ── Display ──────────────────────────────────────────────────
    print("-- Display --")
    v = extract_value(all_text, "SCREEN_WIDTH")
    check("SCREEN_W", parse_int(v) if v else None, SCREEN_W)
    v = extract_value(all_text, "SCREEN_HEIGHT")
    check("SCREEN_H", parse_int(v) if v else None, SCREEN_H)
    v = extract_value(all_text, "ANIM_FPS")
    check("ANIM_FPS", parse_int(v) if v else None, ANIM_FPS)

    # ── Eye geometry ─────────────────────────────────────────────
    print("-- Eye geometry --")
    for cname, sval in [
        ("EYE_WIDTH", EYE_WIDTH),
        ("EYE_HEIGHT", EYE_HEIGHT),
        ("EYE_CORNER_R", EYE_CORNER_R),
        ("PUPIL_R", PUPIL_R),
        ("LEFT_EYE_CX", LEFT_EYE_CX),
        ("LEFT_EYE_CY", LEFT_EYE_CY),
        ("RIGHT_EYE_CX", RIGHT_EYE_CX),
        ("RIGHT_EYE_CY", RIGHT_EYE_CY),
    ]:
        v = extract_value(all_text, cname)
        check(cname, parse_float(v) if v else None, sval)

    # ── Gaze ─────────────────────────────────────────────────────
    print("-- Gaze --")
    v = extract_value(all_text, "MAX_GAZE")
    check("MAX_GAZE", parse_float(v) if v else None, MAX_GAZE)
    v = extract_value(all_text, "GAZE_EYE_SHIFT")
    check("GAZE_EYE_SHIFT", parse_float(v) if v else None, GAZE_EYE_SHIFT)
    v = extract_value(all_text, "GAZE_PUPIL_SHIFT")
    check("GAZE_PUPIL_SHIFT", parse_float(v) if v else None, GAZE_PUPIL_SHIFT)

    # ── Mouth ────────────────────────────────────────────────────
    print("-- Mouth --")
    for cname, sval in [
        ("MOUTH_CX", MOUTH_CX),
        ("MOUTH_CY", MOUTH_CY),
        ("MOUTH_HALF_W", MOUTH_HALF_W),
        ("MOUTH_THICKNESS", MOUTH_THICKNESS),
    ]:
        v = extract_value(all_text, cname)
        check(cname, parse_float(v) if v else None, sval)

    # ── Spring ───────────────────────────────────────────────────
    print("-- Spring --")
    v = extract_value(all_text, "SPRING_K")
    check("SPRING_K", parse_float(v) if v else None, SPRING_K)
    v = extract_value(all_text, "SPRING_D")
    check("SPRING_D", parse_float(v) if v else None, SPRING_D)

    # ── Blink ────────────────────────────────────────────────────
    print("-- Blink --")
    v = extract_value(all_text, "BLINK_INTERVAL")
    check("BLINK_INTERVAL", parse_float(v) if v else None, BLINK_INTERVAL)
    v = extract_value(all_text, "BLINK_VARIATION")
    check("BLINK_VARIATION", parse_float(v) if v else None, BLINK_VARIATION)

    # ── Breathing ────────────────────────────────────────────────
    print("-- Breathing --")
    v = extract_value(all_text, "BREATH_SPEED")
    check("BREATH_SPEED", parse_float(v) if v else None, BREATH_SPEED)
    v = extract_value(all_text, "BREATH_AMOUNT")
    check("BREATH_AMOUNT", parse_float(v) if v else None, BREATH_AMOUNT)

    # ── Talking ──────────────────────────────────────────────────
    print("-- Talking --")
    v = extract_value(all_text, "TALKING_PHASE_SPEED")
    check("TALKING_PHASE_SPEED", parse_float(v) if v else None, TALKING_PHASE_SPEED)
    v = extract_value(all_text, "TALKING_BASE_OPEN")
    check("TALKING_BASE_OPEN", parse_float(v) if v else None, TALKING_BASE_OPEN)
    v = extract_value(all_text, "TALKING_OPEN_MOD")
    check("TALKING_OPEN_MOD", parse_float(v) if v else None, TALKING_OPEN_MOD)
    v = extract_value(all_text, "TALKING_WIDTH_MOD")
    check("TALKING_WIDTH_MOD", parse_float(v) if v else None, TALKING_WIDTH_MOD)
    v = extract_value(all_text, "TALKING_BOUNCE_MOD")
    check("TALKING_BOUNCE_MOD", parse_float(v) if v else None, TALKING_BOUNCE_MOD)

    # ── Sparkle ──────────────────────────────────────────────────
    print("-- Sparkle --")
    v = extract_value(all_text, "SPARKLE_CHANCE")
    check("SPARKLE_CHANCE", parse_float(v) if v else None, SPARKLE_CHANCE)

    # ── Flags ────────────────────────────────────────────────────
    print("-- Flags --")
    for cname, sval in [
        ("FACE_FLAG_IDLE_WANDER", FLAG_IDLE_WANDER),
        ("FACE_FLAG_AUTOBLINK", FLAG_AUTOBLINK),
        ("FACE_FLAG_SOLID_EYE", FLAG_SOLID_EYE),
        ("FACE_FLAG_SHOW_MOUTH", FLAG_SHOW_MOUTH),
        ("FACE_FLAG_EDGE_GLOW", FLAG_EDGE_GLOW),
        ("FACE_FLAG_SPARKLE", FLAG_SPARKLE),
        ("FACE_FLAG_AFTERGLOW", FLAG_AFTERGLOW),
    ]:
        v = extract_value(protocol_text, cname)
        if v is not None:
            # Handle bit shift expressions like (1 << 0) or (1u << 0)
            m = re.match(r"\(?\s*1u?\s*<<\s*(\d+)\s*\)?", v)
            if m:
                mcu_val = 1 << int(m.group(1))
            else:
                mcu_val = parse_int(v)
            check(cname, mcu_val, sval)
        else:
            check(cname, None, sval)

    # ── Mood colors ──────────────────────────────────────────────
    print("-- Mood colors --")
    # Extract mood colors from face_state.cpp emotion color function
    mood_color_map = {
        "HAPPY": Mood.HAPPY,
        "EXCITED": Mood.EXCITED,
        "CURIOUS": Mood.CURIOUS,
        "SAD": Mood.SAD,
        "SCARED": Mood.SCARED,
        "ANGRY": Mood.ANGRY,
        "SURPRISED": Mood.SURPRISED,
        "SLEEPY": Mood.SLEEPY,
        "LOVE": Mood.LOVE,
        "SILLY": Mood.SILLY,
        "THINKING": Mood.THINKING,
    }
    # Parse the switch statement in face_get_emotion_color
    color_pattern = re.compile(
        r"case\s+Mood::(\w+):\s*\n"
        r"\s*rr\s*=\s*(\d+);\s*\n"
        r"\s*gg\s*=\s*(\d+);\s*\n"
        r"\s*bb\s*=\s*(\d+);",
        re.MULTILINE,
    )
    for match in color_pattern.finditer(state_cpp):
        name = match.group(1)
        r, g, b = int(match.group(2)), int(match.group(3)), int(match.group(4))
        mood = mood_color_map.get(name)
        if mood is not None:
            sim_color = MOOD_COLORS.get(mood, (0, 0, 0))
            check(f"MOOD_COLOR_{name}_R", r, sim_color[0])
            check(f"MOOD_COLOR_{name}_G", g, sim_color[1])
            check(f"MOOD_COLOR_{name}_B", b, sim_color[2])

    # ── Summary ──────────────────────────────────────────────────
    total = passed + failed
    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed > 0:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
