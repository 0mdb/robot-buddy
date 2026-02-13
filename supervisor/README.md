# Toy Robot Supervisor & Remote Client Specification

Version: 1.1 (Architecture Hardened)
Target Platform: Raspberry Pi 5
MCUs: ESP32-S3 (Reflex), ESP32-S3 (Face)
Network: Local WiFi (LAN)

---

# 1. System Overview

The Raspberry Pi 5 Supervisor is the orchestration layer of the robot. It:

* Arbitrates motion and expression intent
* Enforces safety policy above the Reflex MCU
* Aggregates telemetry
* Exposes all runtime knobs via a parameter registry
* Streams telemetry to a browser UI
* Accepts remote commands over WiFi
* Survives device resets and reconnects deterministically

The Supervisor does NOT:

* Perform low-level motor control
* Generate PWM
* Directly drive LEDs
* Replace MCU-level safety

Architecture philosophy:

Reflex = Deterministic safety and motion
Face = Deterministic expression timing
Supervisor = Policy + coordination + remote interface

---

# 2. Functional Requirements

## 2.1 Device Management

Supervisor must:

* Connect to Reflex MCU via USB serial
* Connect to Face MCU via USB serial
* Reconnect automatically on disconnect
* Expose connection state in telemetry
* Replay runtime parameters on reconnect

### Stable Serial Requirement (Hard Requirement)

Supervisor MUST NOT use `/dev/ttyACM0` style device paths in production.

Approved options:

1. `/dev/serial/by-id/...`
2. Custom udev rules creating:

   * `/dev/robot_reflex`
   * `/dev/robot_face`

Configuration must reference stable symlinks.

---

## 2.2 Modes

Supported Modes:

* BOOT
* IDLE
* TELEOP
* WANDER
* LINE_FOLLOW
* BALL
* CRANE
* CHARGING (or DOCKED)
* ERROR
* SLEEP (optional)

### CHARGING Mode

If dock detected (switch, voltage signature, or charger signal):

* Motion commands are ignored
* Mode becomes CHARGING
* Exit only allowed when undock detected and explicit command issued

### ERROR Mode

Entered automatically if:

* Reflex disconnects
* Severe fault flag received
* E-STOP issued

Motion locked until cleared.

---

## 2.3 Motion Arbitration

Supervisor produces:

DesiredTwist(v_m_s, w_rad_s, ttl_ms)

Reflex enforces:

* Acceleration limits
* Jerk limits
* Hard stop
* Fault conditions
* Command timeout (TTL)

Supervisor refreshes twist at fixed rate (20–50 Hz).

---

## 2.4 Safety Policy

Supervisor must:

* Stop motion on Reflex fault
* Stop motion on command TTL expiry
* Reduce speed on degraded state
* Apply ultrasonic-based speed caps
* Apply vision-based confidence caps
* Enforce conservative fallback if sensors stale

Ultrasonic acts as speed governor, not final stop.

---

## 2.5 Time Model (Monotonic Only)

There is NO cross-device wall-clock synchronization.

All telemetry must include:

* `dev_uptime_ms` (from MCU)
* `rx_monotonic_ms` (Supervisor receive time)

All internal Supervisor timing uses monotonic clocks.

Wall-clock time is only applied in logging layer.

---

# 3. Sensor Ingestion

Inputs include:

* Ultrasonic distance
* Line tracking state
* Vision outputs
* CyberPi teleop (UDP)

All inputs timestamped.
Confidence decays if stale.

---

# 4. Vision Process Isolation (Hard Requirement)

Vision must run in a separate PROCESS (multiprocessing), not just a thread.

Reason:

* Avoid Python GIL interference
* Prevent 50 Hz control loop jitter
* Avoid TTL expiration under CPU load

Vision process publishes `VisionSnapshot` via non-blocking queue.
Supervisor always consumes latest snapshot.
If stale, confidence decays.

Tick Loop: 50 Hz
Vision Loop: 10–20 Hz

---

# 5. Network API Specification

Two planes:

1. Control & Telemetry Plane (HTTP + WebSocket)
2. Media Plane (future: RTSP/WebRTC)

