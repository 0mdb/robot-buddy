# Robot Buddy

A kid-safe, expressive robot platform combining real-time motor control, an animated LED face, and optional networked AI personality.

## How It Works

Two ESP32-S3 microcontrollers handle the deterministic, safety-critical work: one drives motors with PID control and enforces safety limits, the other renders animated eyes on a WS2812B LED matrix. A Raspberry Pi 5 orchestrates everything at 50 Hz — reading sensors, running the state machine, applying layered safety policies, and streaming telemetry to a browser UI. An optional AI personality server on a separate machine (3090 Ti) generates expressive behavior plans via a local LLM.

Reflexes are local and deterministic. Personality is remote and optional.

## Hardware

| Component | Hardware | Role |
|---|---|---|
| Supervisor | Raspberry Pi 5 | 50 Hz orchestration, safety policy, HTTP/WS API |
| Face MCU | ESP32-S3 WROOM | 16x16 WS2812B LED matrix eyes + animations |
| Reflex MCU | ESP32-S3 WROOM | Differential drive, PID, encoders, IMU, ultrasonic, safety |
| AI Server | PC with 3090 Ti (off-robot) | Local LLM (Qwen 3 14B) + future TTS, on LAN |
| Motor Driver | TB6612FNG | Dual H-bridge for differential drive |
| Power | 2S LiPo | Split into dirty (motors) and clean 5V regulated rails |

## Repository Layout

```
robot-buddy/
├── supervisor/          # Python supervisor (Raspberry Pi 5)
│   ├── supervisor/      # Main package
│   │   ├── io/          # Serial transport, COBS framing
│   │   ├── devices/     # MCU clients (reflex, face, protocol)
│   │   ├── state/       # State machine, datatypes, safety policies
│   │   ├── api/         # FastAPI HTTP/WebSocket server, param registry
│   │   ├── inputs/      # Vision (camera, multiprocessing worker)
│   │   ├── logging/     # Telemetry recording (JSONL)
│   │   ├── mock/        # Mock Reflex MCU for testing (PTY-based)
│   │   ├── config.py    # YAML config with dataclass schemas
│   │   ├── runtime.py   # 50 Hz control loop
│   │   └── main.py      # Entry point, CLI args
│   ├── tests/           # pytest test suite
│   └── pyproject.toml   # Package metadata, deps
├── server/              # AI personality server (3090 Ti, FastAPI + Ollama)
│   ├── app/             # FastAPI app, LLM client, prompts, schemas
│   ├── tests/           # pytest test suite
│   ├── Modelfile        # Ollama model config
│   └── pyproject.toml   # Package metadata, deps
├── esp32-face/          # Face MCU firmware (ESP32-S3, C/C++, ESP-IDF)
│   └── main/            # WS2812B 16×16 LED matrix rendering
├── esp32-reflex/        # Reflex MCU firmware (ESP32-S3, C/C++, ESP-IDF)
│   └── main/            # Differential drive, PID, safety, encoders
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
│  │ Motors, PID │        │ 16×16 LED   │             │
│  │ Encoders    │        │ Eyes +      │             │
│  │ IMU, Range  │        │ Animations  │             │
│  │ Safety      │        │             │             │
│  └─────────────┘        └─────────────┘             │
└──────────────────────────────────────────────────────┘
         │
         │ HTTP (LAN, optional)
         │
┌────────▼───────────────────────────┐
│ AI Server (3090 Ti PC)             │
│                                    │
│ Ollama (qwen3:14b) → FastAPI      │
│ POST /plan → performance plans    │
│ (emote, say, gesture, move)       │
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

Auto-reconnect with exponential backoff (0.5s–5s). See `docs/protocols.md` for packet definitions.

## Tech Stack

| Component | Stack |
|---|---|
| Supervisor | Python 3.11+, asyncio, FastAPI, uvicorn, pyserial, OpenCV |
| AI Server | Python 3.11+, FastAPI, httpx, Pydantic, Ollama (Qwen 3 14B) |
| ESP32 Firmware | C/C++, ESP-IDF (FreeRTOS), CMake |
| Build (Python) | Hatchling via pyproject.toml |
| Build (ESP32) | `idf.py build` (CMake) |
| Tests | pytest, pytest-asyncio |
| Linting | ruff (>=0.15.1) |

## Getting Started

### Supervisor (Raspberry Pi 5)

```bash
cd supervisor
pip install -e ".[dev]"

