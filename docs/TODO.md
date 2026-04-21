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
1–7. _(B1–B5 complete)_
8. _(B6 evaluation: pytest extensions + Studio scenario suite complete)_
9. PE child-safety validation (T4 human protocol — see Face Evaluation)

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
_10 items complete (Stage 4.0 spec/port/parity/buttons/gestures/docs) — see archive_
- [ ] Stage 4.0: Hardware visual pass: Sim V3 vs MCU side-by-side on hardware for all 13 moods (confirm “real” reads match spec intent) `[sonnet]`
- [x] Stage 4.0: Bug: face device buttons not working (PTT/ACTION) — LVGL touch callbacks registered on parent instead of canvas_obj; canvas absorbed all events `[sonnet]`
- [ ] Stage 4.0: Mouth parity: device vs Python sim (Sim V3) vs JS sim (Face Mirror) — migrate firmware mouth to sim upper/lower envelope model; accept when scripted side-by-side shows no obvious mismatch in motion `[sonnet]`
- [ ] Stage 4.0: Gesture parity: HEART_EYES mismatch — port sim heart SDF + scale constants (`HEART_SOLID_SCALE`, `HEART_PUPIL_SCALE`) to firmware; accept when side-by-side scripted checks pass `[sonnet]`
- [ ] Stage 4.0: Blink parity on hardware — eyelids must fully occlude eye fill at full closure (no blue eye outline leak during blink) `[sonnet]`
- [ ] Stage 4.0: Refine THINKING face on hardware (currently reads as angry) `[sonnet]`
- [ ] Stage 4.0: Tune timing values on hardware: ramp durations, hold times, border alpha curves `[sonnet]`
- [ ] Stage 4.0: Face button UX: instant on-device confirmation on press; faster yellow LED blink on PTT error `[sonnet]`
- [ ] Stage 4.1: Baseline integrity gate: revert to float `px_blend(..., float alpha)` as active path; keep fixed-point/u8 helpers disabled/commented with A/B notes; baseline build must pass (`just build-face`)
- [ ] Stage 4.1: Protocol correctness: parse `FACE_STATUS` v1 (4B) and v2 (12B) in supervisor; expose `cmd_seq_last_applied` + `t_state_applied_us` in state/debug
- [ ] Stage 4.1: Low-overhead perf instrumentation in firmware: frame/render/stage timing, dirty px, SPI bytes/s, cmd rx→apply latency (stage sample divisor=8, emit 1 Hz)
- [ ] Stage 4.1: HEARTBEAT optional perf tail (length-based, backward compatible); supervisor + protocol capture decode old/new payload lengths
- [ ] Stage 4.1: Baseline benchmark capture (1000 frames each): idle, listening, thinking, speaking+energy, rage/effects; 2026-02-25 avg/max capture complete, p50/p95 + telemetry overhead A/B (<=1% FPS drop) still pending
- [ ] Stage 4.2: Implement dirty-rectangle invalidation (replace unconditional full-canvas invalidate) and verify normal conversation states stay at p95 frame <= 33.3ms, p50 <= 25ms _(state-aware multi-rect invalidation landed in firmware on 2026-02-25; initial A/B captured but idle/listening were confounded by effects flag state; fixed-flags rerun pending)_
- [x] Stage 4.2: Optimize border/icon hot paths (cache/pre-raster hotspot math) and quantify delta in border-heavy scenarios _(A/B validated on hardware 2026-02-25; see Stage 4.2 snapshot below)_
- [ ] Stage 4.2: Optimize afterglow bandwidth (reduced-resolution buffer + upscale blend behind flag) and quantify effect-on/effect-off cost
- [ ] Stage 4.2: Evaluate SPI/LVGL throughput tuning (40/60/80MHz + queue/buffer settings) after dirty-rect landing; keep best measured config
- [ ] Stage 4.2: Validate perf headroom knobs (`afterglow`, `sparkle`, `edge_glow`) with measured impact and document recommended fallback order
- [ ] Stage 4.x: Post-baseline LVGL component spike — corner buttons as LVGL button objects using `LV_SYMBOL`; adopt only if p95 frame time and visual latency are equal/better with no touch/parity regressions (Font Awesome deferred unless spike wins)

