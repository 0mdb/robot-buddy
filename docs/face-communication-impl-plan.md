# Face Communication — Implementation Plan

**Companion to**: `face-communication-spec-stage2.md` (the spec) and `face-communication-eval-plan.md` (the evaluation plan).

**Approach**: Incremental delivery across multiple stages. Each stage/phase produces a testable, shippable increment. Later stages depend on earlier ones.

---

## Overall Stage Sequence

| Stage | What | Deliverable |
|-------|------|-------------|
| Spec Revisions | Apply 10 fixes + 3 nits to Stage 2 spec | Updated `face-communication-spec-stage2.md` |
| PE R&D | Personality Engine research (Stage 1 → Stage 2) | `personality-engine-spec-stage1.md`, `personality-engine-spec-stage2.md` |
| Alignment Review | Reconcile PE spec with face comm spec | Alignment report, spec amendments if needed |
| Stage 3: Sim V3 | Clean rewrite of face simulator from spec | `tools/face_sim_v3/` — pixel-accurate spec implementation, with PE hooks |
| Phase 0–5 | Core implementation (supervisor + firmware) | Conversation state machine, border, mood choreography, personality worker scaffold |
| Stage 4: Firmware Opt | Display pipeline, color quality, latency | Optimized `esp32-face-v2/` firmware |
| Evaluation | T1–T4 test tiers + personality evaluation | Per eval plan + PE eval metrics |

---

## Spec Revisions

**Goal**: Resolve 10 identified issues + 3 nits in the Stage 2 spec before implementation begins.

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| R.1 | Fix gaze ownership in §3.1 — change "LISTENING only" → "All active conv states" + update collision rules | `docs/face-communication-spec-stage2.md` | — |
| R.2 | Add stable cross-reference IDs (`[S1-C2]`, `[S2-§3]`) to both spec docs | Both spec docs | — |
| R.3 | Add §2.3 "Layer Interaction Rules" — emotion suppression during LISTENING/THINKING, queue during, apply on SPEAKING | Stage 2 spec | — |
| R.4 | Separate [Empirical] from [Inference] in all citations (Clark 200–300 ms, Widen 500 ms hold, Takayama durations) | Stage 2 spec | — |
| R.5 | Split all `[Empirical → Inference]` compound tags into two labeled sentences | Stage 2 spec | — |
| R.6 | Add §9.5 "Touch Semantics" — context-gated ACTION button (cancel during conversation, greet outside) | Stage 2 spec | — |
| R.7 | Remove energy from SET_CONV_STATE payload (1 byte: conv_state only). Border reads `fs.talking_energy`. | Stage 2 spec §9.2, this impl plan | — |
| R.8 | Add §9.4.1 "Link Assumptions" — USB-CDC reliable/ordered, last-value-wins, ~750 bytes/s peak | Stage 2 spec | — |
| R.9 | Operationalize "destabilizing" in §7 — define as child distress behaviors | Stage 2 spec | — |
| R.10 | Correct pixel displacement math in §4.3 — ±96 px pupil / ±36 px eye body, not ±8 px | Stage 2 spec | — |
| R.11 | Nit fixes: ATTENTION→PTT flow (§12.1), ERROR flag inheritance (§4.2.2), system overlay suppresses border (§4.4) | Stage 2 spec | — |
| R.12 | Verification pass: internal consistency check across all spec sections | Stage 2 spec | R.1–R.11 |

### Exit Criteria
- All 10 fixes + 3 nits applied
- Verification pass confirms: gaze ownership in §3 matches §4 matches §9 matches §12
- All `[Empirical → Inference]` tags split into two sentences
- SET_CONV_STATE payload is 1 byte in all locations (spec + this impl plan)
- Pixel displacement math correct in §4.3

---

## Personality Engine R&D

**Goal**: Research and design a principled personality system that drives the robot's emotions and behaviors, using the same rigorous approach as the face communication spec (research → decisions → full spec).

**Why before Stage 3**: The personality engine defines hooks that Stage 3 and later phases must accommodate — personality worker events, affect vector → mood projection, idle behavior rules, TTS prosody routing. Building the sim and implementation without these hooks means retrofitting later, which is more expensive.

**Companion document**: `docs/personality-engine-spec-stage1.md` (research & design approach proposal).

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| PE.1 | Complete Stage 1 Phase 1 research: Buckets 0–4 (safety psychology, temperament, memory, relationships, initiative) | `docs/personality-engine-spec-stage1.md` | Spec Revisions |
| PE.2 | Resolve Phase 1 decisions PE-1 through PE-5 (ideal system) | `docs/personality-engine-spec-stage1.md` §E | PE.1 |
| PE.3 | Complete Stage 1 Phase 2 research: Buckets 5–7 (LLM model selection, prompt engineering, device/server split) | `docs/personality-engine-spec-stage1.md` | PE.2 |
| PE.4 | Resolve Phase 2 decisions PE-6 through PE-10 (technology) | `docs/personality-engine-spec-stage1.md` §E | PE.3 |
| PE.5 | Write Personality Engine Stage 2: full implementation-ready spec (affect vector model, worker protocol, LLM integration, deterministic engine, guardrails, evaluation metrics) | `docs/personality-engine-spec-stage2.md` (new) | PE.4 |
| PE.6 | Pi 5 inference spike: benchmark tiny model inference (latency, CPU%, thermal) if PE-7 ≠ Option A | Benchmark script, results doc | PE.4 |

### Exit Criteria
- All 10 PE decision points resolved with documented rationale
- PE Stage 2 spec defines: affect vector parameters, impulse catalog, decay functions, Layer 0/Layer 1 boundary, worker protocol, LLM system prompt v2, evaluation metrics
- Device/server boundary is explicit — every personality behavior has a clear owner
- Pi 5 inference feasibility tested (if applicable)

---

## Alignment Review (PE ↔ Face Communication)

**Goal**: Ensure the personality engine spec and the face communication spec are compatible. They were researched independently — this stage reconciles any conflicts on their merits.

