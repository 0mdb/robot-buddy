# Robot Buddy — TODO

Single source of implementation truth. All task tracking lives here.

## How to Use This File

- **Priority**: Tasks within each section are listed in recommended execution order (top = highest)
- **Parallel tracks**: Tracks A–D can run concurrently. Dependencies are noted inline.
- **Model tags**: `[opus]` = needs Opus 4.6 (architecture, spec interpretation, complex debugging, prompt engineering). `[sonnet]` = Sonnet handles well (mechanical refactors, test writing, parity checks, README updates).
- **Spec-driven**: Changes that diverge from specs require a spec amendment first. Debate the spec change, update the spec, then implement.

---

## Execution Order & Priority

Living section — reorder as priorities shift. Current recommended sequence:

### Track A: Face Communication (firmware + supervisor)
1. Phase 5 polish (talking sync, protocol docs, dashboard viz)
2. Phase 0 remaining gaps (system logos, thinking face)
3. Sim↔MCU divergence fixes
4. Stage 4 firmware optimization
5. T1–T4 evaluation

### Track B: Personality Engine (server + supervisor)
1. PersonalityWorker scaffold + affect vector
2. Layer 0 deterministic rules
3. Server prompt engineering (system prompt v2)
4. Layer 1 LLM integration
5. Memory system + impulse catalog
6. PE evaluation

### Track C: Reflex MCU Commissioning (hardware)
1. Phase 1: IMU bring-up
2. Phase 2: Motors + encoders
3. Phase 3: Ultrasonic range
4. Phase 4: E-stop & safety
5. Phase 5: Closed-loop PID

### Track D: Infrastructure & Tooling
1. `-v2` rename (supervisor_v2 → supervisor, esp32-face-v2 → esp32-face)
2. specs/INDEX.md for efficient spec navigation

---

## Active Backlog

### Face Communication System

**Phase 0 — Remaining Gaps** `[sonnet]`
- [ ] System logos on device not updated to V3 design
- [ ] Thinking face looks angry on hardware — needs refinement (may defer to Stage 4)
- [ ] Visual review: V3 sim vs MCU side-by-side on hardware for all 13 moods

**Phase 5 — Polish** `[sonnet]`
- [ ] Tune timing values on hardware: ramp durations, hold times, border alpha curves

**Stage 4 — Firmware Display Optimization** `[opus]`
- [ ] Profile current render loop (esp_timer instrumentation, 1000-frame stats)
- [ ] Profile border SDF render cost for all 8 conv states
- [ ] Implement dirty-rectangle tracking (ILI9341 CASET/RASET window commands)
- [ ] Implement DMA double-buffering (render to back buffer during SPI transfer)
- [ ] Optimize border SDF with precomputed lookup table
- [ ] Audit 13 mood colors for RGB565 fidelity — corrected palette
- [ ] Temporal dithering for smooth gradients at RGB565 depth
- [ ] Gamma correction for SDF antialiasing
- [ ] Profile command-to-pixel latency end-to-end
- [ ] Profile sparkle/fire/afterglow effects budget

**Evaluation** `[opus]`
- [ ] T1: Automated CI tests (parity check, unit tests, linting)
- [ ] T2: Instrumented benchmarks (frame time, latency, SPI throughput)
- [ ] T3: Developer review — 5 scenarios (idle, conversation, mood sweep, stress, edge cases)
- [ ] T4: Child evaluation protocol (ages 4-6, per eval plan spec)

---

### Personality Engine Implementation

**Spec reference**: `specs/personality-engine-spec-stage2.md`

**Scaffold** `[opus]`
- [ ] PersonalityWorker as dedicated BaseWorker on Pi 5 (1 Hz tick + event-triggered fast path)
- [ ] Continuous affect vector (valence, arousal) with decaying integrator
- [ ] 13 mood anchors in VA space with asymmetric hysteresis projection
- [ ] 20 axis-derived parameters from 5 personality axes
- [ ] Worker↔tick_loop protocol: personality snapshot struct

**Layer 0 — Deterministic Rules** `[opus]`
- [ ] Impulse catalog implementation (stimulus → affect delta mappings)
- [ ] Duration caps, intensity caps, context gate enforcement
- [ ] Idle behavior rules (SLEEPY after inactivity, CURIOUS on sensor trigger)
- [ ] Auto-recovery sequences for negative moods