Video/audio are NOT transmitted through the control WebSocket.

---

# 6. HTTP API

Base URL: http://<robot_ip>:8080

## 6.1 GET /status

Returns current aggregated robot status.

## 6.2 GET /params

Returns full parameter registry.

## 6.3 POST /params

Transactional parameter update.

Behavior:

* Validate all items
* Write-through to owning device
* Require ACK
* Commit only on success
* Return per-item status

## 6.4 POST /actions

RPC-style endpoint.

Supported actions:

* set_mode
* e_stop
* clear_e_stop
* trigger_gesture

RPC style intentionally preferred over strict REST fragmentation.

## 6.5 Profiles

* GET /profiles
* POST /profiles/save
* POST /profiles/load

Profiles are filtered snapshots of parameter registry.

---

# 7. WebSocket API

Endpoint: ws://<robot_ip>:8080/ws

Envelope:

{
"schema":"supervisor_ws_v1",
"type":"telemetry|event|cmd|ack|error",
"ts_ms":123,
"id":"uuid",
"payload":{}
}

Telemetry emitted at configurable rate (default 10–20 Hz).

JSON format used in v1.
Optional future: compact or msgpack.

Config:

network:
telemetry_format: json

---

# 8. Parameter Registry Specification

Each parameter has:

* name
* type
* min
* max
* step
* default
* value
* owner (reflex|face|supervisor)
* mutable (runtime|boot_only)
* safety (safe|risky)
* documentation

Registry is authoritative source of truth.

On reconnect:

* Supervisor replays last known runtime parameters to device

Parameter writes are transactional.

---

# 9. Telemetry Bandwidth Policy

Default:

* JSON telemetry at 10–20 Hz

If CPU spikes detected:

* Support compact payload mode

Telemetry drop acceptable.
Command drop NOT acceptable.

---

# 10. Logging & Storage Safety

Requirements:

* Telemetry recorder optional
* Record rate configurable (e.g., 10 Hz)
* Log rotation built-in
* Hard cap on disk usage

Example config:

runtime:
record_jsonl: true
record_rate_hz: 10
record_max_mb: 50
record_roll_count: 3

Supervisor must never fill SD card.

---

# 11. Code Structure

```
supervisor/
  main.py
  runtime.py
  config.py

  io/
    serial_transport.py
    udp_transport.py

  devices/
    reflex_client.py
    face_client.py

  inputs/
    camera_vision.py
    ultrasonic.py
    line_sensor.py
    cyberpi.py

  state/
    datatypes.py
    supervisor_sm.py
    policies.py

  api/
    http_server.py
    ws_hub.py
    param_registry.py

  logging/
    recorder.py
```

---

# 12. Simple Web UI Specification

Served as static HTML/JS from FastAPI.

Goals:

* Zero build toolchain
* Auto-generate sliders from parameter registry
* Live telemetry view
* Mode control
* E-STOP

UI Panels:

Left:

* Mode selector
* E-STOP (red)
* Clear

Center:

* v_meas
* w_meas
* ultrasonic
* clear_conf
* ball_conf
* v_cap + cap reasons

Right:

* Parameter sliders grouped by owner

---

# 13. Mock Phase (Required Before Hardware Integration)

Before physical integration, implement:

MockReflex:

* Accept SET_TWIST
* Simulate v_meas/w_meas
* Enforce TTL timeout
* Inject faults
* Stream telemetry

MockFace:

* Accept SET_FACE_STATE
* Stream telemetry

Acceptance Criteria:

* 50 Hz supervisor tick with <5ms jitter
* 20 Hz telemetry streaming
* Teleop works via browser
* E-stop immediate
* Param tuning works
* Log rotation verified
* Reconnect recovery verified

No soldering before this passes.

---

# 14. Deployment

* systemd service
* Auto-start on boot
* Restart on failure
* Stable serial paths
* Log caps enforced

---

# 15. Acceptance Criteria (System Complete)

Supervisor v1 complete when:

* Fully operable from browser
* All MCU knobs exposed and tunable
* Telemetry live
* E-stop deterministic
* Survives MCU reset
* No control loop jitter under vision load
* Disk usage bounded

---

End of Specification
