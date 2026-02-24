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
1. Stage 4.0 parity + hardware polish (system overlays/screens, corner buttons, thinking face read, timing values, docs)
2. Stage 4.1–4.2 firmware optimization (profiling → targeted optimizations)
3. T1–T4 evaluation

### Track B: Personality Engine (server + supervisor)
1. ~~PE↔Face spec compliance fixes~~ ✅ + ~~Server emotion vocab alignment~~ ✅ (B1 complete)
2. ~~Guardrail config + safety timers~~ ✅ (B1b: GuardrailConfig, RS-1/RS-2 session/daily limits, persistence, parent override)
3. ~~Conversation response schema v2 + prompt v2 + guided decoding + model defaults~~ ✅ (B2 core: v2 schema, age 4-8 prompt, Qwen3-8B-AWQ, mood_reason forwarding)
4. ~~Conversation hardening (context-budget, audio overflow, privacy, L1 mood_reason validation)~~ ✅ + chat templates (quality improvement, deferred)
5. ~~Personality profile injection (`personality.llm.profile` → `/converse` prompt injection + anchor cadence)~~ ✅
6. Memory system (local JSON, consent gate, dashboard viewer + forget)
7. ~~Prosody routing (TTS emotion from PE mood)~~ ✅
8. PE evaluation (metrics + guardrail + child-safety validation)

### Track C: Reflex MCU Commissioning (hardware)
1. Phase 1: IMU bring-up
2. Phase 2: Motors + encoders
3. Phase 3: Ultrasonic range
4. Phase 4: E-stop & safety
5. Phase 5: Closed-loop PID

### Track D: Infrastructure & Tooling
_(all items completed)_

---

## Active Backlog

### Face Communication System

**Stage 4 — Parity + Firmware Display Optimization** `[opus]`
- [x] Stage 4.0: Update `specs/face-communication-spec-stage2.md` + `docs/protocols.md` to match chosen behavior:
  - System overlays = Sim V3 “face-based” screens + hide border/buttons while SystemMode != NONE
  - PTT semantics = tap-toggle (not strict press/hold)
  - Corner button hitboxes = `BTN_CORNER_*` constants (not stale 48×48 numbers)
- [x] Stage 4.0: Port Sim V3 system screens to firmware (`tools/face_sim_v3/render/face.py` → `esp32-face`)
- [x] Stage 4.0: Suppress conversation border + corner buttons during system overlays (sim + firmware)
- [x] Stage 4.0: Fix corner button visuals parity (MIC/X icons + ACTIVE/IDLE mapping matches `tools/face_sim_v3/__main__.py`)
- [x] Stage 4.0: Disable corner-button hit-testing + button telemetry during system overlays (buttons hidden)
- [x] Stage 4.0: Fix firmware to accept Mood.CONFUSED (mood_id 12) in `SET_STATE`
- [x] Stage 4.0: Gesture gap analysis: Sim V3 gestures 13–19 exist; defer + gate in sim, keep firmware/protocol at 13 for now
- [x] Stage 4.0: Expand `tools/check_face_parity.py` to catch semantic mismatches (not just constants):
  - CONFUSED mood acceptance, system-mode suppression of border/buttons, corner icon mapping defaults
- [x] Stage 4.0: Supervisor: send LOW_BATTERY param (0–255) derived from `battery_mv` (battery fill/progress)
- [x] Stage 4.0: Doc parity cleanup: reconcile `esp32-face/README.md` with current renderer + corner button semantics
- [ ] Stage 4.0: Hardware visual pass: Sim V3 vs MCU side-by-side on hardware for all 13 moods (confirm “real” reads match spec intent) `[sonnet]`
- [ ] Stage 4.0: Refine THINKING face on hardware (currently reads as angry) `[sonnet]`
- [ ] Stage 4.0: Tune timing values on hardware: ramp durations, hold times, border alpha curves `[sonnet]`
- [ ] Stage 4.1: Profile current render loop (esp_timer instrumentation, 1000-frame stats)
- [ ] Stage 4.1: Profile border SDF render cost for all 8 conv states
- [ ] Stage 4.1: Profile command-to-pixel latency end-to-end (button/wake/PTT → first pixel)
- [ ] Stage 4.1: Profile sparkle/fire/afterglow effects budget
- [ ] Stage 4.2: Implement dirty-rectangle tracking (LVGL invalidation areas and/or ILI9341 CASET/RASET windowing)
- [ ] Stage 4.2: Evaluate/implement DMA overlap + buffering strategy (LVGL flush + SPI transfer overlap)
- [ ] Stage 4.2: Optimize border SDF with precomputed lookup table / SDF map
- [ ] Stage 4.2: Audit 13 mood colors for RGB565 fidelity — corrected palette
- [ ] Stage 4.2: Temporal dithering + gamma correction (only if gradients/banding are visible on hardware)
- [ ] Stage 4.2: Add “perf headroom” knobs (feature kill switches: afterglow/sparkle/edge_glow)

