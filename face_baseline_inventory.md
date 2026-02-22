# Face System — Baseline Inventory

Objective snapshot of every file, enum, parameter, color, timing, and event that defines or influences the robot face. No proposals, no recommendations — facts only.

Generated 2026-02-21 from commit `0060554` (branch `main`).

---

## 1. Repo Surface Area Map

Discovery commands used:

```
rg -l "face|mood|gesture|emotion|talking" --type py supervisor_v2/ tools/
rg -l "face|mood|gesture|Mood|Gesture" esp32-face-v2/main/
rg -l "face|mood|gesture" docs/
```

### Python Simulator (`tools/`)

| Path | Why it matters |
|------|---------------|
| `tools/face_state_v2.py` | Enums (Mood, Gesture, SystemMode), FaceState dataclass, animation state machine, expression shape table, color mapping |
| `tools/face_render_v2.py` | SDF pixel renderer, system overlays, afterglow/fire/sparkle effects, mouth/eye rasterization |
| `tools/face_sim_v2.py` | Pygame harness — keyboard-driven mood/gesture triggers, 30 FPS display loop |
| `tools/conv_border.py` | ConvState enum, border/glow renderer, orbit dots, button rendering (sim-only prototype, not yet ported to firmware) |

### ESP32 Face Firmware (`esp32-face-v2/main/`)

| Path | Why it matters |
|------|---------------|
| `main/face_state.h` | C++ enums (Mood, GestureId, SystemMode), FaceState/EyeState/EyelidState/AnimTimers/EffectsState structs, API declarations |
| `main/face_state.cpp` | Animation state machine: mood shape table, gesture overrides, blink/idle/saccade/talking/breathing logic, boot sequence |
| `main/face_ui.cpp` | LVGL canvas rendering, SDF eye/mouth/heart/cross draw, button/touch UI, afterglow/sparkle/fire effects, main task loop, atomic command latch from serial |
| `main/config.h` | All geometry constants, timing constants, FX toggles, brightness default, calibration flags |
| `main/protocol.h` | FaceCmdId/FaceTelId enums (0x20–0x24, 0x90–0x93), packed payload structs, face flag bitfield, button enums |
| `main/protocol.cpp` | COBS encode/decode, CRC16-CCITT, v1/v2 envelope packing, protocol version atomic |
| `main/system_overlay_v2.cpp` | Full-screen overlays for BOOTING/ERROR/LOW_BATTERY/UPDATING/SHUTTING_DOWN, scanline/vignette post-FX |
| `main/telemetry.cpp` | Telemetry TX task: FACE_STATUS at 20 Hz, HEARTBEAT at 1 Hz, touch/button events on change |
| `main/app_main.cpp` | FreeRTOS task creation: face_ui (pri 5, core 0), usb_rx (pri 7, core 1), telemetry (pri 6, core 1) |
| `main/display.cpp` | ILI9341 SPI init, LEDC backlight PWM, LVGL display driver registration |
| `main/touch.cpp` | FT6336 I2C capacitive touch, 10 calibration presets, transform application |
| `main/led.cpp` | WS2812B single-pixel LED via RMT driver |
| `main/pin_map.h` | GPIO assignments: SPI (11,12,13,10,46), backlight (45), I2C (16,15), touch INT/RST (17,18), LED (42) |
| `main/shared_state.h` | Double-buffered touch/button telemetry ring, gesture SPSC queue (cap 16) |

### Supervisor (`supervisor_v2/`)

| Path | Why it matters |
|------|---------------|
| `supervisor_v2/devices/protocol.py` | Python-side FaceMood/FaceGesture/FaceSystemMode/FaceButtonId enums, face flag constants, struct pack formats |
| `supervisor_v2/devices/expressions.py` | CANONICAL_EMOTIONS, CANONICAL_FACE_GESTURES, alias dicts, normalize functions, bidirectional name↔ID maps |
| `supervisor_v2/devices/face_client.py` | FaceClient: send_state/gesture/system_mode/talking/flags, telemetry parsing (FACE_STATUS/TOUCH/BUTTON/HEARTBEAT) |
| `supervisor_v2/core/tick_loop.py` | Per-tick face orchestration: system mode overlay, talking layer, conversation emotion/gesture, planner emote/gesture, greet routine, flag init |
| `supervisor_v2/core/behavior_engine.py` | Planner action scheduling — `emote` and `gesture` action types routed to face |
| `supervisor_v2/core/event_bus.py` | Face touch/button event routing: `face.touch.{press,release,drag}`, `face.button.{press,release,toggle,click}` |
| `supervisor_v2/core/speech_policy.py` | Event-triggered speech gated by `face_listening` and `face_talking` flags |
| `supervisor_v2/core/state_machine.py` | BOOT→IDLE→TELEOP/WANDER→ERROR transitions that drive face system mode overlay |
| `supervisor_v2/workers/tts_worker.py` | LipSyncTracker: RMS energy → 0–255 via asymmetric smoothing (attack 0.55, release 0.25), emitted as TTS_EVENT_ENERGY |
| `supervisor_v2/workers/ai_worker.py` | Emits AI_CONVERSATION_EMOTION, AI_CONVERSATION_GESTURE, AI_CONVERSATION_DONE to tick loop |

### Documentation

| Path | Why it matters |
|------|---------------|
| `docs/protocols.md` | Wire protocol spec: packet format, all command/telemetry tables, mood/gesture/system mode ID registries |
| `docs/TODO.md` | Known face bugs (booting stuck, talking sync), conversation border backlog |

---

## 2. End-to-End Command Contract

### Wire Format

All MCU packets use the same envelope:

**v1:** `[type:u8] [seq:u8] [payload:N] [crc16:u16-LE]` → COBS-encoded → `0x00` delimiter

**v2 (face):** `[type:u8] [seq:u32-LE] [t_src_us:u64-LE] [payload:N] [crc16:u16-LE]` → COBS-encoded → `0x00` delimiter

