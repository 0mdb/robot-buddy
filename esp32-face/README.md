# esp32-face

ESP32-S3 (Face MCU) firmware: drives **one 16×16 WS2812B matrix** as a compact animated robot face.

Design goal: **buttery-smooth, always-responsive face** that never stutters due to motor control, AI calls, or Jetson workload. Face rendering + LED timing live entirely on this MCU.

---

## Framework
- ESP-IDF
- `led_strip` component (RMT backend) for WS2812 output

---

## Hardware Assumptions
- Single 16×16 WS2812 matrix
- 5V LED power rail with common GND to ESP32
- Brightness capped in firmware to manage current and prevent brownouts
- Matrix mounted behind diffuser / window (pixel blending expected)

---

## Face Layout (Single-Panel Constraint)
With only 16×16 pixels, the face is **symbolic, not literal**:

- Eyes share a single matrix
- Face is split logically into regions:
  - Left eye: columns ~2–6
  - Right eye: columns ~9–13
  - Center gap used for expression spacing / nose suggestion
- Mouth is optional and minimal (single row or implied via eye shapes)
- Emotion is conveyed primarily via:
  - eye shape
  - pupil position
  - eyelids
  - brows / squint overlays

This trades realism for **clarity and robustness**, which is correct for a kid robot.

---

## "Robot Eyes" Port Strategy (RoboEyes-inspired)
We are **not** inventing eye behavior from scratch. We are porting the *behavioral model* from existing “robot eyes” projects while adapting rendering to a **single 16×16 raster**.

### What we reuse (conceptually)
- Eye state machine:
  - emotions/moods
  - blink cadence with randomness
  - idle saccades (micro gaze movement)
  - gaze targets with easing
- Parameterization:
  - blink interval ranges
  - gaze wander limits
  - emotion intensity blending

### What we replace
- OLED / GFX rendering → **custom 16×16 raster renderer**
- Frame-by-frame sprites → **parametric primitives + masks**

### Why this works at 16×16
At this scale, **timing > detail**:
- Human-like blink timing
- Subtle gaze shifts
- Emotion conveyed by eye openness, tilt, and symmetry
- Consistent refresh (30–60 fps)

---

## Rendering Model
- Single 16×16 framebuffer (RGB or indexed + palette)
- XY mapper supporting:
  - serpentine vs progressive wiring
  - configurable origin + rotation
- Logical subregions:
  - left eye region
  - right eye region
- Render loop:
  1) sample current face state
  2) advance eye state machine
  3) rasterize parametric eye primitives into framebuffer
  4) apply global brightness cap (+ optional gamma)
  5) push pixels via `led_strip`

### Eye Primitives
- Sclera mask (static per eye)
- Pupil blob (2×2 or 3×3) with `(x,y)` offset
- Eyelid mask (top/bottom) for blink/squint
- Brow line (1–2 pixels) for emotion emphasis

---

## Control Interface (Jetson → Face MCU)
USB serial binary protocol (no JSON).

### SET_STATE (continuous, ~10–20 Hz)
- emotion_id (happy / curious / scared / sleepy / angry / sad)
- intensity (0–255)
- gaze_x, gaze_y (small range, e.g. -3..+3)
- brightness_cap (0–255)

### GESTURE (events)
- blink / double blink
- wink L/R (implemented as asymmetric eyelids)
- surprise (wide eyes + pause)
- idle_reset

Face MCU owns animation timing; Jetson only requests state changes.

---

## Tasks / Timing
- `usb_serial_task`: parse packets, update shared face state
- `anim_task`: 60 fps tick (state machine + render)
- optional `telemetry_task`: fps, dropped packets, current emotion

No blocking in the animation path.

---

## TODO
### Bring-up
- [ ] Define matrix pinout + LED order (serpentine vs progressive)
- [ ] Confirm orientation and logical eye regions
- [ ] Implement XY mapping helpers + test patterns

### Output
- [ ] Initialize `led_strip` (RMT)
- [ ] Implement framebuffer + push path
- [ ] Verify stable refresh at target FPS

### RoboEyes-inspired behavior port
- [ ] Implement eye state machine core:
  - idle gaze wander
  - randomized blink scheduler
  - emotion → eye shape mapping
- [ ] Implement gestures as temporary overrides layered on emotion

### Protocol
- [ ] Implement USB serial packet framing + parsing
- [ ] Implement SET_STATE + GESTURE handlers
- [ ] Add timeout → safe idle face

### Power robustness
- [ ] Global brightness cap
- [ ] Brownout-safe behavior (drop brightness / simplify animation)
- [ ] Default safe idle face on loss of host commands

