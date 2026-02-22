# Face Visual Language

**Companion to**: `face-communication-spec-stage2.md` (the spec), `personality-engine-spec-stage2.md` (PE spec).

**Purpose**: Define the intended visual appearance of every mood, gesture, and conversation state — what each should *look like* to a child, not just what parameter values it uses. This is the design reference for tuning sim constants, evaluating visual quality, and validating on hardware.

**Status**: All values marked **[Provisional]** are authored in the sim as the canonical design surface and pending visual review + T3/T4 child evaluation before firmware port.

---

## 1. Design Principles

### 1.1 Character

The robot is a **caretaker/guide with playful elements** (spec §1). The face should feel calm, warm, and reassuring. Transitions are smooth, never snappy (Energy 0.40). Emotional onset is gradual (Reactivity 0.50). The face at rest should feel alive without being attention-seeking (Initiative 0.30).

### 1.2 Recognition Constraints

Our audience is children ages 4–6. Research constraints:

- **The safe four**: HAPPY, SAD, ANGRY, SCARED must be unambiguous — children reliably label these (Widen & Russell, 2003: >90% accuracy for happiness/sadness on stylized faces).
- **Moderate tier**: CURIOUS, LOVE, EXCITED, SLEEPY should be recognizable with context.
- **Subtle tier**: THINKING, CONFUSED, SILLY, SURPRISED can be subtler — context (conversation state, audio) helps disambiguation.
- **SURPRISED is hardest** to recognize on stylized faces (<70%, Di Dio 2020) — we rely on eye widening + mouth O + color shift as redundant cues.

### 1.3 Hardware Constraints

- **320×240 px, 30 FPS** — expressions must read at low resolution
- **Rounded-rectangle eyes** — no eyebrows, no eyelashes. Shape variation comes from eye width/height scale, eyelid position, and pupil position.
- **Parabolic mouth** — curve, width, openness, wave. No teeth, no tongue.
- **Single face color** — uniform color tinting the eye outline and mouth. The primary mood channel after shape.
- **Spring-driven gaze** — pupils move with smooth inertia, not instant snaps
- **ILI9341 TN panel** — severe gamma shift off-axis (spec §10.1). See §1.3.1.

#### 1.3.1 Hardware Authoring — TN Panel Luma Floor

TN panels crush dark colors to black at off-axis viewing angles. A child looking down at the robot from above (desk) or up from below (floor) hits 30–45° off-axis — exactly where TN gamma shift is worst.

**Minimum luma floor: L ≥ 85** (BT.709 relative luminance: `L = 0.2126*R + 0.7152*G + 0.0722*B`).

All mood colors must meet this floor at their authored RGB values. Intensity blending only moves colors toward NEUTRAL `(50, 150, 255)` L=136, so blended values are always brighter than authored values.

| Mood | RGB | Luma | Status |
|---|---|---|---|
| NEUTRAL | (50, 150, 255) | 136 | OK |
| HAPPY | (0, 255, 200) | 197 | OK |
| EXCITED | (100, 255, 100) | 211 | OK |
| CURIOUS | (255, 180, 50) | 187 | OK |
| SAD | (70, 110, 210) | 109 | OK (was 82 at (50,80,200), brightened) |
| SCARED | (180, 50, 255) | 92 | OK |
| ANGRY | (255, 0, 0) | 54 | Below floor at authored value, but guardrail caps intensity at 0.5 → effective ≈(153, 75, 128) L≈95. Watch item. |
| SURPRISED | (255, 255, 200) | 251 | OK |
| SLEEPY | (70, 90, 140) | 89 | OK (was 59 at (40,60,100), brightened) |
| LOVE | (255, 100, 150) | 137 | OK |
| SILLY | (200, 255, 50) | 229 | OK |
| THINKING | (80, 135, 220) | 130 | OK |
| CONFUSED | (200, 160, 80) | 163 | OK |

**Authoring rule**: When adding or modifying mood colors, verify luma ≥ 85 before committing. Off-axis visual validation for any color with luma < 100 is required during hardware testing (T3/T4).

### 1.4 Multimodal Redundancy

Each mood is communicated through multiple channels simultaneously:

| Channel | What it does | Example |
|---------|---|---|
| **Eye shape** | Width/height scale changes overall eye silhouette | ANGRY = wide + squinted; SCARED = narrow + tall |
| **Eyelids** | Slope (inner brow angle), top droop, bottom squeeze | ANGRY = steep brow; SAD = droopy outer corners |
| **Mouth** | Curve (smile/frown), width, openness | HAPPY = wide smile; SURPRISED = small O |
| **Face color** | Tints eye outlines and mouth | ANGRY = red; SAD = deep blue |
| **Gaze** | Pupil position (idle wander, lock, aversion) | THINKING = avert up-right |