Stage 4.1 Baseline Snapshot (2026-02-25, robot `192.168.55.201`, target `1000` frames/scenario)
- `idle`: frame_avg `75.12 ms` (`13.31 FPS`), frame_max `80.45 ms`, border_avg `23.01 ms`, effects_avg `17.16 ms`, dirty_px_avg `9600`
- `listening_proxy` (not direct conv_state=2): frame_avg `74.98 ms` (`13.34 FPS`), frame_max `79.65 ms`, border_avg `23.01 ms`, effects_avg `17.09 ms`, dirty_px_avg `9677`
- `thinking_border`: frame_avg `88.51 ms` (`11.30 FPS`), frame_max `99.54 ms`, border_avg `50.62 ms`, dirty_px_avg `9590`
- `talking_energy`: frame_avg `74.28 ms` (`13.46 FPS`), frame_max `91.11 ms`, mouth_avg `19.60 ms`, border_avg `23.41 ms`, dirty_px_avg `9743`
- `rage_effects`: frame_avg `86.53 ms` (`11.56 FPS`), frame_max `88.88 ms`, mouth_avg `30.66 ms`, border_avg `23.10 ms`, dirty_px_avg `9648`
- Findings: all sampled states miss Stage 4 target (`p95 <= 33.3 ms`, `p50 <= 25 ms`) by a wide margin; `thinking_border` is the clearest hotspot (`border_us_avg` ~2.2x idle/listening)
- Findings: `cmd_rx_to_apply_us_avg` is noisy/unreliable in this run (e.g. `thinking_border` outlier); treat as directional until protocol/telemetry validation task is completed
- Finding: listening scenario is currently a proxy because dashboard `/ws` has no direct `face_set_conv_state` command path for forcing LISTENING (`2`)
- Artifact: raw capture saved at `docs/perf/face_stage4_baseline_2026-02-25.json` (generated from `/tmp/face_stage4_baseline.json`)
- [x] Cross-MCU benchmark harness: shared core (`supervisor/api/mcu_benchmark.py`) + face adapter (`mcu_benchmark_face.py`) + reflex adapter (`mcu_benchmark_reflex.py`); p50/p95 per scenario; compare mode (`--compare A B`, <=1% FPS drop gate); WS commands (`mcu_benchmark.start`/`.cancel`), `GET /debug/mcu_benchmark`, CLI (`just mcu-benchmark --target face ...`); 29 unit tests
- [x] Bounded supervisor debug command for direct `SET_CONV_STATE` via WS (`face_set_conv_state` command) — listening/PTT border states can now be benchmarked directly
- [ ] Next: run face benchmark with harness on hardware (p50/p95 capture) and execute telemetry overhead A/B (`--compare` baseline vs `FACE_PERF_TELEMETRY=0`)
- [ ] Next: execute Stage 4.2 in ROI order using this baseline (`thinking_border`/border cache first, then dirty-rect refinement, then transport tuning)
- [ ] Next: reflex MCU benchmark — run `just mcu-benchmark --target reflex` after commissioning Phase 1+ to validate state rate/jitter baselines

Stage 4.2 Border Hotspot A/B Snapshot (2026-02-25, post-cache firmware + updated supervisor)
- Artifacts:
  - baseline: `docs/perf/face_stage4_baseline_2026-02-25.json`
  - post-cache: `docs/perf/face_stage4_post_border_cache_2026-02-25.json`
- `idle`: frame `75.12 -> 58.04 ms` (`-22.7%`), border `23.01 -> 5.98 ms` (`-74.0%`)
- `listening_proxy`: frame `74.98 -> 58.07 ms` (`-22.6%`), border `23.01 -> 5.98 ms` (`-74.0%`)
- `thinking_border`: frame `88.51 -> 51.59 ms` (`-41.7%`), border `50.62 -> 13.86 ms` (`-72.6%`)
- `talking_energy`: frame `74.28 -> 57.19 ms` (`-23.0%`), border `23.41 -> 6.20 ms` (`-73.5%`)
- `rage_effects`: frame `86.53 -> 69.80 ms` (`-19.3%`), border `23.10 -> 6.10 ms` (`-73.6%`)
- Gate check (border tranche): **pass** (`idle border_us_avg <= 8ms`, `thinking border_us_avg <= 20ms`, `thinking frame_us_avg <= 65ms`)
- Remaining gap: overall Stage 4 conversation-frame target still not met (`p95 <= 33.3 ms`, `p50 <= 25 ms`) and p50/p95 collection is still pending

