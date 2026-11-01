# UPS HAT (B) ports, from Ben's photos (2026-11-01)

Photos: `shots/hat/hat_top.jpg` (plan view, GPIO header at the top), `shots/hat/hat_port_edge.jpg`
(the port edge, looking at the Pi's USB-C / micro-HDMI side).

**Correction to 06 §6 and S4:** the HAT has **no USB-C**. Its port edge carries:

| Feature | Silkscreen | Along the edge, from the board's hole end (X_L) 🟡 ±2 | Width | Past the PCB edge |
|---|---|---|---|---|
| Slide switch | OFF/ON | 16.7 | ~3.7 (knob) | ~3 |
| USB-A socket (5 V out) | 5V OUT | ~31 | ~13 | flush, under the HAT PCB |
| DC barrel jack (8.4 V charge in, 5.5 × 2.1 assumed) | 8.4V | 47.5 | ~7.7 | ~2.5, under the HAT PCB |
| Charge / warning LEDs | WARNING | ~70–77 | | top face |

Plus: solder pads beside the silkscreen (5V OUT pair, 8.4V pair), and a **piezo buzzer (Ø ~14)** standing
at the board's +X (USB/Ethernet) end, centre ~3 mm off the board's mid-line, reaching **~15–20 mm past the
PCB** (partly out of frame). The cell holder overhangs the 85 mm board by ~7 mm at the hole end and ~6 at
the +X end (perspective: the holder top is nearer the camera, so these read slightly large).

Method: plan scale from the Pi's 58 × 49 hole pattern (16.3 / 16.5 px/mm). Heights are **not**
recoverable from the angled photo.

## In chassis coordinates

The stack is rotated 180° about Z at PI_AT (−10, 0, 27): the Pi's port edge faces **+Y (left side)**, its
USB/Ethernet end faces aft. So, at y ≈ +28 (tips ~+31):
- switch at chassis x ≈ **+5.8**
- USB-A at x ≈ **−8.6**
- barrel jack at x ≈ **−25**
- buzzer at the aft end, x ≈ −62.5 − (15…20) = **−78…−83**, y ≈ −3. The canopy's rear wall inner face is at
  x −83.2: **check for a clash** (and update the stack envelope, PI_BOX_X 54.5 → ~72 at the buzzer).

The canopy side wall is at |y| ≈ 53, so the switch and jack sit **~22 mm inboard** of it. A plain
cut-out (S4: ≤ 12 × 8, r 3) doesn't reach them: see Q23.

## Still needed from Ben (caliper)
1. Height of the HAT PCB underside above the standoff feet (or above the Pi PCB top). Fixes the switch and
   jack z.
2. The buzzer: how far past the PCB end, its diameter and the height of its centre.
3. Confirm the 53 mm stack height ends at the top of the cell holder.
