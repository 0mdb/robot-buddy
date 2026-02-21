---
name: review
description: Review code for quality, safety, and adherence to project conventions. Use when the user asks for a code review, or before committing significant changes.
argument-hint: "[file or directory]"
allowed-tools: Read, Grep, Glob
---

Review code against robot-buddy project conventions. If `$ARGUMENTS` specifies a file or directory, focus there. Otherwise, review recently changed files (`git diff`).

## What to check

### Python conventions

1. **Type hints everywhere** — `from __future__ import annotations` at top of every module
2. **Dataclasses with `slots=True`** for all data types
3. **Module-level loggers** — `log = logging.getLogger(__name__)`
4. **Async-first** — core runtime and transport must be async (asyncio)
5. **Config via dataclasses** with YAML loading and sensible defaults
6. **Enums** for commands, telemetry types, modes, faults
7. **No JSON on the wire to MCUs** — binary struct packing only
8. **`from __future__ import annotations`** at top of file

### C/C++ conventions (ESP32)

1. **Header-based modules** (`pin_map.h`, `config.h`, `shared_state.h`)
2. **FreeRTOS tasks** for control loop, serial RX, safety, telemetry
3. **Fixed-size binary packets**, little-endian
4. **Tunable parameters** via `config.h` enums + `SET_CONFIG` protocol
5. **Single-writer shared state** — double-buffering or seqlocks, never mutexes in hot paths
6. **`static const char* TAG`** for ESP_LOG macros
7. **`ESP_ERROR_CHECK()`** for all ESP-IDF API calls that can fail

### Safety rules

1. **Safety-critical code lives in the MCU** — supervisor only applies additional caps
2. **Defense-in-depth** — mode gate, fault gate, range scaling, vision scaling, stale timeout
3. **No motion outside TELEOP/WANDER** — mode gate must be enforced
4. **Fault flags zero twist** — any active fault → zero output
5. **Stale data → conservative cap** — never assume fresh data on timeout
6. **Planner output is untrusted** — validator must check all fields and bounds

### Architecture rules

1. **Reflexes deterministic and local to MCUs** — no network dependency for safety
2. **Planner / AI features optional and network-remote**
3. **Prefer simple, direct code over abstractions**
4. **Lock-free inter-task communication** on MCUs (double-buffer, seqlock)
5. **Vision in separate OS process** — avoids GIL, uses multiprocessing queue

### Protocol rules

1. **Matching enums** — MCU protocol.h must match supervisor protocol.py
2. **CRC16 on all packets** — no unvalidated data
3. **COBS framing** — 0x00 delimiter, proper encode/decode
4. **Sequence numbers** — detect drops and ordering issues

## Output format

Report findings grouped by severity:

- **Critical** — safety violations, data races, protocol mismatches
- **Warning** — convention violations, missing type hints, no slots
- **Note** — style suggestions, minor improvements

For each finding, reference the specific file and line number.