**Evaluation** `[opus]`
- [ ] T1: Automated CI tests (parity check, unit tests, linting)
- [ ] T2: Instrumented benchmarks (frame time, latency, SPI throughput)
- [ ] T3: Developer review — 5 scenarios (idle, conversation, mood sweep, stress, edge cases)
- [ ] T4: Child evaluation protocol (ages 4-6, per eval plan spec)

---

### Personality Engine Implementation

**Spec references**: `specs/personality-engine-spec-stage2.md`, `specs/pe-face-comm-alignment.md`, `specs/face-communication-spec-stage2.md`

**Status (already done)** `[opus]`
- [x] L0 PersonalityWorker + affect vector model + tick loop integration (see Completed → “Personality Engine — Layer 0 Implementation”)
- [x] L0 impulse catalog, idle rules, duration caps, context gate, fast-path processing (unit tested)

**B1 — PE↔Face Compliance Fixes** `[sonnet]` ✅
- [x] Tick loop conversation clamping: during LISTENING/PTT force NEUTRAL@0.3, during THINKING force THINKING@0.5, regardless of PE snapshot freshness (face comm S2 §2.3; alignment §4.5)
- [x] Route planner `emote` actions as PE impulses (do not call `FaceClient.send_state()` directly); face mood must come from PE snapshot (face comm S2 “Layer 3 source updated” note)
- [x] Ensure `personality.event.conv_ended` is emitted on all conversation teardown paths (PTT off, ACTION cancel, AI error/disconnect), not only `AI_CONVERSATION_DONE`
- [x] Add PE intensity caps enforcement (SAD 0.70, SCARED 0.60, ANGRY 0.50, SURPRISED 0.80) so the PE-fresh path is guardrail-safe
- [x] Face send-rate discipline: dedup/throttle `SET_STATE`/`SET_CONV_STATE`/`SET_FLAGS` when unchanged; avoid serial/MCU spam (perf + face smoothness)
- [x] Add `confused` to server canonical emotions and ensure it survives end-to-end (server → ai_worker → tick_loop → personality_worker → face)

**B1b — Guardrail Config + Safety Timers** `[opus]` ✅
- [x] Extend `personality.config.init` to include `{axes, guardrails, memory_path, memory_consent}` and plumb into PersonalityWorker (PE spec S2 §9.5, §14.1)
- [x] Implement RS-1 session time limit (900 s) + RS-2 daily time limit (2700 s): enforcement behavior + “daily” semantics + persistence/reset strategy (PE spec S2 §9.3)
- [x] Expose time-limit state via telemetry + add a child-safe UX path (stop-and-redirect + cooldown) + parent override controls

