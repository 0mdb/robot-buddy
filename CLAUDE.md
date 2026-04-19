# CLAUDE.md — Robot Buddy

## Project Overview

Robot Buddy is a kid-safe, expressive robot platform combining real-time motor control, an animated LED face, and optional networked AI planner. The architecture separates deterministic reflexes (ESP32 MCUs) from high-level orchestration (Raspberry Pi 5 supervisor).

## Document Hierarchy

| Document | Role | Mutability |
|----------|------|------------|
| `CLAUDE.md` | Project instructions for Claude Code: conventions, commands, structure | Updated as conventions change |
| `README.md` | Human-facing project overview: architecture, setup, API | Updated on milestones |
| `docs/TODO.md` | **Single source of implementation truth**: prioritized backlog, execution order, parallel tracks | Living document — updated every session |
| `docs/architecture.md` | Detailed system architecture reference | Updated when architecture changes |
| `specs/` | Completed specification documents — immutable reference | Amend only via spec revision process |
| `docs/research/` | Research material (buckets 0-7) — immutable reference | Reference only |
| `docs/` | Operational docs (protocols, wiring, power) | Updated as hardware changes |
| `.claude/skills/` | Claude Code skill definitions (invocable via `/command`) | Updated as workflows evolve |

**Spec-driven development**: Changes that diverge from specs require a spec amendment first. Debate the change, update the spec, then implement.

## Repository Structure

```
robot-buddy/
├── supervisor/       # Python supervisor (Raspberry Pi 5, process-isolated workers)
│   ├── api/             # FastAPI HTTP/WebSocket server, param registry
│   ├── core/            # 50 Hz tick loop, state machine, safety, conv state, mood sequencer
│   ├── devices/         # MCU clients (reflex, face), protocol, expressions
│   ├── io/              # Serial transport, COBS framing, CRC
│   ├── workers/         # Process-isolated workers (TTS, vision, AI, ear)
│   ├── messages/        # NDJSON envelope, event/action types
│   ├── mock/            # Mock Reflex MCU (PTY-based fake serial)
│   ├── tests/           # pytest test suite
│   └── pyproject.toml
├── esp32-face/       # Face MCU firmware (ESP32-S3, C/C++)
│   └── main/            # ILI9341 display, LVGL, touch, LED, border renderer
├── esp32-reflex/        # Motion MCU firmware (ESP32-S3, C/C++)
│   └── main/            # Differential drive, PID, safety, encoders, IMU
├── server/              # Planner server (LLM/STT/TTS on 3090 Ti)
│   ├── app/
│   └── tests/
├── dashboard/           # React dashboard (Vite + TypeScript + Biome)
│   ├── src/             # Components, hooks, stores, tabs
│   └── biome.json       # Lint + format config
├── specs/               # Completed specifications (immutable reference)
├── docs/                # TODO, architecture, protocols, wiring, power, research
│   └── research/        # PE research buckets 0-7
├── deploy/              # Deployment (systemd, install/update scripts)
├── tools/               # Dev utilities (face sim V3, parity check)
└── training/            # Wake word model training
```

### Key File Paths (Common Edit Targets)

**Face protocol (all layers):**
- Supervisor: `supervisor/devices/protocol.py` + `supervisor/devices/face_client.py`
- Firmware: `esp32-face/main/protocol.h` + `esp32-face/main/face_ui.cpp`
- Expressions: `supervisor/devices/expressions.py`

**Face state & rendering:**
- Sim: `tools/face_sim_v3/state/constants.py` (canonical values)
- Firmware: `esp32-face/main/config.h` + `esp32-face/main/face_state.cpp`
- Parity: `tools/check_face_parity.py`

**Core control loop:**
- `supervisor/core/tick_loop.py` — 50 Hz orchestration
- `supervisor/core/conv_state.py` — conversation state machine
- `supervisor/core/state_machine.py` — BOOT/IDLE/TELEOP/WANDER/ERROR

