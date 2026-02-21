# Robot Buddy

A kid-safe, expressive robot platform combining real-time motor control, an animated TFT face, and optional networked AI planner.

## How It Works

Two ESP32-S3 microcontrollers handle the deterministic, safety-critical work: one drives motors with PID control and enforces safety limits, the other renders an animated face on a 320x240 TFT touch display (`esp32-face-v2`). A Raspberry Pi 5 orchestrates everything at 50 Hz — reading sensors, running the state machine, applying layered safety policies, and streaming telemetry to a browser UI. An optional AI planner server on a separate machine (3090 Ti) generates expressive behavior plans via a local LLM.

Reflexes are local and deterministic. Planner is remote and optional.

## Hardware

| Component | Hardware | Role |
|---|---|---|
| Supervisor | Raspberry Pi 5 | 50 Hz orchestration, safety policy, HTTP/WS API |
| Face MCU | ESP32-S3 (ES3C28P) | 320x240 TFT face renderer + touch/buttons telemetry |
| Reflex MCU | ESP32-S3 WROOM | Differential drive, PID, encoders, IMU, ultrasonic, safety |
| AI Server | PC with 3090 Ti (off-robot) | Planner/conversation LLM + TTS on LAN (`LLM_BACKEND=ollama|vllm`) |
| Motor Driver | TB6612FNG | Dual H-bridge for differential drive |
| Power | 2S LiPo | Split into dirty (motors) and clean 5V regulated rails |

## Repository Layout

```
robot-buddy/
├── supervisor_v2/       # Python supervisor (Raspberry Pi 5, process-isolated workers)
│   ├── core/            # 50 Hz tick loop, state machine, safety, behavior engine
│   ├── devices/         # MCU clients (reflex, face), protocol, expressions
│   ├── io/              # Serial transport, COBS framing, CRC
│   ├── workers/         # Process-isolated workers (TTS, vision, AI)
│   ├── messages/        # NDJSON envelope, event/action types
│   ├── api/             # FastAPI HTTP/WebSocket server, param registry
│   ├── mock/            # Mock Reflex MCU for testing (PTY-based)
│   ├── tests/           # pytest test suite
│   └── pyproject.toml   # Package metadata, deps
├── server/              # AI planner server (3090 Ti, FastAPI + backend switch)
│   ├── app/             # FastAPI app, LLM/STT/TTS backends, prompts, schemas
│   ├── tests/           # pytest test suite
│   ├── Modelfile        # Legacy Ollama model config
│   └── pyproject.toml   # Package metadata, deps
├── esp32-face-v2/       # Face MCU firmware (ESP32-S3, C/C++, ESP-IDF)
│   └── main/            # TFT face rendering + touch/buttons + USB protocol
├── esp32-reflex/        # Reflex MCU firmware (ESP32-S3, C/C++, ESP-IDF)
│   └── main/            # Differential drive, PID, IMU, safety, encoders
├── deploy/              # Deployment (systemd service, install/update scripts)
├── tools/               # Dev utilities (face simulation via pygame)
└── docs/                # Architecture, protocol specs, power topology
```

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ On Robot                                             │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ Raspberry Pi 5 — Supervisor                    │  │
│  │                                                │  │
│  │  50 Hz tick loop:                              │  │
│  │    read telemetry → state machine → safety     │  │
│  │    policies → send commands → broadcast        │  │
│  │                                                │  │
│  │  HTTP API (:8080)  WebSocket (:8080/ws)        │  │
│  │  Vision process (separate OS process, 10-20Hz) │  │
│  └──────┬──────────────────────┬──────────────────┘  │
│         │ USB serial (COBS)    │ USB serial (COBS)   │
│  ┌──────▼──────┐        ┌─────▼───────┐             │
│  │ Reflex MCU  │        │  Face MCU   │             │
│  │ ESP32-S3    │        │  ESP32-S3   │             │
│  │             │        │             │             │
│  │ Motors, PID │        │ 320x240 TFT │             │
│  │ Encoders    │        │ Face +      │             │
│  │ IMU, Range  │        │ Touch UI    │             │
│  │ Safety      │        │             │             │
│  └─────────────┘        └─────────────┘             │
└──────────────────────────────────────────────────────┘
         │
         │ HTTP (LAN, optional)
         │