**Layer 1 — LLM Integration** `[opus]`
- [ ] System prompt v2 for personality (from `docs/research/bucket-6-prompt-engineering.md`)
- [ ] Server-side prompt engineering: embed personality axes + affect state in LLM context
- [ ] Qwen3-8B-AWQ integration (per PE spec §8, bucket-5 decision)
- [ ] LLM response → affect impulse parsing
- [ ] Fallback to Layer 0 when server unreachable

**Memory & Prosody** `[opus]`
- [ ] Memory system: local JSON, 5 decay tiers, COPPA compliant (spec §9)
- [ ] TTS prosody routing from affect vector (valence/arousal → speech rate/pitch)
- [ ] Emotional memory consolidation (interaction summaries)

**Evaluation** `[opus]`
- [ ] PE evaluation metrics (spec §13): emotional coherence, response appropriateness
- [ ] Guardrail compliance testing
- [ ] Child interaction safety validation

---

### Reflex MCU Commissioning

**Prerequisite**: ESP-IDF environment, USB-C cable, hardware on breadboard.

**Firmware change required first** `[sonnet]`:
- [ ] Update `pin_map.h`: TRIG GPIO1→GPIO21, VBAT GPIO14→GPIO1 (per `docs/reflex-wiring.md`)

**Phase 1: IMU (BMI270) — I2C Validation** `[sonnet]`
- [ ] I2C bus scan (verify BMI270 at 0x68 or 0x69)
- [ ] BMI270 init: CHIP_ID=0x24, INTERNAL_STATUS=0x01, ODR 400 Hz
- [ ] Live data validation: flat=1g Z, rotate=gyro deflection, tilt=0.7g shift
- [ ] Pass: no IMU_FAIL fault, no I2C recovery in first 60s

**Phase 2: Motors + Encoders — Open-Loop Test** `[sonnet]`
- [ ] Enable `BRINGUP_OPEN_LOOP_TEST 1` in `app_main.cpp`
- [ ] Verify motor direction matches encoder count direction (both wheels)
- [ ] Verify encoder counts (1440 counts/rev for TT motor)
- [ ] Disable open-loop test, flash full firmware

**Phase 3: Ultrasonic Range Sensor** `[sonnet]`
- [ ] Static distance test (100mm, 300mm, 1000mm, 3000mm ± tolerances)
- [ ] OBSTACLE fault triggers at <250mm, clears at >350mm with hysteresis

**Phase 4: E-Stop & Safety Systems** `[sonnet]`
- [ ] E-stop test (GPIO13 switch: open→ESTOP fault, close+CLEAR_FAULTS→recovery)
- [ ] Tilt detection (>45° for >200ms → TILT fault)
- [ ] Command timeout (no commands for 400ms → CMD_TIMEOUT fault + soft-stop)
- [ ] Stall detection (blocked wheel → STALL fault after ~500ms)

**Phase 5: Closed-Loop Integration** `[opus]` for PID tuning
- [ ] PID tuning baseline: SET_TWIST v=100 mm/s, observe convergence
- [ ] Yaw damping: straight-line travel, verify gyro_z correction
- [ ] Full exercise: forward/reverse/spin/arc/stop/accel-limit/obstacle
- [ ] Pass: PID tracks ±20%, no oscillation, safety overrides work under load

**Post-Commissioning** `[sonnet]`
- [ ] Battery voltage sense (ADC) + sag-aware limiting
- [ ] Odometry integration (x, y, theta)
- [ ] Full IMU heading hold PID (currently gyro damping only)

---

### Conversation & Voice

- [ ] `[opus]` LLM conversation history/memory — server-side session context
- [ ] `[sonnet]` TTS from deterministic sources (non-button press) either cut off or not firing
- [ ] `[sonnet]` Wake word model: increase recall from 42%→80%+ (n_samples 15k→50k+, augmentation rounds 3→5, speech-heavy negative data, layer_size 64)
- [ ] `[sonnet]` Wake word: record 20–50 real "hey buddy" utterances from family
- [ ] `[sonnet]` Wake word: soak test 1+ hours idle with household noise
- [ ] `[sonnet]` Wake word: pin openWakeWord commit, skip tflite, add `just retrain-wakeword`

---

### Camera & Vision

- [ ] `[sonnet]` Arducam IMX708 integration — proper V4L2/Picamera2 setup, autofocus config
- [ ] `[sonnet]` Camera calibration/mask/CV settings in dashboard
- [ ] `[sonnet]` Upgrade camera settings for new hardware

---

### Dashboard