CRC16: CRC-CCITT, polynomial 0x1021, init 0xFFFF. Protocol version negotiated via `SET_PROTOCOL_VERSION` (0x07) / `PROTOCOL_VERSION_ACK` (0x87).

---

### Commands (Supervisor → Face MCU)

#### SET_STATE (0x20)

| Field | Type | Range | Default | Scale |
|-------|------|-------|---------|-------|
| mood_id | u8 | 0–11 (Mood enum) | 0 (NEUTRAL) | direct |
| intensity | u8 | 0–255 | 255 | float 0.0–1.0 × 255 |
| gaze_x | i8 | -128–127 | 0 | float × 32, clamped |
| gaze_y | i8 | -128–127 | 0 | float × 32, clamped |
| brightness | u8 | 0–255 | 200 | float 0.0–1.0 × 255 |

**Struct pack:** `<BBbbB` (5 bytes)

**Supervisor encoder:** `face_client.py:send_state()` — clamps intensity/brightness to [0,255], gaze to [-128,127].

**MCU decoder:** Latched to atomics `g_cmd_state_mood`, `g_cmd_state_intensity`, `g_cmd_state_gaze_x`, `g_cmd_state_gaze_y`, `g_cmd_state_brightness` in `face_ui.cpp`. Applied every frame in `face_ui_task`.

**MCU application:** `face_set_mood(fs, mood)` + `face_set_expression_intensity(fs, intensity/255.0)` + `face_set_gaze(fs, gaze_x/32.0 * MAX_GAZE, gaze_y/32.0 * MAX_GAZE)` + backlight via LEDC duty.

**Semantics:** Last-value-wins latched channel. Not rate-limited. Supervisor sends on change (planner emote, conversation emotion) or every tick during talking.

---

#### GESTURE (0x21)

| Field | Type | Range | Default | Notes |
|-------|------|-------|---------|-------|
| gesture_id | u8 | 0–12 (GestureId enum) | — | required |
| duration_ms | u16 | 0–65535 | 0 = use default | clamped to [80, 10000] ms on MCU |

**Struct pack:** `<BH` (3 bytes)

**Supervisor encoder:** `face_client.py:send_gesture()` — passes raw gesture_id and duration_ms.

**MCU decoder:** Pushed to `g_gesture_queue` (SPSC FIFO, capacity 16) in `face_ui.cpp`. Popped one-per-frame in `face_ui_task`.

**MCU application:** `face_trigger_gesture(fs, gesture_id, duration_ms)` — sets `active_gesture`, `active_gesture_until`, and gesture-specific `anim.*` flags.

**Semantics:** FIFO one-shot queue. Multiple gestures can be queued. Supervisor hardcodes 500 ms duration for planner/conversation gestures.

---

#### SET_SYSTEM (0x22)

| Field | Type | Range | Default | Notes |
|-------|------|-------|---------|-------|
| mode | u8 | 0–5 (SystemMode enum) | 0 (NONE) | |
| phase | u8 | reserved | 0 | always 0 |
| param | u8 | 0–255 | 0 | mode-specific (e.g. battery level) |

**Struct pack:** `<BBB` (3 bytes)

**Supervisor encoder:** `face_client.py:send_system_mode()` — passes mode and param.

**MCU decoder:** Latched to `g_cmd_system_mode`, `g_cmd_system_param`. Applied every frame.

**MCU application:** `face_set_system_mode(fs, mode, param/255.0)` — sets `system.mode`, `system.param`. When mode != NONE, system overlay renders full-screen over face.

**Semantics:** Last-value-wins. Supervisor sends only on state change (BOOT→IDLE transition, ERROR entry/exit). Tracked via `_last_face_system_mode`.

---

#### SET_TALKING (0x23)

| Field | Type | Range | Default | Notes |
|-------|------|-------|---------|-------|
| talking | u8 | 0 or 1 | 0 | 0=stopped, 1=speaking |
| energy | u8 | 0–255 | 0 | lip sync energy level |

**Struct pack:** `<BB` (2 bytes)

**Supervisor encoder:** `face_client.py:send_talking()` — clamped to [0,255]. Tracks `last_talking_energy_cmd`.

**MCU decoder:** Latched to `g_cmd_talking`, `g_cmd_talking_energy`. Applied every frame.

**MCU application:** Sets `fs.talking` and `fs.talking_energy` (energy/255.0). When talking=true, mouth animation driven by energy-modulated sine wave. MCU applies 450 ms timeout — if no update received, forces `talking=false`.

**Semantics:** Last-value-wins. Sent every tick (50 Hz) while `world.speaking=True`. Energy sourced from TTS worker at ~20 Hz via `TTS_EVENT_ENERGY`.

---

#### SET_FLAGS (0x24)

| Field | Type | Range | Default | Notes |
|-------|------|-------|---------|-------|
| flags | u8 | bitfield, masked to 0x7F | 0x7F (all on) | see flag table below |

**Flag bits:**

| Bit | Name | Effect |
|-----|------|--------|
| 0 | FACE_FLAG_IDLE_WANDER | Enable idle gaze wander |
| 1 | FACE_FLAG_AUTOBLINK | Enable automatic blink cadence |
| 2 | FACE_FLAG_SOLID_EYE | Enable solid eye mode (heart/X shapes replace entire eye) |
| 3 | FACE_FLAG_SHOW_MOUTH | Enable mouth rendering |
| 4 | FACE_FLAG_EDGE_GLOW | Enable eye edge darkening |
| 5 | FACE_FLAG_SPARKLE | Enable random sparkle pixels |
| 6 | FACE_FLAG_AFTERGLOW | Enable frame-to-frame afterglow blending |

**Struct pack:** `<B` (1 byte)

**Supervisor encoder:** `face_client.py:send_flags()` — masks to `FACE_FLAGS_ALL`.

**MCU decoder:** Latched to `g_cmd_flags`. Applied every frame to `anim.idle`, `anim.autoblink`, `solid_eye`, `show_mouth`, `fx.edge_glow`, `fx.sparkle`, `fx.afterglow`.

**Semantics:** Last-value-wins. Sent once on face reconnect (all flags enabled). Not in `docs/protocols.md` — firmware-only addition.

