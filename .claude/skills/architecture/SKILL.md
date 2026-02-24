---
name: architecture
description: Reference for robot-buddy system architecture. Use when explaining how subsystems work, planning new features, or understanding data flow between components.
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
- `supervisor/core/tick_loop.py` — main tick loop (50 Hz, telemetry broadcast at 20 Hz)
- `esp32-reflex/main/control.cpp` — MCU-side 100 Hz FF+PI controller
- `esp32-reflex/main/control.h`

**Data flow per tick:**
1. Read reflex telemetry (wheel speeds, gyro, faults, range)
2. Read face telemetry (mood, button/touch events)
3. Read worker events (vision snapshots, AI results, TTS state)
4. Route events into WorldState via event router
5. Update state machine
6. Get desired twist (teleop input or skill executor)
7. Apply safety policies (7 layers)
8. Send SET_TWIST to reflex MCU
9. Execute due planner actions
10. Step speech policy
11. Broadcast telemetry at 20 Hz

### state — mode state machine + safety policies

**Key files:**
- `supervisor/core/state_machine.py` — BOOT→IDLE→TELEOP/WANDER→ERROR
- `supervisor/core/safety.py` — 7-layer defense-in-depth

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
- `supervisor/workers/vision_worker.py` — vision worker process, picamera2 + OpenCV

**Architecture:** Runs in a **separate OS process** (worker) to avoid GIL interference. Communicates with core via NDJSON over stdin/stdout pipes. Core receives vision snapshots as events via the event router.

**Detection pipeline:**
- Floor: HSV mask in bottom third → clear confidence (0.0–1.0)
- Ball: Red HSV wrap-around → confidence + bearing (-27° to +27°)
- Output: `VisionSnapshot(clear_confidence, ball_confidence, ball_bearing_deg, timestamp_mono_ms)`

### planner — LLM action planning

**Key files:**
- `supervisor/workers/ai_worker.py` — AI worker process, HTTP client to planner server
- `supervisor/core/behavior_engine.py` — priority arbitration, action scheduling
- `supervisor/core/event_bus.py` — edge-detection events from telemetry
- `supervisor/core/skill_executor.py` — skill → DesiredTwist
- `supervisor/core/speech_policy.py` — event-triggered deterministic speech

**Flow:**
1. Every ~1s: build world_state → POST /plan to remote server (via AI worker)
2. Validate response (allowed actions, field bounds)
3. Schedule actions with per-type and per-key cooldowns
4. Each tick: pop due actions → execute (emote, gesture, say, skill)
5. Event bus triggers speech policy independently

**Allowed skills:** patrol_drift, investigate_ball, avoid_obstacle, greet_on_button, scan_for_target, approach_until_range, retreat_and_recover

### audio — TTS, conversation, lip sync

**Key files:**
- `supervisor/workers/tts_worker.py` — TTS playback, lip sync, audio I/O
- `supervisor/workers/ai_worker.py` — conversation management, planner speech

**Two audio streams:**
1. **Planner speech** — TTS via HTTP POST /tts, played by TTS worker
2. **Conversation** — WebSocket to /converse, full STT→LLM→TTS loop

PTT activation cancels planner speech. Lip sync tracks RMS energy with exponential smoothing (attack=0.55, release=0.25).

### face — display MCU

**Key files:**
- `esp32-face/main/face_state.cpp` — face animation state machine
- `esp32-face/main/face_ui.cpp` — LVGL rendering on ILI9341
- `esp32-face/main/display.cpp` — SPI display init
- `esp32-face/main/touch.cpp` — capacitive touch
- `esp32-face/main/led.cpp` — WS2812B status LED
- `supervisor/devices/expressions.py` — emotion/gesture name mapping

**13 moods:** neutral, happy, excited, curious, sad, scared, angry, surprised, sleepy, love, silly, thinking, confused
**13 gestures:** blink, wink_l/r, confused, laugh, surprise, heart, x_eyes, sleepy, rage, nod, headshake, wiggle

### personality — affect engine + guardrails

**What it does:** Maintains a continuous 2D affect vector (valence/arousal), applies deterministic impulse rules, projects to discrete moods, enforces guardrails (duration/intensity caps, context gate, session/daily time limits), and emits personality snapshots consumed by the tick loop for face mood.

**Key files:**
- `supervisor/workers/personality_worker.py` — process-isolated affect engine (L0 rules, timers, guardrails)
- `supervisor/personality/affect.py` — pure math: trait derivation, integrator, impulse application, mood projection, context gate
- `supervisor/config.py` — `PersonalityConfig` (5 axes) + `GuardrailConfig` (toggleable caps + time limits)
- `supervisor/core/event_router.py` — routes personality snapshots to WorldState

**Architecture:** Runs as a **separate OS process** (like Vision, AI, Ear, TTS). Communicates via NDJSON. The tick loop reads personality snapshots from WorldState and uses them to drive face mood/intensity.

**Configuration (PE spec S2 §14.3):**
- 5 trait axes → 20 derived parameters (energy, reactivity, initiative, vulnerability, predictability)
- GuardrailConfig: negative_duration_caps, negative_intensity_caps, context_gate, session_time_limit_s (900s), daily_time_limit_s (2700s)
- Parent override via `personality.cmd.set_guardrail` (runtime adjustable)

**Safety timers:**
- RS-1: Session time limit (default 900s/15min) — winds down conversation with gentle redirect
- RS-2: Daily time limit (default 2700s/45min) — blocks new conversations, persisted to disk (resets daily)

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
