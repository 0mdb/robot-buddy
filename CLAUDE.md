# CLAUDE.md — Robot Buddy

## Project Overview

Robot Buddy is a kid-safe, expressive robot platform combining real-time motor control, an animated LED face, and optional networked AI planner. The architecture separates deterministic reflexes (ESP32 MCUs) from high-level orchestration (Raspberry Pi 5 supervisor).

## Repository Structure

```
robot-buddy/
├── supervisor/          # Python supervisor (Raspberry Pi 5)
│   ├── supervisor/      # Main package
│   │   ├── io/          # Serial transport, COBS framing
│   │   ├── devices/     # MCU clients, audio orchestration, conversation, expressions
│   │   ├── state/       # State machine, datatypes, safety policies
│   │   ├── api/         # FastAPI HTTP/WebSocket server, param registry, dashboard
│   │   ├── inputs/      # Vision (camera, multiprocessing worker)
│   │   ├── logging/     # Telemetry recording (JSONL)
│   │   ├── mock/        # Mock Reflex MCU for testing (PTY-based)
│   │   ├── planner/     # Planner integration (scheduler, event bus, skills, speech)
│   │   ├── services/    # Audio service
│   │   ├── config.py    # YAML config with dataclass schemas
│   │   ├── runtime.py   # 50 Hz control loop
│   │   └── main.py      # Entry point, CLI args
│   ├── tests/           # pytest test suite
│   └── pyproject.toml   # Package metadata, deps
├── esp32-face-v2/       # Face MCU firmware (ESP32-S3, C/C++)
│   └── main/            # WS2812B 16×16 LED matrix rendering
├── esp32-reflex/        # Motion MCU firmware (ESP32-S3, C/C++)
│   └── main/            # Differential drive, PID, safety, encoders
├── server/              # Planner server (LLM/STT/TTS on 3090 Ti)
│   ├── app/             # Main package
│   │   ├── llm/         # LLM integration (vLLM)
│   │   ├── stt/         # Speech-to-text (faster-whisper)
│   │   ├── tts/         # Text-to-speech (orpheus-speech)
│   │   └── routers/     # API endpoints
│   └── tests/           # pytest test suite
├── deploy/              # Deployment (systemd service, install/update scripts)
├── tools/               # Dev utilities (face simulation via pygame)
└── docs/                # Architecture, protocol specs, power topology
```

## Tech Stack

| Component      | Stack                                                      |
| -------------- | ---------------------------------------------------------- |
| Supervisor     | Python 3.11+, asyncio, FastAPI, uvicorn, pyserial, OpenCV  |
| ESP32 firmware | C/C++, ESP-IDF (FreeRTOS), CMake                           |
| Build (Python) | Hatchling via pyproject.toml, uv for dependency management |
| Build (ESP32)  | `idf.py build` (CMake)                                     |
| Tests          | pytest, pytest-asyncio                                     |
| Linting        | ruff (>=0.15.1)                                            |

## Common Commands

### Running the Supervisor

```bash
cd supervisor
python -m supervisor                     # Default (auto-detect serial)
python -m supervisor --mock              # Mock Reflex MCU (no hardware)
python -m supervisor --port /dev/ttyUSB0 # Explicit serial port
python -m supervisor --no-vision         # Disable vision process
python -m supervisor --http-port 8080    # Custom HTTP port
```

### Testing

```bash
# Run all tests
pytest supervisor/tests/

# Run a specific test file
pytest supervisor/tests/test_state_machine.py -v

# Run with keyword filter
pytest supervisor/tests/ -k "test_boot"
```

### Linting / Formatting

```bash
# Check
ruff check supervisor/

# Fix auto-fixable issues
ruff check --fix supervisor/

# Format
ruff format supervisor/
```

### Running the Server

```bash
cd server
uv sync --extra all       # Install all deps (llm, stt, tts)
uv sync --extra dev       # Install dev deps only
uv run python -m app.main # Start server
uv run pytest tests/ -v   # Run tests
```

### ESP32 Firmware

```bash
cd esp32-face-v2   # or esp32-reflex
idf.py build
idf.py flash
idf.py monitor
```

## Architecture Key Concepts

### Control Loop (runtime.py)
- Runs at **50 Hz** (20 ms tick); telemetry broadcast at **20 Hz**
- Each tick: read telemetry → update state machine → compute twist → apply safety policies → send to MCU

### State Machine (state/supervisor_sm.py)
- **States:** BOOT → IDLE → TELEOP / WANDER → ERROR
- BOOT → IDLE: automatic when Reflex MCU connects with no faults
- Any → ERROR: on disconnect, ESTOP, TILT, or BROWNOUT
- ERROR → IDLE: via `clear_error()` when Reflex is healthy
- OBSTACLE fault does **not** trigger ERROR (handled via speed caps)