**Mood & expression:**
- `supervisor/core/mood_sequencer.py` — 4-phase transition choreography (~470ms)
- `supervisor/core/guardrails.py` — intensity/duration caps, context gate
- `supervisor/core/conv_transition.py` — ConvTransitionChoreographer (gaze ramps, nods)
- `supervisor/devices/expressions.py` — mood → SET_STATE parameter mapping

**Conversation & AI:**
- `supervisor/core/speech_policy.py` — deterministic event-driven TTS intents
- `supervisor/core/action_scheduler.py` — planner action cooldowns, TTL gating
- `supervisor/core/event_bus.py` — PlannerEvent production and subscription

**Workers (process-isolated):**
- `supervisor/workers/tts_worker.py` — TTS_CMD_SPEAK/CANCEL, energy stream
- `supervisor/workers/ear_worker.py` — wake word detection, Silero VAD
- `supervisor/workers/ai_worker.py` — LLM plan requests + conversation + profile forwarding to server
- `supervisor/workers/vision_worker.py` — ball/clear detection via OpenCV

**Voice loop (wake → speak):** ear_worker (wake word + VAD) → ai_worker (stream conversation to server) → tts_worker (playback + energy) → face (talking border + mouth). TTS energy drives face animation in real time.

**Reflex MCU:**
- Entry: `esp32-reflex/main/app_main.cpp`
- Pins: `esp32-reflex/main/pin_map.h`
- Config: `esp32-reflex/main/config.h`

**Server:**
- Entry: `server/app/main.py`
- LLM: `server/app/llm/`
- Prompts: `server/app/llm/conversation.py`

## Tech Stack

| Component      | Stack                                                      |
| -------------- | ---------------------------------------------------------- |
| Supervisor     | Python 3.11+, asyncio, FastAPI, uvicorn, pyserial, OpenCV  |
| ESP32 firmware | C/C++, ESP-IDF (FreeRTOS), CMake                           |
| Build (Python) | Hatchling via pyproject.toml, uv for dependency management |
| Build (ESP32)  | `idf.py build` (CMake), `source ~/esp/esp-idf/export.sh`  |
| Dashboard      | React 19, Vite, TypeScript, Zustand, TanStack Query        |
| Tests          | pytest, pytest-asyncio, Vitest                             |
| Python lint    | ruff (format + check), Pylance/pyright (type checking)     |
| C++ lint       | clang-format (style), cppcheck (static analysis)           |
| Dashboard lint | Biome (format + lint), TypeScript strict mode              |

## Common Commands

All commands are available via `just` (see `justfile` for full list):

```bash
# Testing — all three test recipes accept a positional filter
just test-all                                         # all tests (supervisor, server, dashboard)
just test-supervisor tests/test_api.py::test_foo      # single pytest node
just test-supervisor -k "face and not slow"           # any pytest args pass through
just test-server <filter>                             # same pattern
just test-dashboard SpecificComponent                 # Vitest name filter

# Lint
just lint                  # check Python + C++ + dashboard
just lint-fix              # auto-fix everything
just lint-dashboard        # biome + tsc only
just lint-cpp-tidy         # deep clang-tidy on firmware (requires prior build-reflex/build-face)

# Running
just run-mock [args]       # supervisor with mock hardware (no robot needed)
just run [args]            # supervisor against real hardware
just run-server            # planner server (sources .env if present)
just run-dashboard         # dashboard dev server (Vite)
just build-dashboard       # dashboard production build → supervisor/static/

# Firmware (face and reflex are symmetric)
just build-reflex / build-face
just flash-reflex / flash-face      # build + flash
just monitor-reflex / monitor-face  # serial console

# Tools, deploy, misc
just deploy                # update + restart on Pi
just install               # first-time Pi install
just sim                   # face sim V3
just check-parity          # verify sim↔MCU constant parity
just serial-diag [args]    # scan connected MCUs
just mcu-benchmark --target face --base-url http://<ip>:8080
just tool <script> [args]  # run any tools/*.py with the tools venv
just preflight             # lint + test-all + check-parity (pre-commit gate)
```

