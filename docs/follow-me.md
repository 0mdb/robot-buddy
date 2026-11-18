# Follow me and voice-driven moving

**Status:** design, 2026-11-18. Nothing built yet. Waits on reflex commissioning
Phases 4–5 (e-stop, tilt, command timeout and stall verified; PID tracking ±20%).
Tasks live in `docs/TODO.md` under **Mobility & Voice Commands**.

The family asked for "Buddy, follow me", plus other spoken commands that move Buddy
around the house. This doc covers what Buddy needs, the order to build it in, and
the safety rules for following.

## 1. Settled decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Kids can command movement from day one.** | It's their robot. The safety rules (§7) assume a child is giving the commands. |
| D2 | **Anyone can say "stop", and it's handled on the Pi** as a fixed phrase. It never goes through the server or the LLM. | Stopping can't depend on Wi-Fi or a ~1 s LLM round trip. |
| D3 | **The LLM never produces speeds or turn rates.** It can only map fuzzy wording to one of the commands in §4. | Nothing it says should reach the motors directly. |
| D4 | **Keep the standard IMX708 camera** (75° diagonal, 66° horizontal at full 16:9). The Wide costs ~$82 vs ~$33. Buy it only if following proves flaky because people keep leaving the frame. | Price. Get real data first. |
| D5 | **Face ID only picks who to follow.** Tracking uses a body detector plus a clothing signature. | When following someone you see their back, not their face. |
| D6 | **Downward cliff sensors are required before following without a tether.** | The one HC-SR04 points forward and can't see stairs. |
| D7 | **Person detection runs on the Pi's CPU first.** Buy a Hailo AI HAT+ (13 TOPS) only if it can't hold ~10 fps beside audio and face detection. | Measure before buying. Watch stack height beside the UPS HAT (B), plus ~2–3 W of power. |
| D8 | **"Leader keeps Buddy":** while Buddy is following someone, another person saying "follow me" is politely refused until the leader says "stop following" or is lost. | Avoids tug-of-war between kids. Change if it's no fun. |

## 2. What Buddy has, and what's missing

**Already built:**
- `ear.event.doa`: XVF3800 voice direction (10 Hz, `--doa-offset-deg` / `--doa-sign`
  for mounting; not yet calibrated on the robot).
- YuNet face detection at 15 Hz, giving bearing and elevation. SFace recognition of
  enrolled family members.
- `face_gaze.py` already sticks with the same face.
- WANDER mode: `skill_executor.py`, `safety.py`, speed caps, obstacle escape.
- Reflex hard stops: 250 mm range, tilt, stall, 400 ms command timeout, `/ESTOP`.

**Missing, in build order:**
1. Closed-loop speed control (Phase 5) and **odometry** (x, y, θ from wheel speed
   and gyro): Post-Commissioning tasks.
2. A **local command grammar** in front of the LLM.
3. **Person (body) detection** plus a tracker plus an appearance signature. This is
   the same work as Track E Phase 3, so do it once.
4. **Cliff sensors** (2–4 downward IR distance sensors, e.g. VL53L0X / VL6180X) on
   the reflex board, as a reflex-level hard stop like OBSTACLE.
5. For L4: **AprilTags** (one printed tag per room) to correct odometry drift.

### Camera geometry (check first)

The vision worker asks Picamera2 for **640×480 (4:3)** from a **16:9 sensor**, and
assumes `vision.hfov_deg` 66. If the image processor crops the sides to reach 4:3,
the real horizontal view is about **52°**, not 66°. That means bearings (gaze,
follow) are over-scaled by ~25%, and a third of the available view is thrown away.

**Check:** log `ScalerCrop` from the capture metadata. If it is cropped, capture
**16:9 (e.g. 640×360)** to get the full 66° back for free, or at least set
`hfov_deg` to match. Vertical view at 16:9 is ~41°.

What 66° × 41° means for a low robot:
- A whole 1.7 m adult fits top to bottom only past ~2.3 m. At 1 m Buddy sees legs
  and lower body, so the detector must handle partial bodies.
- A sidestep of about 0.6 m at 1 m leaves the frame. Turning has to react fast.

## 3. Build order

Each level is usable on its own, and each builds pieces the next one needs.

