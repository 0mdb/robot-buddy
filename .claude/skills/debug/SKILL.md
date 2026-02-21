---
name: debug
description: Structured debugging for robot issues. Use when diagnosing faults, communication problems, stale data, unexpected behavior, or investigating logs.
argument-hint: "[serial|vision|planner|state|audio|face]"
allowed-tools: Bash(journalctl:*), Bash(systemctl:*), Bash(ls:*), Bash(tail:*), Bash(python:*), Read, Grep, Glob
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
- Service logs: `journalctl -u robot-buddy-supervisor -n 100 --no-pager`
- Grep for serial errors: `serial_transport`, `CRC`, `COBS`, `reconnect`
- Check USB devices: `ls -la /dev/ttyACM* /dev/robot_*`
- Check transport config: `supervisor/supervisor/io/serial_transport.py` (backoff, timeouts)

**Key files:**
- `supervisor/supervisor/io/serial_transport.py` — async transport, auto-reconnect (0.5–5s backoff)
- `supervisor/supervisor/io/cobs.py` — COBS framing
- `supervisor/supervisor/io/crc.py` — CRC16 validation

**Common issues:**
- USB cable disconnected → auto-reconnect triggers, check logs for pattern
- Wrong serial port → check `/dev/robot_reflex`, `/dev/robot_face` udev symlinks
- CRC mismatches → firmware/supervisor protocol version mismatch

## Subsystem: vision (camera + detection)

**Symptoms:** stale vision, no ball detection, wrong confidence, speed capping

**Check:**
- Vision process alive: look for `VisionProcess` in logs
- Stale vision timeout: >500ms triggers 50% speed cap (policy layer)
- Detection thresholds: HSV bounds in `supervisor/supervisor/inputs/vision_worker.py`
- Camera accessible: `deploy/probe_camera.sh`

**Key files:**
- `supervisor/supervisor/inputs/vision_worker.py` — child process, picamera2, OpenCV pipeline
- `supervisor/supervisor/inputs/camera_vision.py` — parent process queue interface
- `supervisor/supervisor/inputs/detectors.py` — ball + floor detection algorithms

**Common issues:**
- Camera not found → `probe_camera.sh`, check `video` group membership
- Vision always stale → vision process crashed, check multiprocessing queue
- Ball never detected → HSV thresholds wrong for lighting, check `ball_hsv_low/high`

## Subsystem: planner (LLM action planning)

**Symptoms:** no planner actions, stale plans, repeated actions, speech not firing

**Check:**
- Planner connectivity: `GET /health` on planner server
- Plan request/response cycle in logs: `planner`, `scheduler`, `validator`
- Cooldown state: actions may be suppressed by type/key cooldowns
- Plan ordering: out-of-sequence plans are dropped

**Key files:**
- `supervisor/supervisor/devices/planner_client.py` — HTTP client to planner server
- `supervisor/supervisor/planner/scheduler.py` — cooldowns, action queue
- `supervisor/supervisor/planner/validator.py` — action validation (allowed skills, field bounds)
- `supervisor/supervisor/planner/event_bus.py` — edge-detection events from telemetry
- `supervisor/supervisor/planner/speech_policy.py` — event-triggered deterministic speech
- `supervisor/supervisor/planner/skill_executor.py` — skill → DesiredTwist

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
- State transitions in logs: grep `supervisor_sm`, `mode`, `ERROR`, `IDLE`

**Key files:**
- `supervisor/supervisor/state/supervisor_sm.py` — BOOT→IDLE→TELEOP/WANDER→ERROR
- `supervisor/supervisor/state/policies.py` — 7-layer safety policy stack

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
- Conversation WebSocket: logs for `conversation_manager`, `converse`
- Planner speech queue: `audio_orchestrator` logs

**Key files:**
- `supervisor/supervisor/devices/conversation_manager.py` — WebSocket to `/converse`
- `supervisor/supervisor/devices/audio_orchestrator.py` — arbitrates planner speech vs PTT
- `supervisor/supervisor/devices/lip_sync.py` — RMS energy → face talking animation

**Common issues:**
- TTS from planner cuts off → `audio_orchestrator` cancels on PTT activation
- Face stops talking before audio → lip sync tracker decay too fast (attack=0.55, release=0.25)
- No audio output → check `--usb-speaker-device` flag, ALSA device name

## Subsystem: face (display MCU)

**Symptoms:** wrong expression, gestures not playing, system overlay stuck

**Check:**
- Face connection: `GET /debug/devices` from HTTP API
- Face telemetry: FACE_STATUS packets in logs
- Button/touch events: BUTTON_EVENT, TOUCH_EVENT

**Key files:**
- `supervisor/supervisor/devices/expressions.py` — emotion/gesture name mapping
- `esp32-face-v2/main/face_state.cpp` — face animation state machine
- `esp32-face-v2/main/face_ui.cpp` — LVGL rendering
- `esp32-face-v2/main/protocol.h` — mood IDs, gesture IDs, system modes, flags

**Common issues:**
- Gesture not visible → queued behind another, check FIFO
- Wrong mood → emotion alias mapping in expressions.py
- System overlay stuck → SET_SYSTEM mode not cleared to NONE
