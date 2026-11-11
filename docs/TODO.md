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
- [x] Stage 4.0: Blink parity — eyelids now also cover the edge-glow ring (the floating "eyebrow" line), 2026-11-10; confirm on hardware
- [x] Stage 4.0: THINKING read as angry (inward lid slope = ANGRY cue) — redesigned as one raised brow (spec amended, firmware + sim, 2026-11-10); confirm on hardware
- [ ] Stage 4.0: Tune timing values on hardware: ramp durations, hold times, border alpha curves `[sonnet]`
- [x] Stage 4.0: Face button UX — superseded 2026-11-10: corner buttons replaced by whole-screen tap/long-press with on-device ring + boop (see Stage 4.3)
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

**Stage 4.3 — Ultrareview fixes, perf pass, whole-screen gestures (2026-11-10, code done, NOT yet flashed)** `[opus]`
- [x] Ultrareview fixes 1-10 (PTT drift, press origin, SPSC event queues, whole-frame USB writes + TX mutex, CONFUSED mood, 71.6-min timer wrap, latency avg, gesture duration cap, dead overlay_v2)
- [x] Stuck-amber eyes after ERROR_DISPLAY: colour override now cleared on any system-mode change
- [x] Perf: `-O2` + 240 MHz + 1 kHz tick; fixed-rate frame pacing (`xTaskDelayUntil`) with fixed-step animation catch-up; clear/redraw only dirty rects; span fills (rect/rounded rect/circle), row-wise eyelids, per-column mouth; perf tail `render_us_avg`/`dirty_px_avg` denominators fixed. Before: ~13 FPS, frame work 52.6 ms (live heartbeat 2026-11-10)
- [x] Whole-screen gestures replace corner buttons (spec §9.5 amended): tap / long-press classifier (`touch_gesture.cpp`), long-press ring, finger gaze-follow, local boop; host owns meaning (`tick_loop._on_face_button`); sim V3 + parity updated
- [x] Host-link watchdog (3 s) → local sleepy look-around, host state replayed on return (spec §4.4 amended)
- [x] HEARTBEAT sys tail: reset_reason, boot_count, host_link_lost, min free heap; supervisor logs face soft-resets
- [x] `just test-face-host`: gesture classifier + SPSC queue (ASan/UBSan; TSan clean)
- [x] `just test-face-render`: real `face_ui.cpp` drawing on the host vs a full-clear reference (dirty-rect correctness); `render_harness <dir> moods` dumps mood stills for design review
- [x] Mouth drawn hard-edged (firmware + sim): AA shades shifted hue on the TN panel and streaked along the mouth
- [x] Mouth light/dark banding that moved with the eyes = panel row crosstalk (panel mounted sideways: screen columns are panel rows). Fixed by ILI9341 frame inversion (`PANEL_PRESET = 1`, chosen by eye with `PANEL_TUNE_MODE`; preset 5 also worked). Re-tune with `PANEL_TUNE_MODE` if the panel is ever swapped
- [ ] On-device: flash, then confirm FPS ≈ 30 in heartbeat perf (`window_frames`), and record frame/render numbers vs the 13 FPS baseline
- [ ] On-device: tap / long-press / drag feel with a child-size finger; tune `TOUCH_*` in `config.h` (+ sim) if needed; check ring visibility near screen edges
- [ ] On-device: eyes return to mood colour after an ERROR_DISPLAY; unplug supervisor → sleepy look-around within 3 s → restores on reconnect
- [ ] On-device: blink/eyelid look unchanged after the row-wise eyelid rewrite (should be pixel-identical)
- [x] On-device (2026-11-10): flashed + supervisor deployed (`8573f93`): 31 FPS, frame work ~10 ms (was 52.6), dirty px ~22k (sparkle no longer forces full redraws), cmd latency ~20 ms, clean POWERON boot; USB short writes/flush timeouts only during startup
- [x] Mouth follows the gaze part-way (`GAZE_MOUTH_SHIFT_X/Y` 1.5/0.75 px per gaze unit; visual-language §1.5) — flashed 2026-11-11
- [x] Life motion (visual-language §1.6, 2026-11-11): squash & stretch on eye moves + blink-reopen pop, glance blink on big gaze jumps, 15% double blinks, speech eye pulse + pause glance (ported from the sim), petting (stroke ≥ 160 px → PET event, local content look, host `face.touch.pet` remark w/ 20 s cooldown) — flashed 2026-11-11
- [ ] On-device: judge life motion by eye (stretch not too rubbery, glance blinks not too frequent, pet look reads as content); tune constants in `config.h` + sim
- [ ] **Camera-driven gaze** (not implemented yet): no vision → face gaze path exists today; host gaze comes only from the conversation choreographer / conv state. Needs: a target (ball bearing exists, horizontal only; no person/face detection), bearing → gaze mapping from camera FOV to `MAX_GAZE`, smoothing, and priority vs conversation gaze and local finger-follow (finger wins while touching). Verify on hardware that the eyes point at the target. Blocked on the Pi camera ("camera unavailable: list index out of range" since 2026-11-10 13:20)

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
- [ ] `[sonnet]` Reduce server ping/poll frequency: make requests event-driven + add backoff/debounce so Buddy isn’t “talking non-stop” _(period now configurable + disableable via `planner.plan_period_s` / `planner.enabled` params in dashboard. 2026-11-10 `0d86f7e`: the request carries `new_events` and the server answers a tick with none without calling the model, so the poll is now cheap; the poll itself remains)_

---

### Reflex MCU Commissioning