---

### Telemetry (Face MCU → Supervisor)

#### FACE_STATUS (0x90)

| Field | Type | Notes |
|-------|------|-------|
| mood_id | u8 | Current mood |
| active_gesture | u8 | Active gesture ID or 0xFF=none |
| system_mode | u8 | Current system mode |
| flags | u8 | bit 0: touch_active, bit 1: talking, bit 2: ptt_listening |

**Rate:** 20 Hz (every 50 ms). **v2 adds:** `cmd_seq_last_applied:u32`, `t_state_applied_us:u32`.

---

#### TOUCH_EVENT (0x91)

| Field | Type | Notes |
|-------|------|-------|
| event_type | u8 | 0=press, 1=release, 2=drag |
| x | u16 | touch X coordinate |
| y | u16 | touch Y coordinate |

**Rate:** On change. Routed to event bus as `face.touch.{press,release,drag}`.

---

#### BUTTON_EVENT (0x92)

| Field | Type | Notes |
|-------|------|-------|
| button_id | u8 | 0=PTT, 1=ACTION |
| event_type | u8 | 0=PRESS, 1=RELEASE, 2=TOGGLE, 3=CLICK |
| state | u8 | toggle state (0/1 for PTT) |
| reserved | u8 | unused |

**Rate:** On change. Routed to event bus as `face.button.{press,release,toggle,click}`.

---

#### HEARTBEAT (0x93)

68 bytes of USB diagnostics, uptime, TX/RX counters, DTR/RTS state, ptt_listening flag. Rate: 1 Hz.

---

## 3. Face Vocabulary Inventory

### Moods / Emotions

| ID | Enum Name | Python Sim | MCU Firmware | Supervisor API | End-to-End |
|----|-----------|-----------|--------------|----------------|------------|
| 0 | NEUTRAL | `Mood.NEUTRAL` | `Mood::NEUTRAL` | `"neutral"` → 0 | Yes |
| 1 | HAPPY | `Mood.HAPPY` | `Mood::HAPPY` | `"happy"` → 1 | Yes |
| 2 | EXCITED | `Mood.EXCITED` | `Mood::EXCITED` | `"excited"` → 2 | Yes |
| 3 | CURIOUS | `Mood.CURIOUS` | `Mood::CURIOUS` | `"curious"` → 3 | Yes |
| 4 | SAD | `Mood.SAD` | `Mood::SAD` | `"sad"` → 4 | Yes |
| 5 | SCARED | `Mood.SCARED` | `Mood::SCARED` | `"scared"` → 5 | Yes |
| 6 | ANGRY | `Mood.ANGRY` | `Mood::ANGRY` | `"angry"` → 6 | Yes |
| 7 | SURPRISED | `Mood.SURPRISED` | `Mood::SURPRISED` | `"surprised"` → 7 | Yes |
| 8 | SLEEPY | `Mood.SLEEPY` | `Mood::SLEEPY` | `"sleepy"` → 8 | Yes |
| 9 | LOVE | `Mood.LOVE` | `Mood::LOVE` | `"love"` → 9 | Yes |
| 10 | SILLY | `Mood.SILLY` | `Mood::SILLY` | `"silly"` → 10 | Yes |
| 11 | THINKING | `Mood.THINKING` | `Mood::THINKING` | `"thinking"` → 11 | Yes |

**Aliases:** `"tired"` → `"sleepy"` (supervisor only, `expressions.py`)

**Intersection:** All 12 moods supported end-to-end across all three layers.

**Orphans:** None.

---

### Gestures

| ID | Enum Name | Python Sim | MCU Firmware | Supervisor API | End-to-End |
|----|-----------|-----------|--------------|----------------|------------|
| 0 | BLINK | `Gesture.BLINK` | `GestureId::BLINK` | `"blink"` → 0 | Yes |
| 1 | WINK_L | `Gesture.WINK_L` | `GestureId::WINK_L` | `"wink_l"` → 1 | Yes |
| 2 | WINK_R | `Gesture.WINK_R` | `GestureId::WINK_R` | `"wink_r"` → 2 | Yes |
| 3 | CONFUSED | `Gesture.CONFUSED` | `GestureId::CONFUSED` | `"confused"` → 3 | Yes |
| 4 | LAUGH | `Gesture.LAUGH` | `GestureId::LAUGH` | `"laugh"` → 4 | Yes |
| 5 | SURPRISE | `Gesture.SURPRISE` | `GestureId::SURPRISE` | `"surprise"` → 5 | Yes |
| 6 | HEART | `Gesture.HEART` | `GestureId::HEART` | `"heart"` → 6 | Yes |
| 7 | X_EYES | `Gesture.X_EYES` | `GestureId::X_EYES` | `"x_eyes"` → 7 | Yes |
| 8 | SLEEPY | `Gesture.SLEEPY` | `GestureId::SLEEPY` | `"sleepy"` → 8 | Yes |
| 9 | RAGE | `Gesture.RAGE` | `GestureId::RAGE` | `"rage"` → 9 | Yes |
| 10 | NOD | `Gesture.NOD` | `GestureId::NOD` | `"nod"` → 10 | Yes |
| 11 | HEADSHAKE | `Gesture.HEADSHAKE` | `GestureId::HEADSHAKE` | `"headshake"` → 11 | Yes |
| 12 | WIGGLE | `Gesture.WIGGLE` | `GestureId::WIGGLE` | `"wiggle"` → 12 | Yes |

**Aliases:** `"head_shake"` / `"head-shake"` → `"headshake"`, `"xeyes"` / `"x-eyes"` → `"x_eyes"` (supervisor only)

**Intersection:** All 13 gestures supported end-to-end.

**Orphans:** None.

---

### System Modes

