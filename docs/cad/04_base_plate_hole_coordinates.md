# Robot Buddy — Base Plate Hole Coordinate Table

> **Superseded in part by `06_frame_design_spec.md` (2026-10-30):** plate is **170 × 110** (X ∈ [−85, +85]); the §2 idler holes become follower tension slots; the motor mount now has **4 × Ø3.5 holes** (06 §7), not the 2 in §1. Re-derive positions once the assembly is rebuilt in the chassis frame.

Plate-side hole positions to drive the SolidWorks sketches for
`RB-PRT-001_base_plate`. Companion to `03_base_plate_design_spec.md`.

**Coordinate frame** (from spec §1): origin at the **geometric center of the
plate top face**. **+X forward** (drive/motor end), **+Y left**, **+Z up**.
Plate outline **180 (X) × 110 (Y) × 4.5 mm** → X ∈ [−90, +90], Y ∈ [−55, +55].

**Inputs used (spec defaults):** track centerline-to-centerline **70 mm**
(mount pairs at Y = ±35), Raspberry Pi centered **10 mm forward** of plate
center. Change these two numbers → only the motor/idler Y and the Pi X shift.

**Confidence key:** ✅ measured from STL · 🟡 provisional (placement or
undesigned bracket) — verify before committing.

---

## 1. Front motor mounts — ✅ pattern measured, 🟡 placement

2 × M3 per mount, **14.75 mm apart along X**, pair-midpoint at the mount
location. Ø3.4 mm through + Ø6.0 × 2.0 mm counterbore on the **top** face.

| ID | X | Y | Ø | Note |
|----|------|------|-----|------|
| M-L-1 | **+47.63** | **+35.00** | 3.4 | left mount, aft hole |
| M-L-2 | **+62.38** | **+35.00** | 3.4 | left mount, fwd hole |
| M-R-1 | **+47.63** | **−35.00** | 3.4 | right mount, aft hole |
| M-R-2 | **+62.38** | **−35.00** | 3.4 | right mount, fwd hole |

*Pair spacing 14.75 mm (measured). Mount footprint 40 × 38 mm sits X[35,75],
Y[16,54] on the left — clears the plate edge by ~1 mm, tight but OK.*

## 2. Rear idler mounts — 🟡 provisional (bracket not yet designed)

Mirrors the front placement about X = 0. Assumes the idler bracket reuses the
2 × M3 / 14.75 mm foot until a real idler part exists.

| ID | X | Y | Ø | Note |
|----|------|------|-----|------|
| I-L-1 | −62.38 | +35.00 | 3.4 | left idler, aft hole |
| I-L-2 | −47.63 | +35.00 | 3.4 | left idler, fwd hole |
| I-R-1 | −62.38 | −35.00 | 3.4 | right idler, aft hole |
| I-R-2 | −47.63 | −35.00 | 3.4 | right idler, fwd hole |

## 3. Raspberry Pi 5 mount — ✅ standard pattern, 🟡 placement

58 × 49 mm hole pattern, M2.5, Pi center at (+10, 0). Ø2.9 mm through
(use M2.5 standoffs). No counterbore — standoffs sit on top.

| ID | X | Y | Ø | Note |
|----|------|------|-----|------|
| Pi-1 | +39.00 | +24.50 | 2.9 | front-left |
| Pi-2 | +39.00 | −24.50 | 2.9 | front-right |
| Pi-3 | −19.00 | +24.50 | 2.9 | rear-left |
| Pi-4 | −19.00 | −24.50 | 2.9 | rear-right |

*Keep-out: 90 × 60 mm around Pi center → no ribs/bosses inside X[−35,55], Y[−30,30] on the top face.*

## 4. Battery strap — 🟡 provisional (holder not finalized)

2 × M3 strap anchors either side of an 18650 2S2P pack (~75 × 38 mm), aft of Pi.

| ID | X | Y | Ø | Note |
|----|------|------|-----|------|
| Bat-1 | −60.00 | +30.00 | 3.4 | strap anchor L |
| Bat-2 | −60.00 | −30.00 | 3.4 | strap anchor R |

## 5. Wire pass-through slots — obround, Z-axis (print round)

| ID | Center (X, Y) | Size (X × Y) | End radius | Purpose |
|----|---------------|--------------|-----------|---------|
| Slot-Fwd | (+30, 0) | 20 × 6 mm | 3 mm | motor wires up to Pi |
| Slot-Aft | (−40, 0) | 15 × 6 mm | 3 mm | battery to Pi |

*Chamfer 1 mm top & bottom on both slots so wires don't chafe.*

## 6. Not yet placed — needs data

- **Reflex MCU board mount** — pattern unknown. The board model is
  `CAD/library/robot-buddy-reflex-mcu.step`; export it to STL and run
  `measure_mount_holes.py`, or pull the hole pattern from the KiCad PCB
  (`hardware/kicad/robot-buddy-reflex/`), then add a group here.
- **ESP32-face board mount** — same, once the face board footprint is known.
- **Camera mount (`CameraMount1`)** — measure its base holes if it bolts to the
  plate rather than a mast.

---

## Summary counts

| Group | Holes | Ø | Counterbore | Confidence |
|-------|-------|-----|-------------|-----------|
| Motor mounts | 4 | 3.4 | 6.0 × 2.0 top | pattern ✅ / place 🟡 |
| Idler mounts | 4 | 3.4 | 6.0 × 2.0 top | 🟡 |
| Pi 5 | 4 | 2.9 | none | ✅ / place 🟡 |
| Battery | 2 | 3.4 | none | 🟡 |
| Wire slots | 2 (obround) | — | — | from spec |

**14 round holes + 2 slots.** All positions verified inside the plate outline
(max |X| = 62.38 < 90, max |Y| = 35 < 55). Feed the ✅ motor pattern straight in;
treat 🟡 positions as start points and adjust when the mating parts are mated in
the assembly.