### Safety Policies (state/policies.py)
Layered defense-in-depth:
1. Mode gate — no motion outside TELEOP/WANDER
2. Fault gate — any fault → zero twist
3. Reflex disconnect → zero twist
4. Ultrasonic range scaling (hard stop at 250 mm, 50% at 500 mm)
5. Stale range fallback (50% cap)
6. Vision confidence scaling
7. Stale vision timeout (500 ms)

### Serial Protocol (devices/protocol.py, io/serial_transport.py)
- Binary packets: `[type:u8][seq:u8][payload:N][crc16:u16-LE]`
- COBS framing with 0x00 delimiter
- Auto-reconnect with exponential backoff (0.5 s–5 s)

### Vision System (inputs/)
- Runs in a **separate OS process** (avoids GIL interference)
- Main process drains multiprocessing queue non-blocking each tick
- Stale vision (>500 ms) triggers conservative speed cap

### Planner Integration (planner/)
- **Scheduler** (`scheduler.py`) — manages planner task lifecycle
- **Event Bus** (`event_bus.py`) — event-driven communication between subsystems
- **Skill Executor** (`skill_executor.py`) — executes planned skills/actions
- **Validator** (`validator.py`) — validates planner output before execution
- **Speech Policy** (`speech_policy.py`) — governs when/how TTS is triggered
- Integrated into the 50 Hz runtime loop; planner decisions are applied each tick

### Audio & Conversation (devices/)
- **Conversation Manager** (`conversation_manager.py`) — orchestrates conversation flow (STT → LLM → TTS)
- **Audio Orchestrator** (`audio_orchestrator.py`) — manages audio playback/recording lifecycle
- **Audio Bridge** (`audio_bridge.py`) — audio I/O abstraction layer
- **Lip Sync** (`lip_sync.py`) — synchronizes face mouth animation with audio playback
- **Expressions** (`expressions.py`) — maps emotional states to face expressions/moods
- **Planner Client** (`planner_client.py`) — HTTP client to the remote planner server

### Web API (api/http_server.py)
- `GET /status` — robot state JSON
- `GET /params` — full parameter registry
- `POST /params` — transactional parameter updates
- `POST /actions` — RPC (set_mode, e_stop, clear_e_stop)
- `GET /video` — MJPEG video stream
- `GET /debug/devices` — device connection state
- `GET /debug/planner` — planner state
- `WS /ws` — telemetry stream (JSON, 10–20 Hz)
- `WS /ws/logs` — live log stream
- Static files served at `/` for the web dashboard

## Code Conventions

### Python (Supervisor)
- **Type hints everywhere** — use `from __future__ import annotations`
- **Dataclasses with `slots=True`** for all data types (RobotState, DesiredTwist, etc.)
- **Module-level loggers:** `log = logging.getLogger(__name__)`
- **Async-first:** core runtime and transport are async (asyncio)
- **Config via dataclasses** with YAML loading and sensible defaults
- **Enums** for commands, telemetry types, modes, faults
- **No JSON on the wire** to MCUs — binary struct packing only

### C/C++ (ESP32)
- Header-based modules (`pin_map.h`, `config.h`, `shared_state.h`)
- FreeRTOS tasks for control loop (100–200 Hz), serial RX, safety, telemetry
- Fixed-size binary packets, little-endian
- Tunable parameters as enums in `config.h`

### General
- Keep reflexes deterministic and local to MCUs
- Planner / AI features are optional and network-remote
- Safety-critical code lives in the MCU; supervisor applies additional caps
- Prefer simple, direct code over abstractions

## Testing Guidelines

- Tests live in `supervisor/tests/`
- Use `pytest-asyncio` for async tests
- The mock Reflex MCU (`supervisor/mock/mock_reflex.py`) provides a PTY-based fake serial device for integration testing
- Test coverage includes: state machine, protocol encoding, COBS framing, CRC, policies, detectors, face client/protocol, audio orchestrator, conversation manager, planner (client, event bus, validator, scheduler, ordering/idempotency), skill executor, speech policy, lip sync, expressions, and runtime integration
- Run the full test suite before submitting changes

## Configuration

- **Supervisor runtime config:** YAML file (schema defined in `supervisor/config.py`)
  - Sections: serial, control, safety, network, logging, vision
  - Default serial devices: `/dev/robot_reflex`, `/dev/robot_face` (udev symlinks)
- **ESP32 config:** `sdkconfig.defaults` + `config.h` header constants
- **Dependencies:** managed via `uv` with `pyproject.toml` + `uv.lock` in both `supervisor/` and `server/`

## Deployment

- `deploy/install.sh` — first-time setup on the Pi
- `deploy/update.sh` — pull latest and restart service
- `deploy/robot-buddy-supervisor.service` — systemd unit file
- `deploy/supervisor.env` — environment variables for the service