┌────────▼───────────────────────────┐
│ AI Server (3090 Ti PC)             │
│                                    │
│ FastAPI planner server             │
│ LLM backend: ollama | vllm         │
│ TTS: Orpheus (vLLM) + espeak shed  │
│ POST /plan / WS /converse /tts     │
└────────────────────────────────────┘
```

### State Machine

`BOOT` → `IDLE` → `TELEOP` / `WANDER` → `ERROR`

- **BOOT → IDLE**: automatic when Reflex MCU connects with no faults
- **IDLE → TELEOP/WANDER**: via `set_mode` command
- **Any → ERROR**: on disconnect, ESTOP, TILT, or BROWNOUT
- **ERROR → IDLE**: via `clear_error()` when Reflex is healthy

### Safety Policies (Defense in Depth)

1. Mode gate — no motion outside TELEOP/WANDER
2. Fault gate — any fault → zero twist
3. Reflex disconnect → zero twist
4. Ultrasonic range scaling (hard stop at 250 mm, 50% at 500 mm)
5. Stale range fallback (50% cap)
6. Vision confidence scaling
7. Stale vision timeout (500 ms)

Safety-critical enforcement also runs on the Reflex MCU itself (acceleration limits, command TTL, hard stop). The supervisor applies additional caps above this.

### Serial Protocol

Binary packets over USB serial with COBS framing:

```
[type:u8][seq:u8][payload:N][crc16:u16-LE]
```

For `esp32-face-v2`, this protocol carries face state/gesture/system/talking commands and touch/button/status telemetry only. Audio transport is supervisor-side USB audio.

Auto-reconnect with exponential backoff (0.5s–5s). See `docs/protocols.md` for packet definitions.

## Tech Stack

| Component | Stack |
|---|---|
| Supervisor | Python 3.11+, asyncio, FastAPI, uvicorn, pyserial, OpenCV |
| AI Server | Python 3.11+, FastAPI, httpx, Pydantic, Ollama (compat) + vLLM (migration target) |
| ESP32 Firmware | C/C++, ESP-IDF (FreeRTOS), CMake |
| Build (Python) | Hatchling via pyproject.toml |
| Build (ESP32) | `idf.py build` (CMake) |
| Tests | pytest, pytest-asyncio |
| Linting | ruff (>=0.15.1) |

## Getting Started

### Supervisor (Raspberry Pi 5)

```bash
cd supervisor_v2
pip install -e ".[dev]"

# Run with mock hardware (no physical robot needed)
python -m supervisor_v2 --mock

# Run with real hardware
python -m supervisor_v2 --port /dev/ttyUSB0

# Other options
python -m supervisor_v2 --no-vision         # Disable vision worker
python -m supervisor_v2 --http-port 8080    # Custom HTTP port
python -m supervisor_v2 --planner-api http://10.0.0.20:8100 --robot-id robot-1
```

### AI Planner Server (3090 Ti PC)

```bash
# Install and run the server
cd server
uv sync --extra dev --extra llm --extra stt --extra tts

# Recommended testing profile (vLLM planner + CPU STT + espeak)
LLM_BACKEND=vllm STT_DEVICE=cpu TTS_BACKEND=espeak \
uv run --extra llm --extra stt --extra tts python -m app.main
```

The server starts on port 8100. See `server/README.md` for full API docs and configuration.

### ESP32 Firmware

Requires ESP-IDF toolchain.

```bash
cd esp32-face-v2   # or esp32-reflex
idf.py build
idf.py flash
idf.py monitor
```

## Development

### Running Tests

```bash
# Supervisor tests (from repo root)
python -m pytest supervisor_v2/tests/ -v

# AI server tests
cd server
python -m pytest tests/ -v
```

### Linting

```bash
# Check
ruff check supervisor_v2/
ruff check server/

# Auto-fix
ruff check --fix supervisor_v2/ server/

# Format
ruff format supervisor_v2/ server/
```

### Mock Mode

The supervisor includes a PTY-based mock Reflex MCU (`supervisor_v2/mock/mock_reflex.py`) that simulates serial communication, telemetry, and fault injection. Use `--mock` to run the full supervisor stack without any hardware.

### Web UI

When the supervisor is running, open `http://<robot_ip>:8080` in a browser for:
- Live telemetry display
- Mode control (IDLE, TELEOP, WANDER)
- E-STOP button
- Parameter tuning sliders (PID gains, speed limits, safety thresholds)
- MJPEG video stream (if vision enabled)