| ID | Enum Name | Python Sim | MCU Firmware | Supervisor API | End-to-End |
|----|-----------|-----------|--------------|----------------|------------|
| 0 | NONE | `SystemMode.NONE` | `SystemMode::NONE` | `FaceSystemMode.NONE` | Yes |
| 1 | BOOTING | `SystemMode.BOOTING` | `SystemMode::BOOTING` | `FaceSystemMode.BOOTING` | Yes |
| 2 | ERROR_DISPLAY | `SystemMode.ERROR` | `SystemMode::ERROR_DISPLAY` | `FaceSystemMode.ERROR_DISPLAY` | Yes |
| 3 | LOW_BATTERY | `SystemMode.LOW_BATTERY` | `SystemMode::LOW_BATTERY` | `FaceSystemMode.LOW_BATTERY` | Yes |
| 4 | UPDATING | `SystemMode.UPDATING` | `SystemMode::UPDATING` | `FaceSystemMode.UPDATING` | Yes |
| 5 | SHUTTING_DOWN | `SystemMode.SHUTTING_DOWN` | `SystemMode::SHUTTING_DOWN` | `FaceSystemMode.SHUTTING_DOWN` | Yes |

**Name divergence:** Python sim uses `SystemMode.ERROR` (id=2), MCU uses `SystemMode::ERROR_DISPLAY` (id=2). Same integer value, different symbol name.

**Intersection:** All 6 modes supported end-to-end.

**Orphans:** None.

---

### Conversation States (Sim-Only)

| ID | Name | Defined In | Ported to Firmware? |
|----|------|-----------|-------------------|
| 0 | IDLE | `conv_border.py:ConvState.IDLE` | No |
| 1 | ATTENTION | `conv_border.py:ConvState.ATTENTION` | No |
| 2 | LISTENING | `conv_border.py:ConvState.LISTENING` | No |
| 3 | PTT | `conv_border.py:ConvState.PTT` | No |
| 4 | THINKING | `conv_border.py:ConvState.THINKING` | No |
| 5 | SPEAKING | `conv_border.py:ConvState.SPEAKING` | No |
| 6 | ERROR | `conv_border.py:ConvState.ERROR` | No |
| 7 | DONE | `conv_border.py:ConvState.DONE` | No |

**Status:** Prototype exists only in Python sim. No firmware command (0x25 SET_CONV_STATE) exists yet. Documented in `docs/TODO.md` as pending firmware port.

---

### Face Flags

| Bit | Name | Python Sim | MCU Firmware | Supervisor | End-to-End |
|-----|------|-----------|--------------|------------|------------|
| 0 | IDLE_WANDER | `FaceState.anim.idle` | `anim.idle` | via SET_FLAGS | Yes |
| 1 | AUTOBLINK | `FaceState.anim.autoblink` | `anim.autoblink` | via SET_FLAGS | Yes |
| 2 | SOLID_EYE | `FaceState.solid_eye` | `solid_eye` | via SET_FLAGS | Yes |
| 3 | SHOW_MOUTH | `FaceState.show_mouth` | `show_mouth` | via SET_FLAGS | Yes |
| 4 | EDGE_GLOW | `FaceState.fx.edge_glow` | `fx.edge_glow` | via SET_FLAGS | Yes |
| 5 | SPARKLE | `FaceState.fx.sparkle` | `fx.sparkle` | via SET_FLAGS | Yes |
| 6 | AFTERGLOW | `FaceState.fx.afterglow` | `fx.afterglow` | via SET_FLAGS | Yes |

**Note:** SET_FLAGS (0x24) is not listed in `docs/protocols.md` — exists only in code.

---

### Fault/Alert Face Indications

The supervisor sends `SET_SYSTEM(mode=ERROR_DISPLAY)` when the state machine enters ERROR state. This triggers the error overlay on the MCU (flashing triangle, red pulse). No per-fault differentiation — all faults produce the same error display.

`LOW_BATTERY` is available but supervisor code for battery-level face commands was not found (the mode exists in protocol but no supervisor trigger was identified in tick_loop).

---

## 4. Parameter Inventory

### Eye Geometry

| Parameter | Python Sim | MCU | Default | Range/Clamp | Set By |
|-----------|-----------|-----|---------|-------------|--------|
| SCREEN_W | `face_state_v2.py:59` | `config.h:7` | 320 | fixed | compile-time |
| SCREEN_H | `face_state_v2.py:60` | `config.h:8` | 240 | fixed | compile-time |
| EYE_WIDTH | `face_state_v2.py:62` | `config.h:13` | 80.0 | fixed | compile-time |
| EYE_HEIGHT | `face_state_v2.py:63` | `config.h:14` | 85.0 | fixed | compile-time |
| EYE_CORNER_R | `face_state_v2.py:64` | `config.h:15` | 25.0 | fixed | compile-time |
| PUPIL_R | `face_state_v2.py:65` | `config.h:16` | 20.0 | fixed | compile-time |
| LEFT_EYE_CX | `face_state_v2.py:67` | `config.h:18` | 90.0 | fixed | compile-time |
| LEFT_EYE_CY | `face_state_v2.py:68` | `config.h:19` | 85.0 | fixed | compile-time |
| RIGHT_EYE_CX | `face_state_v2.py:69` | `config.h:20` | 230.0 | fixed | compile-time |
| RIGHT_EYE_CY | `face_state_v2.py:70` | `config.h:21` | 85.0 | fixed | compile-time |
| GAZE_EYE_SHIFT | `face_state_v2.py:73` | `config.h:23` | 3.0 | fixed | compile-time |
| GAZE_PUPIL_SHIFT | `face_state_v2.py:74` | `config.h:24` | 8.0 | fixed | compile-time |
| MAX_GAZE | `face_state_v2.py:75` | `config.h:25` | 12.0 | fixed | compile-time |

### Mouth Geometry

| Parameter | Python Sim | MCU | Default | Range/Clamp | Set By |
|-----------|-----------|-----|---------|-------------|--------|
| MOUTH_CX | `face_state_v2.py:77` | `config.h:28` | 160.0 | fixed | compile-time |
| MOUTH_CY | `face_state_v2.py:78` | `config.h:29` | 185.0 | fixed | compile-time |
| MOUTH_HALF_W | `face_state_v2.py:79` | `config.h:30` | 60.0 | fixed | compile-time |
| MOUTH_THICKNESS | `face_state_v2.py:80` | `config.h:31` | 8.0 | fixed | compile-time |