- [ ] 🔴 `[sonnet]` **Supervisor treats a silent reflex as ready** (2026-11-10): with the board enumerated but sending nothing, the link flapped (`rx stalled 3 s` every 3 s) and the state machine still went BOOT → IDLE between stalls. IDLE should need telemetry actually decoded, not just a port open.
- [ ] `[sonnet]` **Reflex USB console conflict** (2026-11-10): data goes over USB-Serial-JTAG (`app_main.cpp` `usb_serial_jtag_driver_install`, enumerates 303a:1001) but `sdkconfig` has `CONFIG_ESP_CONSOLE_USB_CDC=y`; after an RST press the console took the PHY (303a:0009, `can't set config #1, error -71`) and no tty appeared. Set the console to USB-Serial-JTAG or UART. The dev board must be plugged in by its **USB** socket (the COM socket is a CH343 the Pi has no driver for). Breadboard reports IMU all zeros with no `IMU_FAIL` flag: check.

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
- [ ] 🔴 **Direction-change sequencing — required by the v2 board, not optional** `[sonnet]`
  - _2026-11-09: implemented in `motor.cpp` (PWM→0, expander write + INPUT readback, restore; `MOTOR_DRV` on failure; register M13). Open: the hardware acceptance test below, once a v2 board exists._
  On v2 the four TB6612 direction pins (AIN1/AIN2/BIN1/BIN2) no longer come from
  MCU GPIOs. They come from a **TCA9554A I²C expander (U4)**, so setting a
  direction is an I²C transaction, not a register write: it takes ~100 µs+, and
  the four bits do **not** change simultaneously. Flipping direction while PWM is
  still driving walks the H-bridge through invalid states and shoot-through.
  - Sequence must be: **PWM → 0, write the expander, read back, restore PWM.**
  - This is where the 1.5 A direction-flip transient in `docs/power.md` comes
    from, and the VM rail has only **0.5 V of margin** (5 V against the TB6612's
    4.5 V floor), so a sloppy flip is a brownout, not just a current spike.
  - Accept when: a scripted forward↔reverse sweep on both motors shows no
    `BROWNOUT`, no `IMU_FAIL`, and encoder direction reverses cleanly every time.
- [ ] 🔴 **E-stop sense inverts, and gains a cable-detect input** `[sonnet]`
  - _2026-11-09 groundwork: `PIN_ESTOP_N` (GPIO13) + `PIN_ESTOP_LOOP` (GPIO6) configured as inputs; `motor_estop_ok()` / `motor_estop_cable_present()`; `motor_is_enabled()` = software gate AND `/ESTOP` high. Still open: latching the stop, reporting pressed vs. cable-missing, refusing motion modes._
  v2 makes the e-stop fail-safe (register E3), which flips the polarity firmware
  expects and adds a second signal:
  - `/ESTOP` on GPIO13 is now **active-LOW = stopped**, held low by R4 pulling down.
    HIGH means the normally-closed switch is intact and the robot may run. The old
    code treats high as "not pressed"; that is now "healthy", and low must latch a
    stop rather than being a momentary event.
  - `/ESTOP_LOOP` on **GPIO6** (new) distinguishes the two low cases:
    `loop HIGH + estop LOW` = pressed; `loop LOW` = **cable missing**. Report them
    separately — a missing e-stop cable should surface as a fault, not as a press.
  - The hardware kill is unchanged and does not need firmware: `/ESTOP` low drives
    TB6612 STBY low directly. Firmware is for reporting and for refusing to enter
    motion modes, not for stopping.
  - Accept when: unplugging J7 with the robot idle produces a distinct
    "e-stop cable missing" fault, pressing the button produces "e-stop pressed",
    and both refuse entry into motion modes.
  - See `docs/v2-defect-register.md` §A0 (expander baseline) and §A2 (the
    expander's power-up state is a safety property — it comes up as inputs, with
    R12–R15 100 kΩ pull-downs holding all four lines low).
- [ ] Enable `BRINGUP_OPEN_LOOP_TEST 1` in `app_main.cpp`
- [ ] Verify motor direction matches encoder count direction (both wheels)
- [ ] Verify encoder counts (1440 counts/rev for TT motor)
- [ ] Disable open-loop test, flash full firmware

**Phase 3: Ultrasonic Range Sensor** `[sonnet]`
- [x] Static distance test (100mm, 300mm, 1000mm, 3000mm ± tolerances) — commissioned 2026-04-22 on HC-SR04 with 1k/2k divider on ECHO→GPIO2; accuracy within datasheet (±3mm perpendicular, ±8mm against angled surfaces); no firmware smoothing needed given 100mm hysteresis band
- [x] OBSTACLE fault triggers at <250mm, clears at >350mm with hysteresis — verified via fault_flags transition (bit 6) while sweeping target past thresholds; 250/350 defaults left as-is until motor/arm geometry is final (runtime-tunable via SET_CONFIG 0x40/0x41)

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