- [ ] `[sonnet]` Telemetry health panel per device (RTT, offset, drift, seq drops)
- [ ] `[sonnet]` Camera settings panel
- [ ] `[opus]` Personality engine visualization (affect vector, mood anchors, decay curves)

---

### Infrastructure & Tooling

**Rename: Remove -v2 Suffixes** `[sonnet]` — do as a single dedicated commit
- [ ] Rename `supervisor_v2/` → `supervisor/` (update 69+ Python imports, pyproject.toml, justfile, configs, pyrightconfig.json)
- [ ] Rename `esp32-face-v2/` → `esp32-face/` (update CMake, justfile, docs, skills)
- [ ] Update all cross-references (CLAUDE.md, README.md, deploy scripts, .vscode/settings.json)

**New Skills** `[sonnet]`
- [ ] `/status` skill: quick project state snapshot (connected devices, test results, current TODO priority) for session start

**Efficiency Improvements** `[sonnet]`
- [ ] `specs/INDEX.md` — one-paragraph summary of each spec with section links for targeted reading
- [ ] Expand CLAUDE.md "Repository Structure" with annotated key file paths for common tasks

---


---

## Completed

### Face Communication — Research & Specs
- [x] Face communication spec Stage 1 (research) → `specs/face-communication-spec-stage1.md`
- [x] Face communication spec Stage 2 (implementation-ready, ~1340 lines) → `specs/face-communication-spec-stage2.md`
- [x] Spec revisions: 10 fixes + 3 nits applied, verification pass done
- [x] Face visual language design document → `specs/face-visual-language.md`
- [x] Face communication evaluation plan → `specs/face-communication-eval-plan.md`

### Personality Engine — Research & Specs
- [x] Research buckets 0-7 → `docs/research/bucket-*.md`
- [x] PE Stage 1: research & decisions (PE-1 through PE-10) → `specs/personality-engine-spec-stage1.md`
- [x] PE Stage 2: full implementation spec (~1340 lines) → `specs/personality-engine-spec-stage2.md`
- [x] PE↔Face alignment review (5 conflicts resolved) → `specs/pe-face-comm-alignment.md`

### Face Sim V3 (Stage 3)
- [x] Clean rewrite: 16 modules, ~2600 lines, `tools/face_sim_v3/`
- [x] 13 moods with distinct colors, expression intensity blending
- [x] Mood transition choreography (blink → 150ms ramp-down → switch → 200ms ramp-up)
- [x] Negative affect guardrails (context gate, intensity caps, duration caps, auto-recovery)
- [x] Conversation state machine (8 states, auto-transitions, per-state gaze/flag overrides)
- [x] Border renderer (SDF frame + glow, 8 state animations)
- [x] Command bus (all inputs via protocol-equivalent commands)
- [x] CI parity check (196/196 passed)
- [x] Visual language remediation (G1-G7) + review cycles (R1-R5, D1-D5, B1-B3)

### Face Implementation (Phases 0–4)
- [x] Phase 0: Sim/MCU parity sync (17 divergences ported, 196/196 parity; blink interval, idle gaze, gesture durations, talking speed, BG color, mouth curve all confirmed synced; CONFUSED mood verified end-to-end in constants.ts, types.ts, protocols.md, sim)
- [x] Phase 1: Supervisor conversation state machine (ConvStateTracker + tick_loop wiring + 39 tests)
- [x] Phase 2: Firmware border rendering + SET_CONV_STATE 0x25 (~700 lines C++, corner buttons, LED sync + 8 protocol tests)
- [x] Phase 3: Mood transition sequencer + guardrails (MoodSequencer 4-phase ~470ms + Guardrails + tick_loop + 58 tests)
- [x] Phase 4: Conversation phase transitions (ConvTransitionChoreographer: gaze ramps, anticipation blink, re-engagement nod, mood settle + 51 tests)
- [x] Phase 5: Talking sync fix (300ms POST_TALKING_GRACE_TICKS in tick_loop.py), dashboard Face State panel (conv state badge + intensity bar + sequencer phase), SET_FLAGS/SET_CONV_STATE/CONFUSED documented in protocols.md

### Timestamps & Deterministic Telemetry
- [x] Protocol v2 envelope: seq (u32) + t_src_us (u64) for all MCU packets
- [x] TIME_SYNC_REQ/RESP (ClockSyncEngine: min-RTT offset, drift tracking)
- [x] Raw packet logger (binary format per PROTOCOL.md §10.1, 50MB rotation)
- [x] Camera frames: frame_seq, t_cam_ns (Picamera2 SensorTimestamp), t_det_done_ns
- [x] Command causality: cmd_seq (u32), t_cmd_tx_ns tracking
- [x] Telemetry health dashboard (Monitor tab: diagnostic tree, Pi resources, comms, power, sensors, faults, workers)