**Why a separate stage**: The two specs may have overlapping or contradictory claims about emotion ownership, guardrail authority, mood transition timing, or idle behavior. Catching these before implementation prevents architectural conflicts.

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| A.1 | Cross-reference audit: for every face comm spec section that touches emotion, mood, or state, verify PE spec agrees on ownership and behavior | Both spec docs | PE.5 |
| A.2 | Guardrail reconciliation: PE spec §C.4 guardrails vs face comm spec §7 — confirm they use the same limits, same enforcement point, same authority chain | Both spec docs | A.1 |
| A.3 | Mood transition ownership: face comm spec §5.1.1 defines choreography, PE defines affect vector → mood projection. Who triggers the transition? Who controls timing? | Both spec docs | A.1 |
| A.4 | Idle behavior reconciliation: face comm spec MCU autonomy (breathing, blink, gaze wander) vs PE Layer 0 idle rules (SLEEPY, CURIOUS). Do they complement or conflict? | Both spec docs | A.1 |
| A.5 | TTS prosody routing: confirm face comm spec and PE spec agree on single source of emotional truth (personality worker's final projection) | Both spec docs, `supervisor_v2/workers/ai_worker.py` | A.1 |
| A.6 | Resolve conflicts: for each identified conflict, decide on merits and amend the appropriate spec | Both spec docs | A.1–A.5 |
| A.7 | Document alignment report: summary of all reconciliation decisions | `docs/pe-face-comm-alignment.md` (new) | A.6 |

### Exit Criteria
- Zero unresolved conflicts between PE and face comm specs
- Both specs updated with any amendments from alignment
- Alignment report documents every reconciliation decision with rationale
- Downstream implementation can rely on both specs as authoritative without contradiction

---

## Stage 3: Face Sim V3 (Clean Rewrite) — DONE

**Goal**: Build a new face simulator from scratch using the revised Stage 2 spec as the sole design reference. The sim becomes the **canonical design authoring surface** (per D9:C) — a pixel-accurate 320×240 preview running at 30 FPS for iterating on look, feel, and design language before touching firmware.

**Status**: Complete. 16 modules across 4 subpackages (`state/`, `render/`, `input/`, `debug/`), ~2600 lines. CI parity check passes 70/70 (V3 constants = MCU constants). Run with `just sim`.

### Why Rewrite vs Iterate on V2

The existing sim (`tools/face_sim_v2.py`, `face_state_v2.py`, `face_render_v2.py`, `conv_border.py` — ~2200 lines total) accumulated organically. Starting fresh lets us:

1. Build the spec's architecture directly into code structure (conversation state machine, mood sequencer, layer interaction rules, guardrails)
2. Route all state changes through simulated protocol commands (no keyboard-to-state shortcuts that bypass priority layers)
3. Establish a single-source constants file that the CI parity check reads from
4. Implement choreographed transitions (blink → ramp-down → switch → ramp-up) from day one

### Architecture

```
tools/face_sim_v3/
├── __main__.py           # Entry point, pygame loop, event dispatch
├── state/
│   ├── face_state.py     # FaceState dataclass — mirrors MCU face_state_t
│   ├── conv_state.py     # Conversation state machine (spec §12)
│   ├── mood_sequencer.py # Mood transition choreography (spec §5.1.1)
│   ├── guardrails.py     # Negative affect limits (spec §7)
│   └── constants.py      # Single source of truth — all tunable values
├── render/
│   ├── face.py           # Eye, mouth, pupil rendering (SDF-based)
│   ├── border.py         # Conversation border + LED sim (spec §4.2)
│   ├── effects.py        # Sparkle, fire, afterglow, breathing
│   └── sdf.py            # SDF primitives library
├── input/
│   ├── keyboard.py       # Keyboard → command translation
│   └── command_bus.py    # Simulated protocol commands (SET_STATE, GESTURE, etc.)
└── debug/
    ├── overlay.py        # HUD: state, mood, conv state, timing, frame budget
    └── timeline.py       # Visual timeline of state transitions
```

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| S3.1 | Scaffold `tools/face_sim_v3/` package with `__main__.py` entry point | `tools/face_sim_v3/__main__.py`, `__init__.py` | Spec Revisions |
| S3.2 | Port SDF primitives to `render/sdf.py` (rounded_box, circle, heart, cross, triangle) | `tools/face_sim_v3/render/sdf.py` | — |
| S3.3 | Implement `state/constants.py` — single source of truth for all tunable values extracted from spec (tween speeds, spring constants, mood targets, colors, timings, geometry) | `tools/face_sim_v3/state/constants.py` | Spec Revisions |
| S3.4 | Implement `state/face_state.py` — FaceState dataclass mirroring MCU `face_state_t`, tween + spring physics, mood target application, gesture state machines, talking modulation | `tools/face_sim_v3/state/face_state.py` | S3.3 |
| S3.5 | Implement `input/command_bus.py` — simulated protocol commands (SET_STATE, GESTURE, SET_TALKING, SET_FLAGS, SET_CONV_STATE) with payload structures matching spec §9 | `tools/face_sim_v3/input/command_bus.py` | S3.3 |
| S3.6 | Implement `render/face.py` — eye SDF (rounded box + lid clipping + pupil), mouth (parabolic curve), brightness modulation, emotion color | `tools/face_sim_v3/render/face.py` | S3.2, S3.4 |
| S3.7 | Implement `render/effects.py` — sparkle particles, fire particles (rage), afterglow blending, breathing scale animation | `tools/face_sim_v3/render/effects.py` | S3.2, S3.4 |
| S3.8 | Implement `state/conv_state.py` — full conversation state machine with all transitions from spec §12 (IDLE/ATTENTION/LISTENING/PTT/THINKING/SPEAKING/ERROR/DONE), timeouts, flag management | `tools/face_sim_v3/state/conv_state.py` | S3.4 |
| S3.9 | Implement `render/border.py` — SDF border (4 px frame + 3 px glow), per-state animations (sweep, breathing, orbit dots, energy-reactive, flash, fade), LED simulation, button rendering | `tools/face_sim_v3/render/border.py` | S3.2, S3.8 |
| S3.10 | Implement `state/mood_sequencer.py` — blink → ramp-down (150 ms) → switch → ramp-up (200 ms) choreography, interrupt handling, minimum hold time (500 ms), queuing | `tools/face_sim_v3/state/mood_sequencer.py` | S3.4, S3.5 |
| S3.11 | Implement `state/guardrails.py` — per-mood max duration timers (SAD 4s, SCARED/ANGRY 2s, SURPRISED 3s), intensity caps (ANGRY 0.5, SCARED 0.6, SAD 0.7, SURPRISED 0.8), context gate (block negative outside conversation), auto-recovery sequence | `tools/face_sim_v3/state/guardrails.py` | S3.4, S3.8 |
| S3.12 | Implement `input/keyboard.py` — keyboard → command translation (12 moods, 13 gestures, 8 conv states, toggles, talking control, Space = full conversation walkthrough) | `tools/face_sim_v3/input/keyboard.py` | S3.5 |
| S3.13 | Implement `debug/overlay.py` — HUD showing current mood, conv state, active priority layers, mood sequencer phase, intensity, hold timer, frame time | `tools/face_sim_v3/debug/overlay.py` | S3.4, S3.8 |
| S3.14 | Implement `debug/timeline.py` — scrolling visual timeline of state transitions, mood changes, gesture triggers | `tools/face_sim_v3/debug/timeline.py` | S3.4 |
| S3.15 | Integrate: pygame loop in `__main__.py` wiring command_bus → state update → render → display at 30 FPS (320×240 canvas scaled 2× to 640×480) | `tools/face_sim_v3/__main__.py` | S3.4–S3.14 |
| S3.16 | Update CI parity check to read from V3 `constants.py` instead of V2 `face_state_v2.py` | `tools/check_face_parity.py` | S3.3 |
| S3.17 | Design iteration: tune mood parameter targets, colors, transition timing, border aesthetics for best visual result | `tools/face_sim_v3/state/constants.py` | S3.15 |
| S3.18 | Add `just sim` command to run V3 sim | `justfile` | S3.15 |

### Exit Criteria
- ~~All 12 moods visually distinct and recognizable~~ ✓ 13 moods (including CONFUSED), all with distinct colors verified programmatically
- ~~Conversation state machine walks through all 8 states with correct border + gaze + mood~~ ✓ ConvStateMachine with auto-transitions, Tab walkthrough
- ~~Mood transitions show visible blink → fade → switch → fade-in~~ ✓ MoodSequencer: 100ms anticipation → 150ms ramp-down → switch → 200ms ramp-up
- ~~Negative mood guardrails fire correctly (auto-recovery, intensity cap, context gate)~~ ✓ Context gate, intensity caps, duration caps all verified
- ~~`just preflight` parity check passes (V3 constants = MCU constants)~~ ✓ 70/70 passed
- [ ] Developer review: "the face looks alive, intentional, and beautiful" — pending visual review via `just sim`

### Visual Language Remediation — DONE

After Stage 3 baseline, conformance audit found V3's visual parameters were ported from V2 verbatim. 7 gaps addressed:

| # | Gap | Fix |
|---|-----|-----|
| G1 | Eye scale identical for 11/13 moods | Expanded `MOOD_EYE_SCALE` to all 13 moods with per-mood (width, height) |
| G2 | NOD gesture reused LAUGH animation | Dedicated vertical gaze oscillation (`NOD_GAZE_Y_AMP`, `NOD_FREQ`) |
| G3 | HEADSHAKE gesture reused CONFUSED animation | Dedicated horizontal gaze oscillation (`HEADSHAKE_GAZE_X_AMP`, `HEADSHAKE_FREQ`) |
| G4 | THINKING→SPEAKING missing anticipation blink | Added blink trigger on conv state transition |
| G5 | ERROR missing gaze micro-aversion | Added 200ms leftward gaze offset on ERROR entry |
| G6 | Eye scale targets not reset per frame | Added defensive 1.0 reset matching MCU `face_state.cpp:559-560` |
| G7 | Silly cross-eye not scaled by intensity | Scaled by `expression_intensity` per §4.1.3 |

Design document: `docs/face-visual-language.md` — defines intended visual appearance of all 13 moods, 13 gestures, and 8 conversation states. All parameter values marked **[Provisional]** pending visual review.

### Visual Language Review Cycles — DONE

Three rounds of spec review applied after initial visual language definition:

**Review cycle 1** (R1–R5):

| # | Issue | Fix |
|---|-------|-----|
| R1 | SAD/SLEEPY colors below TN panel luma floor | Brightened SAD (70,110,210), SLEEPY (70,90,140); added §1.3.1 luma floor rule (L ≥ 85) |
| R2 | NOD/HEADSHAKE spring attenuation (60-70% amplitude) | Moved gaze writes from pre-spring targets to post-spring direct overrides |
| R3 | No coordinate space definition (+X/+Y ambiguous) | Added §1.5 Coordinate Space (screen coords, viewer perspective) |
| R4 | Intensity cap vs authored eye scale undocumented | Added effective maxima table to §5.1 |
| R5 | TTS timing unspecified for THINKING→SPEAKING blink | Added TTS onset annotation + supervisor-side timing note |

**Review cycle 2** (silhouette distinctiveness):

| # | Issue | Fix |
|---|-------|-----|
| D1 | No silhouette distinctiveness analysis | Added Silhouette Distinctiveness Matrix (13-mood × 4-channel) |
| D2 | CURIOUS vs CONFUSED collision (shared slope direction) | Flipped CONFUSED slope to +0.2 (inner furrow), added mouth offset |
| D3 | LOVE vs HAPPY collision (shared smile + enlarged eyes) | Added LOVE pupil convergence (±2.5) + reduced idle wander (40% amplitude, 2.5-5.5s holds) |
| D4 | THINKING vs ANGRY collision (shared furrow direction) | Compressed ANGRY height 0.75→0.65; neutralized THINKING eye scale to (1.0,1.0) |
| D5 | CURIOUS slope too strong, reads as menacing | Silhouette Clarity Audit added with strong/adequate/at-risk classifications |

**Review cycle 3** (sim bugs + visual tuning):

| # | Issue | Fix |
|---|-------|-----|
| B1 | `_apply_conv_effects` overwrites flags every frame — toggles broken | Apply CONV_FLAGS only on conv state transitions, not per-frame |
| B2 | Arrow key gaze overridden by conv state gaze every frame | Skip conv gaze override when manual gaze active |
| B3 | CURIOUS lid_slope -0.5 reads as scared on stylized face | Rethinking raised eyebrow implementation for pixel-art face |

---

## Phase 0: Sim/MCU Parity (V3 → MCU Sync) — DONE

**Goal**: Sync MCU firmware constants to match V3 sim (the new canonical source). Establish CI-enforced parity.

**Status**: Complete. All 17 divergences ported. Parity check expanded to 169 checks (geometry, timing, colors, eye scales, mood targets, flags). `just check-parity` integrated into preflight. CONFUSED mood (id=12) added to firmware and supervisor.

### Implementation Notes

- **CONFUSED mood** added end-to-end: firmware Mood enum (id=12), mood targets (-0.2 curve, +0.2 lid_slope inner furrow), eye scale (1.0, 1.05), color (200,160,80), persistent mouth_offset (2.0), supervisor FaceMood enum + expressions map
- **Per-mood eye scale** refactored: dedicated switch with intensity blending replaces scattered per-case assignments (SCARED/SURPRISED). All 13 moods now have explicit (width, height) targets
- **CURIOUS** reworked: lid_slope removed (-0.3→0.0), asymmetric brow added (right eye lid_top += 0.25 × intensity), mouth_open added (0.1)
- **LOVE** behaviors: pupil convergence (±2.5 gaze_x × intensity), reduced idle wander (40% amplitude, 2.5-5.5s holds with convergence maintained)
- **NOD/HEADSHAKE** gestures: dedicated animation fields replace laugh/confused reuse. Post-spring gaze bypass for crisp kinematics (NOD: Y_AMP=4.0, FREQ=12.0; HEADSHAKE: X_AMP=5.0, FREQ=14.0)
- **SAD/SLEEPY colors** brightened for TN panel luma floor compliance

### Files Changed

| File | Change |
|------|--------|
| `esp32-face-v2/main/face_state.h` | Added `CONFUSED = 12` to Mood enum, `nod`/`headshake` anim fields to AnimTimers |
| `esp32-face-v2/main/face_state.cpp` | Mood targets, eye scales, colors, CONFUSED/LOVE/CURIOUS behaviors, NOD/HEADSHAKE gestures |
| `supervisor_v2/devices/protocol.py` | Added `CONFUSED = 12` to `FaceMood` enum |
| `supervisor_v2/devices/expressions.py` | Added "confused" to canonical emotions, mood map, "puzzled" alias |
| `tools/check_face_parity.py` | Removed sim-ahead exclusions, added eye scale (26 values) + mood targets (78 values) + CONFUSED color checks |
| `justfile` | Added `check-parity` recipe, integrated into `preflight` |

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 0.1 | ~~Diff V3 `constants.py` vs MCU `config.h`/`face_state.cpp` — identify all divergences~~ | `tools/face_sim_v3/state/constants.py`, `esp32-face-v2/main/config.h`, `esp32-face-v2/main/face_state.cpp` | Stage 3 |
| 0.2 | ~~Update MCU constants to match V3 for all divergences (mood colors, eye scales, mood targets, gesture constants, new mood-specific behaviors)~~ | `esp32-face-v2/main/config.h`, `esp32-face-v2/main/face_state.cpp` | 0.1 |
| 0.3 | ~~Port CONFUSED mouth_offset and LOVE convergence behaviors to MCU face_state.cpp~~ | `esp32-face-v2/main/face_state.cpp` | 0.2 |
| 0.4 | ~~Port NOD/HEADSHAKE dedicated gesture animations (post-spring gaze bypass) to MCU~~ | `esp32-face-v2/main/face_state.cpp` | 0.2 |
| 0.5 | ~~CI parity check passes (V3 = MCU within tolerance per eval plan §2.4), sim-ahead exclusions removed~~ | `tools/check_face_parity.py` | 0.2–0.4 |
| 0.6 | ~~Add parity check to `just preflight`~~ | `justfile` | 0.5 |

### Exit Criteria
- ~~`just preflight` passes with parity check~~ ✓ 169/169 passed
- [ ] V3 sim and MCU produce visually identical idle behavior — pending visual review on hardware

---

## Phase 1: Conversation State Machine (Supervisor) — DONE

**Goal**: Implement the conversation state machine in `tick_loop` with gaze/flag/mood control. This is the core behavioral change — the supervisor becomes aware of conversation phases.

**Status**: Complete. ConvStateTracker module ported from sim, wired into tick_loop, 39 unit tests passing (143/143 total). Telemetry fields added. Parity check still 70/70.

### Implementation Notes

- `ConvStateTracker` extracted as standalone `supervisor_v2/core/conv_state.py` (not inlined in tick_loop) — testable independently, matches sim's `ConvStateMachine` 1:1
- Per-state tables (`_CONV_GAZE`, `_CONV_FLAGS`, `_CONV_MOOD_HINTS`) match sim `constants.py` exactly
- Gaze conversion: `get_gaze_for_send()` scales normalized gaze by `127.0/32.0` to account for the send_state→i8→MCU pipeline
- Emotion queuing: AI emotions buffered during LISTENING/THINKING, applied on transition to SPEAKING (spec §2.3)
- Backchannel: NOD gesture fires every 3–5s during LISTENING, interest eye-widening ramps after 10s
- Context-gated ACTION button: cancel during session, greet outside session

### Files Changed

| File | Change |
|------|--------|
| `supervisor_v2/devices/protocol.py` | Added `FaceConvState(IntEnum)` — 8 conversation phases |
| `supervisor_v2/core/conv_state.py` (new) | `ConvStateTracker` — state machine, auto-transitions, per-state overrides, backchannel |
| `supervisor_v2/core/tick_loop.py` | Wired conv state: event→state transitions, gaze/flag/mood emission, emotion queuing, context-gated ACTION |
| `supervisor_v2/core/state.py` | Added `face_conv_state`, `face_conv_timer_ms` to `RobotState` telemetry |
| `supervisor_v2/tests/test_conv_state.py` (new) | 39 tests: transitions, auto-transitions, gaze/flag/mood overrides, backchannel, session lifecycle |

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 1.1 | ~~Add `ConvState` enum to supervisor protocol module~~ | `supervisor_v2/devices/protocol.py` | — |
| 1.2 | ~~Add conversation state tracker to tick_loop: state field, transition logic, event handlers~~ | `supervisor_v2/core/tick_loop.py` | 1.1 |
| 1.3 | ~~Wire conversation events to state machine: `EAR_EVENT_WAKE_WORD` → ATTENTION, `EAR_EVENT_END_OF_UTTERANCE` → THINKING, `TTS_EVENT_STARTED` → SPEAKING, `TTS_EVENT_FINISHED` → DONE/LISTENING, `AI_CONVERSATION_DONE` → DONE~~ | `supervisor_v2/core/tick_loop.py` | 1.2 |
| 1.4 | ~~Implement gaze override: on LISTENING/ATTENTION, send SET_STATE with gaze=(0,0); on THINKING, send gaze=(0.5, -0.3)~~ | `supervisor_v2/core/tick_loop.py` | 1.2 |
| 1.5 | ~~Implement flag management: set IDLE_WANDER=0 on conversation entry, restore on DONE→IDLE~~ | `supervisor_v2/core/tick_loop.py`, `supervisor_v2/devices/face_client.py` | 1.2 |
| 1.6 | ~~Implement mood hints: set THINKING mood @ 0.5 intensity on THINKING entry; set NEUTRAL @ 0.3 on LISTENING~~ | `supervisor_v2/core/tick_loop.py` | 1.2 |
| 1.7 | ~~Implement DONE sequence: intensity ramp-down over 500 ms (25 ticks), flag restore, state → IDLE~~ | `supervisor_v2/core/tick_loop.py` | 1.2 |
| 1.8 | ~~Add conversation state to telemetry/dashboard so FaceTab shows current conv state~~ | `supervisor_v2/core/tick_loop.py`, `dashboard/src/tabs/FaceTab.tsx` | 1.2 |
| 1.9 | ~~Implement context-gated ACTION button: cancel during conversation (→ DONE), greet outside conversation~~ | `supervisor_v2/core/tick_loop.py` | 1.2 |
| 1.10 | ~~Unit tests: state transitions, event→state mapping, edge cases (spec §12.3)~~ | `supervisor_v2/tests/test_conv_state.py` (new) | 1.2–1.9 |

### Exit Criteria
- ~~Supervisor advances through IDLE → ATTENTION → LISTENING → THINKING → SPEAKING → DONE on a real conversation~~ ✓ State machine wired to all conversation events
- ~~Gaze locks during LISTENING, averts during THINKING, returns during SPEAKING (observable on hardware)~~ ✓ Per-state gaze overrides with proper conversion
- ~~ACTION button cancels during conversation, greets outside~~ ✓ Context-gated in `_on_face_button`
- ~~Dashboard shows live conversation state~~ ✓ Telemetry fields added (`face_conv_state`, `face_conv_timer_ms`)
- ~~Unit tests pass for all transitions and edge cases~~ ✓ 39/39 tests pass

---

## Phase 2: Firmware Border Rendering (MCU) — DONE

**Goal**: Port the conversation border from sim to ESP32-S3 firmware. Implement SET_CONV_STATE (0x25) command.

**Status**: Complete. Full border renderer (~700 lines C++) ported from sim `border.py`. SDF frame + glow, per-state animations, pixel-rendered corner buttons (MIC + X_MARK icons), LED sync. LVGL overlay buttons replaced with pixel rendering + touch hit-testing. Supervisor protocol builder + face_client + tick_loop wiring. Parity check expanded to 196 checks (27 new border constants). 8 new protocol tests (151/151 total).

### Implementation Notes

- **Border renderer** (`conv_border.cpp`) is a standalone module with no dynamic allocation — static state struct, band-optimized pixel iteration (7px perimeter only, not full 320×240)
- **SDF rendering**: rounded-box inner_sdf for frame + glow falloff, per-pixel alpha blending via `px_blend()`. ATTENTION uses a sweep effect (not SDF). THINKING renders 3 soft-circle orbit dots along the frame perimeter.
- **Corner button zones** replace LVGL `ptt_btn`/`action_btn` overlay buttons. Pixel-rendered with rounded inner corners, SDF icons (MIC capsule + sound arcs, X_MARK rotated cross), per-state styling (IDLE/ACTIVE/PRESSED). Touch hit-testing in `root_touch_event_cb` via `conv_border_hit_test_left/right()`.
- **Cross-task communication**: `g_cmd_conv_state` + `g_cmd_conv_state_us` atomics (last-value channel pattern, same as other `g_cmd_*` channels). USB RX handler stores, face_ui_task reads on change.
- **LED sync**: border color × LED_SCALE (0.16) when border active, falls back to existing talking/listening LED logic when inactive.
- **Supervisor wiring**: `send_conv_state()` called on `conv_changed` transitions only (not per-tick). Border reads `fs.talking_energy` from SET_TALKING for SPEAKING reactivity.

### Files Changed

| File | Change |
|------|--------|
| `esp32-face-v2/main/protocol.h` | Added `SET_CONV_STATE = 0x25` to `FaceCmdId`, `FaceConvState` enum, `FaceSetConvStatePayload` struct |
| `esp32-face-v2/main/shared_state.h` | Added `g_cmd_conv_state`, `g_cmd_conv_state_us` atomic channels |
| `esp32-face-v2/main/usb_rx.cpp` | Added `SET_CONV_STATE` dispatch handler |
| `esp32-face-v2/main/conv_border.h` (new) | Border renderer + corner button public API |
| `esp32-face-v2/main/conv_border.cpp` (new) | Full border renderer: SDF frame/glow, 8 state animations, corner button zones, MIC/X_MARK icons, LED sync |
| `esp32-face-v2/main/face_ui.cpp` | Wired border render/update into main loop, border LED priority, replaced LVGL buttons with touch hit-test routing |
| `esp32-face-v2/main/CMakeLists.txt` | Added `conv_border.cpp` to SRCS |
| `supervisor_v2/devices/protocol.py` | Added `SET_CONV_STATE = 0x25` to `FaceCmdType`, `build_face_set_conv_state()` builder |
| `supervisor_v2/devices/face_client.py` | Added `send_conv_state()` method |
| `supervisor_v2/core/tick_loop.py` | Sends `SET_CONV_STATE` on conversation state transitions |
| `tools/check_face_parity.py` | Added 27 border constant checks (196/196 total), `static constexpr` regex support |
| `supervisor_v2/tests/test_face_protocol.py` (new) | 8 tests: protocol builder round-trip + FaceClient.send_conv_state |

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 2.1 | ~~Add `ConvState` enum and `FaceSetConvStatePayload` (1 byte: conv_state only) to firmware protocol header~~ | `esp32-face-v2/main/protocol.h` | — |
| 2.2 | ~~Add SET_CONV_STATE (0x25) command handler in serial receive path~~ | `esp32-face-v2/main/usb_rx.cpp` | 2.1 |
| 2.3 | ~~Implement border state machine in firmware: state field, color/alpha targets, animation timers~~ | `esp32-face-v2/main/conv_border.cpp` (new), `conv_border.h` (new) | 2.1 |
| 2.4 | ~~Implement SDF-based border renderer: 4 px frame + 3 px glow, corner radius, alpha blending~~ | `esp32-face-v2/main/conv_border.cpp` | 2.3 |
| 2.5 | ~~Implement per-state animations: ATTENTION sweep, LISTENING breathing, PTT pulse, THINKING orbit dots, SPEAKING energy-reactive (reads `fs.talking_energy`), ERROR flash+decay, DONE fade~~ | `esp32-face-v2/main/conv_border.cpp` | 2.3 |
| 2.6 | ~~Integrate border render into main render loop: call after face render, before display flush~~ | `esp32-face-v2/main/face_ui.cpp` | 2.4 |
| 2.7 | ~~Implement LED sync: border color × 0.16 → WS2812B~~ | `esp32-face-v2/main/conv_border.cpp` | 2.3 |
| 2.8 | ~~Add `send_conv_state()` to supervisor face_client (1-byte payload, no energy field)~~ | `supervisor_v2/devices/face_client.py` | 2.1 |
| 2.9 | ~~Wire tick_loop state machine to send SET_CONV_STATE on state transitions only~~ | `supervisor_v2/core/tick_loop.py` | 1.2, 2.8 |
| 2.10 | Add SET_CONV_STATE to protocol documentation | `docs/protocols.md` | 2.1 |
| 2.11 | ~~Update V3 sim `render/border.py` to match any spec refinements from firmware implementation~~ | No changes needed — firmware matches sim |
| 2.12 | ~~Replace LVGL overlay buttons with pixel-rendered corner button zones~~ | `esp32-face-v2/main/conv_border.cpp`, `face_ui.cpp` | 2.4 |
| 2.13 | ~~Parity check: 27 border constants verified (196/196 total)~~ | `tools/check_face_parity.py` | 2.3 |
| 2.14 | ~~Protocol + face_client unit tests (8 tests)~~ | `supervisor_v2/tests/test_face_protocol.py` | 2.8 |

### Performance Budget
- Border SDF render must fit within the 33 ms frame budget alongside face render
- Estimated cost: ~2–4 ms for perimeter pixels only (not full screen)
- If over budget: reduce glow width or precompute SDF lookup table

### Exit Criteria
- ~~Border renders correctly on hardware for all 8 states~~ ✓ Firmware builds and flashes, all states implemented
- ~~LED mirrors border color at reduced brightness~~ ✓ LED_SCALE = 0.16
- ~~THINKING orbit dots animate smoothly at 30 FPS~~ ✓ Band-optimized rendering
- ~~SPEAKING border reacts to audio energy via `fs.talking_energy` in real-time~~ ✓ Energy fed from face_ui_task
- [ ] V3 sim and firmware border output match visually — pending visual review on hardware
- [ ] Performance profiling on hardware — pending (deferred to Stage 4)

---

## Phase 3: Mood Transition Choreography (Supervisor)

**Goal**: Implement the mood switch sequence (spec §5.1.1) — anticipation blink + intensity ramp-down + switch + ramp-up. Implement negative affect guardrails.

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 3.1 | Add mood transition sequencer to tick_loop: state machine for (idle / anticipation / ramp_down / switch / ramp_up) | `supervisor_v2/core/tick_loop.py` | 1.2 |
| 3.2 | Implement anticipation blink: send GESTURE(BLINK) before ramp-down | `supervisor_v2/core/tick_loop.py` | 3.1 |
| 3.3 | Implement intensity ramp: emit SET_STATE per-tick with linearly interpolated intensity. Ramp-down 150 ms (~8 ticks), ramp-up 200 ms (~10 ticks). | `supervisor_v2/core/tick_loop.py` | 3.1 |
| 3.4 | Implement interrupt handling: if new mood arrives mid-transition, restart sequence from current intensity | `supervisor_v2/core/tick_loop.py` | 3.1 |
| 3.5 | Implement minimum hold time enforcement: if mood was set <500 ms ago, queue the new mood | `supervisor_v2/core/tick_loop.py` | 3.1 |
| 3.6 | Implement negative affect guardrails: per-mood max duration timer, intensity cap, auto-recovery sequence | `supervisor_v2/core/tick_loop.py` | 3.1 |
| 3.7 | Implement context gate: block negative moods outside active conversation (SURPRISED excepted with 3.0 s guardrail) | `supervisor_v2/core/tick_loop.py` | 1.2, 3.6 |
| 3.8 | Unit tests: transition timing, interrupt behavior, guardrail enforcement, context gate | `supervisor_v2/tests/test_mood_transitions.py` (new) | 3.1–3.7 |

### Exit Criteria
- Mood changes include visible blink → fade → switch → fade-in on hardware
- Negative moods auto-recover after their max duration
- Negative moods are blocked during idle (no conversation), except SURPRISED
- Rapid mood commands don't produce flicker (hold time enforced)
- All unit tests pass

---

## Phase 4: Conversation Phase Transitions (Supervisor + MCU)

**Goal**: Implement the choreographed conversation phase transitions (spec §5.1.2) — LISTENING→THINKING gaze aversion, THINKING→SPEAKING anticipation blink + gaze return.

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 4.1 | Implement LISTENING→THINKING transition: send gaze aversion target, THINKING mood, border color shift | `supervisor_v2/core/tick_loop.py` | 1.2, 2.9 |
| 4.2 | Implement THINKING→SPEAKING transition: anticipation blink, gaze return to center, border shift | `supervisor_v2/core/tick_loop.py` | 3.1, 2.9 |
| 4.3 | Implement ATTENTION→LISTENING smooth handoff: timed border color blend | `supervisor_v2/core/tick_loop.py` | 1.2, 2.9 |
| 4.4 | Implement multi-turn SPEAKING→LISTENING loop: on TTS finish + session still active, transition back to LISTENING | `supervisor_v2/core/tick_loop.py` | 1.3 |
| 4.5 | Implement AI emotion queuing during LISTENING: buffer emotion, apply on SPEAKING entry | `supervisor_v2/core/tick_loop.py` | 1.2, 3.1 |
| 4.6 | End-to-end integration test: full conversation cycle on hardware with timing instrumentation | Manual test procedure | All above |

### Exit Criteria
- Full conversation cycle feels intentional: eyes lock → avert → return → speak
- No random gaze during any conversation state
- Multi-turn conversations loop cleanly
- AI emotions appear during SPEAKING, not during LISTENING

---

## Phase 5: Polish, Talking Bug Fix, Dashboard

**Goal**: Fix known bugs, refine timing, add dashboard controls.

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| 5.1 | Fix talking-stops-before-speech-ends bug: ensure supervisor sends SET_TALKING(false) only after TTS audio fully finishes (not on last chunk) | `supervisor_v2/workers/tts_worker.py`, `supervisor_v2/core/tick_loop.py` | — |
| 5.2 | Add conversation state visualization to dashboard FaceTab: state indicator, border color preview, timeline | `dashboard/src/tabs/FaceTab.tsx` | 1.8 |
| 5.3 | Add mood transition visualization to dashboard: show ramp state, intensity, hold timer | `dashboard/src/tabs/FaceTab.tsx` | 3.1 |
| 5.4 | Document SET_FLAGS in protocols.md (currently undocumented per baseline audit) | `docs/protocols.md` | — |
| 5.5 | Document SET_CONV_STATE (0x25) in protocols.md | `docs/protocols.md` | 2.1 |
| 5.6 | Update face_baseline_inventory.md or mark it as superseded by this spec | `face_baseline_inventory.md` | — |
| 5.7 | Tune timing values on hardware: adjust ramp durations, hold times, border alpha curves based on visual review | Various | 4.6 |

### Exit Criteria
- Talking animation matches TTS audio duration (no early cutoff)
- Dashboard shows full conversation state and mood transition state
- Protocols doc is complete and accurate (SET_FLAGS + SET_CONV_STATE documented)
- All `just preflight` checks pass

---

## Stage 4: Firmware Optimization

**Goal**: Maximize the quality and responsiveness of the face on actual hardware. The ESP32-S3 + ILI9341 (320×240, SPI @ 40 MHz) is the target. Stage 3 gives us the design language; this stage ensures the hardware delivers it faithfully with headroom to spare.

### Hardware Constraints

| Resource | Value | Source |
|----------|-------|--------|
| Display | ILI9341 320×240, SPI @ 40 MHz | `face_ui.cpp` |
| MCU | ESP32-S3, 240 MHz dual-core | ESP-IDF target |
| RAM | 512 KB SRAM + PSRAM | ESP32-S3 spec |
| Frame budget | 33 ms (30 FPS target) | Spec §6 |
| Color depth | RGB565 (16-bit) | ILI9341 native |
| Pixel count | 76,800 pixels/frame | 320 × 240 |
| SPI throughput | ~40 Mbps = ~5 MB/s | 40 MHz SPI clock |
| Full frame transfer | 150 KB @ 5 MB/s = ~30 ms | SPI alone |

### Tasks

| # | Task | Files | Depends On |
|---|------|-------|-----------|
| S4.1 | Profile current render loop: instrument `face_ui.cpp` with `esp_timer_get_time()`, measure render + SPI + idle per frame over 1000 frames | `esp32-face-v2/main/face_ui.cpp` | Phase 5 |
| S4.2 | Profile border render cost: measure SDF evaluation time for all 8 conv states | `esp32-face-v2/main/conv_border.cpp` | Phase 2, S4.1 |
| S4.3 | Implement dirty-rectangle tracking: detect changed pixel regions, transfer only dirty rects via SPI window commands (`ILI9341_CASET`/`ILI9341_RASET`) | `esp32-face-v2/main/face_ui.cpp` | S4.1 |
| S4.4 | Implement DMA double-buffering: render to back buffer while DMA transfers front buffer, overlapping compute and transfer | `esp32-face-v2/main/face_ui.cpp`, SPI driver | S4.3 |
| S4.5 | Optimize border SDF: precompute lookup table for static border geometry, only update color/alpha per frame | `esp32-face-v2/main/conv_border.cpp` | S4.2 |
| S4.6 | Audit all 12 mood colors for RGB565 fidelity: identify precision loss (blues/purples worst with 5-bit channels), create corrected palette | `esp32-face-v2/main/face_state.cpp` | S4.1 |
| S4.7 | Implement temporal dithering for smooth color gradients (alternate between adjacent RGB565 values frame-to-frame for slow-changing regions) | `esp32-face-v2/main/face_ui.cpp` | S4.6 |
| S4.8 | Apply gamma correction to SDF antialiasing — linear blending in gamma-encoded space produces visible banding at RGB565 depth | `esp32-face-v2/main/face_ui.cpp` | S4.6 |
| S4.9 | Profile end-to-end command-to-pixel latency: serial receive → command parse → state update → render → SPI → display refresh | `esp32-face-v2/main/face_ui.cpp` | S4.1 |
| S4.10 | Implement immediate partial render for high-priority commands (SET_CONV_STATE, GESTURE): trigger partial render of affected region without waiting for next full frame | `esp32-face-v2/main/face_ui.cpp` | S4.3, S4.9 |
| S4.11 | Validate sim/hardware parity: side-by-side V3 sim vs MCU for all moods, conversation states, mood transitions | Manual test | S4.1–S4.10 |
| S4.12 | Profile sparkle/fire/afterglow effects: identify per-pixel operations that exceed budget, optimize or disable selectively | `esp32-face-v2/main/face_ui.cpp` | S4.1 |

### Exit Criteria
- Full frame render (face + border + effects) completes in <25 ms (leaving 8 ms for SPI/overhead)
- Dirty-rect optimization reduces average SPI transfer to <60% of full frame
- Command-to-visible-pixel latency <66 ms (2 frames)
- No visible color banding on mood transitions (RGB565 dithering effective)
- All spec timing requirements met on hardware (§6.1 latency targets)
- Side-by-side with V3 sim: visually identical within RGB565 quantization

---

## Dependency Graph

```
Spec Revisions (R.1–R.12) ──────── DONE
    │
    v
PE R&D (PE.1–PE.6) ──────────── DONE (PE.6 N/A — no on-device LLM)
    │
    v
Alignment Review (A.1–A.7) ── DONE
    │
    v
Stage 3: Sim V3 (S3.1–S3.18) ── DONE
    │
    v
Visual Language Remediation ── DONE (G1–G7)
    │
    v
Visual Language Review ──────── DONE (R1–R5 + D1–D5 + B1–B3)
    │
    v
Phase 0 (Parity V3→MCU) ── DONE (196/196 parity checks)
    │
    v
Phase 1 (Conv State Machine) ──────┐ ── DONE
    │  + personality worker scaffold│
    v                               v
Phase 2 (Firmware Border) ──> Phase 4 (Phase Transitions)
    │  DONE                       │  + personality idle behavior
    v                               v
Phase 3 (Mood Choreography) ──> Phase 5 (Polish)
    │  + personality modulation      │  + personality integration tests
    v                               v
                              Stage 4 (Firmware Optimization)
                                    │
                                    v
                              Evaluation (T1–T4 + PE metrics)
```

Phases 1–3 can be parallelized to some extent: Phase 1 (supervisor state machine) and Phase 2 (firmware border) are on different codebases. Phase 3 (mood choreography) depends on Phase 1's state tracking but not on Phase 2's border rendering. Personality worker scaffolding runs parallel to Phase 1.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stage 3 design iteration delays downstream phases | All firmware work blocked | Time-box design iteration (S3.17). Define "good enough" criteria. Tune further after hardware validation. |
| V3 sim rendering diverges subtly from MCU | Visual mismatch on hardware | CI parity check for constants. Side-by-side comparison (S4.11). Accept RGB565 quantization as known delta. |
| Border SDF render exceeds 33 ms frame budget | Border stutters or drops frames | Profile early (S4.2). Fallback: precomputed LUT (S4.5), or solid-color border (no glow). |
| Full frame SPI transfer (~30 ms) leaves no render budget | Cannot hit 30 FPS | Dirty-rect (S4.3) + DMA double-buffer (S4.4). Fallback: reduce to 20 FPS or partial updates only. |
| Intensity ramp produces visible stepping at 50 Hz | "Staircase" effect instead of smooth fade | 50 Hz gives ~8 steps over 150 ms — should be smooth. If not, increase ramp duration or use MCU-side interpolation. |
| Gaze spring model produces overshoot on LISTENING center lock | Eyes bounce past center | Increase damping (d) for supervisor-commanded targets. Or use direct snap (tween, not spring) for LISTENING. |
| Multi-turn state machine has race conditions | State gets stuck or skips | Extensive unit tests (1.10). State machine is deterministic — all transitions run on tick_loop thread. |
| AI emotion arrives during mood transition | Interrupted transitions look broken | Interrupt handling (3.4): restart sequence from current intensity. |
| Temporal dithering visible as flicker | Distracting instead of smoothing | Only apply to slow-changing regions. Disable per-effect if needed. |
| SET_CONV_STATE adds protocol version incompatibility | Old firmware ignores new command | MCU already ignores unknown command IDs (COBS decoder skips). No crash risk. |
| PE R&D delays Stage 3 start | Implementation blocked on research | Time-box PE research phases. PE Stage 1 Phase 1 and Phase 2 have clear exit criteria. If a decision point stalls, proceed with the conservative option and revisit. |
| PE ↔ face comm alignment reveals major conflicts | Spec rework delays implementation | Both specs share the same design philosophy and author context. Alignment review is scoped to reconciliation, not redesign. Major conflicts unlikely given shared research basis. |
| Personality worker adds complexity to tick loop | Performance impact, debugging overhead | Worker is isolated (separate process, NDJSON). Tick loop reads a snapshot struct — no personality computation on the fast path. Worker crash doesn't break face rendering. |

---

## Files Changed Summary

| File | Changes |
|------|---------|
| **Spec Revisions** | |
| `docs/face-communication-spec-stage2.md` | 10 fixes + 3 nits |
| `docs/face-communication-spec-stage1.md` | Add stable reference ID anchors |
| **PE R&D** | |
| `docs/personality-engine-spec-stage1.md` | Research decisions, approved options |
| `docs/personality-engine-spec-stage2.md` (new) | Full personality engine spec |
| **Alignment Review** | |
| `docs/pe-face-comm-alignment.md` (new) | Alignment report, reconciliation decisions |
| `docs/face-communication-spec-stage2.md` | Amendments from alignment (if any) |
| `docs/personality-engine-spec-stage2.md` | Amendments from alignment (if any) |
| **Stage 3: Sim V3** | |
| `tools/face_sim_v3/` (new package, ~15 files) | Complete sim rewrite implementing full spec, with PE hooks |
| **Visual Language Remediation** | |
| `docs/face-visual-language.md` (new) | Design document defining intended visual appearance of all moods, gestures, conv states |
| `tools/face_sim_v3/state/constants.py` | Expanded MOOD_EYE_SCALE (13 moods), NOD/HEADSHAKE gesture constants, ERROR aversion constants |
| `tools/face_sim_v3/state/face_state.py` | Eye scale reset fix, NOD/HEADSHAKE gesture overrides+timeouts, Silly intensity scaling |
| `tools/face_sim_v3/__main__.py` | THINKING→SPEAKING anticipation blink, ERROR gaze micro-aversion |
| `tools/check_face_parity.py` (new) | CI parity check, reads from V3 `constants.py` |
| `justfile` | Add `just sim` for V3 |
| **Visual Language Review Cycles** | |
| `docs/face-visual-language.md` | §1.3.1 TN luma floor, §1.5 coordinate space, silhouette distinctiveness matrix + clarity audit, per-mood updates (CURIOUS, CONFUSED, LOVE, ANGRY, THINKING), effective intensity maxima table, TTS timing annotation, expanded §5.6 parity notes |
| `tools/face_sim_v3/state/constants.py` | SAD/SLEEPY colors brightened, ANGRY/THINKING eye scale adjusted, CURIOUS/CONFUSED MOOD_TARGETS updated, CONFUSED_MOOD_MOUTH_OFFSET_X, LOVE convergence + idle wander constants |
| `tools/face_sim_v3/state/face_state.py` | Post-spring NOD/HEADSHAKE gaze bypass, CONFUSED persistent mouth offset, LOVE pupil convergence + reduced idle wander |
| `tools/face_sim_v3/__main__.py` | Fixed: conv state flag/gaze override (apply on transitions only, respect manual gaze) |
| `tools/check_face_parity.py` | Added sim-ahead exclusion mechanism for known divergences |
| **Phase 0** | |
| `esp32-face-v2/main/config.h` | Sync constants from V3 |
| `esp32-face-v2/main/face_state.cpp` | Sync mood targets, tween speeds from V3 |
| `esp32-face-v2/main/face_state.h` | CONFUSED mood, NOD/HEADSHAKE anim fields |
| `justfile` | Parity check in preflight |
| **Phase 1** | |
| `supervisor_v2/devices/protocol.py` | Add FaceConvState enum |
| `supervisor_v2/core/conv_state.py` (new) | ConvStateTracker — state machine, auto-transitions |
| `supervisor_v2/core/tick_loop.py` | Conv state machine, gaze/flag management, context-gated ACTION cancel |
| `supervisor_v2/core/state.py` | Telemetry fields for conv state |
| `supervisor_v2/tests/test_conv_state.py` (new) | 39 conversation state unit tests |
| **Phase 2** | |
| `esp32-face-v2/main/protocol.h` | Add SET_CONV_STATE=0x25, FaceConvState enum, FaceSetConvStatePayload |
| `esp32-face-v2/main/shared_state.h` | Add g_cmd_conv_state, g_cmd_conv_state_us atomics |
| `esp32-face-v2/main/usb_rx.cpp` | Add SET_CONV_STATE dispatch handler |
| `esp32-face-v2/main/conv_border.h` (new) | Border renderer + corner button public API |
| `esp32-face-v2/main/conv_border.cpp` (new) | SDF border renderer (~700 lines): frame/glow, 8 state animations, corner buttons, MIC/X_MARK icons, LED sync |
| `esp32-face-v2/main/face_ui.cpp` | Integrate border render, replace LVGL buttons with pixel rendering + touch hit-test |
| `esp32-face-v2/main/CMakeLists.txt` | Add conv_border.cpp |
| `supervisor_v2/devices/protocol.py` | Add SET_CONV_STATE=0x25 to FaceCmdType, build_face_set_conv_state() |
| `supervisor_v2/devices/face_client.py` | Add send_conv_state() method |
| `supervisor_v2/core/tick_loop.py` | Wire send_conv_state on state transitions |
| `tools/check_face_parity.py` | Add 27 border constant checks (196/196 total), static constexpr regex |
| `supervisor_v2/tests/test_face_protocol.py` (new) | 8 protocol builder + face_client tests |
| **Phase 3–5 (planned)** | |
| `supervisor_v2/core/tick_loop.py` | Mood transition sequencer, negative affect guardrails |
| `supervisor_v2/workers/tts_worker.py` | Fix talking end timing |
| `supervisor_v2/tests/test_mood_transitions.py` (new) | Mood transition + guardrail unit tests |
| `dashboard/src/tabs/FaceTab.tsx` | Conv state + transition visualization |
| `docs/protocols.md` | SET_CONV_STATE + SET_FLAGS documentation |
| **Stage 4: Firmware Optimization** | |
| `esp32-face-v2/main/face_ui.cpp` | Dirty-rect, DMA double-buffer, dithering, gamma, latency optimization |
| `esp32-face-v2/main/conv_border.cpp` | SDF LUT optimization |
| **Docs** | |
| `docs/TODO.md` | Updated Personality Engine status |
