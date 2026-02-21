# CLAUDE.md — Robot Buddy

## Project Overview

Robot Buddy is a kid-safe, expressive robot platform combining real-time motor control, an animated LED face, and optional networked AI planner. The architecture separates deterministic reflexes (ESP32 MCUs) from high-level orchestration (Raspberry Pi 5 supervisor).

## Repository Structure

```
robot-buddy/
├── supervisor/          # Python supervisor (Raspberry Pi 5)
│   ├── supervisor/      # Main package
│   ├── tests/           # pytest test suite
│   └── pyproject.toml
├── supervisor_v2/       # Supervisor v2 (process-isolated workers)
│   ├── supervisor_v2/
│   ├── tests/
│   └── pyproject.toml
├── esp32-face-v2/       # Face MCU firmware (ESP32-S3, C/C++)
│   └── main/            # ILI9341 display, LVGL, touch, LED
├── esp32-reflex/        # Motion MCU firmware (ESP32-S3, C/C++)
│   └── main/            # Differential drive, PID, safety, encoders
├── server/              # Planner server (LLM/STT/TTS on 3090 Ti)
│   ├── app/
│   └── tests/
├── dashboard/           # React dashboard (Vite + TypeScript + Biome)
│   ├── src/             # Components, hooks, stores, tabs
│   └── biome.json       # Lint + format config
├── deploy/              # Deployment (systemd, install/update scripts)
├── tools/               # Dev utilities (face simulation via pygame)
└── docs/                # Architecture, protocol specs, power topology
```

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
just test-all              # run all tests (supervisor, server, sv2, dashboard)
just test-supervisor       # supervisor tests only
just test-server           # server tests only
just test-dashboard        # dashboard tests only (Vitest)
just lint                  # check Python + C++ + dashboard
just lint-fix              # auto-fix everything
just lint-dashboard        # check dashboard only (biome + tsc)
just preflight             # full pre-commit check (lint + tests)
just run-mock              # run supervisor with mock hardware
just run-server            # run planner server
just run-dashboard         # run dashboard dev server (Vite)
just build-dashboard       # build dashboard → supervisor_v2/static/
just build-reflex          # build reflex firmware (needs ESP-IDF env)
just flash-reflex          # build + flash reflex
just deploy-v2             # update + restart on Pi
```

## Code Conventions

### Python
- **Type hints everywhere** — `from __future__ import annotations`
- **Dataclasses with `slots=True`** for data types
- **Module-level loggers:** `log = logging.getLogger(__name__)`
- **Async-first** — core runtime and transport are async (asyncio)
- **Enums** for commands, telemetry types, modes, faults
- **No JSON on the wire** to MCUs — binary struct packing only

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
- Builds to `supervisor_v2/static/` — served by FastAPI at `/`

### General
- Keep reflexes deterministic and local to MCUs
- Planner / AI features are optional and network-remote
- Safety-critical code lives in the MCU; supervisor applies additional caps
- Prefer simple, direct code over abstractions

## Testing

- Python tests: `supervisor/tests/`, `server/tests/`, `supervisor_v2/tests/`
- Dashboard tests: `dashboard/src/**/*.test.{ts,tsx}` (Vitest + Testing Library)
- Use `pytest-asyncio` for async tests
- Mock Reflex MCU (`supervisor/mock/mock_reflex.py`) — PTY-based fake serial
- Run the full test suite before submitting changes

## Skills

Claude Code skills are in `.claude/skills/`. Key ones:
- `/test`, `/lint`, `/preflight` — quality checks
- `/flash`, `/deploy` — hardware/deployment (manual-only)
- `/protocol`, `/calibrate`, `/architecture` — reference material
- `/debug`, `/review` — diagnostics and code review

## TODOs

See `docs/TODO.md` for the active backlog and the timestamps/telemetry design spec.
