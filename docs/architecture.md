# Architecture

## System Topology

```
┌──────────────────────────────────────────────────────────┐
│ On Robot                                                 │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Raspberry Pi 5 — Supervisor                        │  │
│  │                                                    │  │
│  │  50 Hz tick loop:                                  │  │
│  │    read telemetry → state machine → safety         │  │
│  │    → mood sequencer → conv state → send commands   │  │
│  │    → broadcast telemetry to dashboard              │  │
│  │                                                    │  │
│  │  Workers (separate OS processes):                  │  │
│  │    TTS, Vision, AI/Planner, Ear (wake word + VAD)  │  │
│  │                                                    │  │
│  │  HTTP API (:8080)  WebSocket (:8080/ws)            │  │
│  └──────┬──────────────────────┬──────────────────────┘  │
│         │ USB serial (COBS)    │ USB serial (COBS)       │
│  ┌──────▼──────┐        ┌─────▼───────┐                 │
│  │ Reflex MCU  │        │  Face MCU   │                 │
│  │ ESP32-S3    │        │  ESP32-S3   │                 │
│  │             │        │             │                 │
│  │ Motors, PID │        │ 320×240 TFT │                 │
│  │ Encoders    │        │ Face render │                 │
│  │ IMU (BMI270)│        │ Touch/Btns  │                 │
│  │ Ultrasonic  │        │ Border/LED  │                 │
│  │ Safety      │        │             │                 │
│  └─────────────┘        └─────────────┘                 │
└──────────────────────────────────────────────────────────┘
         │
         │ HTTP (LAN, optional)
         │
┌────────▼────────────────────────────────┐
│ AI Server (3090 Ti PC, off-robot)       │
│                                         │
│ FastAPI planner server (:8100)          │
│ LLM: Qwen3-8B-AWQ via vLLM             │
│ TTS: Orpheus (vLLM) + espeak fallback   │
│ STT: faster-whisper (CPU)               │
│ POST /plan  WS /converse  POST /tts     │
└─────────────────────────────────────────┘
```

## Locked Decisions

- 2× ESP32-S3: Face MCU (display + touch) and Reflex MCU (motors + sensors + safety)
- Raspberry Pi 5 runs Python supervisor at 50 Hz
- AI planner services run off-robot on 3090 Ti server via LAN
- Battery: 2S LiPo with separate dirty motor rail and clean regulated 5V rail
- Reflexes are local and deterministic; planner is remote and optional

## Supervisor Architecture

### Tick Loop (50 Hz)

The tick loop is the central orchestrator. Each tick:

1. **Read**: Poll telemetry from both MCUs (non-blocking)
2. **State machine**: Evaluate transitions (BOOT → IDLE → TELEOP/WANDER → ERROR)
3. **Safety policies**: Apply 7-layer defense-in-depth (mode gate, fault gate, disconnect guard, range scaling, stale range fallback, vision confidence, stale vision timeout)
4. **Conversation state**: Advance ConvStateTracker (8 states: IDLE → ATTENTION → LISTENING → PTT → THINKING → SPEAKING → ERROR → DONE)
5. **Mood sequencer**: Execute 4-phase choreography (anticipation blink → ramp-down → switch → ramp-up, ~470ms)
6. **Guardrails**: Enforce negative affect limits (context gate, intensity caps, duration caps)
7. **Transition choreographer**: Gaze ramps, anticipation blinks, re-engagement nods on conversation phase changes
8. **Send commands**: Emit SET_STATE, GESTURE, SET_TALKING, SET_CONV_STATE, SET_FLAGS to Face MCU; SET_TWIST to Reflex MCU
9. **Broadcast**: Stream telemetry to dashboard via WebSocket (20 Hz)

### Worker Process Model

Workers run as separate OS processes communicating via NDJSON over pipes:

| Worker | Process | Rate | Role |
|--------|---------|------|------|
| TTS | Separate | Event-driven | Audio playback, lip sync energy (RMS → 0-255) |
| Vision | Separate | 10-20 Hz | Camera capture, object detection, ball tracking |
| AI | Separate | Event-driven | Planner client (POST /plan), conversation (WS /converse) |
| Ear | Separate | Continuous | Wake word detection (openWakeWord), VAD (Silero) |

Worker crashes don't bring down the tick loop. Workers communicate via typed events on the event bus.

### State Machine

```
BOOT → IDLE → TELEOP / WANDER → ERROR
  │      │                          │
  │      └──── set_mode ────────────│
  │                                 │
  └──── auto (reflex connects) ─────┘ ← clear_error (when healthy)
```