Stage 4.2 Dirty-Rect A/B Snapshot (2026-02-25, post-dirty firmware + updated supervisor)
- Artifact (pre-dirty): `docs/perf/face_stage4_post_border_cache_2026-02-25.json`
- Artifact (post-dirty): `docs/perf/face_stage4_post_dirty_rect_2026-02-25.json`
- `idle`: frame `58.04 -> 44.21 ms` (`-23.8%`), render `5.37 -> 3.64 ms` (`-32.3%`)
- `listening_proxy`: frame `58.07 -> 43.52 ms` (`-25.1%`), render `5.41 -> 3.54 ms` (`-34.5%`)
- `thinking_border`: frame `51.59 -> 51.96 ms` (`+0.7%`), render `4.53 -> 4.55 ms` (`+0.3%`)
- `talking_energy`: frame `57.19 -> 57.23 ms` (`+0.1%`), render `5.24 -> 5.33 ms` (`+1.7%`)
- `rage_effects`: frame `69.80 -> 69.73 ms` (`-0.1%`), render `6.78 -> 6.86 ms` (`+1.2%`)
- Caveat: idle/listening runs are not apples-to-apples with pre-dirty because `effects_us_avg` dropped from ~17k to ~13 (effects/flags mismatch), so those two gains cannot be fully attributed to dirty-rect changes
- Outcome: keep Stage 4.2 dirty-rect task open; rerun A/B with fixed explicit flags before deciding completion

**Evaluation** `[opus]`
- [ ] T1: Automated CI tests (parity check, unit tests, linting)
- [ ] T2: Instrumented benchmarks (frame time, latency, SPI throughput)
- [ ] T3: Developer review — 5 scenarios (idle, conversation, mood sweep, stress, edge cases)
- [ ] T4: Child evaluation protocol (ages 4-6, per eval plan spec)

---

### Personality Engine Implementation

**Spec references**: `specs/personality-engine-spec-stage2.md`, `specs/pe-face-comm-alignment.md`, `specs/face-communication-spec-stage2.md`

**B1–B5 complete** (31 items archived) — L0, PE↔Face compliance, guardrails, schema v2, profile injection, memory, prosody

**B6 — Evaluation** `[opus]`
_2 items complete (B6 test extensions: guardrail/schema/privacy/RS limits) — see archive_
- [ ] PE evaluation checklist: emotional coherence, guardrail compliance, child-safety validation (PE spec S2 §13 + §9 HC/RS) _(automated guardrail tests pass; child-safety T4 is a human protocol — tracked under Face Evaluation)_
- [ ] `[opus]` Reduce baseline talkativeness (currently “talking non-stop”): review specs + annoyance research; set sane defaults (idle/backchannel frequency, cooldowns, auto-followup) + add tests
- [ ] `[sonnet]` Reduce server ping/poll frequency: make requests event-driven + add backoff/debounce so Buddy isn’t “talking non-stop” _(period now configurable + disableable via `planner.plan_period_s` / `planner.enabled` params in dashboard — event-driven still pending)_

---

### Reflex MCU Commissioning

**Prerequisite**: ESP-IDF environment, USB-C cable, hardware on breadboard.

**Phase 1: IMU (BMI270) — Hardware Validation** `[sonnet]`
- [ ] Hardware bring-up: SSH → supervisor logs → `/status` poll → dashboard Telemetry tab → physical tilt/rotate tests
  - Pass criteria: `BMI270 CHIP_ID=0x24 OK`, `INTERNAL_STATUS=0x01`, no `IMU_FAIL` in first 60 s
  - Flat at rest: `accel_z ≈ 1000 mg`, `accel_x ≈ 0`, `gyro_z ≈ 0`
  - Rotate robot ~45°: `gyro_z` deflects, returns to ~0
  - Tilt ~45°: `accel_x` shifts ~700 mg (0.7g)
- [x] Supervisor derived fields: `tilt_angle_deg` + `accel_magnitude_mg` computed in tick loop, serialized in telemetry (17 unit tests pass)
- [x] Dashboard: "IMU Derived" chart (tilt °, accel |g| mg) in TelemetryTab; accel_z sparkline + tilt readout in MonitorTab IMU card
- [ ] Dashboard: CalibrationTab IMU — add a “bubble level” / balance graphic (pitch/roll + `tilt_thresh_deg` overlay) to illustrate what the IMU tuning is doing `[sonnet]`

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
- [ ] ~~Battery voltage sense (ADC) + sag-aware limiting~~ — obsolete. Reflex can't see the real battery with the current topology (AC → Pi → USB → ESP32s). Pi-side `PiPMICMonitor` shipped as Phase 1; Waveshare UPS HAT (B) fuel gauge is queued as Phase 2. See **Power & Battery** section.
- [ ] Odometry integration (x, y, theta) — integrate `w_meas_mrad_s` → heading θ + `v_meas_mm_s` → x/y
- [ ] Gyro-accel complementary filter — supervisor-side; fuse gyro integral + accel correction for stable heading (prerequisite for heading PID)
- [ ] Full IMU heading hold PID (currently gyro damping only; requires complementary filter first)
- [ ] Accel magnitude shock detection — if `accel_magnitude_mg` spikes >2500 mg, emit `SHOCK` event on event bus (collision awareness) `[sonnet]`
- [ ] Motor-IMU correlation diagnostic — dashboard view comparing `gyro_z` vs `w_cmd` to surface motor/encoder faults `[sonnet]`