### Configuration

**Supervisor** — YAML config file (schema in `supervisor_v2/config.py`):
- Sections: serial, control, safety, network, logging, vision
- Default serial paths: `/dev/robot_reflex`, `/dev/robot_face` (via udev symlinks)

**AI Server** — environment variables:
- `LLM_BACKEND`, `VLLM_MODEL_NAME`, `LLM_MAX_INFLIGHT`, `PERFORMANCE_MODE`
- legacy compatibility: `OLLAMA_URL`, `MODEL_NAME`, `PLAN_TIMEOUT_S`, `TEMPERATURE`, `NUM_CTX`
- See `server/README.md` for the full table

**ESP32** — `sdkconfig.defaults` + `config.h` constants

## Supervisor API

| Endpoint | Method | Description |
|---|---|---|
| `/status` | GET | Current robot state (JSON) |
| `/params` | GET | Full parameter registry |
| `/params` | POST | Transactional parameter updates |
| `/actions` | POST | RPC: `set_mode`, `e_stop`, `clear_e_stop` |
| `/video` | GET | MJPEG stream (if vision enabled) |
| `/debug/devices` | GET | Device connection state |
| `/debug/planner` | GET | Planner state |
| `/ws` | WS | Telemetry stream (20 Hz, JSON) |
| `/ws/logs` | WS | Live log stream |

## AI Server API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server + selected LLM backend status |
| `/plan` | POST | Accept world state + `robot_id/seq/monotonic_ts_ms`, return plan + `plan_id` echo metadata |
| `/converse` | WS | Conversation stream (single active session per `robot_id`) |
| `/tts` | POST | Direct TTS with optional metadata (`robot_id`, `seq`, `monotonic_ts_ms`) |

Plan actions: `say(text)`, `emote(name, intensity)`, `gesture(name, params)`, `skill(name)` — planner proposes intent and supervisor executes deterministic skills.

## Supervisor Fallback Policy

| Failure condition | Immediate supervisor action | Motion policy | Face policy | Speech policy |
|---|---|---|---|---|
| `/plan` unreachable / non-200 | Mark planner disconnected; skip remote plan apply | Local deterministic only (`patrol_drift`/`avoid_obstacle`/safe stop) | `confused` gesture with cooldown | Cancel queued planner speech |
| `/converse` TTS fails mid-turn | Stop playback and clear talking flag | No change to motion authority | Show `thinking` briefly then restore previous mood | Attempt fallback backend once; if unavailable, skip speech |

## Project Status

### Working
- [x] Supervisor: 50 Hz control loop, state machine, safety policies
- [x] Supervisor: serial transport with COBS framing, CRC, auto-reconnect
- [x] Supervisor: FastAPI HTTP/WebSocket API with telemetry streaming
- [x] Supervisor: parameter registry with runtime tuning
- [x] Supervisor: vision process (separate OS process, multiprocessing queue)
- [x] Supervisor: mock Reflex MCU for hardware-free development
- [x] Supervisor: telemetry recording (JSONL)
- [x] AI Server: FastAPI + backend-switchable planner inference (Ollama/vLLM)
- [x] AI Server: bounded performance plans (emote, say, gesture, skill)
- [x] AI Server: direct TTS endpoint with Orpheus/espeak fallback
- [x] ESP32 Face v2: TFT face rendering, touch/button telemetry, supervisor-driven emotions/gestures
- [x] ESP32 Reflex: motor control, PID, encoders, IMU, safety enforcement
- [x] Supervisor-side PlannerClient + planner module (scheduler, event bus, skills)
- [x] WANDER mode driven by deterministic skills + planner intent
- [x] Voice pipeline (STT + TTS on 3090 Ti server, audio on Pi USB devices)
- [x] Conversation flow (button-triggered STT → LLM → TTS → face animation)

### In Progress
- [ ] AI Server: interaction history / conversation memory
- [ ] Lip sync / face-speech timing improvements
- [ ] Wake word detection (remove need for button press)

### Future
- [ ] Additional modes: LINE_FOLLOW, BALL, CRANE, CHARGING
