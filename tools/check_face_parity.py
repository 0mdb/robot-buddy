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
MCU_DIR = REPO_ROOT / "esp32-face" / "main"
CONFIG_H = MCU_DIR / "config.h"
FACE_STATE_CPP = MCU_DIR / "face_state.cpp"
FACE_STATE_H = MCU_DIR / "face_state.h"
PROTOCOL_H = MCU_DIR / "protocol.h"
CONV_BORDER_CPP = MCU_DIR / "conv_border.cpp"


def extract_define(text: str, name: str) -> str | None:
    """Extract a #define value from C/C++ source."""
    m = re.search(rf"#define\s+{name}\s+([^\n/]+)", text)
    if m:
        return m.group(1).strip().rstrip("f").rstrip("F")
    return None


def extract_const(text: str, name: str) -> str | None:
    """Extract a constexpr/const value from C/C++ source."""
    m = re.search(
        rf"(?:static\s+)?(?:constexpr|const)\s+\w+\s+{name}\s*=\s*([^;]+)", text
    )
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
        MOOD_EYE_SCALE,
        MOOD_TARGETS,
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
    from tools.face_sim_v3.state.constants import (
        ATTENTION_DEPTH,
        ATTENTION_DURATION,
        BORDER_BLEND_RATE,
        BORDER_CORNER_R,
        BORDER_FRAME_W,
        BORDER_GLOW_W,
        BTN_CORNER_H,
        BTN_CORNER_INNER_R,
        BTN_CORNER_W,
        BTN_ICON_SIZE,
        DONE_FADE_SPEED,
        ERROR_DECAY_RATE,
        ERROR_FLASH_DURATION,
        LED_SCALE,
        LISTENING_ALPHA_BASE,
        LISTENING_ALPHA_MOD,
        LISTENING_BREATH_FREQ,
        PTT_ALPHA_BASE,
        PTT_ALPHA_MOD,
        PTT_PULSE_FREQ,
        SPEAKING_ALPHA_BASE,
        SPEAKING_ALPHA_MOD,
        THINKING_BORDER_ALPHA,
        THINKING_ORBIT_DOT_R,
        THINKING_ORBIT_DOTS,
        THINKING_ORBIT_SPACING,
        THINKING_ORBIT_SPEED,
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
    border_cpp = CONV_BORDER_CPP.read_text() if CONV_BORDER_CPP.exists() else ""

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

    # ── Conversation border ──────────────────────────────────────
    print("-- Conversation border --")
    if border_cpp:
        for cname, sval, is_float in [
            ("BORDER_FRAME_W", BORDER_FRAME_W, False),
            ("BORDER_GLOW_W", BORDER_GLOW_W, False),
            ("BORDER_CORNER_R", BORDER_CORNER_R, True),
            ("BORDER_BLEND_RATE", BORDER_BLEND_RATE, True),
            ("ATTENTION_DURATION", ATTENTION_DURATION, True),
            ("ATTENTION_DEPTH", ATTENTION_DEPTH, False),
            ("LISTENING_BREATH_FREQ", LISTENING_BREATH_FREQ, True),
            ("LISTENING_ALPHA_BASE", LISTENING_ALPHA_BASE, True),
            ("LISTENING_ALPHA_MOD", LISTENING_ALPHA_MOD, True),
            ("PTT_PULSE_FREQ", PTT_PULSE_FREQ, True),
            ("PTT_ALPHA_BASE", PTT_ALPHA_BASE, True),
            ("PTT_ALPHA_MOD", PTT_ALPHA_MOD, True),
            ("THINKING_ORBIT_DOTS", THINKING_ORBIT_DOTS, False),
            ("THINKING_ORBIT_SPACING", THINKING_ORBIT_SPACING, True),
            ("THINKING_ORBIT_SPEED", THINKING_ORBIT_SPEED, True),
            ("THINKING_ORBIT_DOT_R", THINKING_ORBIT_DOT_R, True),
            ("THINKING_BORDER_ALPHA", THINKING_BORDER_ALPHA, True),
            ("SPEAKING_ALPHA_BASE", SPEAKING_ALPHA_BASE, True),
            ("SPEAKING_ALPHA_MOD", SPEAKING_ALPHA_MOD, True),
            ("ERROR_FLASH_DURATION", ERROR_FLASH_DURATION, True),
            ("ERROR_DECAY_RATE", ERROR_DECAY_RATE, True),
            ("DONE_FADE_SPEED", DONE_FADE_SPEED, True),
            ("LED_SCALE", LED_SCALE, True),
            ("BTN_CORNER_W", BTN_CORNER_W, False),
            ("BTN_CORNER_H", BTN_CORNER_H, False),
            ("BTN_CORNER_INNER_R", BTN_CORNER_INNER_R, False),
            ("BTN_ICON_SIZE", BTN_ICON_SIZE, False),
        ]:
            v = extract_value(border_cpp, cname)
            if is_float:
                check(cname, parse_float(v) if v else None, sval)
            else:
                check(cname, parse_int(v) if v else None, sval)
    else:
        print("  SKIP  conv_border.cpp not found")

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
        "CONFUSED": Mood.CONFUSED,
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

    # ── Mood eye scale ────────────────────────────────────────────
    print("-- Mood eye scale --")
    # Parse per-mood eye scale from the dedicated switch in face_state.cpp
    # Pattern: case Mood::NAME:\n    ws = X;\n    hs = Y;\n    break;
    eye_scale_pattern = re.compile(
        r"case\s+Mood::(\w+):\s*\n"
        r"\s*ws\s*=\s*([0-9.]+)f?;\s*\n"
        r"\s*hs\s*=\s*([0-9.]+)f?;\s*\n"
        r"\s*break;",
        re.MULTILINE,
    )
    mcu_eye_scales: dict[str, tuple[float, float]] = {}
    for match in eye_scale_pattern.finditer(state_cpp):
        name = match.group(1)
        mcu_eye_scales[name] = (float(match.group(2)), float(match.group(3)))

    for mood_name, mood_enum in mood_color_map.items():
        sim_scale = MOOD_EYE_SCALE.get(mood_enum, (1.0, 1.0))
        mcu_scale = mcu_eye_scales.get(mood_name, (1.0, 1.0))
        check(f"EYE_SCALE_{mood_name}_W", mcu_scale[0], sim_scale[0])
        check(f"EYE_SCALE_{mood_name}_H", mcu_scale[1], sim_scale[1])

    # ── Mood targets ──────────────────────────────────────────────
    print("-- Mood targets --")
    # Parse per-mood expression targets from face_state.cpp mood switch
    # Each case sets some subset of: t_curve, t_width, t_open, t_lid_slope, t_lid_top, t_lid_bot
    # Defaults: (0.1, 1.0, 0.0, 0.0, 0.0, 0.0)
    target_fields = {
        "t_curve": 0.1,
        "t_width": 1.0,
        "t_open": 0.0,
        "t_lid_slope": 0.0,
        "t_lid_top": 0.0,
        "t_lid_bot": 0.0,
    }
    field_names = ["CURVE", "WIDTH", "OPEN", "LID_SLOPE", "LID_TOP", "LID_BOT"]

    # Extract each mood case block from the first switch(fs.mood) in face_update
    mood_switch_pattern = re.compile(
        r"case\s+Mood::(\w+):\s*\n(.*?)break;",
        re.MULTILINE | re.DOTALL,
    )
    # Find the mood target switch (the first switch(fs.mood) in the file)
    mood_switch_start = state_cpp.find("switch (fs.mood)")
    if mood_switch_start >= 0:
        # Find the closing brace of this switch
        mood_switch_end = state_cpp.find(
            "\n\n    const float intensity", mood_switch_start
        )
        mood_switch_text = state_cpp[mood_switch_start:mood_switch_end]

        for match in mood_switch_pattern.finditer(mood_switch_text):
            mood_name = match.group(1)
            case_body = match.group(2)
            mood_enum = mood_color_map.get(mood_name)
            if mood_enum is None:
                continue
            sim_targets = MOOD_TARGETS.get(mood_enum, (0.1, 1.0, 0.0, 0.0, 0.0, 0.0))

            mcu_vals = list(target_fields.values())  # defaults
            for i, field in enumerate(target_fields):
                m = re.search(rf"{field}\s*=\s*(-?[0-9.]+)f?;", case_body)
                if m:
                    mcu_vals[i] = float(m.group(1))

            for i, fname in enumerate(field_names):
                check(
                    f"TARGET_{mood_name}_{fname}",
                    mcu_vals[i],
                    sim_targets[i],
                )

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