---

### Conversation & Voice

_3 items complete (LLM session memory, TTS resampler hardening, conversation studio session_id fix) — see archive_
- [x] `[sonnet]` Streaming LLM → TTS pipeline (2026-04-18): per-sentence TTS with metadata arriving before audio; cuts first-audio latency ~1–3s on multi-sentence replies. Config flag `llm_stream_enabled` (`RB_LLM_STREAM` env, default on). Pipeline capped at 2 TTS calls/turn (first natural sentence + coalesced continuation). `ConversationResponseV2` schema reordered so `text` is last; new `ConversationStreamParser` extracts metadata from the JSON prefix, sentence-segments the text value, emits `MetadataReady`/`Sentence` events. Supervisor side: `ai_worker` sends zero-length frame as explicit EOS on WS `done`; `tts_worker` idle watchdog bumped 0.8→2.0s as safety net. 28 new tests.
- [x] `[sonnet]` Orpheus prosody-tag fix (2026-04-18): verified via tokenizer probe that `<happy>`, `<excited>`, `<sad>`, `<scared>`, `<angry>`, `<surprised>` are NOT special tokens — they BPE-split and get pronounced as literal speech ("happy happy…" / "excited…" leak). Dropped all fake tags, corrected `silly` → canonical `<laugh>` (was broken `<laughing>`), kept `sleepy` → `<yawn>`. Added `EMOTION_HIGH_INTENSITY_CUES` map that applies real paralinguistic tags (`<chuckle>`/`<gasp>`/`<sigh>`/`<groan>`) only when intensity ≥ per-emotion threshold. `apply_prosody_tag` + `OrpheusTTS.stream/synthesize` now take `intensity` kwarg; threaded through converse batch + live paths. 17 new tests.
- [x] `[sonnet]` TTS ring modulator (2026-04-18): phase-continuous sine multiplication for Dalek-ish robot voice. Off by default (`RB_RING_MOD_HZ=0`); configurable at startup (`RB_RING_MOD_HZ`/`RB_RING_MOD_MIX` env) and at runtime (`tts.cmd.set_ring_mod`). Phase tracked in normalised cycles for sample-accurate continuity across chunk boundaries. 8 tests covering disable paths, phase continuity at 30/50/80 Hz, drift stability, dry/wet mix blend.
- [x] `[sonnet]` Bug: conversation studio chat + PTT not working — envelope deserializer pops `session_id` from payload into header field; AI worker read from payload (always empty); fixed to read `envelope.session_id`; added error events + logging for silent failures
- [x] `[sonnet]` Bug: dashboard text chat replied in `espeak` while supervisor speech used Orpheus — implement conversation priority-1 speech arbitration (preempt in-flight `/tts`; hold planner `say` + suppress speech_policy during active sessions)
- [ ] `[sonnet]` Bug: wake word not working — `--wakeword-model` CLI flag added + ear worker now accepts built-in model names (`alexa`, `hey_jarvis`, etc.); `just download-wakewords` downloads them; test on Pi to confirm pipeline works, then diagnose custom model (threshold? audio device?)
- [ ] `[sonnet]` “Quiet mode” while working: pause deterministic speech-policy comments/backchannels (dashboard toggle; ideally without affecting explicit user-initiated turns)
- [ ] `[opus]` Voice consistency: Buddy’s voice sometimes switches between “male” and “female” — investigate why and make voice selection consistent (pin voice/engine + persist config)
  - [x] Server: pin Orpheus model + voice (`ORPHEUS_VOICE` env var → `tara` default; passed to both legacy + vLLM backends; no model fallback)
  - [x] Unit tests: assert voice is pinned for both Orpheus backends (`server/tests/test_tts_pinning.py`)
  - [ ] Validate on Orpheus: 10+ utterances, no voice drift; then check off parent item
