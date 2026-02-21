---
name: architecture
description: Reference for robot-buddy system architecture. Use when explaining how subsystems work, planning new features, or understanding data flow between components.
argument-hint: "[control|state|vision|planner|audio|face|protocol|safety]"
allowed-tools: Read, Grep, Glob
---

Load architecture reference for `$ARGUMENTS` subsystem. If no argument, provide a high-level overview.

## Key docs

- `docs/architecture.md` — high-level system overview
- `docs/protocols.md` — wire protocol spec
- `docs/power.md` — power topology

## Subsystem guide

### control — 50 Hz runtime loop

**What it does:** Reads telemetry → updates state machine → computes twist → applies safety → sends to MCU.

**Key files:**
- `supervisor/supervisor/runtime.py` — main tick loop (50 Hz, telemetry broadcast at 20 Hz)
- `esp32-reflex/main/control.cpp` — MCU-side 100 Hz FF+PI controller
- `esp32-reflex/main/control.h`

**Data flow per tick:**
1. Read reflex telemetry (wheel speeds, gyro, faults, range)
2. Read face telemetry (mood, button/touch events)
3. Read vision snapshot (non-blocking drain of multiprocessing queue)
4. Ingest into event bus (edge detection)
5. Update state machine
6. Get desired twist (teleop input or skill executor)
7. Apply safety policies (7 layers)
8. Send SET_TWIST to reflex MCU
9. Execute due planner actions
10. Step speech policy
11. Broadcast telemetry at 20 Hz

### state — mode state machine + safety policies

**Key files:**
- `supervisor/supervisor/state/supervisor_sm.py` — BOOT→IDLE→TELEOP/WANDER→ERROR
- `supervisor/supervisor/state/policies.py` — 7-layer defense-in-depth

**State transitions:**
```
BOOT → IDLE              (reflex connected + healthy)
IDLE ↔ TELEOP / WANDER   (user request)
Any → ERROR              (disconnect, ESTOP, TILT, BROWNOUT)
ERROR → IDLE             (clear_error + reflex healthy)
```

**Safety policy layers (applied every tick):**
1. Mode gate — no motion outside TELEOP/WANDER
2. Fault gate — any fault → zero twist
3. Reflex disconnect → zero twist
4. Ultrasonic range scaling (hard stop 250mm, 50% at 500mm)
5. Stale range fallback (50% cap)
6. Vision confidence scaling
7. Stale vision timeout (>500ms → 50% cap)

### vision — camera + detection pipeline

**Key files:**
- `supervisor/supervisor/inputs/camera_vision.py` — parent process, queue interface
- `supervisor/supervisor/inputs/vision_worker.py` — child process, picamera2 + OpenCV
- `supervisor/supervisor/inputs/detectors.py` — ball + floor detection algorithms

**Architecture:** Runs in a **separate OS process** to avoid GIL interference. Communicates via multiprocessing queues (result queue + frame queue + config queue). Main process drains non-blocking each tick.

**Detection pipeline:**
- Floor: HSV mask in bottom third → clear confidence (0.0–1.0)
- Ball: Red HSV wrap-around → confidence + bearing (-27° to +27°)
- Output: `VisionSnapshot(clear_confidence, ball_confidence, ball_bearing_deg, timestamp_mono_ms)`

### planner — LLM action planning

**Key files:**
- `supervisor/supervisor/devices/planner_client.py` — HTTP client, POST /plan
- `supervisor/supervisor/planner/scheduler.py` — cooldowns, action queue, TTL
- `supervisor/supervisor/planner/validator.py` — untrusted output validation
- `supervisor/supervisor/planner/event_bus.py` — edge-detection events from telemetry
- `supervisor/supervisor/planner/skill_executor.py` — skill → DesiredTwist
- `supervisor/supervisor/planner/speech_policy.py` — event-triggered deterministic speech

**Flow:**
1. Every ~1s: build world_state → POST /plan to remote server
2. Validate response (allowed actions, field bounds)
3. Schedule actions with per-type and per-key cooldowns
4. Each tick: pop due actions → execute (emote, gesture, say, skill)
5. Event bus triggers speech policy independently

**Allowed skills:** patrol_drift, investigate_ball, avoid_obstacle, greet_on_button, scan_for_target, approach_until_range, retreat_and_recover

### audio — TTS, conversation, lip sync

**Key files:**
- `supervisor/supervisor/devices/conversation_manager.py` — WebSocket to /converse
- `supervisor/supervisor/devices/audio_orchestrator.py` — arbitrates planner speech vs PTT
- `supervisor/supervisor/devices/audio_bridge.py` — audio I/O abstraction
- `supervisor/supervisor/devices/lip_sync.py` — RMS energy → face talking animation

**Two audio streams:**
1. **Planner speech** — TTS via HTTP POST /tts, queued by audio orchestrator
2. **Conversation** — WebSocket to /converse, full STT→LLM→TTS loop

PTT activation cancels planner speech. Lip sync tracks RMS energy with exponential smoothing (attack=0.55, release=0.25).

### face — display MCU

**Key files:**
- `esp32-face-v2/main/face_state.cpp` — face animation state machine
- `esp32-face-v2/main/face_ui.cpp` — LVGL rendering on ILI9341
- `esp32-face-v2/main/display.cpp` — SPI display init
- `esp32-face-v2/main/touch.cpp` — capacitive touch
- `esp32-face-v2/main/led.cpp` — WS2812B status LED
- `supervisor/supervisor/devices/expressions.py` — emotion/gesture name mapping

**12 moods:** neutral, happy, excited, curious, sad, scared, angry, surprised, sleepy, love, silly, thinking
**13 gestures:** blink, wink_l/r, confused, laugh, surprise, heart, x_eyes, sleepy, rage, nod, headshake, wiggle

### protocol — binary serial communication

Use `/protocol` skill for full reference. Key points:
- COBS framing + CRC16-CCITT
- Little-endian, no JSON to MCUs
- v1 envelope: `[type:u8][seq:u8][payload][crc16:u16-LE]`
- v2 envelope (Face only): adds `seq:u32` + `t_src_us:u64`

### safety — defense-in-depth

**MCU layer (hard limits):**
- Motor fault detection (stall, brownout)
- IMU tilt detection (45°)
- Ultrasonic hard stop (250mm)
- Command timeout watchdog (400ms)

**Supervisor layer (additional caps):**
- Mode gate, fault gate, disconnect gate
- Range scaling (25% at 300mm, 50% at 500mm)
- Vision confidence scaling
- Stale data timeout (500ms → 50% cap)

**Design principle:** MCU reflexes are deterministic and local. Supervisor adds conservative caps. Safety never depends on the network or the planner.