**B2 — Conversation Schema V2 + Prompt V2 (Layer 1)** `[opus]` _(core schema + guided decoding done)_
- [x] Implement ConversationResponse v2 schema (PE spec S2 §12.3): `inner_thought`, `emotion`, `intensity`, `mood_reason`, `emotional_arc`, `child_affect`, `text`, `gestures`, `memory_tags`
- [x] Normalize target child age range across prompts/specs/eval docs to **age 4–8** (canonical; enforce in system prompt)
- [x] Rewrite CONVERSATION_SYSTEM_PROMPT v2 (PE spec S2 §12.4): 6 sections (personality rules, emotion intensity limits, speech style, safety, response format, examples)
- [x] vLLM schema-guided decoding (PE spec S2 §12.2) for conversation via `GuidedDecodingParams`; eliminates JSON repair loop for conversation
- [x] Set server defaults: `VLLM_MODEL_NAME=Qwen/Qwen3-8B-Instruct-AWQ` and `VLLM_DTYPE=auto` (PE spec S2 §12.1)
- [x] `/converse` websocket protocol: include `mood_reason` with emotion metadata; `ai_worker.py` parsing + forwarding
- [x] Implement conversation history context-budget enforcement (PE spec S2 §12.6): recent window (8 turns), older turns compressed to summary tuples, token budget enforcement
- [x] Harden `/converse` websocket: cap per-utterance `audio_buffer` bytes (~30s / 960KB), reject on overflow with `audio_buffer_overflow` error
- [x] Privacy hardening: `LOG_TRANSCRIPTS=false` by default — conversation text not logged at INFO level; only emotion/intensity/length logged
- [x] Extend `personality.event.ai_emotion` payload forwarding: include `session_id`, `turn_id`, `mood_reason`
- [x] Update PersonalityWorker L1 pipeline (PE spec S2 §13): `mood_reason` validation + modulation factor; rejected reasons substitute THINKING and emit guardrail-trigger event
- [ ] Add `personality.event.memory_extract` emission per turn (memory_tags from v2 schema)
- [ ] Use model chat templates (Qwen) instead of ad-hoc `ROLE: ...` prompting to avoid behavior drift between backends (quality + token efficiency)

**B3 — Personality Profile Injection (server conditioning)** `[opus]` ✅
- [x] Add outbound `personality.llm.profile` from PersonalityWorker (conv start + 1 Hz during conv) and route it to AI worker
- [x] Extend `/converse` protocol to accept `{“type”:”profile”,”profile”:{...}}`; server injects “CURRENT STATE …” system block each turn + anchor reminder every 5 turns (PE spec S2 §12.5, §12.7)

**B4 — Memory System (COPPA)** `[opus]`
- [ ] Implement local memory store per PE spec S2 §8: decay tiers, max 50 entries, eviction, local-only JSON, consent gate default false
- [ ] Memory timestamps: clarify/resolve monotonic-vs-wall-clock for persistence across reboots; implement `boot_id` + wall-clock fallback if needed (may require spec amendment)
- [ ] Dashboard: parent memory viewer + “Forget everything” button (`personality.cmd.reset_memory`) (PE spec S2 §8.5)
- [ ] Apply memory bias term in affect update (step 3) (PE spec S2 §8.3)

**B5 — Prosody** `[sonnet]` ✅
- [x] Route TTS emotion tag from `world.personality_mood` (PE spec S2 §11.5) instead of hardcoding `”neutral”`

**B6 — Evaluation** `[opus]`
- [ ] Add/extend tests: clamping behavior, worker intensity caps, planner-emote impulse routing, conv-ended teardown coverage, `confused` server vocab, schema-v2 parsing, guided decoding compliance
- [ ] Add tests for RS-1/RS-2 time limits, `/converse` overflow/timeouts/disconnects, and “no transcript logs by default” privacy policy
- [ ] PE evaluation checklist: emotional coherence, guardrail compliance, child-safety validation (PE spec S2 §13 + §9 HC/RS)

---

### Reflex MCU Commissioning

**Prerequisite**: ESP-IDF environment, USB-C cable, hardware on breadboard.

**Firmware** `[sonnet]`:
- [x] Pin map verified — GPIO 17/18 (SDA/SCL) confirmed correct; TRIG→GPIO21 and VBAT→GPIO1 already in `pin_map.h`. No firmware change needed.

**Phase 1: IMU (BMI270) — Hardware Validation** `[sonnet]`
- [ ] Hardware bring-up: SSH → supervisor logs → `/status` poll → dashboard Telemetry tab → physical tilt/rotate tests
  - Pass criteria: `BMI270 CHIP_ID=0x24 OK`, `INTERNAL_STATUS=0x01`, no `IMU_FAIL` in first 60 s
  - Flat at rest: `accel_z ≈ 1000 mg`, `accel_x ≈ 0`, `gyro_z ≈ 0`
  - Rotate robot ~45°: `gyro_z` deflects, returns to ~0
  - Tilt ~45°: `accel_x` shifts ~700 mg (0.7g)
