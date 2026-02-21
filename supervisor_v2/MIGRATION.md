# Supervisor V2 Migration Plan

> **Note:** V1 has been removed from the repository. This document is retained
> as architectural context for the v2 design decisions.

## Context

The current supervisor (`supervisor/supervisor/`) is a single-process, tightly-coupled architecture where `runtime.py` (728 lines) orchestrates everything inline: MCU I/O, vision polling, planner lifecycle, audio/speech, face commands, and safety policies — all in one 350-line `_tick()` method. This works but creates jitter risk (audio/camera/LLM can stall the control loop), makes fault isolation impossible (a bad TTS lib can freeze the robot), and blocks the GIL across all subsystems.

The v2 architecture separates concerns into a **Core process** (safety, timing, MCU I/O, arbitration) and **Worker processes** (TTS/audio, vision, AI planning) connected via NDJSON over stdin/stdout. This gives us process isolation, real parallelism, crash containment, and a clean seam for a future Rust core.

---

## Decision: New Package

Build `supervisor_v2/` as a sibling to `supervisor/`. The coupling in `runtime.py` is too deep to refactor incrementally — face_client calls are scattered across audio_orchestrator, conversation_manager, and runtime; planner lifecycle spans 6 methods with shared mutable state; audio PTT is callback-wired through face button events. A clean build lets us copy the good pieces verbatim and restructure the wiring.

v1 stays runnable throughout for rollback.

---

## Package Structure

```
supervisor_v2/
├── __init__.py
├── __main__.py
├── main.py                     # Entry point, CLI, launches core
├── config.py                   # YAML config (adapted from v1)
│
├── messages/                   # Shared types (Core + Workers import these)
│   ├── __init__.py
│   ├── envelope.py             # Envelope dataclass + NDJSON codec (inline fields on wire, see PROTOCOL.md §1.8)
│   ├── events.py               # Event type constants + payload schemas
│   └── actions.py              # Action type constants + payload schemas
│
├── core/                       # Core process modules
│   ├── __init__.py
│   ├── tick_loop.py            # 50 Hz loop: drain events → state → safety → emit actions
│   ├── state.py                # RobotState (MCU hw) + WorldState (perception from workers)
│   ├── state_machine.py        # COPY from v1 state/supervisor_sm.py
│   ├── safety.py               # COPY from v1 state/policies.py (add WorldState param)
│   ├── event_router.py         # Routes worker events → WorldState updates
│   ├── behavior_engine.py      # Priority arbitration: safety > conversation > planner > patrol
│   ├── action_scheduler.py     # COPY scheduler + validator logic from v1 planner/
│   ├── worker_manager.py       # Launch, heartbeat monitor, restart workers
│   ├── event_bus.py            # COPY from v1 planner/event_bus.py
│   ├── skill_executor.py       # COPY from v1 planner/skill_executor.py
│   └── speech_policy.py        # COPY from v1 planner/speech_policy.py
│
├── devices/                    # MCU I/O (Core process only)
│   ├── __init__.py
│   ├── protocol.py             # VERBATIM from v1
│   ├── reflex_client.py        # VERBATIM from v1
│   ├── face_client.py          # VERBATIM from v1
│   └── expressions.py          # VERBATIM from v1
│
├── io/                         # Serial transport (Core process only)
│   ├── __init__.py
│   ├── serial_transport.py     # VERBATIM from v1
│   ├── cobs.py                 # VERBATIM from v1
│   └── crc.py                  # VERBATIM from v1
│
├── workers/                    # Worker process implementations
│   ├── __init__.py
│   ├── base.py                 # BaseWorker: NDJSON stdin/stdout loop, heartbeat
│   ├── tts_worker.py           # TTS + audio playback + lip sync (pure audio I/O)
│   ├── vision_worker.py        # Camera capture + detection
│   └── ai_worker.py            # LLM plan requests + conversation orchestration
│
├── api/                        # HTTP/WS server (Core process)
│   ├── __init__.py
│   ├── http_server.py          # ADAPT from v1 (new state structure)
│   ├── param_registry.py       # VERBATIM from v1
│   └── ws_hub.py               # VERBATIM from v1
│
└── mock/
    ├── mock_reflex.py          # VERBATIM from v1
    └── mock_worker.py          # Mock worker for testing
```

---

## Message Schema

### Envelope (all messages)

Wire format: one JSON line per message, newline-terminated (`\n`). Payload fields are inline (not nested in a `payload` object). See PROTOCOL.md §1.8 and §3.1 for the canonical schema.

