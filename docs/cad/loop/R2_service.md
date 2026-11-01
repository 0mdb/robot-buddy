# R2 service tasks, timed on paper (tick 37, 2026-10-31)

Target: **one tool, < 5 min each.** Steps from the generated geometry and R1's sequence; times are estimates for an adult with the parts in hand.

| Task | Steps | Tools | Time | Verdict |
|---|---|---|---|---|
| **Swap the battery** (2 × 18650) | canopy off (4 buttons) · swap cells in the HAT clips · canopy on | 2.0 key | ~3 min | ✓ (the 2.0 key is the deliberate exception, A2) |
| **Swap a track** | canopy off? (see note) · loosen the carriage clamp (M3 × 16 down to a **nyloc under the plate**) · back the jack screw off (ball-end 2.5, 18 mm to the encoder, R1-F3) · push the carriage forward (4.6 mm install slack, 08) · belt off sideways over the wheels · reverse | 2.5 ball-end key **+ 5.5 spanner under the plate** | ~4 min | ⚠️ two tools, the nut is blind under the plate: **R2a** |
| **Swap a motor** | canopy off · deck + Pi stack off as one unit (4 × M3, open since P4b) · unplug the motor lead at the reflex board · sprocket off (M2, 1.5 key) · 2 × M3 × 28 through the gearbox · reverse | 2.0 + 2.5 + 1.5 keys | ~8–10 min | ❌ the lead ends on the reflex board **under the deck**: **R2b** |
| **Reach the reflex USB port** | canopy off · then depends on the connector's edge: the board sits under the deck (z 3–18.6, deck at 24, 5.4 mm over it); the board's side edges (\|y\| 30) face the encoders 0.7 mm away | 2.0 key | ~1 min if the port faces the rear bay, else deck off (~5 min) | ⚠️ **R2c: a PCB layout decision, and the PCB isn't ordered yet** |

## Fixes
- **R2a (sw):** heat-set M3 insert in the carriage foot for the clamp screw, so it threads from the top (05 already lists this option) and the nut under the plate goes away. One 2.5 key for the whole track swap.
- **R2b (doc → wiring), corrected tick 58:** the motor lead is **6 wires** (reflex J1/J2 are JST-XH 6-pin: AO1, AO2, +5 V, GND, ENC_A, ENC_B), not 2. The fix is a break in that lead near the mount, so a motor swap never touches the deck:
  1. **If the encoder TT motor has its own socket on the encoder board** (many Yahboom encoder motors ship with a PH2.0 6-pin socket and a loose cable): use it. The lead already unplugs at the motor end; nothing to add. **Check on the motors in hand** (TODO measurement list).
  2. Otherwise an **inline 6-pin JST-XH pair** (same family as J1/J2, keyed, one crimp tool) within ~40 mm of the mount, with the plug on the motor side. Clip it to the plate in the free strip between the canopy tongue slot and the motor (x −14…−10 is tight; the wire slot at y 0 is the route to the board).
  Either way, motor swap: canopy off, sprocket off (M2, 1.5 key), unplug, 2 × M3 through the gearbox (2.5): **~4 min**, two small keys (the sprocket's M2 is set by the TT shaft).
- **R2c (PCB, before ordering the reflex board):** put the USB-C on the board's **rear edge (x −40)**, facing the free bay between the board and the carriages (x −47…−40, |y| < 28, under the deck): reachable with only the canopy off, even with a right-angle plug. Not the side edges (0.7 mm to the encoders) and not up (5.4 mm to the deck). Goes into the reflex PCB verify step in TODO.