- [x] Supervisor derived fields: `tilt_angle_deg` + `accel_magnitude_mg` computed in tick loop, serialized in telemetry (17 unit tests pass)
- [x] Dashboard: "IMU Derived" chart (tilt °, accel |g| mg) in TelemetryTab; accel_z sparkline + tilt readout in MonitorTab IMU card

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
- [ ] Odometry integration (x, y, theta) — integrate `w_meas_mrad_s` → heading θ + `v_meas_mm_s` → x/y
- [ ] Gyro-accel complementary filter — supervisor-side; fuse gyro integral + accel correction for stable heading (prerequisite for heading PID)
- [ ] Full IMU heading hold PID (currently gyro damping only; requires complementary filter first)
- [ ] Accel magnitude shock detection — if `accel_magnitude_mg` spikes >2500 mg, emit `SHOCK` event on event bus (collision awareness) `[sonnet]`
- [ ] Motor-IMU correlation diagnostic — dashboard view comparing `gyro_z` vs `w_cmd` to surface motor/encoder faults `[sonnet]`

---

### Conversation & Voice

- [ ] `[opus]` LLM conversation history/memory — server-side session context
- [ ] `[sonnet]` TTS perf hardening: replace Python-loop resampling in `server/app/tts/orpheus.py` with an efficient resampler; add max utterance duration safeguards
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

- [x] `[sonnet]` Telemetry health panel per device (RTT, offset, drift, seq drops)
- [ ] `[sonnet]` Camera settings panel
- [ ] `[opus]` Personality engine visualization (affect vector, mood anchors, decay curves)

---

### Infrastructure & Tooling

---

## Completed

### Face Communication — Research & Specs
- [x] Face communication spec Stage 1 (research) → `specs/face-communication-spec-stage1.md`
- [x] Face communication spec Stage 2 (implementation-ready, ~1340 lines) → `specs/face-communication-spec-stage2.md`
- [x] Spec revisions: 10 fixes + 3 nits applied, verification pass done
- [x] Face visual language design document → `specs/face-visual-language.md`
- [x] Face communication evaluation plan → `specs/face-communication-eval-plan.md`

### Personality Engine — Layer 0 Implementation
- [x] `supervisor/personality/affect.py`: sigmoid_map, TraitParameters, AffectVector, Impulse, PersonalitySnapshot, update_affect, apply_impulse, project_mood, enforce_context_gate
- [x] `supervisor/workers/personality_worker.py`: L0 rules 01–13, duration caps, idle rules, fast path, all event handlers
- [x] `supervisor/core/event_router.py` + `state.py` + `tick_loop.py`: full PE integration (event forwarding + snapshot → WorldState)
- [x] `supervisor/tests/test_affect.py`: 47 tests covering all affect model math
- [x] `supervisor/tests/test_personality_worker.py`: 44 tests covering all L0 rules, idle rules, duration caps, context gate

### Dashboard
- [x] Per-device clock health panel (`DeviceClockPanel` in `MonitorTab.tsx`): RTT, offset, drift, samples, data age, last seq per MCU

### IMU Derived Fields
- [x] `tilt_angle_deg` + `accel_magnitude_mg` computed in tick_loop, exposed in telemetry + dashboard

### Personality Engine — B1b Guardrail Config + Safety Timers
- [x] `GuardrailConfig` dataclass + `PersonalityConfig` section in `supervisor/config.py` (YAML-loadable)
- [x] Extended `personality.config.init` payload: axes, guardrails, memory_path, memory_consent
- [x] PersonalityWorker consumes guardrail config: toggleable duration caps, intensity caps, context gate
- [x] RS-1 session time limit (900s default): per-conversation timer, guardrail_triggered event, tick_loop wind-down with gentle redirect speech
- [x] RS-2 daily time limit (2700s default): persistent daily counter (JSON, resets on new day), blocks new conversations, guardrail_triggered event
- [x] `personality.cmd.set_guardrail` handler: parent runtime override of limits + `reset_daily` command
- [x] Session/daily time state in personality snapshot → WorldState → telemetry (dashboard-visible)
- [x] Tick loop enforces daily limit gate on `_start_conversation` + session limit wind-down via delayed teardown
- [x] 30 new unit tests: config parsing, guardrail toggles, session/daily timer increments, limit events, persistence, set_guardrail command