### Dynamic Face State Parameters

| Parameter | Default | Range | Tween Speed | Set By |
|-----------|---------|-------|-------------|--------|
| eye openness | 1.0 (open) | 0.0–1.0 | 0.6 close / 0.4 open | blink/wink/gesture |
| gaze_x | 0.0 | ±MAX_GAZE (12.0) | spring k=0.25, d=0.65 | supervisor SET_STATE, idle wander, gesture |
| gaze_y | 0.0 | ±MAX_GAZE (12.0) | spring k=0.25, d=0.65 | supervisor SET_STATE, idle wander, gesture |
| width_scale | 1.0 | 0.8–1.3 | 0.2 | mood/gesture (surprised=1.2, scared=0.9, surprise=1.3) |
| height_scale | 1.0 | 1.0–1.25 | 0.2 | mood/gesture (surprised=1.2, surprise=1.25) |
| eyelid top_l/top_r | 0.0 | 0.0–1.0 | 0.6 close / 0.4 open | mood/gesture/blink |
| eyelid bottom_l/bottom_r | 0.0 | 0.0–1.0 | 0.3 | mood (happy=0.4, excited=0.3, love=0.3) |
| eyelid slope | 0.0 | -0.6–0.9 | 0.3 | mood/gesture |
| mouth_curve | 0.2 | -1.0–1.0 | 0.2 | mood/gesture (-1=frown, +1=smile) |
| mouth_open | 0.0 | 0.0–1.0 | 0.4 | mood/gesture/talking |
| mouth_width | 1.0 | 0.4–1.2 | 0.2 | mood/gesture |
| mouth_wave | 0.0 | 0.0–0.7 | 0.1 | rage gesture |
| mouth_offset_x | 0.0 | unbounded (×10 in render) | 0.2 | confused/thinking |
| expression_intensity | 1.0 | 0.0–1.0 | direct set | supervisor SET_STATE intensity field |
| brightness | 1.0 | 0.0–1.0 | direct set | supervisor SET_STATE brightness field, LEDC PWM |
| talking_energy | 0.0 | 0.0–1.0 | direct set | supervisor SET_TALKING energy field |
| talking_phase | 0.0 | wrapping | +15.0×dt (MCU) / +12–18×dt (sim) | internal, incremented while talking |
| solid_eye | true | bool | — | supervisor SET_FLAGS |
| show_mouth | true | bool | — | supervisor SET_FLAGS |

### Breathing

| Parameter | Default | Where Defined | Set By |
|-----------|---------|--------------|--------|
| breath_speed | 1.8 rad/s | `config.h:39`, `face_state_v2.py:158` | compile-time |
| breath_amount | 0.04 (±4%) | `config.h:40`, `face_state_v2.py:159` | compile-time |
| breath_phase | 0.0 | runtime | internal, wraps at 2π |

Breath scale: `1.0 + sin(breath_phase) * breath_amount` → applied to eye width/height.

### Saccade / Jitter

| Parameter | Value | Where Defined |
|-----------|-------|--------------|
| Jitter range (x) | ±0.5 | `face_state_v2.py:477`, `face_state.cpp` |
| Jitter range (y) | ±0.5 | `face_state_v2.py:478`, `face_state.cpp` |
| Saccade interval | 0.1–0.4 s (uniform) | `face_state_v2.py:483`, `face_state.cpp` |

### Idle Gaze Wander

| Parameter | Python Sim | MCU |
|-----------|-----------|-----|
| Idle target X | ±MAX_GAZE (12.0) | ±MAX_GAZE |
| Idle target Y | ±MAX_GAZE × 0.6 (7.2) | ±MAX_GAZE × 0.6 |
| Idle interval | 1.0 + random×2.0 s | IDLE_INTERVAL(1.5) + random×IDLE_VARIATION(2.5) |

**Divergence:** Python sim base interval is 1.0 s, MCU is 1.5 s. Python sim variation is 2.0 s, MCU is 2.5 s.

### Effects

| Parameter | Default | Where Defined | Set By |
|-----------|---------|--------------|--------|
| sparkle_chance | 0.05 (5% per frame) | `face_state.h:166`, `face_state_v2.py:564` | internal |
| sparkle life | 5–15 frames | `face_state.h:141`, `face_state_v2.py:569` | internal |
| MAX_SPARKLE_PIXELS | 48 | `face_state.h:135` | compile-time |
| MAX_FIRE_PIXELS | 64 | `face_state.h:136` | compile-time |
| fire spawn chance | 0.3 (30% per frame per eye) | `face_state.cpp`, `face_state_v2.py:583` | internal (rage only) |
| fire heat decay | ×0.9 per frame | `face_state.cpp`, `face_state_v2.py:579` | internal |
| fire y drift | -3.0 per frame (upward) | `face_state.cpp`, `face_state_v2.py:579` | internal |
| fire x drift | ±1.5 (uniform) | `face_state.cpp`, `face_state_v2.py:579` | internal |
| afterglow decay | 0.4 | `face_render_v2.py:571` (sim), `face_ui.cpp` (MCU) | internal |
| edge_glow_falloff | 0.4 | `face_state.h:171`, `face_state_v2.py` | internal |

---

## 5. Color & Palette Inventory

### Emotion Colors (Mood → RGB)

Defined in `face_state_v2.py:get_emotion_color()` (sim) and `face_state.cpp:face_get_emotion_color()` (MCU). Colors are blended from NEUTRAL base by `expression_intensity`.

| Mood | R | G | B | Hex |
|------|---|---|---|-----|
| NEUTRAL (default) | 50 | 150 | 255 | #3296FF |
| HAPPY | 0 | 255 | 200 | #00FFC8 |
| EXCITED | 100 | 255 | 100 | #64FF64 |
| CURIOUS | 255 | 180 | 50 | #FFB432 |
| SAD | 50 | 80 | 200 | #3250C8 |
| SCARED | 180 | 50 | 255 | #B432FF |
| ANGRY | 255 | 0 | 0 | #FF0000 |
| SURPRISED | 255 | 255 | 200 | #FFFFC8 |
| SLEEPY | 40 | 60 | 100 | #283C64 |
| LOVE | 255 | 100 | 150 | #FF6496 |
| SILLY | 200 | 255 | 50 | #C8FF32 |