```json
{"v": 2, "type": "domain.entity.verb", "src": "source_id", "seq": 12345, "t_ns": 0, ...payload fields inline...}
```

### Events (Worker → Core)

All type names use canonical taxonomy (`domain.entity.verb`). See PROTOCOL.md §4 for complete definitions.

| Type | Source | Payload |
|------|--------|---------|
| `vision.detection.snapshot` | vision | `clear_confidence, ball_confidence, ball_bearing_deg, frame_seq, fps` |
| `tts.event.started` | tts | `ref_seq, text` |
| `tts.event.energy` | tts | `energy` (0-255 for lip sync) |
| `tts.event.finished` | tts | `ref_seq, duration_ms, chunks_played` |
| `tts.event.error` | tts | `error` |
| `tts.event.mic_dropped` | tts | `count` (frames dropped due to backpressure) |
| `ai.plan.received` | ai | `plan_id, plan_seq, actions, ttl_ms` (raw from server; Core validates) |
| `ai.conversation.emotion` | ai | `session_id, turn_id, emotion, intensity` |
| `ai.conversation.gesture` | ai | `session_id, turn_id, names` |
| `ai.conversation.transcription` | ai | `session_id, turn_id, text` |
| `ai.conversation.done` | ai | `session_id, turn_id` |
| `ai.state.changed` | ai | `state, prev_state, session_id, turn_id, reason` |
| `ai.status.health` | ai | `connected, state, session_id` |

### Actions (Core → Worker)

| Type | Target | Payload |
|------|--------|---------|
| `tts.config.init` | tts | `audio_mode, mic_socket_path, spk_socket_path, speaker_device, mic_device, tts_endpoint` |
| `tts.cmd.speak` | tts | `text, emotion, source, priority` |
| `tts.cmd.cancel` | tts | (empty) |
| `tts.cmd.start_mic` | tts | (empty — begin arecord capture) |
| `tts.cmd.stop_mic` | tts | (empty — stop capture) |
| `vision.config.update` | vision | `floor_hsv_low/high, ball_hsv_low/high, min_ball_radius` |
| `ai.config.init` | ai | `audio_mode, mic_socket_path, spk_socket_path, server_base_url, robot_id` |
| `ai.cmd.request_plan` | ai | `world_state` |
| `ai.cmd.start_conversation` | ai | `session_id, turn_id` |
| `ai.cmd.end_utterance` | ai | `session_id, turn_id` |
| `ai.cmd.end_conversation` | ai | `session_id` |
| `ai.cmd.cancel` | ai | (empty) |

### Critical Design Rules

1. **Only Core sends commands to MCUs.** Workers never touch face_client or reflex_client. When TTS worker reports `speech_chunk` with `energy_rms`, Core translates that into `face.send_talking(True, energy)`. This eliminates the v1 coupling where audio_orchestrator and conversation_manager both held face_client references.

2. **Core is the control plane, not the data plane.** Raw audio streams directly between TTS and AI workers via a dedicated unix domain socket (see PROTOCOL.md §6.6). Core sends control signals (start/stop mic, start/cancel conversation) and receives semantic events (energy, transcript, emotion, gesture). Core never forwards raw audio bytes in production (Mode A).

---

## Core Tick Loop (replaces runtime.py)

```
Each tick at 50 Hz:
  1. Drain worker events (non-blocking from worker_manager)
     → event_router updates WorldState (vision, audio, planner fields)
     → ai plans go through validator → scheduler

  2. Read MCU telemetry (same as v1)
     → reflex telemetry → RobotState
     → face telemetry → RobotState

  3. Edge detection (event_bus.ingest)

  4. State machine update (BOOT/IDLE/TELEOP/WANDER/ERROR)

  5. Behavior engine: pick twist source
     → TELEOP: use teleop_twist
     → WANDER: skill_executor.step()
     → else: zero

  6. Safety policies (7-layer, same as v1)

  7. Emit outputs:
     → reflex MCU: send_twist
     → face MCU: send_state, send_gesture, send_talking, send_system_mode
     → workers: tts.cmd.speak (from speech_policy or scheduler)

  8. Broadcast telemetry at 20 Hz
```

Key simplification vs v1: the planner HTTP transport moves into ai_worker. But Core retains authority — plan acceptance (dedup, seq ordering, TTL enforcement via `t_plan_rx_ns`, validation, scheduling) stays in `event_router` + `action_scheduler`. AI worker handles transport hygiene (HTTP retry/backoff, connection health); Core decides what to accept and execute.