### Personality Engine — B3 Personality Profile Injection
- [x] `personality.llm.profile` emitted from PersonalityWorker at conv start + 1 Hz during conversation (PE spec S2 §10.4)
- [x] Tick loop enriches profile with `turn_id`/`session_id` and routes to AI worker via `AI_CMD_SEND_PROFILE`
- [x] AI worker forwards `{"type":"profile","profile":{...}}` over WebSocket to server
- [x] `/converse` WebSocket handler accepts `profile` message type, stores on ConversationHistory
- [x] `_build_current_state_block()`: dynamic CURRENT STATE system block injected before each user turn (mood, intensity, arc, continuity constraint per §12.5)
- [x] Personality anchor (§12.7): 30-token reminder injected every 5 turns to prevent persona drift
- [x] 10 new tests: profile emission timing, payload fields, CURRENT STATE block content, anchor cadence, profile+anchor coexistence

### Personality Engine — B5 Prosody Routing
- [x] `_enqueue_say()` in tick_loop.py: replaced hardcoded `"neutral"` emotion with `self.world.personality_mood` (PE spec S2 §11.5)
- [x] TTS worker already forwards emotion tag to server HTTP POST — no changes needed downstream
- [x] 3 new tests in `test_core.py::TestProsodyRouting`: default neutral, PE mood forwarding, multiple moods

### Personality Engine — B2 Conversation Schema V2 + Guided Decoding
- [x] `ConversationResponseV2` Pydantic model (9 fields: inner_thought, emotion, intensity, mood_reason, emotional_arc, child_affect, text, gestures, memory_tags)
- [x] `CONVERSATION_SYSTEM_PROMPT` v2 rewrite: 6 sections (personality rules, emotion intensity limits, speech style, safety, response format with v2 JSON, 3 examples), target age 4-8
- [x] vLLM guided JSON decoding via `GuidedDecodingParams(json_object=schema)` — eliminates repair loop for conversation; graceful fallback if `GuidedDecodingParams` unavailable
- [x] Server config defaults updated: `Qwen/Qwen3-8B-Instruct-AWQ`, `dtype=auto` (PE spec S2 §12.1)
- [x] `/converse` WebSocket emotion message includes `mood_reason` field
- [x] `ai_worker.py` parses and forwards `mood_reason` from server emotion messages
- [x] `ConversationResponse` dataclass extended with `mood_reason` + `memory_tags` fields
- [x] `parse_conversation_response_content()` accepts both v1 (4 fields) and v2 (9 fields) JSON payloads
- [x] Conversation history context-budget: 8-turn recent window + older turns compressed to `(turn_N: topic, emotion)` summary tuples + token budget enforcement
- [x] Audio buffer overflow protection: 30s/960KB cap, `audio_buffer_overflow` error on exceed
- [x] Privacy: `LOG_TRANSCRIPTS=false` default — conversation text not in server logs
- [x] `personality.event.ai_emotion` payload extended: forwards `session_id`, `turn_id`, `mood_reason` from ai_worker through tick_loop to personality worker

### Personality Engine — B1 PE↔Face Compliance
- [x] Tick loop conversation clamping: LISTENING/PTT → NEUTRAL@0.3, THINKING → THINKING@0.5 (overrides PE snapshot)
- [x] Planner `emote` actions routed as PE impulses (not direct `FaceClient.send_state()`)
- [x] `personality.event.conv_ended` emitted on all teardown paths (PTT off, ACTION cancel, AI done)
- [x] PE intensity caps enforced in PersonalityWorker (SAD 0.70, SCARED 0.60, ANGRY 0.50, SURPRISED 0.80)
- [x] Face send-rate dedup: `SET_STATE`/`SET_CONV_STATE`/`SET_FLAGS` skip when unchanged
- [x] `confused` added to server canonical emotions (end-to-end: server → ai_worker → PE → face)

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

