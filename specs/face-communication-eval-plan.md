# Face Communication — Stage 2: Evaluation Plan

**Companion to**: `face-communication-spec-stage2.md` (the spec). Implementation tracking is in `docs/TODO.md`.

**Purpose**: Define how to verify that the face communication system achieves its goals — the robot's actions feel intentional and aware rather than random, for children ages 4–6. This plan covers automated tests, instrumented benchmarks, and human evaluation protocols.

---

## 1. Evaluation Tiers

| Tier | What | When | Who |
|------|------|------|-----|
| **T1: Automated** | Timing compliance, state machine correctness, parity | Every commit (CI) | Machine |
| **T2: Instrumented** | Latency measurement, hold time compliance, transition profiling | Per-phase completion | Developer on hardware |
| **T3: Developer Review** | Visual quality assessment, "does it look right" | Per-phase completion | Developer(s) |
| **T4: Child Evaluation** | Recognition, comfort, over-interpretation | After Phase 4, after Phase 5 | Children ages 4–6 + parents |

---

## 2. T1: Automated Tests

### 2.1 Conversation State Machine (Phase 1)

**Test file**: `supervisor/tests/test_conv_state.py`

| Test Case | Assertion |
|-----------|-----------|
| Wake word → ATTENTION → LISTENING | State advances correctly with correct timing |
| PTT press → ATTENTION → PTT → (release) → THINKING | PTT variant works |
| LISTENING → (VAD end) → THINKING → (TTS start) → SPEAKING → (TTS done + session done) → DONE → IDLE | Full happy-path cycle |
| Multi-turn: SPEAKING → (TTS done, session active) → LISTENING | Loop back to listening |
| THINKING 30 s timeout → ERROR | Timeout produces error |
| Cancel during LISTENING → DONE | Graceful cancellation |
| Cancel during SPEAKING → DONE | Interruption works |
| Wake word during SPEAKING → ignored | No re-entry during active speech |
| PTT during SPEAKING → LISTENING (PTT) | Interruption via PTT |
| DONE → (500 ms) → IDLE | Cleanup completes |
| Flags on LISTENING entry | IDLE_WANDER=0 |
| Flags on DONE→IDLE | IDLE_WANDER=1, AUTOBLINK=1, SPARKLE=1 |
| Gaze on LISTENING | gaze = (0, 0) sent |
| Gaze on THINKING | gaze = (0.5, -0.3) sent |
| Mood on THINKING entry | THINKING @ intensity 0.5 |
| Mood on LISTENING entry | NEUTRAL @ intensity 0.3 |

### 2.2 Mood Transition Choreography (Phase 3)

**Test file**: `supervisor/tests/test_mood_transitions.py`

| Test Case | Assertion |
|-----------|-----------|
| Mood change triggers blink gesture | GESTURE(BLINK) sent before ramp-down |
| Ramp-down duration ~150 ms | Intensity reaches ~0 within 7–9 ticks |
| Mood ID switches at intensity ~0 | New mood_id sent when intensity < 0.05 |
| Ramp-up duration ~200 ms | Intensity reaches target within 9–11 ticks |
| Total transition ~450–500 ms | End-to-end timing |
| Interrupt mid-ramp restarts from current intensity | New mood triggers new sequence from current value |
| Minimum hold time 500 ms enforced | Second mood queued if first is <500 ms old |
| Queued mood executes after hold time | Transition starts at 500 ms mark |

### 2.3 Negative Affect Guardrails (Phase 3)

| Test Case | Assertion |
|-----------|-----------|
| SAD held > 4 s triggers auto-recovery | Ramp-down to NEUTRAL after 4.0 s |
| SCARED held > 2 s triggers auto-recovery | Ramp-down after 2.0 s |
| ANGRY held > 2 s triggers auto-recovery | Ramp-down after 2.0 s |
| SURPRISED held > 3 s triggers auto-recovery | Ramp-down after 3.0 s |
| AI overrides mood before guardrail → timer resets | New mood accepted, old timer cancelled |
| ANGRY intensity capped at 0.5 | Even if AI sends 1.0, MCU receives ≤128 |
| SAD intensity capped at 0.7 | Clamped correctly |
| Negative mood blocked outside conversation | SET_STATE for SAD/SCARED/ANGRY rejected when conversation_active=False |
| SURPRISED allowed outside conversation (exception) | Accepted with 3.0 s guardrail |