**Final Solder Prep — Robot Build** `[sonnet]`
Context: single-rail 5V topology per `docs/power.md` (UPS HAT (B) → Pi + ESP32s + TB6612 VM + sensors). Bench testing is done on the dev board; these items are blockers/gotchas before the final robot is soldered up and running untethered.
- [ ] TB6612 VM bulk cap: 1000 µF electrolytic (≥10V, low-ESR) physically adjacent to the VM pin (short leads, ≤20mm trace) to absorb direction-flip sag — per `docs/power.md` §Topology
- [ ] Motor-current wiring gauge: 22AWG minimum / 20AWG preferred on UPS HAT → TB6612 VM and TB6612 → motor leads; breadboard jumpers will sag under ~1.5A peaks
- [ ] HC-SR04 cable routing: twist 5V/GND pair; separate from motor PWM/direction wires to prevent ultrasonic trigger corruption from switching noise
- [x] Free obsolete `PIN_VBAT_SENSE = GPIO_NUM_1` in `esp32-reflex/main/pin_map.h` _(shipped 2026-04-26, `83e204c`)_ — battery telemetry comes from the HAT's INA219 now, not ESP32 ADC.
- [x] Waveshare UPS HAT (B) INA219 monitor (`WaveshareUpsBMonitor`) _(shipped 2026-04-25/26, `9a89368`/`8a0d5d4`)_ — Phase 2 power monitor plan complete; SoC readout, undervoltage warnings, low-battery speech all live.
- [ ] Dev-board motor bring-up: power the breadboard's 5V rail from the UPS HAT (tap Pi header 5V/GND) — validates the power plan and motor driver simultaneously; bench supply @ 5V/≥3A is the backup if Pi isn't nearby

---

### Conversation & Voice

_3 items complete (LLM session memory, TTS resampler hardening, conversation studio session_id fix) — see archive_
- [ ] **First on-robot voice bring-up (2026-11-10, cad-loop deployed to the Pi):** Flex mic + face + old USB speaker (`UACDemoV10`, set in `/etc/robot-buddy/supervisor.env`; backup `.bak-20261110`) + reflex all connected. Wake word "alexa" fires (scores 0.72 / 0.94, oww_amp low: tune `ear.xvf.asr_out_gain`). Server round trip from the Pi works (STT 0.3 s, LLM 0.8 s, first audio ~1.5 s, faster than real time) **when the GPU isn't contended**. Not yet heard end to end through the robot's own speaker. Resume here.
- [ ] 🔴 `[sonnet]` **Supervisor: no timeout on a conversation turn that never completes.** 2026-11-10: the server's Orpheus stream stalled (GPU starved) and the session stayed open 10 min; a second wake word (0.94) was ignored as "blocked by active session". Add a turn watchdog (no `done` within N s after end-of-utterance → end session, face back to IDLE).
- [ ] `[sonnet]` **Planner `/plan` timeouts from the Pi** (2026-11-10): "LLM timed out generating plan" every ~2 min (`plan_period_s` 120, `PLAN_TIMEOUT_S` 5) even with the GPU free, while a direct `/plan` probe answers in 0.1–0.5 s. Find what the Pi's request carries that the probe does not (prompt length? recent_events?) and whether vLLM keeps generating after the timeout; a timed-out plan overlapping a voice turn pushed LLM latency 0.8 → 6 s. Also: warm-up logs `Failed to parse plan: union_tag_not_found {'emote': 'neutral'}` (gemma emits `{"emote": ...}` without `"action"`). _(The parse failure is fixed: plans are guided by `ModelPlan`'s schema with `action` required, `b35857c`. Quiet ticks no longer call the model at all, `0d86f7e`, which removes most `/plan` load. The timeouts themselves are unexplained: re-check once deployed.)_
- [x] `[sonnet]` **Fault speech never fires** (found and fixed 2026-11-10): `SpeechPolicy` reads `payload["fault_flags"]` but `PlannerEventBus` emits the key as `"flags"`, so every `fault.raised` reads as non-severe and ESTOP / TILT / BROWNOUT are never announced. No test fed a real bus event into the policy. _Fixed: the policy reads `"flags"`; new tests feed `PlannerEventBus` output into it (severe faults speak, CMD_TIMEOUT / STALL / OBSTACLE stay quiet). This turns on fault speech the robot has never actually produced: ESTOP / TILT / BROWNOUT now say "I found a fault, stopping now." — confirm on the bench that it is wanted._
- [x] `[opus]` **Planner speaks about faults** (planner suite, 2026-11-10): on a fault Buddy says "A fault has been raised" (jargon) and "I think I need a little break" (tired-talk the prompt forbids). The supervisor owns fault speech (`SpeechPolicy`, severe faults only, by design). Hide `fault.*` from the planner as the battery events are; forbid fault and tired talk in the prompt; add both to the suite's hard checks. _Done: `fault.*` hidden (a fault tick is quiet for the planner); prompt rules; a targeted note when `faults` is non-empty ("Yay!" while stalled 2/3 → 0/3); suite hard checks for fault talk and "need a break". Left: "I feel like something is up. Let's take a little break." (1/3, passes the check, hints at the fault)._
- [x] `[sonnet]` **Emoji reach TTS** (planner suite, 2026-11-10): planner `say` text carries 🎉 / 🤔 into the speech path. Strip pictographs before TTS for every speech source, and tell the planner prompt not to use them. _Done: `orpheus.speakable()` at `synthesize`/`stream`, covering every source and the espeak fallback; prompt rule added (the model still writes some, so the strip is what holds)._
- [ ] `[opus]` **Planner `recent_says` — held** (2026-11-10): send the last ~3 lines the supervisor actually spoke with the world state, so the stateless planner can avoid repeating itself. Held because the scheduler's cooldowns (3 s any, 12 s same text) plus `new_events` leave 1 reworded repeat in 36 heard lines (`planner_sim`). Revisit if the suite or the bench shows more.
- [ ] `[sonnet]` **Server GPU budget on WSL** (2026-11-10): Windows apps (SolidWorks, browsers) share the 3090 Ti; a full GPU spills to system RAM silently and TTS drops below real time. Local `.env` (untracked): `VLLM_GPU_MEMORY_UTILIZATION=0.42`, Orpheus 0.35 + `ORPHEUS_KV_CACHE_MEMORY_BYTES=805306368` + `ORPHEUS_MAX_MODEL_LEN=4096` + `ORPHEUS_MAX_NUM_SEQS=4`, `MCP_SERVER_URL=http://192.168.55.180:8080/mcp/`. On native Ubuntu re-check: the KV-bytes setting works around a WSL memory-accounting artifact and may be unnecessary; consider `STT_DEVICE=cpu`. The config default `MCP_SERVER_URL` still names the old Pi `.201`. Under WSL the Pi needs a Windows portproxy for :8100.
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
- [x] `[opus]` Vantage video source (2026-11-10): with `--vantage --vantage-video` the vision worker writes each rotated full-res picture into a Vantage `frame_shm` slot (`RB_FRAME_SHM`, default `rb_camera`) before detection, stamped with SensorTimestamp when plausible; the bridge's media worker (aiortc, H.264) encodes it only while a client watches. A rotation change recreates the slot and the media worker follows. Tests: `tests/test_vision_frame_slot.py`; the Vantage side is `~/vantage/supervisor/media_selftest.py`.
- [ ] `[sonnet]` Pi 5 bench gate for `--vantage-video` (operator): install the extra by hand (`uv pip install --python supervisor/.venv/bin/python 'aiortc>=1.9'`; deploy installs base deps only), run with a client watching, and record media-worker CPU and glass-to-glass against `~/vantage/docs/DECISIONS.md` #7 (720p30 under about one core, under about 150 ms). If it passes, add the install to `deploy/install.sh` and `update.sh`; if not, the webrtc-rs sidecar takes over behind the same seam.