---

## State Split

**RobotState** (MCU hardware, updated synchronously each tick):
- `mode`, `twist_cmd`, `twist_capped`, `speed_caps`
- Reflex: `speed_l/r_mm_s`, `gyro_z_mrad_s`, `battery_mv`, `fault_flags`, `range_mm`, `range_status`, `reflex_connected`
- Face: `face_mood`, `face_gesture`, `face_system_mode`, `face_touch_active`, `face_talking`, `face_listening`, `face_connected`, button state
- Timing: `tick_mono_ms`, `tick_dt_ms`

**WorldState** (perception from workers, updated asynchronously from events):
- Vision: `clear_confidence`, `ball_confidence`, `ball_bearing_deg`, `fps`, `rx_mono_ms`
- Audio: `speaking`, `current_energy`, `ptt_active`, `speech_queue_depth`
- Planner: `connected`, `active_skill`, `last_plan_mono_ms`, drop counters
- Worker health: `last_heartbeat_ms` per worker

Safety policies receive both: `apply_safety(twist, robot_state, world_state)`.

---

## Worker Manager

- Launches workers via `asyncio.create_subprocess_exec(sys.executable, "-m", module, ...)`
- stdin/stdout are NDJSON pipes; stderr goes to Core's log
- Background task reads stdout lines, parses envelopes, queues for event_router
- Heartbeat monitor: each worker emits heartbeat every 1s; timeout at 5s triggers kill+restart
- Max restarts with backoff (5 attempts, 1s → 5s)
- On worker crash: Core zeroes relevant WorldState fields (e.g., vision goes stale → safety cap kicks in automatically)
- **Audio socket setup**: Creates two unix domain sockets at startup (`/tmp/rb-mic-<pid>.sock` for mic, `/tmp/rb-spk-<pid>.sock` for speaker), passes both paths to TTS and AI workers via their init config messages. Cleans up socket files on shutdown. See PROTOCOL.md §6.6 for wire format.

---

## Workers

### tts_worker (pure audio I/O)

Absorbs: `audio_orchestrator.py`, `lip_sync.py`

- Receives `tts.config.init` with `audio_mode`, `mic_socket_path`, and `spk_socket_path` (see PROTOCOL.md §6.6)
- Receives `tts.cmd.speak` → calls planner server `/tts`, streams audio via `aplay`, reports energy chunks
- Receives `tts.cmd.cancel` → kills playback, clears queue
- Receives `tts.cmd.start_mic` / `tts.cmd.stop_mic` → starts/stops `arecord`
- **Mode A (direct):** Mic PCM written to `rb-mic` socket; conversation TTS PCM read from `rb-spk` socket and played via aplay. Mic capture loop never blocks — uses bounded 200ms ring buffer, drops oldest frames and emits `tts.event.mic_dropped` on backpressure.
- **Mode B (relay):** Mic PCM emitted as NDJSON events through Core; conversation TTS PCM received as NDJSON actions from Core
- **Never calls face_client** — reports energy, Core sends face commands
- **Does not own conversation logic** — pure audio transport

### vision_worker

Absorbs: `inputs/vision_worker.py`, `inputs/camera_vision.py`

- Reuses `detectors.py` detection logic verbatim
- Camera capture → HSV detection → emits `vision.detection.snapshot`
- Receives `vision.config.update` for HSV threshold updates
- Switch from multiprocessing.Queue to NDJSON stdin/stdout

### ai_worker (conversation brain + planner transport)

Absorbs: `planner_client.py`, `conversation_manager.py`

- Receives `ai.config.init` with `audio_mode`, `mic_socket_path`, `spk_socket_path`, and `server_base_url` (see PROTOCOL.md §6.6)
- **Plan requests**: Receives `ai.cmd.request_plan` with world_state dict, HTTP to `/plan`
- **Transport hygiene**: Handles HTTP retry/backoff, connection health. Does NOT do plan dedup/ordering/validation — that stays in Core (Core is authoritative for plan acceptance)
- Emits `ai.plan.received` (raw from server) or `ai.lifecycle.error`
- **Conversation orchestration**: Owns the WebSocket to planner server `/converse`
  - Receives `ai.cmd.start_conversation` (with `session_id`, `turn_id`) / `ai.cmd.end_conversation` from Core
  - **Mode A (direct):** Reads mic PCM from `rb-mic` socket, forwards to server WS; reads TTS PCM from server WS, writes to `rb-spk` socket
  - **Mode B (relay):** Receives mic PCM as NDJSON actions from Core; emits TTS PCM as NDJSON events through Core
  - Emits `ai.conversation.emotion` (emotion → Core sends to face MCU)
  - Emits `ai.conversation.gesture` (gesture → Core sends to face MCU)
  - Emits `ai.conversation.transcription` (for telemetry/logging)
  - Echoes Core-provided `session_id` and `turn_id` on all conversation events