- [ ] `[sonnet]` Wake word model: increase recall from 42%→80%+ (n_samples 15k→50k+, augmentation rounds 3→5, speech-heavy negative data, layer_size 64)
- [ ] `[sonnet]` Wake word: record 20–50 real "hey buddy" utterances from family
- [ ] `[sonnet]` Wake word: soak test 1+ hours idle with household noise
- [x] `[sonnet]` Wake word: pin openWakeWord commit, skip tflite, add `just retrain-wakeword`
- [ ] `[sonnet]` Server VRAM: reduce `ORPHEUS_MAX_NUM_SEQS` 8 → 4. Robot is single-user; current headroom on 3090 Ti is only ~1.6 GB free with Qwen + Orpheus + STT large-v3-turbo all loaded. Expected reclaim ~1 GB. Validate no TTS quality/latency regression.
- [ ] `[sonnet]` Server health: reconcile `orpheus_vram_free_gb` (reports ~14 GB free) vs actual `nvidia-smi` free (~1.6 GB). The health field appears to compute "budget available under cap" rather than measured free memory — rename or add a true `gpu_free_vram_gb` field from an `nvmlDeviceGetMemoryInfo` query so false confidence doesn't mask OOM risk.
- [ ] `[sonnet]` Orpheus lifecycle: under `PERFORMANCE_MODE=1`, Orpheus stays permanently resident — `orpheus_idle_timeout_s=8` never unloads. Either the unload path is broken or `orpheus_min_free_vram_gb=10` is effectively dead config. Audit `server/app/tts/orpheus.py` lifecycle and either fix the unload path or remove the now-misleading config knobs.
- [ ] `[sonnet]` Server: add CUDA OOM alerting in `/health` (or a dedicated `/metrics` endpoint) — surface measured VRAM headroom, recent OOM counts, and a warning flag when free VRAM drops below a threshold (e.g. 512 MB). Belt-and-suspenders now that STT runs on GPU alongside LLM+TTS.

---

### Camera & Vision

- [x] `[sonnet]` Arducam IMX708 integration — validated on-hardware 2026-04-19. Sensor detected by libcamera (imx708 @ 4608×2592, ISP via pisp); supervisor vision worker streams at 640×480 BGR888. Fix was runtime config, not code: supervisor venv had `include-system-site-packages = false` so the apt-installed `python3-picamera2` was invisible — flipped the flag to `true` in `supervisor/.venv/pyvenv.cfg`. Default `vision.hfov_deg=66` is correct for the standard Camera Module 3 lens (75° diagonal ≈ 66° horizontal).
- [x] `[sonnet]` Camera calibration/CV settings in dashboard (HSV + min radius + safety thresholds + /video preview + eyedropper)
- [x] `[sonnet]` Mask editor + camera calibration tooling in dashboard (floor + ball exclusion polygons; persisted to `./data/vision_mask.json`)
- [x] `[sonnet]` Upgrade camera settings for new hardware (camera/ISP params + dashboard UI; Picamera2 controls + rotate/FOV/JPEG quality)

---

### Power & Battery

**Phase 1 (shipped 2026-04-21):** `PowerState` chassis + `PiPMICMonitor` (reads `vcgencmd get_throttled` for undervoltage/throttled bits). Planner prompt + speech_policy own low-battery UX; LLM no longer authors sleepy/nap content. Dashboard `PowerPanel` renders the new state. See `docs/power.md`.