### 2.4 Sim/MCU Parity (Phase 0)

**Test file**: `tools/check_face_parity.py`

| Check | Sim Source | MCU Source | Tolerance |
|-------|-----------|-----------|-----------|
| Blink interval range | `face_state_v2.py` | `config.h` | Exact match |
| Idle gaze interval range | `face_state_v2.py` | `config.h` | Exact match |
| Background color | `face_sim_v2.py` | `face_ui.cpp` | Exact match |
| All 12 mood parameter targets | `face_state_v2.py` | `face_state.cpp` | ±0.01 per parameter |
| All 12 mood colors | `face_state_v2.py` | `face_state.cpp` | ±2 per RGB channel |
| Gesture default durations | `face_state_v2.py` | `face_state.cpp` | ±10 ms |
| Spring constants (k, d) | `face_state_v2.py` | `face_state.cpp` | Exact match |
| Tween speeds (all parameters) | `face_state_v2.py` | `face_state.cpp` | ±0.01 |
| Conversation border colors | `conv_border.py` | `conv_border.cpp` | ±2 per RGB channel |
| Conversation border timing | `conv_border.py` | `conv_border.cpp` | ±33 ms (1 frame) |

---

## 3. T2: Instrumented Benchmarks

These require running on hardware with timing instrumentation.

### 3.1 Latency Measurements

Instrument the supervisor tick_loop and MCU render loop to log timestamps at key points.

| Metric | Measurement Points | Target | Spec Reference |
|--------|-------------------|--------|---------------|
| Wake word → first pixel change | ear_worker detection timestamp → MCU display refresh timestamp | < 200 ms | §6.1 |
| PTT press → first pixel change | button event timestamp → MCU display refresh timestamp | < 100 ms | §6.1 |
| End-of-utterance → THINKING visual | VAD end timestamp → border change visible on display | < 300 ms | §6.1 |
| TTS audio start → gaze return visible | tts_worker start timestamp → gaze center visible on display | < 100 ms | §6.1 |
| Mood command → visible change | send_state timestamp → MCU render of new mood parameters | < 50 ms | §6.1 |

**Method**: Add optional `perf_log` mode to supervisor that records event timestamps to a circular buffer. MCU adds frame counter to telemetry. Post-process logs to compute cross-system latencies.

### 3.2 Hold Time Compliance

| Metric | Method | Target |
|--------|--------|--------|
| Mood hold time | Log mood_id changes with timestamps; check minimum gap ≥ 500 ms | 100% compliance |
| Border state hold time | Log conv_state changes; check minimum gap ≥ 300 ms | 100% compliance |
| Gesture completion | Log gesture trigger + expected end; check no mood change during gesture | 100% compliance |

**Method**: Record a 5-minute conversation session. Post-process logs for hold time violations.

### 3.3 Frame Budget

| Metric | Method | Target |
|--------|--------|--------|
| MCU frame time with border | Profile render loop: face + border + display flush | < 33 ms (30 FPS) |
| MCU frame time THINKING state | Profile with orbit dot animation active | < 33 ms |
| Supervisor tick time with conv state machine | Profile tick_loop including mood transition sequencer | < 20 ms (50 Hz) |

**Method**: Add timing instrumentation to MCU render loop (`esp_timer_get_time()` before/after). Log worst-case frame time over 1000 frames.

---

## 4. T3: Developer Review

Subjective assessment by developer(s) watching the robot during test scenarios.

### 4.1 Review Scenarios

Run each scenario and answer the review questions.

**Scenario A: Cold Start Conversation**
1. Robot is idle for 30 seconds
2. Say wake word
3. Ask a question
4. Wait for response
5. Conversation ends

Review questions:
- Did the face visibly react to the wake word? How quickly?
- During listening, did the eyes stay on you? Did it feel like the robot was paying attention?
- During thinking, was there a visible "processing" state? Did the gaze avert?
- Did the robot's face change before or as it started speaking (not after)?
- Did the conversation end feel clean (fade out, not abrupt)?

**Scenario B: Multi-Turn Conversation**
1. Have a 3–4 turn conversation
2. Observe transitions between turns

