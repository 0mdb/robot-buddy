---
name: diagnose
description: Diagnose robot issues by querying live MCU telemetry via supervisor API. Use when debugging faults, communication problems, or unexpected behavior.
---

Structured diagnostic tool for robot issues. Detects connected MCUs, queries supervisor API, and analyzes telemetry.

## Argument parsing

- `reflex` → focus on reflex MCU diagnostics
- `face` → focus on face MCU diagnostics
- `comms` → focus on communication/protocol issues
- `frame-too-long` → diagnose frame timing issues
- No argument → full diagnostic sweep

## Step 1: Detect Hardware

Check what's connected:
```bash
ls -l /dev/serial/by-id 2>/dev/null || true
ls -l /dev/ttyACM* 2>/dev/null || true
ls -l /dev/robot_* 2>/dev/null || true
```

## Step 2: Check Supervisor Status

If supervisor is running (on Pi or locally):
```bash
curl -s http://localhost:8080/status 2>/dev/null | python3 -m json.tool || echo "Supervisor not reachable at localhost:8080"
curl -s http://localhost:8080/debug/devices 2>/dev/null | python3 -m json.tool || true
```

## Step 3: Analyze Telemetry

Key fields to check in `/status` response:
- `mode`: Current state (BOOT/IDLE/TELEOP/WANDER/ERROR)
- `faults`: Active fault flags
- `face_connected` / `reflex_connected`: Device connection state
- `rx_face_status_packets` / `rx_reflex_state_packets`: Packet counters (should be increasing)
- `face_conv_state`: Current conversation state
- `face_system_mode`: System overlay state (0=NONE, should be 0 in normal operation)

## Step 3b: Personality / Time Limits

Key personality fields in telemetry:
- `personality_mood`: Current PE-projected mood
- `personality_session_time_s`: Current session conversation time
- `personality_session_limit_reached`: RS-1 triggered (15 min default)
- `personality_daily_time_s`: Total conversation time today
- `personality_daily_limit_reached`: RS-2 triggered (45 min default)

**Diagnosing time limit issues:**
- "Session limit reached" → conversation was ended with gentle redirect speech
- "Daily limit reached" → all new conversations blocked for the rest of the day
- Reset daily counter: send `personality.cmd.set_guardrail` with `{"reset_daily": true}`
- Daily state persisted at: `./data/daily_usage.json` (resets automatically on new day)
- Override limits: `personality.cmd.set_guardrail` with `{"session_time_limit_s": 1200}`

## Step 4: Fault-Specific Diagnostics

### "frame too long" / timing issues
1. Check `face_heartbeat` data for frame time stats
2. Look for `FRAME_TOO_LONG` in recent logs
3. Check if border rendering or effects are exceeding 33ms budget
4. Read `esp32-face-v2/main/config.h` for `FRAME_TIME_LOG_INTERVAL_MS`

### Communication issues
1. Check packet counters in `/debug/devices` — any stalled?
2. Check `seq` gaps — indicates dropped packets
3. Check clock sync offset drift in monitor tab
4. Read transport error logs

### Reflex faults
1. Check `fault_flags` in `/status`
2. Common: CMD_TIMEOUT (no commands for 400ms — normal if no mode set)
3. IMU_FAIL (I2C issue), STALL (blocked wheel), ESTOP (switch open)

## Step 5: Local Supervisor (Dev PC)

If MCUs are plugged into the dev PC (not Pi), you can run supervisor locally:
```bash
just run-mock  # or with real hardware on detected ports
```

Then query the API at localhost:8080 for direct debugging without SSH.

## Rules

1. Always start with hardware detection — don't assume what's connected.
2. If supervisor isn't reachable, help the user start it.
3. Report findings in a structured format: what's working, what's failing, suggested fixes.
4. Cross-reference fault patterns with `docs/protocols.md` and commissioning procedures.
5. For timing issues, always check frame time stats before suggesting code changes.