---

### Power & Battery

**Phase 1 (shipped 2026-04-21):** `PowerState` chassis + `PiPMICMonitor` (reads `vcgencmd get_throttled` for undervoltage/throttled bits). Planner prompt + speech_policy own low-battery UX; LLM no longer authors sleepy/nap content. Dashboard `PowerPanel` renders the new state. See `docs/power.md`.

**Phase 2 (shipped 2026-04-26):** Waveshare UPS HAT (B) fuel gauge fully integrated. Pi-side power monitor stack now drives all battery UX; reflex `battery_mv` field retired from the wire.
- [x] `[sonnet]` **WaveshareUpsBMonitor** _(2026-04-25, `9a89368`)_: new `PowerMonitor` subclass in `supervisor/devices/power_monitor.py`. Reads INA219 @ `0x43` over `/dev/i2c-1`; derives charging from current sign, SoC from a piecewise-linear 2S 18650 curve. Auto-detected via I²C probe, composes with `PiPMICMonitor` so PMIC undervoltage stays authoritative. `smbus2 >= 0.4` added; new `--power-monitor=ups-b` mode.
- [x] `[sonnet]` **Pi-side rail voltage via `vcgencmd pmic_read_adc`** _(2026-04-26, `50b4329`)_: tolerant parser pulls `3V3_SYS_V` (proxy for overall rail health) into `PiPMICMonitor.voltage_mv`. Refactored the inline subprocess call into a `_run_vcgencmd()` helper shared by `get_throttled` + `pmic_read_adc`.
- [x] `[sonnet]` **Dashboard chart** _(2026-04-26, `826e61d`)_: `RING_METRICS` now supports dot-paths (`power.voltage_mv`); `MonitorTab` + `TelemetryTab` + `DriveTab` all read the nested key. Thresholds re-tuned for 2S 18650 (8.0 / 7.0 / 6.4 V). `power.soc_pct` and `power.current_ma` also added to the ring set for future sparklines.
- [x] `[sonnet]` **Firmware cleanup** _(2026-04-26, `83e204c`)_: dropped `PIN_VBAT_SENSE` and `battery_mv` from `esp32-reflex/main/{pin_map.h,protocol.h,shared_state.h,telemetry.cpp}` — wire format `<hhhhhhHHHB` → `<hhhhhhHHB` (v1: 21→17 bytes, v2: 27→25 bytes), no version-flag bump (coordinated flash + deploy). Supervisor: dropped `RobotState.battery_mv`, `low_battery_mv` config + tick_loop param, legacy fallback in low-battery emit, mock_reflex / protocol_capture / mcp_tools / dashboard `types.ts` references.
- [x] `[sonnet]` **Safety** _(2026-04-26, `bdcd5ad`)_: `apply_safety` zeroes motion when `0 ≤ power.soc_pct ≤ soc_critical_pct` (gate 4); `state_machine.request_mode` refuses entry into motion modes with reason "battery too low — please charge". Face system mode flips to `LOW_BATTERY` on the same SoC threshold for visual cue. Reflex BROWNOUT remains the hard floor.
- [x] `[sonnet]` **`power.soc_warn_pct` / `power.soc_critical_pct` params** _(2026-04-26, `bdcd5ad`)_: registered with defaults 25 / 10. Wired through `_configure_power_policy_from_registry` into `safety.py` (critical → motion gate) and `PlannerEventBus.set_soc_thresholds` (warn-edge + critical-edge emit `power.low_soc_raised` with severity payload, +5% hysteresis). `SpeechPolicy` keys cooldowns + phrases by severity (`power.low_soc_raised:warn` and `:critical`) so warn doesn't silence critical.
- [x] `[sonnet]` **Session capture** _(confirmed 2026-04-25)_: physical fit check on Pi 5 — went with the GPIO-header variant of UPS HAT (B) instead of the pogo-pin version, which sidesteps the CSI-ribbon clearance risk entirely. Fits cleanly.