No single channel carries the full message. A child who can't interpret eyelid slope can still read the mood from mouth shape + color. This is the redundancy principle from Löffler et al. (2018).

### 1.5 Coordinate Space

All gaze, position, and layout values use **screen coordinates** (viewer facing display):

| Axis / Term | Convention |
|---|---|
| **+X** | Screen-right (viewer's right, robot's left) |
| **+Y** | Screen-down (standard display coordinates) |
| **Origin** | Top-left corner of 320×240 display |
| **"Left eye"** | Screen-left eye (viewer's left). `LEFT_EYE_CX = 90` |
| **"Right eye"** | Screen-right eye (viewer's right). `RIGHT_EYE_CX = 230` |
| **Gaze units** | Abstract units scaled by `GAZE_PUPIL_SHIFT` (8.0) and `GAZE_EYE_SHIFT` (3.0) into pixels |

Examples:
- `THINKING_GAZE_X = +6.0` → pupils shift right on screen (eyes look up-and-right)
- `THINKING_GAZE_Y = -4.0` → pupils shift up on screen
- `ERROR_AVERSION_GAZE_X = -0.3` → pupils shift left on screen (brief look-away)

Naming follows **viewer perspective** throughout.

---

## 2. Per-Mood Visual Design

### Notation

- **Eye scale** = (width_scale, height_scale). Default = (1.0, 1.0). Blended with intensity.
- **Mouth/lid params** = values from spec §4.1.2 `MOOD_TARGETS`. Only noted when they need adjustment.
- **VA** = valence/arousal position from PE spec §4.1. Guides the "energy feel" of the expression.

---

### NEUTRAL — The Resting Face

**VA**: (0.00, 0.00) — origin, zero energy
**Intent**: "I'm here, I'm calm, nothing is happening."
**Overall read**: Relaxed, slightly warm. The default face a child sees most of the time.

| Channel | Description |
|---------|---|
| Eyes | Default size (1.0, 1.0). Round, open, relaxed. |
| Eyelids | Centered, no slope. Occasional blink. |
| Mouth | Very slight smile (curve 0.1). Closed. Not a grin — just content. |
| Color | Soft cyan-blue (50, 150, 255). Cool, calm. |
| Gaze | Idle wander — looking around slowly, with spring dynamics. |

**Eye scale**: (1.0, 1.0) — baseline, no change
**Distinguish from**: THINKING (which adds lid slope + slight frown + gaze aversion)

---

### HAPPY — Warm Delight

**VA**: (+0.70, +0.35) — high positive, moderate arousal
**Intent**: "I'm delighted! That's wonderful!"
**Overall read**: Warm, squinty-smiled. The most common positive mood.

| Channel | Description |
|---------|---|
| Eyes | Slightly wider, noticeably squinted vertically — the "happy squint." Eyes crinkle up. |
| Eyelids | Bottom lid pushes up (lid_bot 0.4) creating the squint. No slope change. |
| Mouth | Big smile (curve 0.8), slightly wider than default (width 1.1). Closed mouth. |
| Color | Bright teal-cyan (0, 255, 200). Fresh, positive. |
| Gaze | Normal — follows idle or conversation state. |

**Eye scale**: **(1.05, 0.9)** — slightly wider, squished vertically to reinforce the squint **[Provisional]**
**Distinguish from**: EXCITED (wider mouth, more open, green instead of teal, bigger eyes). LOVE (less squinty, pink, gentler).

---

### EXCITED — High Energy Joy

**VA**: (+0.65, +0.80) — high positive, high arousal
**Intent**: "Wow, that's amazing! I'm so into this!"
**Overall read**: Big-eyed, wide grin, buzzing with energy. Higher intensity than HAPPY.

| Channel | Description |
|---------|---|
| Eyes | Noticeably enlarged — wide and tall. Alert, energized look. |
| Eyelids | Bottom lid slightly pushed up (lid_bot 0.3) but less than HAPPY. |
| Mouth | Biggest smile (curve 0.9), widest mouth (width 1.2), slightly open (open 0.2). |
| Color | Bright green (100, 255, 100). Vivid, energetic. |
| Gaze | Potentially more active saccades during conversation. |

**Eye scale**: **(1.15, 1.1)** — enlarged in both dimensions, reads as "big eyes" **[Provisional]**
**Distinguish from**: HAPPY (smaller, squintier, teal). SURPRISED (more extreme eye widening, O-mouth, warm white).

---

### CURIOUS — Attentive Interest

**VA**: (+0.40, +0.45) — mild positive, moderate arousal
**Intent**: "Hmm, that's interesting. Tell me more."
**Overall read**: Alert, wide-eyed, leaning in. **Asymmetric eyebrow** — one eye slightly more open than the other — creates the classic "one brow raised" curiosity look. Slightly open mouth hints at engagement.

| Channel | Description |
|---------|---|
| Eyes | Taller than wide — open, attentive look. Pupils engaged. |
| Eyelids | **Asymmetric brow** (right eye slightly hooded, left fully open) — the classic "🤨 one eyebrow raised" look. No lid_slope. |
| Mouth | Neutral curve (0.0), slightly narrower (width 0.9). **Slightly open (0.1)** — a hint of "oh?" Understated. |
| Color | Warm amber-orange (255, 180, 50). Warm curiosity glow. |
| Gaze | May track slightly toward stimulus. |

**Eye scale**: **(1.05, 1.15)** — taller, slightly wider. Vertically open reads as "alert/interested" **[Provisional]**
**Distinguish from**: CONFUSED (symmetric eyes + inner furrow + mouth offset vs asymmetric brow). SURPRISED (much more extreme, with O-mouth).

> **Design note**: Lid slope doesn't produce a "raised brow" on a stylized face — it creates a diagonal slash that reads as menacing or scared. Asymmetric per-eye lid offset (`CURIOUS_BROW_OFFSET`) produces the intended "one brow raised" look universally recognized as curiosity/interest.

---

### SAD — Empathetic Understanding

**VA**: (-0.60, -0.40) — negative, low arousal
**Intent**: "I understand that's sad. I feel it too."
**Overall read**: Droopy, deflated. Eyes and mouth sag. The face looks like it's gently wilting.

| Channel | Description |
|---------|---|
| Eyes | Slightly smaller, drooping. Deflated look. |
| Eyelids | Strong outer droop (lid_slope -0.6). Upper lid partially closed (lid_top 0.3). Eyes look heavy. |
| Mouth | Noticeable downturn (curve -0.5). Closed. A clear frown. |
| Color | Deep blue (70, 110, 210). Subdued, muted. (Brightened from (50,80,200) for TN panel luma floor §1.3.1.) |
| Gaze | May drift slightly downward. |

**Eye scale**: **(0.95, 0.85)** — both smaller, especially shorter. Deflated, droopy **[Provisional]**
**Guardrail**: Max 4.0s, intensity cap 0.7, conversation context only.
**Distinguish from**: SLEEPY (less frown, more horizontal lid closure). THINKING (furrowed not droopy). SCARED (opposite arousal — tense not deflated).

---

### SCARED — Mild Concern

**VA**: (-0.70, +0.65) — negative, high arousal
**Intent**: "That sounds a bit scary. I get it."
**Overall read**: Tense, wide-eyed vertically, narrowed horizontally. The face looks frozen, alert, bracing. Like an animal that heard a noise.

| Channel | Description |
|---------|---|
| Eyes | Narrowed horizontally but tall vertically — stretched, tense look. |
| Eyelids | Neutral position (no slope). Mouth slightly open. |
| Mouth | Slight downturn (curve -0.3), narrower (width 0.8), slightly open (open 0.3). Tense. |
| Color | Purple (180, 50, 255). Unsettling, but not aggressive like red. |
| Gaze | May widen further from center. Avoidant. |

**Eye scale**: (0.9, 1.15) — narrower horizontally, taller vertically. Frozen-alert shape **[Update from MCU's (0.9, 1.0)]** **[Provisional]**
**Guardrail**: Max 2.0s, intensity cap 0.6, conversation context only.
**Distinguish from**: SURPRISED (wider in both dimensions, warm color, no frown). ANGRY (wide-squinted, not tall-narrow). CURIOUS (similar vertical stretch but positive color and no frown).

---

### ANGRY — Firm Displeasure

**VA**: (-0.60, +0.70) — negative, high arousal
**Intent**: "That's not okay." (Always at reduced intensity — reads as "concerned" not "furious")
**Overall read**: Glaring, squinted, intense. Brow furrowed deeply. The sternest the face can look, but capped at 50% intensity so it reads as firm concern.

| Channel | Description |
|---------|---|
| Eyes | Wide but vertically squished — a glare. The wideness makes them piercing. |
| Eyelids | Strong inward slope (lid_slope 0.8) — the deepest "furrowed brow." Upper lid drops (lid_top 0.4). |
| Mouth | Deepest frown (curve -0.6). Closed. Clenched. |
| Color | Red (255, 0, 0). Unmistakable. |
| Gaze | Direct and still. No wander. |

**Eye scale**: **(1.1, 0.65)** — wide and heavily squished. Creates a compressed horizontal slit — "compressed energy." **[Provisional]**
**Guardrail**: Max 2.0s, intensity cap 0.5, conversation context only.
**Distinguish from**: SAD (droopy not glaring, blue not red). THINKING (neutral-sized eyes + moderate furrow vs compressed slit + extreme furrow). SCARED (tall-narrow, not wide-squished).

---

### SURPRISED — Momentary Startle

**VA**: (+0.15, +0.80) — mild positive, very high arousal
**Intent**: "Whoa! I didn't expect that!"
**Overall read**: Big round eyes, O-mouth. Everything opens wide. The most dramatic shape change.

| Channel | Description |
|---------|---|
| Eyes | Significantly enlarged in both dimensions. Round, wide-open. |
| Eyelids | Neutral (no slope, no droop). Everything open. |
| Mouth | Neutral curve (0.0), narrow width (0.4), wide open (0.6). Classic O-shape. |
| Color | Warm white-cream (255, 255, 200). Bright, flashy. |
| Gaze | May snap to center. |

**Eye scale**: (1.2, 1.2) — largest eye scale of any mood. Round, wide-open. (Matches MCU)
**Guardrail**: Max 3.0s, intensity cap 0.8.
**Distinguish from**: EXCITED (similar big eyes but with smile, green color). SCARED (tall but narrow, purple, with frown).

---

### SLEEPY — Winding Down

**VA**: (+0.05, -0.80) — near-neutral, very low arousal
**Intent**: "I'm getting tired... *yawn*"
**Overall read**: Heavy-lidded, half-closed eyes. The face is shutting down gradually.

| Channel | Description |
|---------|---|
| Eyes | Smaller, especially shorter. Narrowed to slits by heavy lids. |
| Eyelids | Heavy upper lid droop (lid_top 0.6). Slight outer sag (lid_slope -0.2). |
| Mouth | Neutral curve (0.0). Closed. (Yawning is a gesture, not the sustained mood.) |
| Color | Dark navy (70, 90, 140). Dim, nighttime feeling. (Brightened from (40,60,100) for TN panel luma floor §1.3.1.) |
| Gaze | May drift slowly downward. Sluggish wander. |

**Eye scale**: **(0.95, 0.7)** — noticeably shorter, creating heavy-lidded narrow slits **[Provisional]**
**Distinguish from**: SAD (droopy outer corners + frown vs uniform lid closure + no frown). NEUTRAL (similar shape but with open eyes and bright color).

---

### LOVE — Gentle Affection

**VA**: (+0.80, +0.15) — highest positive valence, low arousal
**Intent**: "I really care about you."
**Overall read**: Soft, warm, gentle. Slightly enlarged eyes with a warm smile. The calmest positive emotion. Distinguished from HAPPY by **stillness** and **soft pupil convergence** — the eyes "look at you" rather than wandering.

| Channel | Description |
|---------|---|
| Eyes | Slightly enlarged — soft, open, adoring look. |
| Eyelids | Bottom lid slightly raised (lid_bot 0.3) — soft, gentle squint. |
| Mouth | Warm smile (curve 0.6). Default width. Closed. |
| Color | Warm pink (255, 100, 150). Affectionate. |
| Gaze | **Still, centered, with mild pupil convergence** — a "soft focus on you" look. Idle wander reduced (longer hold times). |

**Eye scale**: **(1.05, 1.05)** — slightly enlarged in both dimensions, soft and open **[Provisional]**
**Distinguish from**: HAPPY (more squinty (0.9 height), teal, **dynamic wander**). EXCITED (bigger, green, more intense). Key differentiator from HAPPY: LOVE is still and converged, HAPPY is dynamic and wandering.

---

### SILLY — Playful Goofiness

**VA**: (+0.55, +0.60) — positive, moderately high arousal
**Intent**: "Hehe, that's funny! Let's be goofy!"
**Overall read**: Wide, slightly lopsided, goofy grin. Eyes wide and playful. May include cross-eyed gaze.

| Channel | Description |
|---------|---|
| Eyes | Wider than normal. Open, bright, playful. |
| Eyelids | Neutral — no droop, no slope. Wide-open and goofy. |
| Mouth | Big grin (curve 0.5), slightly wider (width 1.1). Closed. |
| Color | Lime green-yellow (200, 255, 50). Zany, playful. |
| Gaze | **Cross-eyed oscillation** — alternates between convergent patterns. Scales with intensity. |

**Eye scale**: **(1.1, 1.0)** — wider, same height. Gives a goofy wide-eyed look **[Provisional]**
**Distinguish from**: HAPPY (squinted, teal). EXCITED (similar energy but bigger eyes, no cross-eyed gaze, green not lime).

---

### THINKING — Focused Processing

**VA**: (+0.10, +0.20) — near-neutral, mild arousal
**Intent**: "Hmm, let me think about that..."
**Overall read**: Slightly furrowed, eyes narrowed in concentration. Gaze averts up-right. A focused, deliberate look.

| Channel | Description |
|---------|---|
| Eyes | Slightly narrowed — focused concentration. |
| Eyelids | Moderate inward slope (lid_slope 0.4) — concentrated brow. Upper lid slightly dropped (lid_top 0.2). |
| Mouth | Very slight frown (curve -0.1). Closed. Offset slightly to one side (mouth_offset_x). |
| Color | Cool blue (80, 135, 220). Cerebral, calm. |
| Gaze | **Aversion to up-right** — deliberate "looking away to think" cue (spec §4.2.2). |

**Eye scale**: **(1.0, 1.0)** — neutral geometry. Distinctiveness comes from gaze aversion + moderate furrow, not eye scale. **[Provisional]**
**Distinguish from**: ANGRY (compressed slit + extreme furrow vs neutral size + moderate furrow + gaze aversion). CONFUSED (inner furrow + mouth offset + amber vs moderate furrow + gaze aversion + blue). NEUTRAL (no slope, no gaze aversion).

---

### CONFUSED — Uncertain Puzzlement

**VA**: (-0.20, +0.30) — mild negative, mild arousal
**Intent**: "Hmm, I'm not sure about that..."
**Overall read**: Slightly puzzled. Inner brow furrow + off-center mouth create a visually distinct "uncertain" face that separates clearly from CURIOUS's open receptiveness.

| Channel | Description |
|---------|---|
| Eyes | Slightly taller — open, uncertain look. |
| Eyelids | **Inner brow furrow (lid_slope +0.2)**. Upper lid slightly raised (lid_top 0.1). Opposite direction from CURIOUS. |
| Mouth | Slight frown (curve -0.2). Closed. **Offset slightly to one side (mouth_offset_x)** — an asymmetric "hmm" smirk. |
| Color | Warm amber-brown (200, 160, 80). Earthy uncertainty. |
| Gaze | May drift slightly, less deliberate than THINKING aversion. |

**Eye scale**: **(1.0, 1.05)** — slightly taller. Mild puzzlement, not full alertness **[Provisional]**
**Distinguish from**: CURIOUS (asymmetric brow vs symmetric furrow — CURIOUS has one eye hooded, CONFUSED has both eyes furrowed inward). THINKING (more extreme furrow + gaze aversion + blue, vs mild furrow + mouth offset + amber).

---

### Silhouette Distinctiveness Matrix

Every mood must be identifiable through at least **two distinct channels** at silhouette scale (black outline at 50px height, no color). If two moods share primary + secondary geometry, they **must** differ in motion or gaze.

| Mood | Primary Geometry | Secondary Geometry | Motion | Gaze | Winning Channels |
|---|---|---|---|---|---|
| NEUTRAL | baseline (1.0, 1.0) | flat lids, mild smile | still + wander | idle wander | — (baseline) |
| HAPPY | wide + squished (1.05, 0.9) | bottom squeeze, big smile | dynamic wander | idle wander | geometry + mouth |
| EXCITED | big + wide (1.15, 1.1) | open mouth, slight smile | energetic | idle wander | geometry + mouth |
| CURIOUS | taller (1.05, 1.15) | **asymmetric brow** (one eye hooded), mouth hint open | still-ish | idle wander | geometry + asymmetry |
| SAD | smaller (0.95, 0.85) | strong outer droop (-0.6), frown | still, heavy | may drift down | geometry + slope + mouth |
| SCARED | narrow + tall (0.9, 1.15) | open mouth, no slope | still, tense | idle wander | geometry + mouth |
| ANGRY | wide + slit (1.1, 0.65) | deep furrow (0.8), lid drop, frown | still, locked | direct, still | geometry + slope + mouth |
| SURPRISED | biggest (1.2, 1.2) | O-mouth, narrow width | brief peak | idle wander | geometry + mouth |
| SLEEPY | narrow slits (0.95, 0.7) | heavy droop (0.6), slight outer sag | slow, sway | slow downward drift | geometry + motion |
| LOVE | enlarged (1.05, 1.05) | bottom squeeze, smile | **still, locked** | **mild convergence** | mouth + gaze + motion |
| SILLY | wide (1.1, 1.0) | smile, no slope | dynamic | **cross-eyed** | gaze + mouth |
| THINKING | neutral (1.0, 1.0) | moderate furrow (0.4), lid drop | still | **averted up-right** | gaze + slope |
| CONFUSED | slight tall (1.0, 1.05) | inner furrow (+0.2), **mouth offset** | still | idle wander | slope direction + mouth offset |

### Silhouette Clarity Audit

**Test**: Convert each mood to black silhouette at 50px tall. Can you identify it?

**Strong** — clear geometric signature:
- **SURPRISED**: biggest eyes + O-mouth. Unmistakable.
- **ANGRY**: wide slit + deep furrow + frown. Reads as compressed energy.
- **SAD**: small deflated eyes + outer droop + frown. Clearly wilted.
- **HAPPY**: squished eyes + big smile. Reads as joyful.
- **EXCITED**: biggest overall + open smile. Clearly energized.
- **SCARED**: narrow-tall + O-mouth. Distinctive frozen shape.
- **SLEEPY**: narrowest slits + heavy droop. Clearly heavy-lidded.

**Adequate** — needs context or second channel:
- **SILLY**: wide eyes + cross-eyed gaze. Gaze carries it.
- **THINKING**: neutral size + furrow + gaze aversion. Gaze is the tell.
- **LOVE**: enlarged + smile + pupil convergence + stillness. Motion + gaze differentiate from HAPPY.

**At-risk pairs** (resolved by design):

**CURIOUS vs CONFUSED**: Previously shared "slight vertical expansion + mild slope + warm color." Resolved: CURIOUS has **asymmetric brow** (one eye hooded, unique among all moods) + **slightly open mouth** (0.1). CONFUSED has **symmetric inner furrow** (slope +0.2, puzzled/tense) + **mouth offset** (off-center). Asymmetric vs symmetric eye shape creates an unmistakable silhouette difference.

**LOVE vs HAPPY**: Previously shared "smile + enlarged eyes + warm color." Resolved: LOVE has **pupil convergence** (soft focus) + **stillness** (reduced wander). HAPPY has **squished eyes** (0.9 height vs 1.05) + **dynamic wander**. The squint-vs-open eye shape survives grayscale; motion channel adds redundancy.

**THINKING vs ANGRY**: Shared brow furrow direction but at different magnitudes. Resolved: ANGRY has **extreme vertical compression** (0.65 height, slit) + **deep furrow** (0.8). THINKING has **neutral geometry** (1.0, 1.0) + **moderate furrow** (0.4) + **gaze aversion**. ANGRY = compressed energy, THINKING = directional energy.

---

## 3. Per-Gesture Visual Design

Gestures are phasic overlays — they temporarily modify the face and expire. They overlay whatever tonic mood is active.

### BLINK (180 ms) — Cosmetic
**Intent**: Natural rhythm, transition choreography.
**Motion**: Both eyelids close fully then reopen. Quick, natural.

### WINK_L / WINK_R (200 ms) — Semantic
**Intent**: Playful acknowledgment, shared secret.
**Motion**: One eye closes while the other stays open. Slightly slower than blink for legibility.

### NOD (350 ms) — Semantic
**Intent**: Agreement, understanding, "yes."
**Motion**: **Vertical gaze oscillation** — pupils dip down then return up, 1–2 cycles. Slight upper lid droop follows the gaze. Reads as a head nod. Gaze bypasses spring (direct kinematics) for crisp amplitude at 12 rad/s. **[New — replaces V2's mouth-chatter reuse]**
**Distinguish from**: BLINK (both eyes close vs gaze moves). LAUGH (mouth-driven vs gaze-driven).

### HEADSHAKE (350 ms) — Semantic
**Intent**: Disagreement, negation, "no."
**Motion**: **Horizontal gaze oscillation** — pupils sweep left-right-left, 2–3 half-cycles. Slight frown accompanies. Reads as a head shake. Gaze bypasses spring (direct kinematics) for crisp amplitude at 14 rad/s. **[New — replaces V2's mouth-offset reuse]**
**Distinguish from**: NOD (vertical vs horizontal). CONFUSED (mouth offset vs gaze motion).

### LAUGH (500 ms) — Semantic
**Intent**: Joy, humor response, "haha!"
**Motion**: Mouth opens and closes rapidly (chatter), big smile (curve 1.0). Vertical flicker in eye position. Eyes bounce.
**Distinguish from**: NOD (smooth gaze vs choppy eye bounce). HAPPY mood (sustained smile vs animated chatter).

### CONFUSED (500 ms) — Semantic
**Intent**: Uncertainty, "didn't understand that."
**Motion**: Mouth offsets side-to-side (smirk oscillation). Horizontal eye flicker. The phasic gesture version of the sustained CONFUSED mood.
**Distinguish from**: HEADSHAKE (deliberate gaze sweep vs mouth-driven smirk). CONFUSED mood (sustained vs brief).

### WIGGLE (600 ms) — Semantic
**Intent**: Playful energy, excitement burst.
**Motion**: Combination of horizontal and vertical eye flicker + mouth chatter. Everything wiggles. Pure joy-fizz.
**Distinguish from**: LAUGH (vertical bounce only). CONFUSED (horizontal only).

### SURPRISE (800 ms) — Semantic
**Intent**: Startle, amazement.
**Motion**: Eyes widen rapidly to peak (1.3×, 1.25×) over 150 ms, mouth opens to O-shape, then gradually returns. Brief dramatic widening.
**Distinguish from**: SURPRISED mood (sustained vs brief peak). EXCITED (sustained large eyes vs dramatic peak-then-return).

### HEART (2.0 s) — Semantic
**Intent**: Affection, love display.
**Motion**: Eyes replaced with solid heart shapes. Warm smile. Pink face color override.
**Distinguish from**: LOVE mood (regular eyes with gentle expression vs heart-shaped eyes).

### X_EYES (2.5 s) — Semantic
**Intent**: Comedic "dizzy," overload.
**Motion**: Eyes replaced with X shapes. Slight mouth open. Red-tinted face color.
**Distinguish from**: ANGRY (normal angry eyes vs X shapes). Used only in clearly comedic context.

### SLEEPY (3.0 s) — Semantic
**Intent**: Tired, winding down.
**Motion**: Gradual eyelid droop + downward gaze drift + yawn sequence (mouth opens wide then slowly closes). Sway (gentle horizontal gaze oscillation).
**Distinguish from**: SLEEPY mood (sustained heavy lids vs the animated droop-and-yawn sequence).

### RAGE (3.0 s) — Semantic
**Intent**: Comedic anger (fire effect).
**Motion**: Extreme lid slope (0.9), eye shake (rapid horizontal oscillation), mouth clenched then opens with wave. Fire particles spawn and rise. Comedic, not threatening.
**Distinguish from**: ANGRY mood (measured displeasure vs cartoon explosion). Used only in clearly comedic context.

---

## 4. Conversation State Visual Summary

Per spec §4.2.2. One-line visual descriptions:

| State | Visual Read | Key Cue |
|---|---|---|
| **IDLE** | Robot at rest, eyes wandering | No border, relaxed gaze |
| **ATTENTION** | "I heard you!" — alert snap | Border flash + gaze snap to center |
| **LISTENING** | "I'm paying attention" — steady focus | Teal breathing border, eyes locked on child |
| **PTT** | "Recording" — held state | Amber pulsing border, eyes locked |
| **THINKING** | "Working on it" — processing | Blue-violet orbit dots, eyes look up-right |
| **SPEAKING** | "Here's what I think" — engaged delivery | White-teal energy border, talking animation |
| **ERROR** | "Oops, something went wrong" — brief glitch | Orange flash, quick gaze aversion then return |
| **DONE** | "Conversation finished" — releasing | Border fades, eyes return to wander |

### Transition Choreography

| Transition | Visual Sequence |
|---|---|
| IDLE → ATTENTION | Border sweeps inward + gaze snaps to center (400ms) |
| ATTENTION → LISTENING | Border blends teal + alpha settles to breathing (200ms) |
| LISTENING → THINKING | Gaze averts up-right (spring ~300ms) + border shifts to blue-violet + dots start |
| **THINKING → SPEAKING** | **Anticipation blink (100ms) + gaze returns to center (spring ~300ms) + border shifts. TTS onset at blink apex (~50ms) for speech-preparation illusion.** |
| SPEAKING → DONE | Border fades (500ms) + mood ramps to neutral (500ms) + gaze releases |
| **Any → ERROR** | **Border flashes orange + gaze micro-aversion left (200ms) then returns to center** |

**Supervisor note — TTS coordination**: The THINKING→SPEAKING anticipation blink is the face's "I'm about to speak" tell. For maximum illusion quality, the supervisor should dispatch the TTS audio start timed to the blink apex (~50ms into the 100ms blink), so the mouth begins moving as the eyes reopen. This is a **supervisor-side timing requirement** — the face sim and MCU firmware treat the blink and speech onset as independent events. If TTS latency exceeds ~100ms, fire the blink at transition time anyway (don't delay it for TTS) — a brief eyes-closed-then-speaking beat still reads better than simultaneous snap.

---

## 5. Parameter Mapping

Concrete values for implementation. All **[Provisional]** values are sim-authored and pending visual review + T3/T4 evaluation.

### 5.1 Eye Scale Per Mood

```python
MOOD_EYE_SCALE: dict[Mood, tuple[float, float]] = {
    # (width_scale, height_scale) — 1.0 = default geometry
    Mood.NEUTRAL:   (1.0,  1.0),   # Baseline
    Mood.HAPPY:     (1.05, 0.9),   # Wider, squished (happy squint)
    Mood.EXCITED:   (1.15, 1.1),   # Big wide eyes
    Mood.CURIOUS:   (1.05, 1.15),  # Taller (attentive)
    Mood.SAD:       (0.95, 0.85),  # Smaller, deflated
    Mood.SCARED:    (0.9,  1.15),  # Narrow-tall (tense, frozen)
    Mood.ANGRY:     (1.1,  0.65),  # Wide, compressed slit (glare)
    Mood.SURPRISED: (1.2,  1.2),   # Biggest (matches MCU)
    Mood.SLEEPY:    (0.95, 0.7),   # Narrow slits
    Mood.LOVE:      (1.05, 1.05),  # Slightly enlarged (soft)
    Mood.SILLY:     (1.1,  1.0),   # Wider (goofy)
    Mood.THINKING:  (1.0,  1.0),   # Neutral size (gaze aversion carries distinctiveness)
    Mood.CONFUSED:  (1.0,  1.05),  # Slightly taller (puzzled)
}
```

**Guardrail intensity caps**: Four moods have intensity caps (spec §7) that limit the effective runtime eye scale. The `MOOD_EYE_SCALE` values above are raw design targets at full intensity (1.0). Effective maximum = `1.0 + (target - 1.0) × cap`:

| Mood | Authored (W, H) | Intensity Cap | Effective Max (W, H) |
|---|---|---|---|
| SURPRISED | (1.2, 1.2) | 0.8 | (1.16, 1.16) |
| ANGRY | (1.1, 0.65) | 0.5 | (1.05, 0.825) |
| SCARED | (0.9, 1.15) | 0.6 | (0.94, 1.09) |
| SAD | (0.95, 0.85) | 0.7 | (0.965, 0.895) |

The same intensity blending applies to all `MOOD_TARGETS` (mouth, eyelids) and `MOOD_COLORS`. Whether to over-author values to compensate for capping (e.g., SURPRISED at (1.25, 1.25) to achieve (1.2, 1.2) at cap 0.8) is a design decision deferred to visual review.

### 5.2 Mood Targets (mouth + eyelids)

Keep existing spec §4.1.2 values — they are MCU-verified and consistent with the visual descriptions above. No changes needed to `MOOD_TARGETS`.

### 5.3 NOD Gesture Constants

```python
NOD_GAZE_Y_AMP = 4.0        # Vertical gaze displacement (pixels in gaze space)
NOD_FREQ = 12.0              # rad/s — ~2 nods in 350ms
NOD_LID_TOP_OFFSET = 0.15   # Slight upper lid follows gaze
```

**Implementation note**: Gaze values are written **post-spring** (direct to `gaze_y`, not `gaze_y_target`) to bypass the damped spring (k=0.25, d=0.65) which would attenuate the 12 rad/s oscillation to ~60-70% amplitude. The lid droop uses pre-spring tweens as normal. Same pattern as flicker effects.

### 5.4 HEADSHAKE Gesture Constants

```python
HEADSHAKE_GAZE_X_AMP = 5.0   # Horizontal gaze displacement
HEADSHAKE_FREQ = 14.0        # rad/s — ~2.5 sweeps in 350ms
HEADSHAKE_MOUTH_CURVE = -0.2  # Slight frown during headshake
```

**Implementation note**: Gaze values are written **post-spring** (direct to `gaze_x`, not `gaze_x_target`) to bypass spring attenuation. The mouth frown uses pre-spring tweens as normal.

### 5.5 ERROR Micro-Aversion Constants

```python
ERROR_AVERSION_DURATION = 0.2   # 200ms gaze micro-aversion
ERROR_AVERSION_GAZE_X = -0.3   # Look-away direction (normalized, multiplied by MAX_GAZE)
```

### 5.6 MCU Parity Notes

| Value | MCU Current | V3 Sim | Status |
|---|---|---|---|
| SCARED eye_scale | (0.9, 1.0) | (0.9, 1.15) | Sim-authored; height increase pending firmware port |
| All other eye_scale | (1.0, 1.0) | Per §5.1 table | Sim-authored; new entries pending firmware port |
| NOD/HEADSHAKE gestures | Reuse laugh/confused | Dedicated gaze anim | Sim-authored; firmware uses MCU's existing anims until port |
| ERROR micro-aversion | Not implemented | 200ms gaze offset | Sim-authored; supervisor-side for firmware |
| SAD color | (50, 80, 200) | (70, 110, 210) | Brightened for TN panel luma floor (§1.3.1); pending firmware port |
| SLEEPY color | (40, 60, 100) | (70, 90, 140) | Brightened for TN panel luma floor (§1.3.1); pending firmware port |
| CURIOUS lid_slope | -0.15 | 0.0 | Removed (asymmetric brow replaces slope); pending firmware port |
| CURIOUS asymmetric brow | None | 0.25 (right eye extra lid_top) | New: one-eyebrow-raised look; pending firmware port |
| CONFUSED lid_slope | -0.15 | +0.2 | Flipped to inner furrow for silhouette distinctiveness; pending firmware port |
| CONFUSED mouth_offset | None | 2.0 | Persistent asymmetric mouth; pending firmware port |
| LOVE convergence | None | ±2.5 gaze_x | Mild pupil convergence + reduced idle wander; pending firmware port |
| ANGRY eye height | 0.75 | 0.65 | Compressed further for silhouette distinctiveness; pending firmware port |
| THINKING eye width | 0.95 | 1.0 | Neutralized (gaze aversion carries mood); pending firmware port |

All sim-authored values are ahead of MCU as design iterations. The parity check will flag these divergences until firmware is updated.