### Infrastructure & Tooling
- [x] `/diagnose` skill — curl commands, 5-step workflow, fault-specific diagnostics
- [x] Protocol docs: SET_FLAGS (0x24) + SET_CONV_STATE (0x25) + CONFUSED mood ID 12 added to `docs/protocols.md`
- [x] Border constants parity (`BORDER_FRAME_W`, `GLOW_W`, `CORNER_R`, `BLEND_RATE`) in `check_face_parity.py`
- [x] `docs/architecture.md` — 181-line comprehensive rewrite (was stale 17-line stub)
- [x] `SystemMode::ERROR_DISPLAY` symbol parity — consistent across sim, supervisor, MCU
- [x] LOW_BATTERY supervisor trigger wired: `low_battery_mv` threshold in `SafetyConfig`, `FaceSystemMode.LOW_BATTERY` overlay in `tick_loop.py` `_emit_mcu`
- [x] README spec compliance: model refs (Qwen2.5-3B → Qwen3-8B-AWQ), hardware refs (Jetson → Pi 5), stale In Progress items removed

### Infrastructure
- [x] Voice pipeline: STT + TTS on 3090 Ti server, audio on Pi USB devices
- [x] Conversation flow: button-triggered STT → LLM → TTS → face animation
- [x] Wake word detection with "hey buddy" + Silero VAD
- [x] Ear worker plays `assets/chimes/listening.wav` on wake word detection
- [x] Planner server: FastAPI + vLLM backend, conversation + planning endpoints
- [x] Dashboard: React 19, Vite, TypeScript, Zustand, TanStack Query
- [x] Deploy scripts + systemd service on Pi

---

## Future Development & R&D

### Near-Term Ideas
- Voice ID / speaker identification — per-child voice embeddings for personalized responses
- Home Assistant light control via conversation (see `docs/home-assistant-integration.md`)
- Additional modes: LINE_FOLLOW, BALL, CRANE, CHARGING

### R&D Research Plan
- On-device inference feasibility if PE spec revisits PE-7 decision
- Advanced wake word models (transformer-based, multi-keyword)
- Multi-modal interaction (gesture recognition via camera + IMU fusion)
- Proactive behavior triggers from sensor patterns (per bucket-4 research)

### Ongoing Research Cadence
- Monthly spec review: check assumptions against upstream model releases (Qwen, Orpheus)
- Track ESP-IDF updates for display pipeline improvements
- Monitor child-robot interaction research for safety/ethical updates

---

## Model Assignment Guide

| Task Type | Model | Rationale |
|-----------|-------|-----------|
| Spec writing & interpretation | Opus 4.6 | Requires deep understanding of multi-document specs |
| Architecture decisions | Opus 4.6 | Trade-off analysis, system-level reasoning |
| Complex debugging | Opus 4.6 | Multi-system causality tracing |
| Personality engine design | Opus 4.6 | Psychology-informed design, prompt engineering |
| PID tuning & control theory | Opus 4.6 | Mathematical reasoning, parameter sensitivity |
| Mechanical refactors | Sonnet 4.6 | Pattern-apply across files (rename, import updates) |
| Test writing | Sonnet 4.6 | Well-scoped, pattern-following |
| README/doc updates | Sonnet 4.6 | Factual updates, no design decisions |
| Parity checks | Sonnet 4.6 | Systematic comparison, no judgment calls |
| Protocol documentation | Sonnet 4.6 | Transcribe from code to docs |
| Linter/config fixes | Sonnet 4.6 | Mechanical, well-defined |

---

## Efficiency Notes

### Token optimization
- **Spec navigation**: Use `specs/INDEX.md` (once created) for targeted reading instead of re-reading full 1000+ line specs
- **Key file paths**: Common edit targets are listed in CLAUDE.md under Repository Structure
- **Debug cycles**: Use `/diagnose` skill (once created) to debug MCUs directly from dev PC, avoiding Pi SSH round-trips

### Process improvements
- **Spec-first**: Never implement counter to a spec without debating the spec change first
- **Parity checks**: Run `just check-parity` after any face constant changes
- **Preflight**: Run `just preflight` before any commit (lint + test + parity)