Review questions:
- Did the SPEAKING→LISTENING transitions feel natural?
- Did the robot maintain attention across turns?
- Were mood changes smooth (blink + fade) or abrupt?

**Scenario C: Negative Emotion**
1. During conversation, trigger a topic that elicits SAD or SCARED from the AI
2. Observe the negative mood display and recovery

Review questions:
- Was the negative emotion recognizable but not alarming?
- Did the face recover to neutral smoothly?
- How long did the negative emotion display? Did it feel appropriate?

**Scenario D: Error/Interruption**
1. Cancel a conversation mid-speech (touch cancel button)
2. Trigger a network timeout during THINKING

Review questions:
- Did the error flash feel informative (not startling)?
- Did the face recover to idle cleanly?
- Was there any stuck state or visual artifact?

**Scenario E: Idle Observation**
1. Watch the robot idle for 2 minutes without interacting

Review questions:
- Does the face feel alive (breathing, blinking, subtle gaze)?
- Does the gaze wander feel random or intentional? Does it feel like the robot is "looking at" something specific?
- Is the overall impression calm and ambient, or restless?

### 4.2 Review Scoring

For each question, score 1–5:

| Score | Meaning |
|-------|---------|
| 1 | Broken — clearly wrong, distracting, or alarming |
| 2 | Noticeable problem — feels off, needs work |
| 3 | Acceptable — functional but not polished |
| 4 | Good — feels intentional and natural |
| 5 | Excellent — delightful, exceeds expectations |

**Pass threshold**: All questions score ≥ 3. Average across all questions ≥ 3.5.

---

## 5. T4: Child Evaluation

### 5.1 Participants

- **Age**: 4–6 years old
- **Sample size**: 5–8 children (qualitative evaluation, not statistical power)
- **Setting**: Familiar environment (home or known play space). Parent present.
- **Duration**: 15–20 minutes per child (including warm-up)
- **Consent**: Parental informed consent. Child verbal assent. Child may stop at any time.

### 5.2 Protocol

#### Phase 1: Warm-Up (3–5 min)

Child meets the robot in idle state. Free play — touching, looking, getting comfortable. No conversation yet. Researcher observes but does not direct.

**Observation notes**: Does the child approach the robot? Comment on the face? Describe what it's doing? ("It's looking at me," "It's sleeping," etc.)

#### Phase 2: Emotion Recognition (5–7 min)

The robot displays each of 6 moods (HAPPY, SAD, ANGRY, SCARED, NEUTRAL, EXCITED) for 3 seconds each, in randomized order. After each mood:

**Prompt**: "How does the robot feel right now?"

Record the child's response verbatim. Code responses as: correct, adjacent (reasonable confusion, e.g., "sad" for "scared"), or incorrect.

**Selection rationale**: These 6 moods span positive/negative/neutral and are the most reliably recognized by this age group per Widen & Russell (2003). SURPRISED, CURIOUS, THINKING, SLEEPY, LOVE, SILLY are excluded from this test — they are less reliably named by 4–6 year olds and would increase task fatigue.

#### Phase 3: Conversation (5–7 min)

The child has a natural conversation with the robot (2–3 turns). The researcher does not script the conversation — the child talks about whatever they want.

**Observation notes during conversation**:
- Does the child look at the robot's face during conversation?
- Does the child wait for the robot to "finish thinking" before speaking again?
- Does the child comment on the border/glow?
- Any signs of discomfort, confusion, or delight?

**Post-conversation prompts** (asked casually, not as a test):
- "What was the robot doing when you were talking?" (probes LISTENING awareness)
- "What was it doing before it talked back to you?" (probes THINKING awareness)
- "Was the robot listening to you?" (probes perceived attention)

#### Phase 4: Over-Interpretation Probe (2–3 min)

During idle (no conversation), while the robot's eyes wander:

**Prompts**:
- "What is the robot looking at right now?"
- "Why did its eyes move just now?"
- "What is the robot thinking about?"