**Follow-ups (deferred):** Empirical SoC curve refinement against measured 2S 18650 discharge data — the current waypoints in `_SOC_CURVE` are textbook estimates. Run the pack down once or twice on a real load and adjust waypoints if the kid's experience of "low battery" doesn't line up with reality. Cell configuration confirmed 2026-08-06: **2× 18650 Li-ion in series, inside the HAT**, so the 2S curve and the 8.0 / 7.0 / 6.4 V dashboard thresholds are correct as shipped.

---

### Frame & Mechanical (CAD)

> SolidWorks authored on Windows against `smb://freenas2.local/dev/Robots/robot-buddy/CAD/`, rsynced into `CAD/`. Design rules: **`docs/print-dfm.md`** (0.6 mm nozzle, PET-CF structural). Print on P2S. Material palette shared with robot-scout.

- [ ] **Chassis frame** — structural, PET-CF. Shell + ribs, fillet internal corners, model so load runs along layers.
- [ ] **Raspberry Pi 5 holder** — PET-CF; heat-set M2.5 inserts (boss per insert spec, not printed threads).
- [ ] **Tank-tread tensioners** — idler tensioner mechanism; PET-CF structure, slip/adjust fits 0.3–0.4 mm/side, precision on bearings/bushings not on printed features.
- [ ] Populate `CAD/{parts,assemblies,drawings,exports}`; keep vendor/downloaded models in `CAD/library/`.

---

### Frame & Mechanical (CAD)

> **Repo `CAD/` is the master** (Git LFS); SolidWorks works on the Windows mirror via `tools/sw.py push|pull` (`just cad-*`), driven over COM from WSL. See `.claude/skills/solidworks/SKILL.md` and `docs/cad/solidworks-api.md` (ported from fpv250 2026-10-30). NAS share `smb://freenas2.local/dev/Robots/robot-buddy/CAD/` is retired as a working store (backup only). Design rules: **`docs/print-dfm.md`** (0.6 mm nozzle, PET-CF structural). Print on P2S.

**Setup (2026-10-30)**
- [x] CAD tree imported from the NAS snapshot into git (branch `cad`), LFS for authored CAD, vendor raw downloads ignored
- [x] `tools/sw.py` push/pull/probe/refs verified against SOLIDWORKS 32.3.1
- [ ] Repoint Pi 5 `SD CARD` sub-parts off `C:\Users\Ben\Desktop\robots\buddy\model\…` (see skill "Known state"); re-check `sw.py refs`
- [ ] Save the 3 virtual components in `RB-ASM-100_chassis` (`Part2`, `MirrorPart2`, `Part8`) out to `CAD/parts/` with real names