| Level | Commands | New pieces | Done when |
|---|---|---|---|
| **L1 Short moves** | "back up", "go forward a bit", "turn around", "spin", "turn left/right" | Grammar, odometry-limited move skill, `MOVE` mode | Each move ends within ±10% distance / ±15° turn on a hard floor; "stop" cuts any move off within 300 ms of the end of the word |
| **L2 Come here** | "Buddy, come here" | Voice direction → turn, face find, approach to ~1 m | From 4 directions at 2–3 m: turns to the speaker, ends 0.8–1.2 m from them, facing them, 8/10 times |
| **L3 Follow me** | "follow me", "stop following", "wait here" | Person detector, tracker, clothing signature, follow controller, `FOLLOW` mode, lost/wait behaviour | 2-room walk at a kid's pace with one doorway: stays locked, waits when lost, picks the leader back up; never follows the wrong person past a 2-person crossing (5 trials) |
| **L4 Go to a place** | "this is the kitchen" (teaching, while following), "go to the kitchen" | Room AprilTags, a pose graph of named places, simple route between places | Reaches a taught room from 2 others, 4/5 times |
| **L5 Find someone** | "go find Sam" | L4 + face ID + room-by-room search | Finds a person in one of 3 rooms, asks "Sam, are you here?" |

L4 and L5 are sketches; write them up properly once L3 works.

## 4. Commands and the speech path

```
STT transcript ─► local grammar (Pi) ─ match ─► motion command ─► mode change
                       │ no match
                       ▼
                server /converse ─► LLM may return one motion command from the
                                    same list (tool), never numbers
```

- **Stop handled on the robot:** a short list of stop phrases ("stop", "Buddy stop",
  "freeze", "halt") checked against the STT transcript on the Pi. Later: a dedicated
  wake-word-style "stop" model in the ear worker, so it works without STT and during
  Buddy's own speech (barge-in is already on).
- **Other stop sources:** a screen tap or long-press while moving (already routed in
  `tick_loop._on_face_button`), `/ESTOP`, the dashboard.
- **Motion commands** (a closed enum in `messages/types.py`):
  `stop`, `move_forward_short`, `move_back_short`, `turn_left`, `turn_right`,
  `turn_around`, `spin`, `come_here`, `follow_me`, `stop_following`, `wait_here`,
  later `teach_place(name)`, `go_to(place)`, `find(person)`.
- **Who said it:** voice ID isn't built (Track E Phase 2). Until then, the speaker is
  the face Buddy recognises closest to the voice direction when the command is heard.
  No recognised face → "Who's asking? Stand where I can see you!"