Record responses verbatim. Code as:
- **Accurate**: "Nothing" / "I don't know" / "It's just looking around"
- **Mild over-interpretation**: "It's looking at the wall" / "It's looking at me" (plausible but unintended)
- **Strong over-interpretation**: "It's looking at my toy because it wants to play with it" (attributed intent the robot doesn't have)

#### Phase 5: Comfort Check (1–2 min)

**To child**: "Did you like talking to the robot? Was it scary at any point? Would you want to talk to it again?"

**To parent** (separately): "Did anything about the robot's expressions seem inappropriate, confusing, or concerning?"

### 5.3 Metrics

| Metric | Measurement | Target | Source |
|--------|-------------|--------|--------|
| **Emotion recognition rate** | % of 6 moods correctly identified | ≥ 70% across all children, ≥ 50% per child | Phase 2 |
| **Conversation state awareness** | % of children who describe LISTENING and/or THINKING when prompted | ≥ 60% describe at least one state | Phase 3 prompts |
| **Perceived attention** | % of children who answer "yes" to "Was it listening?" | ≥ 80% | Phase 3 prompt |
| **Over-interpretation rate** | % of idle gaze prompts coded as "strong over-interpretation" | ≤ 20% | Phase 4 |
| **Comfort** | % of children who want to talk again + 0 parent concerns | 100% want to talk again, 0 parent concerns flagged | Phase 5 |
| **Startle incidents** | Count of visible distress reactions (flinching, crying, backing away) during the session | 0 | All phases (observational) |

### 5.4 Pass/Fail Criteria

| Criterion | Threshold | Action on Fail |
|-----------|-----------|----------------|
| Emotion recognition < 70% overall | Fail | Review mood parameter targets. Increase differentiation between confused pairs. Re-test. |
| Conversation state awareness < 60% | Fail | Increase border salience (brighter, wider). Add audio cues. Re-test. |
| Perceived attention < 80% | Fail | Review gaze lock during LISTENING. May need longer hold or center snap instead of spring. |
| Over-interpretation > 20% | Fail | Reduce idle gaze wander range or speed. Add idle gaze centering bias. |
| Any startle incident | Fail | Review the trigger. If negative mood: reduce intensity cap. If transition: increase ramp duration. If border flash: soften ERROR state. |
| Any parent concern | Review | Assess severity. If related to negative affect: tighten guardrails. If related to attention: adjust idle behavior. |

### 5.5 Iteration

If any metric fails:
1. Identify the likely cause from observation notes
2. Adjust spec parameters (this is a Tuning-class change — cheap to iterate per Stage 1 classification)
3. Re-run T2 (instrumented) and T3 (developer review) to verify the change
4. Re-run T4 with 3 new children (not the same ones, to avoid learning effects)

Maximum 3 iteration cycles before escalating to a design review (revisiting Stage 1 decisions).

---

## 6. Test Schedule

| Impl Phase | Automated (T1) | Instrumented (T2) | Dev Review (T3) | Child Eval (T4) |
|:----------:|:--------------:|:-----------------:|:---------------:|:---------------:|
| Phase 0 | Parity check | — | — | — |
| Phase 1 | Conv state tests | Latency benchmarks | Scenario A, B | — |
| Phase 2 | Parity check | Frame budget | Scenario A (border focus) | — |
| Phase 3 | Mood transition + guardrail tests | Hold time compliance | Scenario C | — |
| Phase 4 | All above | All above | All scenarios (A–E) | — |
| Phase 5 | All above | All above | All scenarios | Full T4 protocol |

Child evaluation (T4) runs only after Phase 5 (all features integrated and polished). Running T4 on partial implementations would produce misleading results — children would react to missing features rather than design quality.

---

## 7. Instrumentation Requirements

To support T2 benchmarks, the following instrumentation must be added during implementation:

| Component | Instrumentation | Output |
|-----------|----------------|--------|
| `tick_loop.py` | Log conversation state transitions with `time.monotonic_ns()` | `perf_log` buffer or file |
| `tick_loop.py` | Log mood set commands with timestamp and intensity | Same |
| `tick_loop.py` | Log SET_STATE sends with all parameters | Same |
| `ear_worker.py` | Log wake word detection timestamp | Event bus |
| `tts_worker.py` | Log TTS start/finish timestamps | Event bus |
| `face_ui.cpp` | Log frame render time (esp_timer delta) | Serial telemetry (optional field) |
| `face_ui.cpp` | Log command receive → render latency | Serial telemetry (optional field) |

Instrumentation should be gated behind a debug flag (`PERF_LOG=1` or similar) — zero overhead in production.