**Divergence:** THINKING has no explicit color case in either layer — falls through to NEUTRAL (50, 150, 255). MCU code has an explicit `THINKING` mapping to (80, 135, 220) / `#5087DC`. Python sim does not.

### Gesture Override Colors

Active gesture overrides emotion color:

| Gesture | R | G | B | Hex | Condition |
|---------|---|---|---|-----|-----------|
| RAGE | 255 | 30 | 0 | #FF1E00 | `anim.rage == true` |
| HEART | 255 | 105 | 180 | #FF69B4 | `anim.heart == true` |
| X_EYES | 200 | 40 | 40 | #C82828 | `anim.x_eyes == true` |

Matched between Python sim and MCU.

### Background Color

| Layer | R | G | B | Hex | Where |
|-------|---|---|---|-----|-------|
| Python sim (face) | 10 | 10 | 14 | #0A0A0E | `face_render_v2.py:38` |
| MCU (face) | 0 | 0 | 0 | #000000 | `face_ui.cpp:25-27` |
| MCU (system overlay) | 10 | 10 | 14 | #0A0A0E | `system_overlay_v2.cpp` |

**Divergence:** Normal face rendering on MCU uses pure black background. System overlay uses dark blue-gray matching the sim.

### Pupil Color

| Layer | R | G | B | Where |
|-------|---|---|---|-------|
| Python sim | 10 | 15 | 30 | `face_render_v2.py:376` |
| MCU | UNKNOWN — not located in audit | | | |

### Conversation State Colors (Sim Only)

Defined in `conv_border.py:CONV_COLORS`. Not ported to firmware.

| State | R | G | B | Hex |
|-------|---|---|---|-----|
| IDLE | 0 | 0 | 0 | #000000 |
| ATTENTION | 180 | 240 | 255 | #B4F0FF |
| LISTENING | 0 | 200 | 220 | #00C8DC |
| PTT | 255 | 200 | 80 | #FFC850 |
| THINKING | 120 | 100 | 255 | #7864FF |
| SPEAKING | 200 | 240 | 255 | #C8F0FF |
| ERROR | 255 | 160 | 60 | #FFA03C |
| DONE | 0 | 0 | 0 | #000000 |

### Button Colors (Sim Only)

| Element | R | G | B | Where |
|---------|---|---|---|-------|
| Button idle BG | 40 | 44 | 52 | `conv_border.py:80` |
| Button idle border | 80 | 90 | 100 | `conv_border.py:81` |
| Button icon | 200 | 210 | 220 | `conv_border.py:82` |
| Cancel active | 255 | 120 | 80 | `conv_border.py:83` |

### Button Colors (MCU)

| Element | Hex | Where |
|---------|-----|-------|
| PTT idle BG | 0x2A6A4A | `face_ui.cpp` |
| PTT listening BG | 0x2F80ED | `face_ui.cpp` |
| PTT border | 0x54C896 | `face_ui.cpp` |
| PTT text | 0xF4FFFF | `face_ui.cpp` |
| ACTION border | 0xFFBE8B | `face_ui.cpp` |
| ACTION BG | 0xB66A3A | `face_ui.cpp` |
| ACTION text | 0xFFF7EA | `face_ui.cpp` |

### LED Status Colors (MCU)

| State | R | G | B | Where |
|-------|---|---|---|-------|
| Talking | 180 | 80 | 0 | `face_ui.cpp:900` |
| Listening (PTT) | 0 | 90 | 180 | `face_ui.cpp:902` |
| Idle/connected | 0 | 40 | 0 | `face_ui.cpp:904` |

### System Overlay Colors

Defined in `system_overlay_v2.cpp` (MCU) and `face_render_v2.py` (sim). Key values:

**BOOTING:**
- Radar ring: (0, 200, 255)
- Grid: (0, 50, 100) at 0.2 alpha
- Progress bar border: (0, 150, 255), fill: (0, 200, 255)

**ERROR:**
- Pulsing background red: 0–40
- Triangle with RGB shift glitch

**LOW_BATTERY:**
- Battery >50%: (0, 220, 100)
- Battery 20–50%: (220, 180, 0)
- Battery <20%: (220, 40, 40)
- Wave: `sin(x*0.1 + elapsed*5.0) * 3.0`

**UPDATING:**
- Outer ring: (0, 255, 100)
- Inner ring: (0, 200, 255)
- Center dot: (255, 255, 255)

**SHUTTING_DOWN:**
- Fades to black over 0.8 s (no distinctive color)

**Fire Particle Colors (rage gesture):**

| Heat Range | R | G | B |
|------------|---|---|---|
| > 0.85 | 255 | 220 | 120 |
| > 0.65 | 255 | 140 | 20 |
| > 0.40 | 220 | 50 | 0 |
| ≤ 0.40 | 130 | 20 | 0 |

### Post-Processing FX Colors

- **Scanlines:** Every other row darkened to 80% (×0.8 sim, ×4/5 MCU)
- **Vignette:** Radial falloff from center, 50%→100% max distance
- **Sparkle pixels:** White (255, 255, 255) with life-based alpha

All above are internal-only. Not externally controlled.

---

## 6. Timing Model

### Render Loop

| Parameter | Python Sim | MCU |
|-----------|-----------|-----|
| Frame rate | 30 FPS (`face_sim_v2.py:76`) | 30 FPS (`config.h:34`) |
| Frame period | 33 ms (pygame clock) | 33 ms (`vTaskDelay(pdMS_TO_TICKS(33))`) |
| Animation dt | fixed 0.033 s | measured `esp_timer_get_time()` delta |
| Frame stats logging | N/A | every 5000 ms (`FRAME_TIME_LOG_INTERVAL_MS`) |

