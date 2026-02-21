# Robot Buddy — TODO

## Active Backlog

- ~~Add trigger word so conversations flow more naturally. Wait for silence. Remove need to press button.~~ Done — ear worker with "hey buddy" wake word + Silero VAD end-of-utterance detection. See `supervisor_v2/workers/ear_worker.py`.
- Upgrade the camera and adjust settings.
- Add camera calibration/mask/cv settings in supervisor dash.
- ~~Fix server issue when trying to run better TTS model.~~ Fixed — persistent event loop for Orpheus vLLM engine + proper GPU memory cleanup on reset.
- Don't send planner updates so often.
- Add LLM history so conversations feel more natural.
- TTS from non-button press (deterministic sources) either cut off or not firing at all.
- Face stops talking before speech stops playing, needs better sync.
- ~~Should play a sound when listening for command is active (either by button press or keyword).~~ Done — ear worker plays `assets/chimes/listening.wav` on wake word detection.
- Face stuck displaying "booting" system mode — can't override expression from dashboard panel even though telemetry shows face MCU is connected.

---

## Conversation State Visual System (In Progress)

Visual feedback for conversation flow — border animations, LED sync, button redesign. Prototyped in Python face sim (`tools/conv_border.py`), not yet ported to firmware.

### Completed (sim prototype)
- [x] ConvBorder state machine — 8 states: idle, attention, listening, PTT, thinking, speaking, error, done
- [x] Border renderer — 4px frame with 3px glow, SDF-based, smooth color/alpha transitions
- [x] Per-state animations: attention sweep, listening breath, thinking orbit dots, speaking energy-reactive, error flash+fade
- [x] LED color sync (simulated WS2812B indicator)
- [x] Button redesign — PTT (concentric arcs icon), Cancel (X mark), 36px visible / 48px hit target
- [x] Talking phase-speed coupling: `phase_speed = 12 + 6 * energy` (was fixed 15 rad/s)
- [x] Sim controls: F7-F12 for conv states, P for PTT toggle, HUD updates

### Remaining (pending v3 design review)
- [ ] Firmware port — protocol command 0x25 SET_CONV_STATE, ESP32 border/button/LED rendering
- [ ] Supervisor wiring — conv state transitions in tick_loop (wake_word→ATTENTION→LISTENING→THINKING→SPEAKING→DONE)
- [ ] Dashboard Conversation tab — state timeline, event log, manual controls
- [ ] Integration test — end-to-end wake word → full visual state flow on hardware

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
- [x] Add telemetry health dashboard (Monitor tab: diagnostic tree, Pi resources, comms, power, sensors, faults, workers)

---

## Wake Word Model — Next Steps

First pass trained (v1, 2025-02-21). Metrics on synthetic test set:
- Accuracy: 71%, Recall: 42%, FP/hour: 0.27

### Improve recall (currently 42% — should be 80%+)
- [ ] Increase `n_samples` from 15k → 50k+ (more voice diversity)
- [ ] Increase `augmentation_rounds` from 3 → 5
- [ ] Add speech-heavy negative data (LibriSpeech, AudioSet speech subset) — currently only FMA music backgrounds
- [ ] Try `layer_size: 64` (more model capacity, still tiny at ~400KB)

### Improve robustness with real audio
- [ ] Record 20–50 real "hey buddy" utterances from the family (different distances, volumes, rooms)
- [ ] Place recordings in `training/real_clips/` and add to config as `custom_verifier_clips`
- [ ] Re-train and compare metrics

### Reduce false positives in deployment
- [ ] Add more negative phrases based on real-world triggers observed during testing
- [ ] Soak test: run idle for 1+ hours with household noise, log all detections
- [ ] Tune detection threshold in ear worker (currently 0.5 — may need adjustment)

### Training infrastructure
- [ ] Pin openWakeWord to a specific commit in setup.sh (avoid breaking changes)
- [ ] Skip tflite conversion (we only need ONNX) — currently fails due to onnx_tf version mismatch
- [ ] Add a `just retrain-wakeword` target that skips Phase 1 if clips already exist

---

## Future / Ideas

- Investigate voice ID / speaker identification — know which kid said 'hey buddy' so the robot can personalize the conversation and response (e.g. per-child voice embeddings, speaker diarization on wake word audio).
- Home Assistant light control via conversation — kid says "turn off my light" and Buddy does it. Extend conversation JSON schema with `home_actions`, add server-side HA REST client, YAML device whitelist. Lights only to start. See [docs/home-assistant-integration.md](home-assistant-integration.md) for full plan.
