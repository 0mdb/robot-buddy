# CLAUDE.md — Robot Buddy

## Project Overview

Robot Buddy is a kid-safe, expressive robot platform combining real-time motor control, an animated LED face, and optional networked AI planner. The architecture separates deterministic reflexes (ESP32 MCUs) from high-level orchestration (Raspberry Pi 5 supervisor).

## Repository Structure

```
robot-buddy/
├── supervisor/          # Python supervisor (Raspberry Pi 5)
│   ├── supervisor/      # Main package
│   │   ├── io/          # Serial transport, COBS framing
│   │   ├── devices/     # MCU clients (reflex_client, face_client, protocol)
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
├── esp32-face/          # Face MCU firmware (ESP32-S3, C/C++)
│   └── main/            # WS2812B 16×16 LED matrix rendering
├── esp32-reflex/        # Motion MCU firmware (ESP32-S3, C/C++)
│   └── main/            # Differential drive, PID, safety, encoders
├── server/              # Optional planner server (LLM/TTS on 3090 Ti)
├── tools/               # Dev utilities (face simulation via pygame)
└── docs/                # Architecture, protocol specs, power topology
```

## Tech Stack

| Component | Stack |
|-----------|-------|
| Supervisor | Python 3.11+, asyncio, FastAPI, uvicorn, pyserial, OpenCV |
| ESP32 firmware | C/C++, ESP-IDF (FreeRTOS), CMake |
| Build (Python) | Hatchling via pyproject.toml, uv for dependency management |
| Build (ESP32) | `idf.py build` (CMake) |
| Tests | pytest, pytest-asyncio |
| Linting | ruff (>=0.15.1) |

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
uv sync --extra dev       # Install deps
uv run python -m app.main # Start server (Ollama must be running)
uv run pytest tests/ -v   # Run tests
```

### ESP32 Firmware

```bash
cd esp32-face   # or esp32-reflex
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

### Web API (api/http_server.py)
- `GET /status` — robot state JSON
- `GET /params` — full parameter registry
- `POST /params` — transactional parameter updates
- `POST /actions` — RPC (set_mode, e_stop, clear_e_stop)
- `WS /ws` — telemetry stream (JSON, 10–20 Hz)

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
- State machine, protocol encoding, COBS framing, CRC, policies, and detectors all have dedicated test files
- Run the full test suite before submitting changes

## Configuration

- **Supervisor runtime config:** YAML file (schema defined in `supervisor/config.py`)
  - Sections: serial, control, safety, network, logging, vision
  - Default serial devices: `/dev/robot_reflex`, `/dev/robot_face` (udev symlinks)
- **ESP32 config:** `sdkconfig.defaults` + `config.h` header constants
- **Dependencies:** managed via `uv` with `pyproject.toml` + `uv.lock` in both `supervisor/` and `server/`

## Files to Avoid Committing

Per `.gitignore`: `__pycache__/`, `*.pyc`, `.env`, `.venv/`, `build/`, `dist/`, `sdkconfig`, `*.lock`