- **Mode guard:** motion commands only act from IDLE or another voice-motion mode,
  never during ERROR. A refusal is spoken ("I can't move right now, my motors are
  resting").

## 5. Architecture

New modes in `core/state.py`: `MOVE` (L1), `APPROACH` (L2), `FOLLOW` (L3), added to
`MOTION_MODES`. The skills go in `skill_executor.py` beside WANDER. Each one outputs
a `DesiredTwist` that passes through `apply_safety()`. The reflex board stays the
last word.

### Perception (vision worker)

- **Person detector:** YOLO-nano (ncnn), 320 px input, person class (plus cat/dog
  for Track E). Target ≥10 fps while face detection stays at 15 Hz. Benchmark it in
  the Track E Phase 3 spike, and record CPU with the full audio stack running.
- **Tracker:** a simple box tracker (Kalman + IoU matching, ByteTrack-style) with
  stable track ids.
- **Clothing signature:** at lock-on, HSV histograms of the top and bottom halves
  of the person's box, averaged over ~1 s. Matching combines box overlap with
  signature similarity. Later option: a small re-ID network if colours aren't
  distinctive enough (two kids in school uniforms).
- **Snapshot fields:** `persons[]` (track id, normalised box, bearing, signature
  score, is_leader), alongside the existing `faces[]`.

### Lock-on ("follow me")

1. The command arrives with a voice direction.
2. Pick the face nearest that direction. Name them with SFace if possible.
3. Find the person box containing that face. Store its signature, then lock that
   track id as the leader.
4. Say "Okay Sam, I'm following you!" (or "Okay, I'm following you!" if unknown).
5. If there's no face or body within ±30° of the voice: turn toward the voice, then
   retry once. If that fails: "I can't see you. Come stand in front of me!"

### Follow controller

- **Turning:** from the leader's bearing, PD control with a fast gain. Turning
  reacts faster than forward speed.
- **Forward speed:** from estimated distance, targeting `follow.gap_m` (1.3 m).
  Distance comes from the ultrasonic when it sees the leader (bearing within ±10°
  and range under 2 m). Otherwise it's from box width, with box height used only
  when the full body is in view.
- Never drive forward when the gap is under `follow.min_gap_m`. Reverse gently if
  the leader walks toward Buddy.
- Slow down the turn when bearing error is large and the leader is close, so Buddy
  turns on the spot rather than swinging wide.

### Follow states

```
LOCKING ─► FOLLOWING ─► LOST ─► SEARCHING ─► WAITING ─► (give up) IDLE
              ▲           │          │           │
              └───────────┴──────────┴───────────┘  re-acquired (signature match)
```

- **LOST:** the leader has been out of view for `follow.lost_ms` (700 ms). Keep
  driving toward the last bearing for at most `follow.coast_mm` (500 mm), turning
  toward the last bearing.
- **SEARCHING:** turn in place toward the last side they were seen, up to ±90°,
  and listen for voice direction ("over here, Buddy"). A voice direction turns
  Buddy toward the voice.
- **WAITING:** stop. "Where'd you go? I'll wait right here!" Re-acquire on a
  signature match, or a "follow me" from anyone (the leader slot is free now).
- **Give up** after `follow.wait_s` (30 s) → IDLE, with a cheerful line. **Never
  wanders off to search on its own.**

## 6. Personality

- Lock-on: eyes snap to the leader, happy mood, the leader's name.
- Following: eyes track the leader; small "trotting" speech now and then (respect
  the talkativeness work, keep it rare).
- Falling behind (gap growing at max speed): "Wait for me!" Kids will love making
  Buddy chase them; that's fine within the speed cap.
- Lost and waiting: curious, not sad (HC-5: no loneliness, no "I miss you").
- Refusals (another kid trying to steal Buddy): "I'm following Sam right now! Ask
  Sam to say stop following."
- Face shows a small "moving" indicator so everyone can tell Buddy is in a motion
  mode (spec amendment in `face-visual-language.md` before building it).

## 7. Safety rules

Commands come from children (D1), so these are requirements, not suggestions.

- **Speed caps:** `follow.v_max_mm_s` starts at 200, below WANDER's maximum. Turn
  rate is capped too. MOVE/APPROACH use the same caps.
- **Gap:** never accelerate toward a person closer than `follow.min_gap_m` (0.8 m).
  Approaching ends at ~1 m.
- **Stops (any one):** the stop phrase from anyone, a screen tap, `/ESTOP`, dashboard,
  vision stale over 500 ms (already in `safety.py`), lost the leader past the coast
  limit, speech/ear worker dead, reflex fault, SoC critical.
- **Cliff:** a reflex-level cliff fault stops the motors like OBSTACLE, allowing only
  a reverse escape. L3 is tethered-only (an adult walks beside Buddy) until cliff
  sensors work.
- **What it follows:** people only (detector class), never pets or toys.
- **Time limits:** MOVE ends after its distance or 10 s. APPROACH ends after 20 s.
  FOLLOW ends after `follow.max_s` (10 min) and asks "Still want me to follow you?"
- **Stalls:** rugs, cables and doorway thresholds rely on the reflex stall fault and
  WANDER's no-progress check, reused for FOLLOW.
- **Logging:** every motion command (who, words, mode, outcome) is logged so odd
  behaviour can be replayed.

## 8. Tunables (registered as `follow.*`, live in the dashboard)

| Param | Start | Notes |
|---|---|---|
| `gap_m` | 1.3 | Narrow camera, so keep back far enough to see the body |
| `min_gap_m` | 0.8 | Hard floor |
| `v_max_mm_s` | 200 | Raise after tests |
| `w_max_mrad_s` | 1200 | Turning must keep up with sidesteps |
| `bearing_kp` / `bearing_kd` | tune | Start from WANDER's turn gains |
| `lost_ms` | 700 | |
| `coast_mm` | 500 | |
| `search_deg` | 90 | Each side |
| `wait_s` | 30 | |
| `max_s` | 600 | |
| `sig_match_min` | tune | Clothing-signature similarity to re-acquire |

## 9. Open questions

1. Is there a spare I2C bus or GPIO on the v2 reflex board for cliff sensors? If not,
   the Pi could read them, but then the hard stop isn't on the reflex board.
2. Is the Pi CPU budget enough for person detection beside audio (D7)?
3. Does the XVF3800 voice direction stay usable with the motors running? See the
   TODO item on motor false wakes.
4. Stairs: which floor(s) will Buddy drive on, and are there drops it could reach?
