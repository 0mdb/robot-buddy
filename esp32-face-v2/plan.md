# Face V2 Parity + Supervisor Cutover

Updated: 2026-02-19

## Decisions Locked

1. Hard cutover to `esp32-face-v2` for face rendering + touch/button telemetry.
2. Audio is **not** handled by face firmware. Audio I/O is supervisor-owned USB mic/speaker on Pi.
3. Face wire command IDs remain unchanged:
   - `0x20 SET_STATE`
   - `0x21 GESTURE`
   - `0x22 SET_SYSTEM`
   - `0x23 SET_TALKING`
4. Landscape orientation is the baseline for parity and tuning.
5. Face controls are discreet corner icons (no wide bottom bar):
   - PTT icon at bottom-left
   - ACTION icon at bottom-right
   - visual diameter `32 px`, hitbox `40 px`, margin `8 px`

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
- UI controls switched from large text buttons to compact icon controls:
  - PTT uses `LV_SYMBOL_AUDIO`
  - ACTION uses `LV_SYMBOL_CHARGE`
  - button IDs and event semantics unchanged
- System overlays refactored into `system_overlay_v2.*` and aligned to Python v2 behavior:
  - booting radar/grid/progress
  - error warning triangle + glitch-channel effect
  - low battery SDF battery shell/fill pulse
  - updating concentric spinner arcs + pulse core
  - shutdown CRT-style collapse phases
  - post FX: scanlines + vignette
- Added frame-time diagnostics in `face_ui_task` (periodic avg/max/fps logs) and compile-time
  system FX toggles in `config.h`.
- Rendering path hardening:
  - face canvas uses explicit `LV_COLOR_FORMAT_RGB888` with `lv_color_t` backing
  - this fixed the prior garbled-text/byte-stride mismatch seen with native-format assumptions
  - additional face-mode scaling artifact is still open (documented below in parity gaps)

## Test Status

- Server tests: `36 passed`
- Supervisor targeted parity/arbitration tests added and passing:
  - `supervisor/tests/test_expressions.py`
  - `supervisor/tests/test_runtime_personality_face.py`
- Firmware build: `esp32-face-v2` builds successfully with ESP-IDF 5.4.

Note: full supervisor suite currently has unrelated pre-existing failures in
`tests/test_set_config.py` around `reflex.imu_odr_hz` mutability mapping.

## Supervisor Validation (No Serial Logs, 2026-02-19)

Validation method: run supervisor with mock reflex + real face MCU and verify through
`/status`, `/debug/devices`, and `/actions` only.

Observed pass criteria:
- `face_connected=true` and `reflex_connected=true`
- face telemetry flowing (`rx_face_status_packets`, `rx_heartbeat_packets` increasing)
- baseline state stable (`face_system_mode=0`, `face_gesture=255`, `face_talking=false`)
- runtime action path updates face system state:
  - POST `/actions {"action":"e_stop"}` -> `/status.mode=ERROR` and `face_system_mode=2`

Run snapshot highlights:
- `face_seq` advanced to `245`
- `rx_face_status_packets=167`, `rx_heartbeat_packets=9`
- `tx_packets=2` (face command path active from runtime actions)
- transport remained connected throughout run

Note: shutdown stack traces in captured logs are from forced timeout/kill during scripted
test teardown, not runtime transport failure.

## Remaining Hardware Validation

1. Run scripted sweep of all 12 moods, 13 gestures, and 6 system modes from supervisor.
2. Stress test high-rate `SET_TALKING` while injecting gestures; verify no gesture loss.
3. Confirm visual parity on target panel:
   - no duplicate eyes
   - wink/heart/x-eyes shape correctness
   - stable talking modulation
4. Confirm telemetry parity:
   - mood/gesture/system/flags reflect commanded state correctly.

## Python-v2 Parity Gap Analysis (Current)

### Aligned

- Command surface parity: all four face commands retained (`SET_STATE`, `GESTURE`,
  `SET_SYSTEM`, `SET_TALKING`) with strict ID mappings.
- Expression contract parity: 12 moods + 13 gestures + 6 system modes mapped end-to-end.
- Supervisor arbitration parity: `/plan` face emote/gesture suppression during listen/talk.
- System overlay module parity: dedicated `system_overlay_v2.*` implemented with scanlines
  and vignette gates.

### Gaps

1. Face renderer is still not a 1:1 port of Python SDF eye/mouth rasterization.
   - Firmware uses simplified primitive draws for core face shapes.
   - Python uses anti-aliased SDF pipeline for eye fill/pupil/lids/mouth.
2. Pupil containment parity is incomplete.
   - Python clamps pupil displacement to eye bounds.
   - Firmware path does not currently apply equivalent explicit clamp math.
3. Background + afterglow blending differs from Python defaults.
   - Python baseline background is `(10,10,14)`.
   - Firmware face-mode background currently renders from black.
4. Boot-state behavior diverges.
   - Python v2 `face_state_update` boot path is short/simple.
   - Firmware has a multi-phase boot sequence in state update.
5. Critical visual issue remains open on hardware:
   - symptoms from latest run: repeated multi-eye rendering, mouth not visible, and
     face content not filling expected frame area
   - this is now treated as an unresolved display/render parity defect, not closed.

## System Screen Checkpoint Matrix (Python v2 Parity Target)

Use these checkpoints while sweeping `SET_SYSTEM` modes from supervisor.

| Mode | t=0.0s | t=0.5s | t=1.0s | t=2.0s |
| --- | --- | --- | --- | --- |
| `BOOTING` | dark bg + grid + ring appears | radar sweep arc visible | progress bar ~33% | progress bar ~66% |
| `ERROR_DISPLAY` | red pulse starts + warning triangle | channel offset/glitch visible | pulse cycle repeats | stable warning glyph with continued pulse |
| `LOW_BATTERY` | battery shell + level fill | wave/gloss visible in fill | low-level alert pulse (if `<20%`) | repeating fill pulse + alert cadence |
| `UPDATING` | center core + outer ring seeds | rotating arc segments distinct | inner and outer rotations phase-shifted | continuous smooth loop |
| `SHUTTING_DOWN` | full white-ish collapse frame starts | strong vertical collapse | near-line collapse | almost black/off |