## Files to Avoid Committing

Per `.gitignore`: `__pycache__/`, `*.pyc`, `.env`, `.venv/`, `build/`, `dist/`, `sdkconfig`, `*.lock`

# TODO
- add trigger word so conversations flow more naturally.  wait for silence.  remove need to press button
- upgrade the camera and adjust settings
- add camera calibration/mask/cv settings in supervisor dash
- fix server issue when trying to run better tts model
- don't send planner updates so often
- add llm history so conversations feel more natural
- tts from non-button press (determinisitic sources) either cut off or not firing at all
- face stops talking before speach stops playing, needs better sync
- should play a sound when listening for command is active (either by button press or keyword)

## timestamps todo

### Goal

Design deterministic, replayable telemetry across **Pi + Reflex MCU + Face MCU** so autonomy and debugging are based on evidence, not guesswork.

We must be able to answer:

- Did it turn because of IMU data?
- Because vision was stale?
- Because a motor fault occurred?
- Or because of latency?

---

### Principles

- Use **monotonic clocks only** (no wall clock in control paths).
- Timestamp at **acquisition time**, not publish time.
- Add **sequence numbers everywhere**.
- Maintain a stable mapping from MCU time → Pi time.
- Log raw bytes for perfect replay.

---

### Clock Domains

- **Pi** → `CLOCK_MONOTONIC` (ns)
- **Reflex MCU** → `t_reflex_us` since boot (u64)
- **Face MCU** → `t_face_us` since boot (u64)

---

### Required Fields (All MCU Messages)

Every packet must include:

- `src_id`
- `msg_type`
- `seq` (u32)
- `t_src_us` (monotonic since boot)
- `payload`

On Pi receive, attach:

- `t_pi_rx_ns`

Minimum viable envelope:
```
t_pi_est_ns = t_src_us * 1000 + offset_ns
```

Sync at 2–10 Hz.  
Use lowest RTT samples for stable offset.

---

### Reflex MCU Timestamp Rules

Timestamp at **acquisition moment**:

- IMU → at I2C/SPI read completion or DRDY interrupt
- Encoders → at control loop tick boundary
- Ultrasonic → at echo completion
- Motor PWM applied → when update committed
- Faults → at detection moment

Optional (ultrasonic precision):

- `t_trig_us`
- `t_echo_us`

---

### Face MCU Timestamp Rules

Timestamp:

- `STATE_APPLIED`
- `BLINK`
- `GAZE_CHANGE`
- `FAULT`
- Future audio-related events (lip sync, beat sync)

Consistency is more important than frequency.

---

### Camera Frames (Pi Domain)

Each frame must include:

- `frame_seq`
- `t_cam_ns` (sensor timestamp if available)
- `t_rx_ns` (Pi receive time)

Detection events must reference:

- `frame_seq`
- `t_frame_ns`
- `t_det_done_ns`

Never use detection completion time for sensor fusion alignment.

---

### Commands & Causality

Motion commands:

- Add `cmd_seq`
- Record `t_cmd_tx_ns` on Pi

Reflex echoes back:

- `cmd_seq_last_applied`
- `t_applied_src_us`

This enables full control causality tracing.

---

### Server Events

For each planner request:

- `req_id`
- `t_req_tx_ns`
- `t_resp_rx_ns`
- `rtt_ns`

Never use server wall clock for control decisions.

---

### Logging Strategy (Critical)

#### 1. Raw Binary Log (Authoritative)

For each received packet:

- `t_pi_rx_ns`
- `src_id`
- `len`
- raw bytes

This is your deterministic replay stream (rosbag equivalent).

---

#### 2. Derived Log (Optional)

Decoded fields:

- `t_pi_est_ns`
- latency diagnostics
- seq gap detection
- offset + drift estimate

---

### Telemetry Health Metrics

Add dashboard panel:

Per device:

- RTT min / avg
- offset_ns
- drift estimate
- seq drop rate

---

### Known Failure Modes

- Offset drift → periodic sync + drift estimation
- USB jitter → rely on minimum RTT samples
- Packet drops → detect via seq gaps
- Sensor fusion misalignment → enforce acquisition timestamps

---

### Immediate Actions

- [ ] Add `seq` and `t_src_us` to all MCU packets
- [ ] Implement `TIME_SYNC_REQ / RESP`
- [ ] Log raw packets with `t_pi_rx_ns`
- [ ] Add `frame_seq`, `t_cam_ns`, `t_det_done_ns`
- [ ] Add `cmd_seq` to motion commands
- [ ] Add telemetry health dashboard

---

This keeps the system:

- Deterministic  
- Replayable  
- SLAM-ready  
- Debuggable under load  