**ESP-IDF note:** the `build-*` / `flash-*` / `monitor-*` recipes auto-source `~/esp/esp-idf/export.sh` (override via `ESP_IDF_EXPORT=/path/to/export.sh`) and skip sourcing if `idf.py` is already on PATH. Prefer the `just` recipes over manual `idf.py` invocation — they also detect build-dir path mismatches and run `fullclean` when needed, and regenerate `compile_commands.json` for clang-tidy.

## Code Conventions

### Python
- **Type hints everywhere** — `from __future__ import annotations`
- **Dataclasses with `slots=True`** for data types
- **Module-level loggers:** `log = logging.getLogger(__name__)`
- **Async-first** — core runtime and transport are async (asyncio)
- **Enums** for commands, telemetry types, modes, faults
- **No JSON on the wire** to MCUs — binary struct packing only
- **Unused imports**: ruff warns but does not auto-remove (see `ruff.toml`)

### C/C++ (ESP32)
- **Linux brace style** — functions on new line, everything else attached
- **4-space indent**, 120-col limit (see `.clang-format`)
- **FreeRTOS tasks** for control loop, serial RX, safety, telemetry
- **Fixed-size binary packets**, little-endian
- **Single-writer shared state** — double-buffering or seqlocks, no mutexes in hot paths
- **`static const char* TAG`** for ESP_LOG macros

### Dashboard (React/TypeScript)
- **TypeScript strict mode** — `strict: true`, `noUnusedLocals`, `noUnusedParameters`
- **Biome** for formatting + linting (single tool, like ruff for Python)
- **Zustand** for state management, **TanStack Query** for server state
- **CSS Modules** for component styles (`.module.css`)
- **Custom hooks** in `src/hooks/` for data fetching and WebSocket state
- **Tab-based layout** — each tab is a self-contained page component in `src/tabs/`
- Builds to `supervisor/static/` — served by FastAPI at `/`

### General
- Keep reflexes deterministic and local to MCUs
- Planner / AI features are optional and network-remote
- Safety-critical code lives in the MCU; supervisor applies additional caps
- Prefer simple, direct code over abstractions

## Safety (defense in depth)

The Reflex MCU enforces acceleration limits, command TTL, and hard stop independently. The supervisor then applies these layers in order — any one can zero the twist:

1. Mode gate — no motion outside TELEOP/WANDER
2. Fault gate — any active fault → zero twist
3. Reflex disconnect → zero twist
4. Ultrasonic range scaling — hard stop at 250 mm, 50% at 500 mm
5. Stale range fallback — 50% cap if range telemetry is stale
6. Vision confidence scaling
7. Stale vision timeout — 500 ms

## Serial Protocol

Binary packets over USB serial with COBS framing:

```
[type:u8][seq:u8][payload:N][crc16:u16-LE]
```

Little-endian, fixed-size payloads per message type. Auto-reconnect with exponential backoff (0.5s–5s). The face link carries face state/gesture/system/talking commands and touch/button/status telemetry only — audio is supervisor-side USB audio, not serial. See `docs/protocols.md` for packet definitions.

## Testing

- Python tests: `supervisor/tests/`, `server/tests/`
- Dashboard tests: `dashboard/src/**/*.test.{ts,tsx}` (Vitest + Testing Library)
- Use `pytest-asyncio` for async tests
- Mock Reflex MCU (`supervisor/mock/mock_reflex.py`) — PTY-based fake serial
- Run `just preflight` before submitting changes (lint + tests + parity)

## Skills

Claude Code skills are in `.claude/skills/`. Key ones:
- `/test`, `/lint`, `/preflight` — quality checks
- `/flash`, `/deploy` — hardware/deployment (manual-only)
- `/protocol`, `/calibrate`, `/architecture` — reference material
- `/debug`, `/review` — diagnostics and code review

## TODOs

See `docs/TODO.md` — the single source of implementation truth. All task tracking, priority ordering, parallel tracks, and R&D planning lives there.