**Chassis: the remaining build.** It holds the MCUs, motors, screen and mic/speaker. Frame spec: `docs/cad/06_frame_design_spec.md` (rear-follower tensioning, 3-piece body: plate / front bulkhead / canopy, plate 170 × 110).
- [ ] **Materials / fasteners / FEA**: `docs/cad/07_materials_fasteners_fea.md`. Measure insert stock (M2.5/M3 OD × L) + screw stock; print **insert ladder coupon** in PET-CF + ASA (07 §4.2); port fpv250 `swsim.cs` → `tools/swsim.cs`; run S1/S2/S5 before the first PET-CF print, S3/S4 with the canopy (07 §3)
- [x] **Assembly rebuild in chassis frame** (06 §2, 2026-10-30): `RB-ASM-101_chassis` + `RB-PRT-001_base_plate` + `TT_Motor_envelope_v2` via `tools/chassis.py rebuild`. Open: delete old `RB-ASM-100` (Ben's OK), measure TT motor widths (interference 🟡)
- [x] **Envelopes first** (2026-10-30, 06 §9): Pi stack, FNK0104 face board, reflex board, TT motor v2 built in `CAD/library/` from known data. Still open: XVF3800 Flex disc + core board and CE40P-8 + back box (need measurements), battery is inside the Pi stack (UPS HAT), TB6612 is on the reflex board or TBD
- [x] **Specify a proper mic + speaker solution**: `docs/audio-hardware.md` (2026-10-30). USB XVF3800 with hardware AEC (reSpeaker Flex Circular-4), Dayton CE40P-8 in a ~30 cc sealed box, PAM8302A only if the Flex amp won't run on 5 V
- [ ] **Buy drivetrain hardware** (2026-11-09): ~~Ø4 × 8 dowel pins~~ (ordered 2026-11-09: uxcell 4 × 8 bearing steel ×100, due 2026-11-10; check the slide into the 624 bore on arrival) and DIN 988 4 × 8 × 0.5 stainless shim rings, pack of 10+ (idler axle stack, 05 amendment). Print RB-PRT-023 idler spacer ×2 with the next PET-CF plate
- [ ] **Order audio parts + bench-validate** per `docs/audio-hardware.md` §7 (enumerate, amp-on-5V, AEC/barge-in, motor noise, SPL cap, USB current, measure boards). Gates the speaker/mic envelopes + mounts
- [ ] Audio software follow-ups (`docs/audio-hardware.md` §8): 2-ch capture + ASR channel select, ALSA card names, keep VAD/wake word live during TTS, `max_volume` hard cap, persist XVF tuning
  - [x] _(2026-11-06, branch `audio-xvf3800` cd92124)_ 2-ch capture + channel select, ALSA `match:<card>` names, XVF3800 USB control client (`supervisor/devices/xvf3800.py`), `ear.event.doa` voice direction (`--xvf-control`), udev rule + pyusb. Needs the bench (§7 step 1) to pick the ASR channel and calibrate the DoA offset
  - [ ] Use the voice direction: face gaze follows the speaker; turn-to-speaker after wake word (planner, safety-gated); speech-energy gate on wake word; fixed beam during a conversation
  - [ ] Mic mute: parent switch on the Flex FPC GPIO, or software only (Ben, before the canopy prints)
  - [x] _(2026-11-06)_ First bench on the Pi (`docs/audio-hardware.md` §7 amendment): `2886:001E`, 6 ch firmware, card `C16K6Ch`, ch 0 = processed ASR (quiet), ch 1 = second processed, ch 2–5 raw mics; FPC orientation catch. Code fix d53bb65. AEC untested until the speaker + amp are wired
- [ ] **Voice pipeline refactor (XVF3800)** `[opus]` (Ben, 2026-11-06). Code on branch `audio-xvf3800` (5f3c098), plan `~/.claude/plans/tranquil-honking-giraffe.md`, contract in `supervisor/PROTOCOL.md` §4.4a / §6.4 / §7.5:
  - [x] One card for capture and playback: persistent clocked playback stream, chimes mixed over speech, lip sync + `finished` on the mixer clock, cancel flushes; `arecord` + `aplay` supervised (USB replug recovers); init + settings replayed on worker restart
  - [ ] Deploy: merge/push the branch, `deploy/update.sh` on the Pi, set `/etc/robot-buddy/supervisor.env` to the Flex line in `deploy/supervisor.env` (voice is down on the Pi until then: it still names the old `UACDemoV10` / `Device` cards). Ben's go-ahead
  - [x] XVF startup config: `ear.xvf.*` params (factory defaults), written each time the board opens, never `SAVE_CONFIGURATION`; `ear.mic_channel` param; mic level in ear health
  - [ ] Tune after mounting: raise `ear.xvf.asr_out_gain` / AGC so ch 0 speech reaches ~−30 dBFS (~30 dB short today); ch 0 vs ch 1 for the wake word
  - [x] `--barge-in` (wake word interrupts speech, full duplex) built behind the flag
  - [ ] Enable `--barge-in` after the echo test with the real speaker + PAM8302A (`docs/audio-hardware.md` §7 step 3)
  - [x] `--max-volume` hard cap (default 80, multiplies with the user volume)
  - [ ] Set `--max-volume` from the SPL test (§5, §7 step 5)
  - [ ] Speech-energy gate against motor false wakes; DoA consumers (face gaze, turn-to-speaker) after mounting + calibration
- [x] **Base plate** rev 1 (2026-10-30, 06 §4.1): `RB-PRT-001_base_plate` generated by `tools/chassis.py` (motor-mount inserts, ribs, Pi-deck posts, reflex standoffs, follower slots + jack stops, rear-corner track relief, bulkhead foot, wire slot). Old `bottom_plate.SLDPRT` superseded. Open: fins on deck posts + rib layout after FEA; bulkhead foot strip only 6.5 mm
- [ ] **Motor mounts** L/R: **fixed** (round holes, no slots); true mirror pair placed on the plate; print on side; confirm Ø on SLDPRT
- [ ] **Screen/face mount**: TFT bezel + touch clearance, viewing angle, USB cable exit
- [ ] **Speaker + mic mounts** per `docs/audio-hardware.md` §4: mic disc hung under the canopy's full-width hump roof, z 110 (2026-11-08, CAD P6m2; the separate pod RB-PRT-005 is dropped), floated on TPU washers, gasketed Ø1.2 mm ports; speaker forward below TFT, sealed box, ≤2 mm grille + mesh; ≥70 mm mic↔speaker
- [ ] **Raspberry Pi 5 holder**: PET-CF; heat-set M2.5 inserts (boss per insert spec, not printed threads)
- [ ] **Tank-tread tensioners** = rear follower carriages per `05_follower_spec.md` (the only tension point); PET-CF structure, slip/adjust fits 0.3–0.4 mm/side, precision on bearings/bushings not on printed features
- [ ] **Printed TPU track system** (decided 2026-10-30, replaces the kit track): TPU belt + D-bore sprocket + 2×624 toothed idler per `docs/cad/08_tpu_track_rnd.md`, generator `tools/drivetrain.py` (branch `drivetrain-rnd`). CAD integration = loop BACKLOG P11–P13 (rev 1: two Ø18 road wheels per side, idler 3 mm below the TT shaft, tread variants pads / bars / smooth). Bench first (08 §7): TT shaft measurements, bore/624/684 coupons, TPU 85A vs 95A strip creep, lug ratchet, tread A/B/C (tilt μ, pivot current, mic noise), step blocks 5–25 mm
- [ ] **Reflex motion limit: deceleration cap ~0.1 g** (08 rev 1 §4): harder braking rocks the robot forward onto the raised sprocket (≤ 6°, the face nods). Belongs with the reflex safety/ramp limits
- [ ] **Drop-off (cliff) sensing** — nothing in the design stops it driving off a stair or table edge (08 §8). Decide: downward IR/ToF at the front corners, or behaviour-only (no tables). Kid-safety item, not drivetrain
- [ ] **Front bulkhead** (06 §5): face TFT (15° tilt), speaker box, HC-SR04, camera; PET-CF
  - [x] **Split the HC-SR04 holder out of RB-PRT-002** _(2026-11-09)_: RB-PRT-070_sonar_holder, box through a window, lips on the face, 2 × M2 × 8 thread-forming from the front (07 F18); knee gusset notched + widened round it (06 §5 amendment). Bulkhead 54.3 g, holder 11.7 g; no interference with each other. Plate `petcf6` (bulkhead + holder, no support)
  - [ ] Before `petcf6` prints: Ben reviews the holder + bulkhead (eyes before electrons); re-run S5 / S5c on the new gusset; buy M2 × 8 pan head thread-forming ×2
- [x] **All bought hardware in RB-ASM-101** _(2026-11-10)_: 138 envelopes (`tools/hardware.py`, `chassis.py hardware_layout()`), bill via `chassis.py hwbom` → 07 amendment. Fixes: F4 clamp M3 × 12, F11 M3 × 6, F12 M3 × 8
  - [x] **Road-axle retention** _(2026-11-10, Ben)_: blind Ø3.95 press bores in the side plate, one DIN 6799 E-clip per axle on the inner 684, Ø6 × 0.9 land for the outer 684 (06 §7 amendment, 07 F20). S9i (all load on the inner disc) added to `tools/fea.py`
    - [ ] Buy 4 × Ø4 × 42 ground shafts with one E-ring groove (1.86 from the end) + E-clips DIN 6799 size 3.2; reprint the track frames
  - [ ] Check the bought idler shoulder bolt: Ø4 × 53.5 shoulder + ≥ 8 mm M3 thread
- [x] **Motor mounts: gearbox end-lug slot** _(2026-11-10, Ben)_: the TT's lug on the gearbox's far end needs the slot his original mounts had (2.9 x 5.4 through the end stop, 7.7-10.6 off the motor face; here +-3.2 about the axis). Added to RB-PRT-010/011 and the lug to `TT_Motor_envelope_v2` (`MOT_LUG_*`); no motor/mount interference
  - [ ] Reprint the mounts (plate `mounts`, 25.5 g / 57 min): the ones on `petcf5` have no slot. Measure the lug (length past the gearbox end, width, height) and confirm the fit
  - [ ] **PETG fit check first** _(2026-11-11, Ben)_: plate `fit` = base plate + both mounts in Polymaker PETG (`just cad-slice --plate fit --mat PETG` → `CAD/exports/print/PETG_fit.3mf`, 120.6 g / 3 h 24 m, 0.6 nozzle, textured PEI, 240 °C). Commit to PET-CF once the mounts, lug slot and plate holes fit
- [x] **PAM8302A amp mount** _(2026-11-10)_: slide-in rails on the canopy's inner left wall, front, beside the speaker (`audio-hardware.md` §2 amendment, `chassis.py` `canopy_amp_lines`)
  - [ ] Measure the PAM8302A in hand (parts within 1 mm of the long edges? header fitted or wires?) before the canopy prints
- [x] **IMU mount** _(2026-11-10, Ben: under the deck)_: BMI270 Qwiic breakout hung under the Pi deck at (−54, 0), parts down, on 4 × M2.5 × 8 + 3 mm spacers into deck inserts (07 F19, 06 amendment). Deck: insert bosses, USB-cable slot → open rear-edge notch, vents start at x −38. Envelope `CAD/library/bmi270_envelope.SLDPRT` (`chassis.py bmi270_lines`)
  - [ ] Measure the breakout (outline, hole Ø + pattern, parts height, which edges the Qwiic connectors are on) and check the J5 cable reaches (~75 mm from J5 at (19, 11.5) to the IMU): a 100 mm Qwiic cable
  - [x] _(2026-11-10, robot-buddy-ae check)_ Reflex USB-C cable: a **straight** plug clears the IMU by 4.4 and its cable bends up through the rear notch with 0 interference. **Not an up-angle plug**: raised 8 mm it hits the IMU (785 mm³). Keep the IMU underside ≥ z 16.4 and the notch at x −76…−68, |y| ≤ 4
- [ ] **Top shell / canopy** (06 §6): ASA white, tool-only opening (cells inside), mic disc on top; access to USB-C charge + power switch
- [ ] Assembly: interference check + mass/CoG; review renders with Ben before any print (eyes before electrons)
- [x] **Reflex PCB: verify + order** (`hardware/kicad/robot-buddy-reflex/`). Re-run ERC/DRC, check footprints/pinouts against the parts actually bought, confirm the outline + M3 holes (now 52.5 × 46, 45.5 × 39 pattern: `board_outline.py`) and connector exits against the frame (06 §3–4) before the plate locks; then order (fab + Canadian shipping). **Connector exits (CAD loop R2c, 2026-10-31):** USB-C on the board's **rear edge (x −40)**, facing the free bay under the Pi deck: the side edges are 0.7 mm from the motor encoders and there is 5.4 mm above the board to the deck; motor leads (6 wires: motor + encoder) on a connector near the mounts (R2b): check whether the encoder TT motors have their own socket on the encoder board (then nothing to add), else an inline 6-pin JST-XH pair so a motor swap doesn't need the deck off (`docs/cad/loop/R2_service.md`)
  - ✅ **2026-11-10: ORDERED at JLCPCB** (Ben): v2 63 × 46 board (M12, `b0adb54`), 4-layer 1.6 mm, lead-free HASL, qty 5, Economic PCBA top side (21 SMD parts, 9 LCSC lines checked against JLC part pages, all value + package match; J5 C160390 is the vertical BM04B). Placement confirmation on: check U4 pin 1 and J5 orientation in JLC's image. Hand-solder: U1, U2 headers, C3, C6, J1, J2, J6, J7, J9. Harness crimp map: `docs/reflex-wiring.md` (motor socket ≠ XH order). USB-C: straight plug, overmold ≤ ~22 mm, cable ≤ 4 mm. Next: bring-up (rail short checks before plugging modules).
  - **(superseded 2026-11-09: the 46 mm board clears the sockets with no notch)** HOLD the order (2026-11-08): the encoder TT's connector stands 8.5 mm inboard of the mount face (to |y| 23.9), past the board's ±30 edges. Plan: notch both side edges over the encoder (board x ≈ 29–45 KiCad, wider to ~19 if the motor is longer than the 75 mm envelope), keeping the 65 × 60 outline elsewhere and all four M3 holes. Top notch is clear of parts (2 traces: ESTOP, ENC_LA); bottom notch needs J10 LED + J11 NeoPixel moved, C3 nudged, +5V / I2C rerouted. Measured (Ben 2026-11-08): connector bottom z 4 (through the PCB plane), motor 75.2 (envelope OK) → **notch needed**: KiCad x ≈ 30–49, y < 7 and y > 53 (chassis x −10…9, |y| > 23). Toolchain (`hardware/kicad/layout_pcb.py` → `route_pcb.py`: kicad-cli + pcbnew 10, kiutils, freerouting 2.0) is not installed on this WSL.
  - ✅ **2026-11-09 (2nd pass): v2 board carries the order-QC fixes and is shrunk to 52.5 × 46, no notches** (TB6612 footprint un-mirrored in `~/kicad-libs`, pad angles, USB-C flush on the rear edge, encoders on +3V3, J10/R10 LED deleted). ERC 0, DRC 0/0, all gates + `pcb_qc.py` pass except the firmware pin map. Outline/holes/chassis position: `hardware/kicad/board_outline.py` (imported by `tools/chassis.py`). Rebuild: `populate_schematic.py` → `layout_pcb.py --fresh` → `route_pcb.py` → `make_fab.py` → `pcb_qc.py`. Detail: `docs/v2-defect-register.md` §M/M11.
  - [x] **Encoder-plug clash (register M12)** _(2026-11-10)_: plug ~2 mm + wires straight out, full socket height → `PLUG_DEPTH` 7; board lengthened to **63 × 46** (rear edge still x −40, front x 23; holes 56 × 39, front standoffs (19.5, ±19.5)); J1/J2 into a front-strip pair of columns. Routed (freerouting 2.1.0), DRC 0/0, `pcb_qc.py` 0 fail / 0 warn.
  - [ ] **Also before ordering:** SolidWorks rebuild of the base plate + `reflex_board_envelope` (relayout done 2026-11-10: 63 × 46, front standoffs moved); C3 = Rubycon 16ZLH1000MEFC10X16 (Ben 2026-11-09; put it in the BOM/footprint, confirm on the datasheet, re-run the register §O ripple numbers; 1.4 mm to the deck, M14); fix the U2 3D proxy (robot-scout `gen_3d_proxies.py`: 20.32×20.32×11); JLC match-review step (all 9 BOM lines now have verified LCSC numbers); Ben looks at `hardware/kicad/robot-buddy-reflex/qc/`
  - [x] **Firmware `pin_map.h` → v2** _(2026-11-09)_: SDA GPIO7 / SCL GPIO8 on a shared `i2c_bus.cpp`, TCA9554A driver (`expander.cpp`), `motor.cpp` direction via the expander with PWM→0 / write / readback / restore, new `Fault::MOTOR_DRV` (bit 7, wired through supervisor + dashboard + PROTOCOL.md). Builds clean; `pcb_qc.py` §3 passes. Register M13
  - **Order QC (2026-11-09, cad-loop, v1 layout; superseded by the line above, kept for the record):** `python3 hardware/kicad/fab_export.py && python3 hardware/kicad/pcb_qc.py` (exits 1 on any FAIL; checks the June order's failure modes: footprint/pinout, silk on pads, plus DRC/ERC/parity, firmware pin map, mechanics, PTH/NPTH split, stale gerbers). Fixed before ordering: **U2 TB6612 footprint/symbol did not match SparkFun's .brd** (pin 16 "VM2" = +BATT sat on a breakout GND pin: dead short; AO1/AO2/GND shuffled); **USB-C (the Pi link) faced a side behind J6/J7** → U1 turned 90°, USB-C flush on the rear edge (R2c done), J8 to the bottom edge, U2 turned 180°; encoders now powered from **+3V3** (A/B straight into non-5V-tolerant GPIO); U3 → **74AHCT1G125** (LVC at 5 V needs 3.5 V in); silk minus mask; separate PTH/NPTH drills; JLC PCBA BOM/CPL (SMD only; U1/U2/THT by hand). Re-routed (freerouting 2.0.1, `FREEROUTING_JAR=...`), 0 DRC errors / 0 unconnected.
  - [ ] Sign-off items printed by `pcb_qc.py` (U1 cluster-pad GPIO labels vs module back silk, motor harness pin order, NeoPixel pin order, C3 ≤ 10×12.5, right-angle USB-C plug in the rear bay, Ben reviews `gerbers/qc/`), then order: 4-layer 1.6 mm, PCBA top side. Buy: 2× 1×8 2.54 mm female headers (U2), 74AHCT1G125 if not via PCBA
  - [ ] `robot-buddy-reflex.step` is stale (this install has no 3D models); regenerate for the CAD envelope (J8 moved to the bottom edge, USB-C at the rear edge)

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
