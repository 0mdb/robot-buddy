# Robot Buddy — TODO

## Active Backlog

- ~~Add trigger word so conversations flow more naturally. Wait for silence. Remove need to press button.~~ Done — ear worker with "hey buddy" wake word + Silero VAD end-of-utterance detection. See `supervisor_v2/workers/ear_worker.py`.
- Upgrade the camera and adjust settings.
- Add camera calibration/mask/cv settings in supervisor dash.
- ~~Fix server issue when trying to run better TTS model.~~ Fixed — persistent event loop for Orpheus vLLM engine + proper GPU memory cleanup on reset.
- Add LLM history so conversations feel more natural.
- TTS from non-button press (deterministic sources) either cut off or not firing at all.
- work through reflex comissioning plan, all hardware has arrived and ready on the bread board
- Face stops talking before speech stops playing, needs better sync.
- camera replaced with Arducam for Raspberry Pi Camera Module 3, 12MP IMX708 75°(D) Autofocus Pi Camera V3.  This needs to be properly integrated into the stack and set up correctly for the robot.
- ~~Should play a sound when listening for command is active (either by button press or keyword).~~ Done — ear worker plays `assets/chimes/listening.wav` on wake word detection.

---

## Conversation State Visual System (Sim V3 Complete — Firmware Pending)

Face Sim V3 (`tools/face_sim_v3/`, ~2600 lines, 16 modules) is the canonical design authoring surface. Run with `just sim`. Full spec implementation with command bus protocol, mood sequencer choreography, conversation state machine, negative affect guardrails, and CI parity check (70/70 constants match MCU).

### Completed — Face Sim V3 (Stage 3)
- [x] Clean rewrite from spec — modular package replacing V2's 4 monolithic files
- [x] 13 moods (including CONFUSED) with distinct colors, expression intensity blending
- [x] Mood transition choreography — blink → 150ms ramp-down → switch → 200ms ramp-up
- [x] Negative affect guardrails — context gate, intensity caps, duration caps, auto-recovery
- [x] Conversation state machine — 8 states with auto-transitions, per-state gaze/flag overrides
- [x] Border renderer — SDF frame + glow, per-state animations (sweep, breathing, orbit dots, energy-reactive, flash, fade)
- [x] Command bus — all inputs → protocol-equivalent commands (no direct state mutation)
- [x] LED sync, PTT/Cancel buttons, sparkle/fire/afterglow effects
- [x] Debug HUD + scrolling timeline of state transitions
- [x] CI parity check — `tools/check_face_parity.py` (70/70 passed)

### Remaining (Phase 0–5)
- [ ] Phase 0: Sync MCU constants to match V3 sim — 17 divergences ported, parity check 169/169, `just check-parity` in preflight
    - gaps remain, the system logos on device not updated, thinking face looks angry(needs refinement in sim?), could add this to the firmware optmization as part of step 5?
- [x] Phase 1: Supervisor conversation state machine in tick_loop — `ConvStateTracker` module + tick_loop wiring + 39 tests
- [x] Phase 2: Firmware border rendering + SET_CONV_STATE (0x25)
- [x] Phase 3: Supervisor mood transition sequencer + guardrails — `MoodSequencer` (4-phase choreography ~470ms) + `Guardrails` (context gate, intensity caps, duration caps) + tick_loop integration + 58 tests
- [x] Phase 4: Conversation phase transition choreography — `ConvTransitionChoreographer` (gaze ramps, anticipation blink, re-engagement nod, mood settle) + tick_loop integration + 51 tests
- [ ] Phase 5: Polish, talking sync fix, dashboard visualization

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

- [x] Add `seq` and `t_src_us` to all MCU packets (MCU v2 envelope done; supervisor activates via `negotiate_v2()`)
- [x] Implement `TIME_SYNC_REQ / RESP` (ClockSyncEngine with min-RTT offset, drift tracking)
- [x] Log raw packets with `t_pi_rx_ns` (RawPacketLogger: binary format per PROTOCOL.md §10.1, 50MB rotation)
- [x] Add `frame_seq`, `t_cam_ns`, `t_det_done_ns` (Picamera2 SensorTimestamp extraction)
- [x] Add `cmd_seq` to motion commands (u32 seq, `t_cmd_tx_ns` causality tracking)
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

---

## Personality Engine (Complete — Ready for Stage 3)

Principled personality system driving the robot's emotions. Research complete, spec written, alignment review done. Ready for Stage 3 implementation.

### Research & Decisions — Complete

**Phase 1 — Ideal System** (Buckets 0–4):
- [x] Bucket 0: Safety psychology — `docs/research/bucket-0-safety-psychology.md`
- [x] Bucket 1: Temperament & personality models — `docs/research/bucket-1-temperament-models.md`
- [x] Bucket 2: Emotional memory & affect dynamics — `docs/research/bucket-2-memory-affect.md`
- [x] Bucket 3: Child-robot relationship development — `docs/research/bucket-3-relationships.md`
- [x] Bucket 4: Proactive vs reactive behavior — `docs/research/bucket-4-proactive-reactive.md`
- [x] Decision points PE-1 through PE-5 (recorded in Stage 1 spec §E)

**Phase 2 — Technology** (Buckets 5–7):
- [x] Bucket 5: LLM model selection → Qwen3-8B-AWQ — `docs/research/bucket-5-llm-model-selection.md`
- [x] Bucket 6: Prompt engineering for personality — `docs/research/bucket-6-prompt-engineering.md`
- [x] Bucket 7: Device/server split — `docs/research/bucket-7-device-server-split.md`
- [x] Decision points PE-6 through PE-10 (recorded in Stage 1 spec §E)

**Specs**:
- [x] PE Stage 1: Research & decisions — `docs/personality-engine-spec-stage1.md`
- [x] PE Stage 2: Full implementation-ready spec — `docs/personality-engine-spec-stage2.md` (~1340 lines, 14 sections + appendix)
- ~~Pi 5 inference spike~~ N/A — PE-7 = Option C (rules only, no on-device LLM)

### Alignment Review — Complete

- [x] Alignment review: reconcile PE spec with face communication spec → `docs/pe-face-comm-alignment.md`
  - 5 conflicts resolved: guardrail enforcement (tiered model), SURPRISED reclassification, mood transition ownership, CONFUSED mood addition, suppress-then-read model
  - Both specs amended in place, alignment report written

### Architecture

- **PersonalityWorker** (dedicated BaseWorker on Pi 5) — 1 Hz tick + event-triggered fast path
- **Continuous affect vector** (valence, arousal) with decaying integrator, 20 axis-derived parameters
- **13 mood anchors** in VA space with asymmetric hysteresis projection
- **Layer 0** (deterministic rules, no server) + **Layer 1** (LLM-enhanced, Qwen3-8B)
- **Single source of emotional truth** — personality worker is final authority on face + TTS prosody
- **Memory system** — local-only JSON, 5 decay tiers, COPPA compliant