### Face Stage 4.0 — Parity + Hardware Polish
- [x] Suppress conversation border + corner buttons during system overlays (sim + firmware, spec §4.4)
- [x] Fix corner button visuals: right button default MIC→X_MARK, drive icon/state/color from conv state
- [x] Disable corner-button hit-testing + telemetry during system overlays (g_system_mode guard)
- [x] Port Sim V3 face-based system screens to firmware (system_face.cpp: BOOTING, ERROR, LOW_BATTERY, UPDATING, SHUTTING_DOWN)
- [x] Small SDF icon overlays on face: warning triangle, battery bar, progress bar
- [x] Reconcile esp32-face/README.md with current renderer + corner button semantics
- [x] Parity tool: fix false negative for comment-referenced function calls; 235/235 passing
- [x] Justfile: add --passWithNoTests to dashboard test recipe

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
- [x] `/status` skill — git state, hardware detection, top TODO priorities, quick test status
- [x] `specs/INDEX.md` — one-paragraph summaries with section links for all 6 spec files
- [x] CLAUDE.md Key File Paths expanded: workers, mood/expression, conversation AI paths added
- [x] TTS deterministic speech fix: `SpeechPolicy._held` queue retries face-busy intents for 1500ms
- [x] Protocol docs: SET_FLAGS (0x24) + SET_CONV_STATE (0x25) + CONFUSED mood ID 12 added to `docs/protocols.md`
- [x] Border constants parity (`BORDER_FRAME_W`, `GLOW_W`, `CORNER_R`, `BLEND_RATE`) in `check_face_parity.py`
- [x] `docs/architecture.md` — 181-line comprehensive rewrite (was stale 17-line stub)
- [x] `SystemMode::ERROR_DISPLAY` symbol parity — consistent across sim, supervisor, MCU
- [x] LOW_BATTERY supervisor trigger wired: `low_battery_mv` threshold in `SafetyConfig`, `FaceSystemMode.LOW_BATTERY` overlay in `tick_loop.py` `_emit_mcu`
- [x] README spec compliance: model refs (Qwen2.5-3B → Qwen3-8B-AWQ), hardware refs (Jetson → Pi 5), stale In Progress items removed
- [x] `-v2` rename: `supervisor_v2/` → `supervisor/`, `esp32-face-v2/` → `esp32-face/` (~85 files, Python imports, configs, deploy, docs, specs, skills, VSCode)

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
- `[opus]` Speaker personalization (HC-2 compliant): explicit per-child profiles via parent UI; no voice ID / biometric embeddings
- Home Assistant light control via conversation (see `docs/home-assistant-integration.md`)
- Additional modes: LINE_FOLLOW, BALL, CRANE, CHARGING

### Blue-Sky Personality Features
- `[opus]` Homeostatic drives layer (energy/curiosity/social “batteries”) that slowly biases PE impulses over minutes
- `[opus]` Rituals & routines library: parent-scheduled “morning / bedtime / homework” scripts with safe affect arcs
- `[opus]` Curiosity threads (“quests”): bounded follow-ups based on `memory_tags` with decay + consent gate
- `[opus]` Social repair skills: apologize, clarify misunderstandings, de-escalate, and re-engage after frustration
- `[opus]` Story mode: short interactive stories with `emotional_arc` + gestures + prosody (bounded + opt-out)
- `[opus]` Humor timing engine: callbacks, playful patterns, and “inside jokes” without parasocial deepening
- `[opus]` Embodied habits: micro-motions / gaze cues synced to PE mood + sensor context (with strict safety caps)
- `[opus]` Parent-tunable “persona packs”: seasonal themes, catchphrases, preferred activities (opt-in + reversible)

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

| Task Type                     | Model      | Rationale                                           |
| ----------------------------- | ---------- | --------------------------------------------------- |
| Spec writing & interpretation | Opus 4.6   | Requires deep understanding of multi-document specs |
| Architecture decisions        | Opus 4.6   | Trade-off analysis, system-level reasoning          |
| Complex debugging             | Opus 4.6   | Multi-system causality tracing                      |
| Personality engine design     | Opus 4.6   | Psychology-informed design, prompt engineering      |
| PID tuning & control theory   | Opus 4.6   | Mathematical reasoning, parameter sensitivity       |
| Mechanical refactors          | Sonnet 4.6 | Pattern-apply across files (rename, import updates) |
| Test writing                  | Sonnet 4.6 | Well-scoped, pattern-following                      |
| README/doc updates            | Sonnet 4.6 | Factual updates, no design decisions                |
| Parity checks                 | Sonnet 4.6 | Systematic comparison, no judgment calls            |
| Protocol documentation        | Sonnet 4.6 | Transcribe from code to docs                        |
| Linter/config fixes           | Sonnet 4.6 | Mechanical, well-defined                            |

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