- **BOOT → IDLE**: Automatic when Reflex MCU connects with no faults
- **IDLE → TELEOP/WANDER**: Via `set_mode` command
- **Any → ERROR**: On disconnect, ESTOP, TILT, or BROWNOUT
- **ERROR → IDLE**: Via `clear_error()` when Reflex is healthy

## Communication Protocol

Binary packets over USB serial with COBS framing:

**v1 envelope**: `[type:u8][seq:u8][payload:N][crc16:u16-LE]`

**v2 envelope** (negotiated): `[type:u8][seq:u32-LE][t_src_us:u64-LE][payload:N][crc16:u16-LE]`

CRC16-CCITT (polynomial 0x1021, init 0xFFFF). Protocol version negotiated via SET_PROTOCOL_VERSION (0x07) / PROTOCOL_VERSION_ACK (0x87).

Auto-reconnect with exponential backoff (0.5s–5s). See `docs/protocols.md` for full packet definitions.

### Face MCU Commands

| ID | Command | Pattern | Purpose |
|----|---------|---------|---------|
| 0x20 | SET_STATE | Last-value-wins | Mood, intensity, gaze, brightness |
| 0x21 | GESTURE | FIFO queue (cap 16) | One-shot animations |
| 0x22 | SET_SYSTEM | Last-value-wins | System overlays (boot, error, battery) |
| 0x23 | SET_TALKING | Last-value-wins | Lip sync (talking flag + energy) |
| 0x24 | SET_FLAGS | Last-value-wins | Feature toggles (blink, wander, sparkle) |
| 0x25 | SET_CONV_STATE | Last-value-wins | Conversation border state |

### Face MCU Telemetry

| ID | Telemetry | Rate |
|----|-----------|------|
| 0x90 | FACE_STATUS | 20 Hz |
| 0x91 | TOUCH_EVENT | On change |
| 0x92 | BUTTON_EVENT | On change |
| 0x93 | HEARTBEAT | 1 Hz |

## Safety Architecture (Defense in Depth)

Safety enforcement at two levels:

**MCU-level (Reflex)**: Acceleration limits, command TTL (400ms timeout), hard stop on ESTOP/TILT/STALL, watchdog.

**Supervisor-level**: 7 policies applied every tick:
1. Mode gate — no motion outside TELEOP/WANDER
2. Fault gate — any fault → zero twist
3. Reflex disconnect → zero twist
4. Ultrasonic range scaling (hard stop at 250mm, 50% at 500mm)
5. Stale range fallback (50% cap)
6. Vision confidence scaling
7. Stale vision timeout (500ms)

## Face Rendering Pipeline

**Face MCU** (ESP32-S3 + ILI9341 320×240 SPI):
- 30 FPS render loop on core 0
- SDF-based eye/mouth rasterization with spring gaze, idle wander, micro-saccades, breathing
- 13 moods with per-mood eye scale, color, expression targets
- 13 gestures (one-shot FIFO queue)
- Conversation border renderer (SDF frame + glow, 8 state animations)
- Corner button zones (pixel-rendered MIC + X_MARK icons, touch hit-testing)
- System overlays (boot, error, low battery, updating, shutdown)
- Effects: sparkle, fire particles (rage), afterglow blending

**Design authoring surface**: Face Sim V3 (`tools/face_sim_v3/`, ~2600 lines) is the canonical design tool. CI parity check enforces constant alignment between sim and firmware (196/196 checks).

## Personality Engine (Planned)

Spec: `specs/personality-engine-spec-stage2.md`

- **PersonalityWorker**: Dedicated BaseWorker on Pi 5 (1 Hz tick + event-triggered)
- **Continuous affect vector**: (valence, arousal) with decaying integrator
- **13 mood anchors** in VA space with asymmetric hysteresis projection
- **Layer 0**: Deterministic rules (no server required)
- **Layer 1**: LLM-enhanced via Qwen3-8B-AWQ on server
- **Single source of emotional truth**: Personality worker is final authority on face + TTS prosody
- **Memory**: Local-only JSON, 5 decay tiers, COPPA compliant

## Deterministic Telemetry

All MCU packets carry monotonic timestamps (`t_src_us`) and sequence numbers. Pi receives with `t_pi_rx_ns`. Clock sync via TIME_SYNC_REQ/RESP (min-RTT offset, drift tracking). Raw binary logging for deterministic replay.

## Open Questions

- Final battery pack choice (2S LiPo vs welded 2S 18650 pack with BMS)
- Motor voltage strategy (raw 2S capped PWM vs regulated motor rail)