# Run with mock hardware (no physical robot needed)
python -m supervisor --mock

# Run with real hardware
python -m supervisor --port /dev/ttyUSB0

# Other options
python -m supervisor --no-vision         # Disable vision process
python -m supervisor --http-port 8080    # Custom HTTP port
```

### AI Personality Server (3090 Ti PC)

```bash
# Install Ollama and pull the model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:14b

# Install and run the server
cd server
pip install -e ".[dev]"
python -m app.main
```

The server starts on port 8100. See `server/README.md` for full API docs and configuration.

### ESP32 Firmware

Requires ESP-IDF toolchain.

```bash
cd esp32-face   # or esp32-reflex
idf.py build
idf.py flash
idf.py monitor
```

## Development

### Running Tests

```bash
# Supervisor tests (from repo root)
python -m pytest supervisor/tests/ -v

# AI server tests
cd server
python -m pytest tests/ -v
```

### Linting

```bash
# Check
ruff check supervisor/
ruff check server/

# Auto-fix
ruff check --fix supervisor/ server/

# Format
ruff format supervisor/ server/
```

### Mock Mode

The supervisor includes a PTY-based mock Reflex MCU (`supervisor/mock/mock_reflex.py`) that simulates serial communication, telemetry, and fault injection. Use `--mock` to run the full supervisor stack without any hardware.

### Web UI

When the supervisor is running, open `http://<robot_ip>:8080` in a browser for:
- Live telemetry display
- Mode control (IDLE, TELEOP, WANDER)
- E-STOP button
- Parameter tuning sliders (PID gains, speed limits, safety thresholds)
- MJPEG video stream (if vision enabled)

### Configuration

**Supervisor** — YAML config file (schema in `supervisor/config.py`):
- Sections: serial, control, safety, network, logging, vision
- Default serial paths: `/dev/robot_reflex`, `/dev/robot_face` (via udev symlinks)

**AI Server** — environment variables:
- `OLLAMA_URL`, `MODEL_NAME`, `PLAN_TIMEOUT_S`, `TEMPERATURE`, `NUM_CTX`
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
| `/ws` | WS | Telemetry stream (20 Hz, JSON) |

## AI Server API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server + Ollama status |
| `/plan` | POST | Accept world state, return performance plan |

Plan actions: `say(text)`, `emote(name, intensity)`, `gesture(name, params)`, `move(v, w, duration)` — all bounded for safety. See `server/README.md` for request/response examples.

## Project Status

### Working
- [x] Supervisor: 50 Hz control loop, state machine, safety policies
- [x] Supervisor: serial transport with COBS framing, CRC, auto-reconnect
- [x] Supervisor: FastAPI HTTP/WebSocket API with telemetry streaming
- [x] Supervisor: parameter registry with runtime tuning
- [x] Supervisor: vision process (separate OS process, multiprocessing queue)
- [x] Supervisor: mock Reflex MCU for hardware-free development
- [x] Supervisor: telemetry recording (JSONL)
- [x] AI Server: FastAPI + Ollama integration with structured output
- [x] AI Server: bounded performance plans (emote, say, gesture, move)
- [x] ESP32 Face: LED matrix rendering, eye animations
- [x] ESP32 Reflex: motor control, PID, encoders, safety enforcement

### In Progress
- [ ] Supervisor-side PersonalityClient (connects to AI server)
- [ ] AI Server: TTS endpoint
- [ ] AI Server: interaction history / conversation memory

### Future
- [ ] WANDER mode driven by AI personality
- [ ] Voice pipeline (STT on Pi, TTS on 3090 Ti)
- [ ] Additional modes: LINE_FOLLOW, BALL, CRANE, CHARGING
