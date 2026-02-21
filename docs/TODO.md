# Robot Buddy — TODO

## Active Backlog

- Add trigger word so conversations flow more naturally. Wait for silence. Remove need to press button.
- Upgrade the camera and adjust settings.
- Add camera calibration/mask/cv settings in supervisor dash.
- Fix server issue when trying to run better TTS model.
- Don't send planner updates so often.
- Add LLM history so conversations feel more natural.
- TTS from non-button press (deterministic sources) either cut off or not firing at all.
- Face stops talking before speech stops playing, needs better sync.
- Should play a sound when listening for command is active (either by button press or keyword).
- Face stuck displaying "booting" system mode — can't override expression from dashboard panel even though telemetry shows face MCU is connected.

---

## Timestamps & Deterministic Telemetry

### Goal

Design deterministic, replayable telemetry across **Pi + Reflex MCU + Face MCU** so autonomy and debugging are based on evidence, not guesswork.

We must be able to answer:

- Did it turn because of IMU data?
- Because vision was stale?
- Because a motor fault occurred?
- Or because of latency?

### Principles

- Use **monotonic clocks only** (no wall clock in control paths).
- Timestamp at **acquisition time**, not publish time.
- Add **sequence numbers everywhere**.
- Maintain a stable mapping from MCU time → Pi time.
- Log raw bytes for perfect replay.

### Clock Domains

- **Pi** → `CLOCK_MONOTONIC` (ns)
- **Reflex MCU** → `t_reflex_us` since boot (u64)
- **Face MCU** → `t_face_us` since boot (u64)

### Required Fields (All MCU Messages)

Every packet must include:

- `src_id`
- `msg_type`
- `seq` (u32)
- `t_src_us` (monotonic since boot)
- `payload`

On Pi receive, attach:

- `t_pi_rx_ns`

Minimum viable envelope:
```
t_pi_est_ns = t_src_us * 1000 + offset_ns
```

Sync at 2–10 Hz. Use lowest RTT samples for stable offset.

### Reflex MCU Timestamp Rules

Timestamp at **acquisition moment**:

- IMU → at I2C/SPI read completion or DRDY interrupt
- Encoders → at control loop tick boundary
- Ultrasonic → at echo completion
- Motor PWM applied → when update committed
- Faults → at detection moment

Optional (ultrasonic precision):

- `t_trig_us`
- `t_echo_us`

### Face MCU Timestamp Rules

Timestamp:

- `STATE_APPLIED`
- `BLINK`
- `GAZE_CHANGE`
- `FAULT`
- Future audio-related events (lip sync, beat sync)

Consistency is more important than frequency.

### Camera Frames (Pi Domain)

Each frame must include:

- `frame_seq`
- `t_cam_ns` (sensor timestamp if available)
- `t_rx_ns` (Pi receive time)

Detection events must reference:

- `frame_seq`
- `t_frame_ns`
- `t_det_done_ns`

Never use detection completion time for sensor fusion alignment.

### Commands & Causality

Motion commands:

- Add `cmd_seq`
- Record `t_cmd_tx_ns` on Pi

Reflex echoes back:

- `cmd_seq_last_applied`
- `t_applied_src_us`

This enables full control causality tracing.

### Server Events

For each planner request:

- `req_id`
- `t_req_tx_ns`
- `t_resp_rx_ns`
- `rtt_ns`

Never use server wall clock for control decisions.

### Logging Strategy (Critical)

#### 1. Raw Binary Log (Authoritative)

For each received packet:

- `t_pi_rx_ns`
- `src_id`
- `len`
- raw bytes

This is your deterministic replay stream (rosbag equivalent).

#### 2. Derived Log (Optional)

Decoded fields:

- `t_pi_est_ns`
- latency diagnostics
- seq gap detection
- offset + drift estimate

### Telemetry Health Metrics

Add dashboard panel per device:

- RTT min / avg
- offset_ns
- drift estimate
- seq drop rate

### Known Failure Modes

- Offset drift → periodic sync + drift estimation
- USB jitter → rely on minimum RTT samples
- Packet drops → detect via seq gaps
- Sensor fusion misalignment → enforce acquisition timestamps

### Immediate Actions

- [ ] Add `seq` and `t_src_us` to all MCU packets
- [ ] Implement `TIME_SYNC_REQ / RESP`
- [ ] Log raw packets with `t_pi_rx_ns`
- [ ] Add `frame_seq`, `t_cam_ns`, `t_det_done_ns`
- [ ] Add `cmd_seq` to motion commands
- [ ] Add telemetry health dashboard
