# Face V2 Parity + Supervisor Cutover

Updated: 2026-02-18

## Decisions Locked

1. Hard cutover to `esp32-face-v2` for face rendering + touch/button telemetry.
2. Audio is **not** handled by face firmware. Audio I/O is supervisor-owned USB mic/speaker on Pi.
3. Face wire command IDs remain unchanged:
   - `0x20 SET_STATE`
   - `0x21 GESTURE`
   - `0x22 SET_SYSTEM`
   - `0x23 SET_TALKING`
4. Landscape orientation is the baseline for parity and tuning.

## Canonical Expression Contract

### Moods (12)
`neutral, happy, excited, curious, sad, scared, angry, surprised, sleepy, love, silly, thinking`

### Gestures (13)
`blink, wink_l, wink_r, confused, laugh, surprise, heart, x_eyes, sleepy, rage, nod, headshake, wiggle`

### System Modes (6)
`none, booting, error_display, low_battery, updating, shutting_down`

## Implemented

### Server (`server/app/llm`)

- Added canonical vocabulary module: `expressions.py`
- Strict allowlist validation + alias normalization in `schemas.py`
  - emotion aliases: `tired -> sleepy`
  - gesture aliases: `head-shake -> headshake`, `x-eyes -> x_eyes`
- Conversation pipeline now uses canonical emotion/gesture lists and strict gesture filtering.
- Prompts now source emotion/gesture vocab from one canonical location.

### Supervisor (`supervisor/supervisor`)

- Added canonical face mapping module: `devices/expressions.py`
- Runtime now uses canonical normalization/mapping tables (no duplicated maps).
- Added conversation-priority arbitration:
  - suppresses `/plan` face `emote` and `gesture` actions while face is listening or talking.
- Added protocol ID guard sets:
  - `VALID_FACE_MOOD_IDS`
  - `VALID_FACE_GESTURE_IDS`

### Face Firmware (`esp32-face-v2/main`)

- Replaced single command buffer with reliable channels:
  - latched atomics for `SET_STATE`, `SET_SYSTEM`, `SET_TALKING`
  - FIFO gesture queue for one-shot `GESTURE`
- `face_ui_task` now consumes the new channels and queue directly.
- Talking timeout protection retained.
- Mood intensity is applied (`SET_STATE.intensity` no longer ignored).
- Ported Python-v2 behavior into C++ state/render path:
  - spring gaze, idle wander, micro-saccades, breathing
  - eyelid top/bottom/slope model
  - mouth curve/open/wave/offset/width model
  - heart eyes, x-eyes, wink/blink/gesture timers
  - sparkle, rage fire particles, afterglow, system overlays
- Telemetry now reports distinct active gestures via `fs.active_gesture`
  (including `nod`, `headshake`, `wiggle`).

## Test Status

- Server tests: `36 passed`
- Supervisor targeted parity/arbitration tests added and passing:
  - `supervisor/tests/test_expressions.py`
  - `supervisor/tests/test_runtime_personality_face.py`
- Firmware build: `esp32-face-v2` builds successfully with ESP-IDF 5.4.

Note: full supervisor suite currently has unrelated pre-existing failures in
`tests/test_set_config.py` around `reflex.imu_odr_hz` mutability mapping.

## Remaining Hardware Validation

1. Run scripted sweep of all 12 moods, 13 gestures, and 6 system modes from supervisor.
2. Stress test high-rate `SET_TALKING` while injecting gestures; verify no gesture loss.
3. Confirm visual parity on target panel:
   - no duplicate eyes
   - wink/heart/x-eyes shape correctness
   - stable talking modulation
4. Confirm telemetry parity:
   - mood/gesture/system/flags reflect commanded state correctly.