**Phase 2 — land when Waveshare UPS HAT (B) arrives:**
- [ ] `[sonnet]` **WaveshareUpsBMonitor**: new `PowerMonitor` subclass in `supervisor/devices/power_monitor.py`. Reads INA219 (typical address `0x43`) over `/dev/i2c-1` for pack voltage + current; derive charging from current sign, SoC from voltage-curve lookup for 2S 18650 (8.4V=100% → 6.0V=0%). Auto-detect via I²C probe in `pick_power_monitor()`; compose with `PiPMICMonitor` so PMIC undervoltage stays authoritative. Add `adafruit-circuitpython-ina219` or `smbus2` to `supervisor/pyproject.toml`.
- [ ] `[sonnet]` **Pi-side rail voltage via `vcgencmd pmic_read_adc`**: parse the labeled output (`3V3_SYS_V`, `3V7_WL_SW_V`) in `PiPMICMonitor.poll()` and populate `voltage_mv` with a meaningful health reading. The current `in*_input` hwmon channels are internal PMIC rails (core/DDR) — not useful. Parser needs to tolerate vcgencmd format drift.
- [ ] `[sonnet]` **Dashboard chart**: switch the `battery_mv` time-series source from legacy `battery_mv` to `power.voltage_mv` (requires supervisor to emit `power.voltage_mv` in the chart's expected key or the chart to read the new nested path). Adjust thresholds for 2S 18650 (6.4V / 7.0V / 8.0V).
- [ ] `[sonnet]` **Firmware cleanup**: delete `PIN_VBAT_SENSE = GPIO_NUM_1` from `esp32-reflex/main/pin_map.h` and the `battery_mv` field from reflex protocol packets (`esp32-reflex/main/protocol.h`, `shared_state.h`, `telemetry.cpp`). Drop `RobotState.battery_mv` + its telemetry key + `_low_battery_mv` config param in the same change. Bump `v_meas`/`w_meas` packet or the reflex protocol version if field sizes shift.
- [ ] `[sonnet]` **Safety**: once SoC is known, wire the `soc_critical_pct` (~10%) threshold into `state_machine.update()` as a "park and refuse motion mode changes" soft-floor. Keep reflex BROWNOUT as the hard floor.
- [ ] `[sonnet]` **`power.soc_warn_pct` / `power.soc_critical_pct` params**: add to `supervisor/api/param_registry.py` with defaults 25 / 10, ranges 10-40 / 5-20. Wire into speech_policy + state_machine gates.
- [ ] `[sonnet]` **Session capture**: physical fit check on Pi 5 — confirm the HAT's pogo-pin stack doesn't foul the CSI ribbon. If it does, order a 15 cm+ ribbon.

---

### Dashboard

- [ ] `[opus]` **Tuning Studio (expand Face tab; consolidate dashboard; built to complete B6)** — one place to tune face parameters (mouth sync), personality, models, server settings, and the full voice pipeline
  - [x] **Dashboard consolidation (no redundant tuning UI)**
    - [x] Re-scope existing `dashboard/src/tabs/FaceTab.tsx` into “Tuning Studio” (keep tab id `face`; rename tab label to “Tuning”)
    - [x] Keep `Monitor` = health overview, `Protocol` = raw packets, `Params` = param registry; avoid duplicating controls across tabs
    - [x] Fold the previously-planned “Personality engine visualization” into this Studio (no separate dashboard feature)
  - [ ] **Face tuning controls (hardware)**
    - [ ] `[sonnet]` Bug: changing gaze in dashboard Tuning tab does not shift face gaze on device
  - [x] **Tuning Studio layout / UX polish** _(UX review complete; all phases implemented)_
    - [x] `[sonnet]` Phase 1: Two-column face tuning layout — Face Mirror (sticky, left) + scrollable face controls column (Face State, Mood, Gestures, System Mode, Talking, Flags, Manual Lock) on right; CSS grid with `@media` breakpoint at ~1024px collapsing to single-column
    - [x] `[sonnet]` Phase 1: Merge Talking + Flags + Manual Lock into a single "Face Options" card (3 cards → 1)
    - [x] `[sonnet]` Phase 1: Compact gesture grid — 4-column layout with smaller buttons; reduce ~200px to ~120px vertical footprint
    - [x] `[sonnet]` Phase 2: Wrap Server Health, TTS Benchmark, Wake Word Workbench in collapsible `<details>` (default closed); Scenario Runner already collapsible
    - [x] `[sonnet]` Phase 2: Add section group headers — "Face Controls", "Conversation", "Personality", "Diagnostics" — with subtle dividers for visual hierarchy
    - [x] `[sonnet]` Phase 2: Extract FaceTab inline styles → `FaceTab.module.css`; add `:hover`/`:focus` states to buttons
    - [x] `[sonnet]` Phase 3: Conversation Studio restructure — separate inputs from outputs (divider or sub-columns); collapse raw event log behind "Show events" toggle (default closed); group device badges and mute toggles on separate lines
    - [x] `[sonnet]` Phase 3: Move Personality Engine closer to Face Mirror area (immediately after face controls, before diagnostics)
    - [x] `[sonnet]` Phase 4: Sticky Face Mirror in single-column mode (`position: sticky; top: 0`) so it stays visible while scrolling controls
    - [x] `[sonnet]` Phase 4: Wide-viewport 3-column layout at >=1440px (mirror | face controls | personality VA scatter)
    - [x] `[opus]` Phase 4: Evaluate sub-tab navigation — not needed; collapsible diagnostics + two-column layout brings visible content well under 1500px threshold
  - [ ] **Accurate Face Mirror (TypeScript port; protocol-driven)**
    - [x] Phase 1-3: Port core sim to `dashboard/src/face_sim/*` — constants, types, SDF, moods, render (eyes+mouth+sparkles), animation state machine (tweens, spring gaze, blink, breathing, idle wander, talking), protocol bridge (SET_STATE/SET_FLAGS/SET_TALKING/GESTURE/SET_CONV_STATE/SET_SYSTEM → FaceState)
    - [x] `FaceMirrorCanvas.tsx` — 320×240 canvas (2x CSS), 30fps rAF loop, live protocol packet ingestion from useProtocolStore
    - [x] Integrated into FaceTab (Tuning Studio)
    - [x] Supervisor: extend `supervisor/api/protocol_capture.py` to name+decode Face `SET_CONV_STATE (0x25)` (required for border parity)
    - [x] Dashboard: allow protocol WS connection while Studio is open (not only on Protocol tab)
    - [x] Phase 4: Gestures & effects — 20 gesture visual overrides (heart eyes SDF, X-eyes cross, rage shake, sleepy droop, peek-a-boo, shy, dizzy, celebrate, etc.), fire particles, afterglow buffer, holiday effects (birthday/halloween/christmas/new year), snow, confetti, rosy cheeks, system mode animations (boot/shutdown/error/battery/updating)
    - [x] Phase 5: Border renderer — conv-state-driven border (8 states: IDLE/ATTENTION/LISTENING/PTT/THINKING/SPEAKING/ERROR/DONE), border SDF frame + inner glow + attention sweep + thinking orbit dots, corner buttons with 6 icon types, energy sync from talking
    - [x] Phase 6: Mirror modes (Live/Sandbox) + deterministic PRNG toggle + FPS selector (30/60) — sandbox dispatch API, simTime threading, mulberry32 PRNG, breathing dt fix
    - [ ] Phase 7 (deferred): Parity harness — TS face sim may replace Python sim as firmware tuning reference; pin TS sim first, then golden-state pixel-diff suite
  - [x] **Conversation harness (multi-input; addresses Conversation & Voice backlog)**
    - [x] Inputs in one panel: physical PTT, dashboard PTT, wake word, text chat (bypass STT), “simulate wake word” button
    - [x] Fix PTT semantics: PTT OFF = `end_utterance` (no immediate teardown; teardown after response)
    - [x] Multi-turn PTT semantics: keep session open; ACTION cancels session; optional idle timeout ends session
    - [x] Supervisor WS commands: `conversation.start` / `conversation.cancel` / `conversation.end_utterance` / `conversation.send_text`
    - [x] AI worker: add `ai.cmd.send_text` (send `{"type":"text"}` to `/converse`) + handle server `assistant_text` → `ai.conversation.assistant_text`
    - [x] Server `/converse`: always emit `assistant_text` before audio; add client `config` (stream_audio/stream_text/debug); support `stream_audio=false` (true text-only)
  - [x] Add a conversation event stream for Studio (avoid bloating 20 Hz telemetry): per-turn transcript (opt-in), emotion/intensity/mood_reason, gestures, memory_tags, timings, errors
  - [x] **Output modes (two toggles)** — mute speaker playback + no-TTS generation both implemented
  - [x] `[sonnet]` Robot volume control — speaker volume is currently fixed + loud (dashboard slider + persisted setting)
  - [x] `[sonnet]` Bug: Pipeline timeline is blank after sending a chat message (verify `/ws/conversation` + ConversationCapture event wiring)
  - [x] `[sonnet]` Bug: Studio device status indicators wrong (mic DOWN when installed; speaker UP when disconnected)
  - [ ] `[sonnet]` Bug: Conversation Studio shows “conversation disconnected”; typing messages doesn’t work; no events shown
  - [x] `[sonnet]` Conversation Studio UX: filter/search events — type-prefix toggles (tts/personality/ear/ai/conv), search, sort, live/pause; personality OFF by default hides 1Hz snapshot spam
  - [ ] `[sonnet]` Conversation Studio UX: evolve into a chat-style transcript UI (text + voice) while keeping raw events for debugging
  - [x] `[sonnet]` Fault TTS: CMD_TIMEOUT + non-severe faults suppressed from speech policy (only ESTOP/TILT/BROWNOUT speak); IDLE mode speech removed entirely; planner gated when idle_state != "awake" or session_limit_reached
  - [ ] `[sonnet]` Session limit scope: `session_limit_reached` currently appears in every personality snapshot; the flag should only gate conversation starts, not influence personality state broadcasts — decouple the two uses
  - [x] **Voice + latency diagnostics**
    - [x] Pipeline timeline per turn: trigger → VAD end → transcription → emotion → first audio chunk → done (+ error states) — `PipelineTimeline.tsx` component + `/ws/conversation` endpoint + `ConversationCapture` + first_audio/assistant_text events
    - [x] TTS benchmark runner: fixed corpus via `/tts`, time-to-first-byte, total synth time, chunk cadence — `TtsBenchmark.tsx` + `supervisor/api/tts_benchmark.py` + WS commands
    - [x] Full-pipeline timing fields: server emits `stt_latency_ms`/`llm_latency_ms`; supervisor forwards those + `roundtrip_ms` on first audio
    - [x] Conversation benchmark runner (text-mode `/converse`): ws_connect + llm + tts_ttfb + total — `supervisor/api/conv_benchmark.py` + `ConvBenchmark.tsx` + WS command
    - [x] Wake word workbench: live score/threshold view + event log + soak-test summary — `WakeWordWorkbench.tsx` + ear worker score streaming + threshold tuning
  - [x] **Personality tuning + B6 completion harness**
    - [x] Personality visualization: VA scatter plot, mood anchors, mood bar, layer/idle/conv badges, guardrail status + last trigger, RS-1/RS-2 session/daily timers
    - [x] Runtime tuning controls: PE axes sliders (5 params), guardrail toggles (3 bools + 2 time limits), debug impulse injection with presets, param registry integration, WS commands (`personality.override_affect`, `personality.set_guardrail`)
    - [x] **B6 scenario suite inside Studio** (scripted conversations + assertions) — `ScenarioRunner.tsx` + `scenarios.ts`: 6 scenarios (4 mock-only + 2 server-required), clamping/routing/teardown/vocab/limits/privacy, collapsible panel with per-step assertion results
  - [ ] **Future-proofing (models/prompt/server settings + prototyping)**
    - [ ] Versioned “prompt packs” selectable per session (no ad-hoc prompt hacking); show active pack in UI + exports
    - [x] Show planner server `/health` snapshot (model ids, backend, timeouts, GPU budget) inside Studio; include in exports
    - [x] **Model template config visibility + vLLM telemetry (Studio)**
      - [x] Server: expose active model name + resolved chat template kwargs (from `server/app/llm/model_config.py`) via `/health` or `/debug/llm` (include family + kwargs + notes + where applied)
      - [x] Supervisor: ingest server model/template snapshot (poll or push) and surface in Studio + exports (so tuning sessions always include “what model + template”)
      - [x] vLLM metrics: add a lightweight `/debug/vllm` snapshot (queue depth, running/waiting requests, token throughput, KV cache usage, GPU mem/util if available) + show in Studio
    - [x] Optional dev-only per-session generation overrides (temperature/max_output_tokens) for fast experiments
  - [ ] **Record / replay / export (diagnose + share + regressions)**
    - [ ] Define `TuningSession.v1` export schema: config snapshots, per-turn messages/metadata, protocol slice, timings/errors
    - [ ] “Record session” (opt-in; default off) + export bundle + replay bundle (offline debugging)
  - [ ] **Deterministic behavior harness (capture + modify + replay) — keep PE + comm tuning reproducible in one place**
    - [ ] Define a “determinism contract”: which subsystems must be deterministic given the same inputs (PE L0, speech policy, conv_state, mood sequencer) + list sources of nondeterminism (LLM/STT/TTS, random backchannel, idle wander)
    - [ ] Studio “Sandbox” mode: apply *temporary* overrides (PE axes/guardrails, speech policy toggles, conv_state timings, face params) without changing prod defaults; export overrides with the session
    - [ ] Deterministic seed controls: make all Studio randomness seedable (face sim, conv_state backchannel scheduling) and always include seed(s) in exports
    - [ ] Replay runner: re-run deterministic subsystems from a recorded session (inputs/events) and diff outputs (face TX stream, PE snapshot, guardrail triggers, speech intents)
    - [ ] Diff UI: show before/after timelines + packet diffs to validate tuning changes quickly
  - [ ] **Recipes + Codex-friendly skills**
    - [ ] Declarative tuning recipe runner (YAML/JSON): set toggles/config → run turns (text/audio) → assertions → export
    - [ ] Supervisor HTTP: list recipes / run recipe (stream progress) / fetch bundles
    - [ ] Add a Codex CLI skill to list/run recipes and summarize failures from exported bundles

---

## Completed

_138 items archived to `docs/TODO-archive.md` (latest: 2026-02-24). Sections: Face specs, PE L0, Dashboard, IMU, PE B1b–B5, Face Sim V3, Stage 4.0, Face phases 0–5, Timestamps, Infrastructure, B6 tests, Conversation & Voice, Camera settings._

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
