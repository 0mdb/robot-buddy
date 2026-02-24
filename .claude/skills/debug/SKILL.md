---
name: debug
description: Structured debugging for robot issues. Use when diagnosing faults, communication problems, stale data, unexpected behavior, or investigating logs.
---

Structured debugging. Parse `$ARGUMENTS` for the subsystem to investigate.

## General approach

1. Gather symptoms — ask the user what they observed.
2. Check the relevant subsystem (below).
3. Trace causality — timestamps, sequence numbers, state transitions.
4. Report root cause and suggest fix.

## Subsystem: serial (Reflex/Face MCU communication)

**Symptoms:** MCU disconnect, stale telemetry, CRC errors, dropped packets

**Check:**
- Service logs: `journalctl -u robot-buddy-supervisor-v2 -n 100 --no-pager`
- Grep for serial errors: `serial_transport`, `CRC`, `COBS`, `reconnect`
- Check USB devices: `ls -la /dev/ttyACM* /dev/robot_*`
- Check transport config: `supervisor/io/serial_transport.py` (backoff, timeouts)

**Key files:**
- `supervisor/io/serial_transport.py` — async transport, auto-reconnect (0.5–5s backoff)
- `supervisor/io/cobs.py` — COBS framing
- `supervisor/io/crc.py` — CRC16 validation

**Common issues:**
- USB cable disconnected → auto-reconnect triggers, check logs for pattern
- Wrong serial port → check `/dev/robot_reflex`, `/dev/robot_face` udev symlinks
- CRC mismatches → firmware/supervisor protocol version mismatch

## Subsystem: vision (camera + detection)

**Symptoms:** stale vision, no ball detection, wrong confidence, speed capping

**Check:**
- Vision worker alive: look for `vision_worker` in logs
- Stale vision timeout: >500ms triggers 50% speed cap (policy layer)
- Detection thresholds: HSV bounds in `supervisor/workers/vision_worker.py`
- Camera accessible: `deploy/probe_camera.sh`

**Key files:**
- `supervisor/workers/vision_worker.py` — vision worker process, picamera2, OpenCV pipeline

**Common issues:**
- Camera not found → `probe_camera.sh`, check `video` group membership
- Vision always stale → vision worker crashed, check worker manager logs
- Ball never detected → HSV thresholds wrong for lighting, check `ball_hsv_low/high`

## Subsystem: planner (LLM action planning)

**Symptoms:** no planner actions, stale plans, repeated actions, speech not firing

**Check:**
- Planner connectivity: `GET /health` on planner server
- Plan request/response cycle in logs: `planner`, `scheduler`, `validator`
- Cooldown state: actions may be suppressed by type/key cooldowns
- Plan ordering: out-of-sequence plans are dropped

**Key files:**
- `supervisor/workers/ai_worker.py` — AI worker process, HTTP client to planner server
- `supervisor/core/behavior_engine.py` — priority arbitration, action scheduling
- `supervisor/core/event_bus.py` — edge-detection events from telemetry
- `supervisor/core/speech_policy.py` — event-triggered deterministic speech
- `supervisor/core/skill_executor.py` — skill → DesiredTwist

**Common issues:**
- Planner server unreachable → check `--planner-api` flag, network
- Actions validated out → check validator allowed skills/actions
- Repeated speech → cooldown too short, or phrase cycling exhausted
- Skill not executing → scheduler may have dropped it (stale TTL, cooldown)

## Subsystem: state (state machine + safety)

**Symptoms:** stuck in ERROR/BOOT, unexpected mode transitions, motion disabled

**Check:**
- Current state: `GET /status` from HTTP API
- Fault flags: `fault_flags` in telemetry (bitfield)
- State transitions in logs: grep `state_machine`, `mode`, `ERROR`, `IDLE`

**Key files:**
- `supervisor/core/state_machine.py` — BOOT→IDLE→TELEOP/WANDER→ERROR
- `supervisor/core/safety.py` — 7-layer safety policy stack

**Fault flag bits (Reflex):**
| Bit | Fault | Triggers ERROR? |
|-----|-------|-----------------|
| 0 | CMD_TIMEOUT | No |
| 1 | ESTOP | Yes |
| 2 | TILT | Yes |
| 3 | STALL | No |
| 4 | IMU_FAIL | No |
| 5 | BROWNOUT | Yes |
| 6 | OBSTACLE | No (speed cap only) |

**Common issues:**
- Stuck in BOOT → Reflex MCU not connected or has faults on startup
- Stuck in ERROR → need `clear_error()` + Reflex healthy; check which fault
- No motion in TELEOP → safety policy capping to zero (check range, vision, faults)

## Subsystem: audio (TTS, conversation, lip sync)

**Symptoms:** no speech, TTS cutoff, lip sync out of sync, PTT not working

**Check:**
- Audio devices: `aplay -l`, `arecord -l`
- TTS worker logs: grep for `tts_worker`, `converse`
- AI worker logs: grep for `ai_worker`, speech queue

**Key files:**
- `supervisor/workers/tts_worker.py` — TTS playback, lip sync, conversation audio
- `supervisor/workers/ai_worker.py` — conversation management, planner speech requests

**Common issues:**
- TTS from planner cuts off → conversation activation cancels planner speech
- Face stops talking before audio → lip sync tracker decay too fast (attack=0.55, release=0.25)
- No audio output → check `--usb-speaker-device` flag, ALSA device name

## Subsystem: personality (affect engine + guardrails)

**Symptoms:** wrong mood, stuck emotion, conversation blocked, time limit issues

**Check:**
- Worker alive: `personality` in worker_alive telemetry
- Personality health in logs: grep `personality_worker`, `guardrail`, `session_time`, `daily`
- Current guardrail state: `personality_session_limit_reached`, `personality_daily_limit_reached` in telemetry
- Daily timer persistence: `./data/daily_usage.json`

**Key files:**
- `supervisor/workers/personality_worker.py` — L0 affect engine, guardrail enforcement, timers
- `supervisor/personality/affect.py` — affect math, mood projection, context gate
- `supervisor/config.py` — GuardrailConfig (session/daily limits, toggleable caps)

**Common issues:**
- Conversation blocked → daily limit reached; check `personality_daily_limit_reached` in telemetry; reset via `personality.cmd.set_guardrail` with `reset_daily: true`
- Mood stuck negative → check if context gate or duration caps are disabled
- Personality worker not updating → check `personality_snapshot_ts_ms` age; if stale (>3000ms), worker may have crashed
- Session ended unexpectedly → RS-1 session limit (900s default) triggered; check logs for "RS-1 session time limit reached"

## Subsystem: face (display MCU)

**Symptoms:** wrong expression, gestures not playing, system overlay stuck

**Check:**
- Face connection: `GET /debug/devices` from HTTP API
- Face telemetry: FACE_STATUS packets in logs
- Button/touch events: BUTTON_EVENT, TOUCH_EVENT

**Key files:**
- `supervisor/devices/expressions.py` — emotion/gesture name mapping
- `esp32-face/main/face_state.cpp` — face animation state machine
- `esp32-face/main/face_ui.cpp` — LVGL rendering
- `esp32-face/main/protocol.h` — mood IDs, gesture IDs, system modes, flags

**Common issues:**
- Gesture not visible → queued behind another, check FIFO
- Wrong mood → emotion alias mapping in expressions.py
- System overlay stuck → SET_SYSTEM mode not cleared to NONE