---

## Conversation Flow (PTT — Mode A, Direct Audio Sockets)

```
Face button press → Core detects PTT toggle
  → Core sends tts.cmd.start_mic to tts_worker (control plane)
  → Core sends ai.cmd.start_conversation{session_id, turn_id=1} to ai_worker

  ┌─ AUDIO DATA PLANE (two unix sockets, bypass Core) ─────────────┐
  │ tts_worker: starts arecord, writes mic PCM to rb-mic socket     │
  │ ai_worker: reads mic PCM from rb-mic socket                     │
  │ ai_worker: forwards to server via WebSocket                     │
  │                                                                 │
  │ ai_worker: receives TTS audio from server                       │
  │ ai_worker: writes TTS PCM to rb-spk socket                      │
  │ tts_worker: reads TTS PCM from rb-spk socket, plays via aplay   │
  └─────────────────────────────────────────────────────────────────┘

  → ai_worker: emits ai.conversation.emotion{session_id, turn_id} (semantic → Core)
  → Core: sends emotion/gesture to face MCU
  → tts_worker: emits tts.event.energy (semantic → Core)
  → Core: translates energy to face.cmd.set_talking()
```

AI worker is the conversation brain. TTS worker is pure audio I/O. Core owns `session_id` and `turn_id`, is the control plane (start/stop/cancel), and receives semantic events (emotion, energy, transcript) — it never touches raw audio bytes. See PROTOCOL.md §6.6 for the audio socket wire format.

---

## Files: Verbatim Copy vs Rewrite

### Verbatim copy (no changes needed)

| v1 Source | v2 Destination |
|-----------|----------------|
| `supervisor/io/cobs.py` | `supervisor_v2/io/cobs.py` |
| `supervisor/io/crc.py` | `supervisor_v2/io/crc.py` |
| `supervisor/io/serial_transport.py` | `supervisor_v2/io/serial_transport.py` |
| `supervisor/devices/protocol.py` | `supervisor_v2/devices/protocol.py` |
| `supervisor/devices/reflex_client.py` | `supervisor_v2/devices/reflex_client.py` |
| `supervisor/devices/face_client.py` | `supervisor_v2/devices/face_client.py` |
| `supervisor/devices/expressions.py` | `supervisor_v2/devices/expressions.py` |
| `supervisor/state/supervisor_sm.py` | `supervisor_v2/core/state_machine.py` |
| `supervisor/planner/skill_executor.py` | `supervisor_v2/core/skill_executor.py` |
| `supervisor/planner/speech_policy.py` | `supervisor_v2/core/speech_policy.py` |
| `supervisor/api/param_registry.py` | `supervisor_v2/api/param_registry.py` |
| `supervisor/api/ws_hub.py` | `supervisor_v2/api/ws_hub.py` |
| `supervisor/mock/mock_reflex.py` | `supervisor_v2/mock/mock_reflex.py` |
| `supervisor/inputs/detectors.py` | used inside `supervisor_v2/workers/vision_worker.py` |

### Minor adaptation needed

| v1 Source | v2 Destination | Change |
|-----------|----------------|--------|
| `supervisor/state/policies.py` | `core/safety.py` | Add `world_state` param for vision staleness |
| `supervisor/planner/event_bus.py` | `core/event_bus.py` | Accept split RobotState + WorldState |
| `supervisor/planner/scheduler.py` + `validator.py` | `core/action_scheduler.py` | Combine into one module |
| `supervisor/api/http_server.py` | `api/http_server.py` | New state structure, worker debug endpoints |
| `supervisor/config.py` | `config.py` | Add worker config section |

### New code