### FreeRTOS Tasks (MCU)

| Task | Priority | Stack | Core | Period |
|------|----------|-------|------|--------|
| face_ui | 5 | 8192 | 0 | 33 ms (30 FPS) |
| usb_rx | 7 | 4096 | 1 | continuous (blocking read) |
| telemetry | 6 | 4096 | 1 | 10 ms loop (`TELEMETRY_LOOP_MS`) |

### Telemetry Rates (MCU → Supervisor)

| Type | Rate | Source |
|------|------|--------|
| FACE_STATUS | 20 Hz (50 ms) | `TELEMETRY_HZ = 20` in `config.h:62` |
| HEARTBEAT | 1 Hz (1000 ms) | `HEARTBEAT_PERIOD_US = 1000000` in `telemetry.cpp:13` |
| TOUCH_EVENT | on change | event-driven |
| BUTTON_EVENT | on change | event-driven |

### Supervisor Tick Rate

| Parameter | Value |
|-----------|-------|
| Tick rate | 50 Hz (20 ms) |
| Face command emission | every tick while state changes |
| SET_TALKING rate | every tick while speaking (~50 Hz) |
| Telemetry broadcast | 20 Hz (every 2.5 ticks) |

### Blink Cadence

| Parameter | Python Sim | MCU |
|-----------|-----------|-----|
| Base interval | 3.0 s (`BLINK_INTERVAL`) | 2.0 s (`BLINK_INTERVAL`) |
| Random variation | +0–4.0 s (`BLINK_VARIATION`) | +0–3.0 s (`BLINK_VARIATION`) |
| Total range | 3.0–7.0 s between blinks | 2.0–5.0 s between blinks |
| Close speed | 0.6 (tween rate) | 0.6 |
| Open speed | 0.4 (tween rate) | 0.4 |

**Divergence:** Python sim blinks every 3–7 s, MCU blinks every 2–5 s.

### Idle Gaze Cadence

| Parameter | Python Sim | MCU |
|-----------|-----------|-----|
| Base interval | 1.0 s | 1.5 s (`IDLE_INTERVAL`) |
| Random variation | +0–2.0 s | +0–2.5 s (`IDLE_VARIATION`) |
| Total range | 1.0–3.0 s | 1.5–4.0 s |

### Easing / Interpolation

All face parameters use **exponential tween** (lerp toward target per frame):
```
value += (target - value) * speed
```
where `speed` is the tween rate (0.0–1.0 per frame at 30 FPS).

**Gaze** uses **spring physics**:
```
force = (target - current) * k
velocity = (velocity + force) * d
current += velocity
```
with k=0.25, d=0.65.

**Boot sequence** uses **cubic ease-out**: `1.0 - (1.0 - t)^3`.

**System overlay vignette** uses **smoothstep**: `x² × (3 - 2x)`.

### Gesture Durations

| Gesture | Default Duration (Python Sim) | Default Duration (MCU) |
|---------|------------------------------|----------------------|
| BLINK | ~0.18 s (automatic) | 0.18 s |
| WINK_L/R | ~0.20 s | 0.20 s |
| CONFUSED | 0.5 s | 0.5 s |
| LAUGH | 0.5 s | 0.5 s |
| SURPRISE | 1.0 s (sim) | 0.8 s (MCU) |
| HEART | 2.0 s | 2.0 s |
| X_EYES | 2.5 s (sim) | 1.5 s (MCU) |
| SLEEPY | 3.0 s | 3.0 s |
| RAGE | 3.0 s | 3.0 s |
| NOD | 0.35 s (MCU fallback) | 0.35 s |
| HEADSHAKE | 0.35 s (MCU fallback) | 0.35 s |
| WIGGLE | 0.60 s (MCU fallback) | 0.60 s |

**Divergences:** SURPRISE: 1.0 s (sim) vs 0.8 s (MCU). X_EYES: 2.5 s (sim) vs 1.5 s (MCU).

### Talking Animation

| Parameter | Python Sim | MCU |
|-----------|-----------|-----|
| Phase speed | `12.0 + 6.0 * energy` | `15.0` (fixed) |
| Mouth base open | `0.2 + 0.5 * energy` | `0.2 + 0.5 * energy` |
| Mouth modulation | `abs(noise) * 0.6 * energy` | `abs(noise) * 0.6 * energy` |
| Width modulation | `cos(phase*0.7) * 0.3 * energy` | `cos(phase*0.7) * 0.3 * energy` |
| Eye bounce | `abs(sin(phase)) * 0.05 * energy` | `abs(sin(phase)) * 0.05 * energy` |

**Divergence:** Python sim talking phase speed is energy-dependent (12–18 rad/s). MCU uses fixed 15 rad/s.

### Command Timeouts

| Timeout | Value | Where |
|---------|-------|-------|
| MCU talking timeout | 450 ms | `face_ui.cpp:24` — forces `talking=false` if no SET_TALKING received |
| Supervisor greet debounce | 5000 ms | `tick_loop.py` — minimum interval between ACTION button greet triggers |

---

## 7. Runtime Event Triggers

### Supervisor → Face Command Mapping

#### State Machine Transitions

| Trigger | Source | Face Command | Details |
|---------|--------|-------------|---------|
| Enter BOOT mode | `state_machine.py` | `SET_SYSTEM(BOOTING, 0)` | Sent on every tick while mode=BOOT |
| Exit BOOT → IDLE | `state_machine.py` | `SET_SYSTEM(NONE, 0)` | Clears system overlay |
| Enter ERROR | `state_machine.py` | `SET_SYSTEM(ERROR_DISPLAY, 0)` | Sent on every tick while mode=ERROR |
| Exit ERROR → IDLE | `state_machine.py` | `SET_SYSTEM(NONE, 0)` | Clears system overlay |
| Face MCU connects | `tick_loop.py` | `SET_FLAGS(0x7F)` | Sent once on (re)connect |

#### Planner Actions