| File | Purpose |
|------|---------|
| `messages/envelope.py` | Envelope dataclass + NDJSON codec |
| `messages/events.py` | Event type constants + payload schemas |
| `messages/actions.py` | Action type constants + payload schemas |
| `core/tick_loop.py` | Simplified control loop (~200 lines vs 350) |
| `core/state.py` | Split RobotState + WorldState definitions |
| `core/event_router.py` | Routes worker events → WorldState updates |
| `core/behavior_engine.py` | Priority-based twist source selection |
| `core/worker_manager.py` | Subprocess lifecycle + heartbeat monitoring |
| `workers/base.py` | BaseWorker NDJSON loop + heartbeat |
| `workers/tts_worker.py` | TTS/audio (from audio_orchestrator + lip_sync) |
| `workers/vision_worker.py` | Camera/detection (from inputs/vision_worker) |
| `workers/ai_worker.py` | Plans + conversation (from planner_client + conversation_manager) |
| `main.py` | New entry point with worker-based wiring |
| `mock/mock_worker.py` | Test helper for worker NDJSON protocol |

---

## Implementation Phases

### Phase 1: Scaffold + Messages
- Create package structure, `pyproject.toml`
- Implement `messages/` (Envelope, codec, event/action type constants)
- Implement `workers/base.py` (BaseWorker NDJSON loop + heartbeat)
- Copy all verbatim files into place
- Write unit tests for codec round-trip, base worker heartbeat
- **Testable:** `pytest supervisor_v2/tests/test_messages.py`

### Phase 2: Core Tick Loop + MCU I/O (robot can drive)
- Implement `core/state.py` (RobotState + WorldState split)
- Copy + adapt state_machine, safety policies, event_bus
- Implement `core/tick_loop.py`, `core/behavior_engine.py`
- Implement `core/worker_manager.py` (launch/monitor/restart)
- Implement `core/event_router.py`
- Implement `main.py` entry point
- **Testable:** `python -m supervisor_v2 --mock` — state machine transitions, safety, twist output

### Phase 3: Vision Worker
- Port vision_worker to use BaseWorker NDJSON
- Wire worker_manager to launch vision worker
- Wire event_router to update WorldState.vision from snapshots
- **Testable:** Vision snapshots flow through, safety vision-staleness policy works

### Phase 4: TTS Worker (pure audio I/O)
- Implement tts_worker: `tts.cmd.speak` → HTTP `/tts` → `aplay` → energy events; mic capture via `arecord` with bounded ring buffer (200ms, drop oldest on backpressure)
- Wire Core: speech_policy intents → `tts.cmd.speak`; `tts.event.energy` → `face.cmd.set_talking()`
- Copy speech_policy, action_scheduler (scheduler + validator)
- **Testable:** Deterministic speech works end-to-end, lip sync tracks energy, cancel works

### Phase 5: AI Worker + Planner + Conversation
- Implement ai_worker: plan requests (HTTP to `/plan`) + conversation orchestration (WebSocket to `/converse`)
- Wire Core: periodic `ai.cmd.request_plan`, route `ai.plan.received` through validator → scheduler
- Wire Core plan acceptance: dedup (plan_id), seq ordering, TTL enforcement via `t_plan_rx_ns`, validation — Core is authoritative
- Wire audio data plane: worker_manager creates two unix domain sockets (mic + spk), passes paths to TTS + AI workers via init config
- Wire PTT conversation flow: face button → Core sends control signals (start_mic, start_conversation with session_id + turn_id) → workers stream audio directly via sockets → Core receives semantic events (emotion, energy, transcript) → face commands
- Core owns turn_id: passed in `ai.cmd.start_conversation` and `ai.cmd.end_utterance`, AI echoes on all events
- Wire face button greet routine
- **Testable:** Plans flow through with correct ordering/dedup, actions execute. PTT conversation works end-to-end with direct audio streaming.

### Phase 6: API + Dashboard
- Adapt http_server for v2 state structure
- Add worker health debug endpoints
- Wire param changes to workers and MCUs
- Telemetry broadcast with combined RobotState + WorldState
- **Testable:** Dashboard shows all data, params work, MJPEG video works

### Phase 7: Cutover
- Run v2 on real hardware, verify behavior matches v1
- Update `deploy/` scripts and systemd service
- Keep v1 for rollback

---

## Verification

After each phase:
1. `ruff check supervisor_v2/ && ruff format --check supervisor_v2/`
2. `pytest supervisor_v2/tests/ -v`
3. For phases 2+: Run with `--mock` and verify via dashboard/WebSocket telemetry
4. For phase 7: Side-by-side comparison on real hardware

Key integration tests:
- Worker crash → Core detects stale heartbeat → restarts worker → robot stays safe (vision stale = speed cap)
- TTS energy events → face lip sync within 50ms
- Plan request → validate → schedule → execute → face/motion commands
- PTT button → audio capture → conversation → emotion/gesture response