| Trigger | Source | Face Command | Details |
|---------|--------|-------------|---------|
| Planner `emote` action | `behavior_engine.py` → `tick_loop._apply_emote()` | `SET_STATE(mood_id, intensity)` | intensity from action dict, default 0.7 |
| Planner `gesture` action | `behavior_engine.py` → `tick_loop._apply_gesture()` | `GESTURE(gesture_id, 500)` | hardcoded 500 ms duration |

#### Conversation Layer

| Trigger | Source | Face Command | Details |
|---------|--------|-------------|---------|
| AI conversation emotion | `ai_worker.py` → `AI_CONVERSATION_EMOTION` | `SET_STATE(mood_id, intensity)` | buffered, sent next tick |
| AI conversation gesture | `ai_worker.py` → `AI_CONVERSATION_GESTURE` | `GESTURE(gesture_id, 500)` | buffered, all sent next tick, then cleared |
| AI conversation done | `ai_worker.py` → `AI_CONVERSATION_DONE` | (clears buffers) | no face command; reverts to planner/idle |

#### TTS / Speaking

| Trigger | Source | Face Command | Details |
|---------|--------|-------------|---------|
| TTS playback starts | `tts_worker.py` → `world.speaking=True` | `SET_TALKING(1, energy)` | Sent every tick at 50 Hz |
| TTS energy update | `tts_worker.py` → `TTS_EVENT_ENERGY` | `SET_TALKING(1, energy)` | energy 0–255, ~20 Hz from worker |
| TTS playback ends | `tts_worker.py` → `world.speaking=False` | `SET_TALKING(0, 0)` | Sent once |

#### Button / Touch Events

| Trigger | Source | Face Command | Details |
|---------|--------|-------------|---------|
| PTT button TOGGLE (state=1) | MCU → `BUTTON_EVENT` | (no face cmd) | Starts conversation session |
| PTT button TOGGLE (state=0) | MCU → `BUTTON_EVENT` | (no face cmd) | Ends conversation session |
| ACTION button CLICK | MCU → `BUTTON_EVENT` | `SET_STATE(EXCITED, 0.8)` + `GESTURE(NOD, 500)` | Greet routine, 5 s debounce |
| Touch press/release/drag | MCU → `TOUCH_EVENT` | (no face cmd) | Routed to event bus only |

#### Dashboard Commands

| Trigger | Source | Face Command | Details |
|---------|--------|-------------|---------|
| Dashboard set state | HTTP API | `SET_STATE(...)` | Direct pass-through |
| Dashboard gesture | HTTP API | `GESTURE(...)` | Direct pass-through |
| Dashboard set system | HTTP API | `SET_SYSTEM(...)` | Direct pass-through |
| Dashboard set talking | HTTP API | `SET_TALKING(...)` | Direct pass-through |
| Dashboard set flags | HTTP API | `SET_FLAGS(...)` | Direct pass-through |
| Dashboard manual lock | HTTP API | (gates planner) | Sets `face_manual_lock=True`; planner/conversation layer skipped |

### Command Priority (Composition Layers)

From `docs/protocols.md` §8.2 and `tick_loop.py` implementation:

```
System layer (boot, error, shutdown) → full-screen overlay, highest priority
  ↓
Talking layer (TTS energy) → mouth animation during speech
  ↓
Conversation layer (AI emotion/gesture) → during active conversation session
  ↓
Planner layer (emote/gesture actions) → scheduled by behavior engine
  ↓
Idle layer (neutral mood, auto-blink, idle wander) → baseline
```

`face_manual_lock` gates conversation + planner layers. System and talking layers always pass through.

---

## 8. Known Issues Captured in Code

### From `docs/TODO.md`

| Issue | Exact Text | Status |
|-------|-----------|--------|
| Booting stuck | "Face stuck displaying 'booting' system mode — can't override expression from dashboard panel even though telemetry shows face MCU is connected." | Open (line 14) |
| Talking sync | "Face stops talking before speech stops playing, needs better sync." | Open (line 12) |
| Conversation border | "Visual feedback for conversation flow — border animations, LED sync, button redesign. Prototyped in Python face sim (`tools/conv_border.py`), not yet ported to firmware." | In Progress — sim done, firmware port pending (line 20) |
| SET_CONV_STATE | "Firmware port — protocol command 0x25 SET_CONV_STATE, ESP32 border/button/LED rendering" | Pending (line 32) |
| Supervisor wiring | "conv state transitions in tick_loop (wake_word→ATTENTION→LISTENING→THINKING→SPEAKING→DONE)" | Pending (line 33) |

### Divergences Found Between Layers

| Item | Python Sim | MCU Firmware | Impact |
|------|-----------|--------------|--------|
| Blink interval | 3.0 + 0–4.0 s | 2.0 + 0–3.0 s | MCU blinks more frequently |
| Idle gaze interval | 1.0 + 0–2.0 s | 1.5 + 0–2.5 s | MCU changes gaze less frequently |
| SURPRISE duration | 1.0 s | 0.8 s | MCU surprise ends sooner |
| X_EYES duration | 2.5 s | 1.5 s | MCU x_eyes ends 1 s sooner |
| Talking phase speed | 12.0 + 6.0×energy (variable) | 15.0 (fixed) | MCU doesn't modulate talking speed by energy |
| THINKING color | falls through to NEUTRAL (50,150,255) | explicit (80,135,220) | MCU has distinct thinking color, sim doesn't |
| Background color (face) | (10,10,14) | (0,0,0) | Sim has slight blue tint, MCU is pure black |
| Neutral mouth curve default | 0.2 (sim) | 0.1 (MCU) | Slight smile difference at neutral |
| SystemMode.ERROR name | `SystemMode.ERROR` | `SystemMode::ERROR_DISPLAY` | Different symbol, same integer (2) |
| SET_FLAGS protocol doc | not in `docs/protocols.md` | implemented in firmware | Undocumented command |
| LOW_BATTERY trigger | mode exists in protocol | no supervisor code sends it | Dead code path (no trigger found) |

### From Source Code (TODOs/FIXMEs)

No TODO, FIXME, HACK, BUG, or XXX comments found in any face-related file across all three layers.
