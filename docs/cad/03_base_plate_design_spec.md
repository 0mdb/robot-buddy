# Robot Buddy — Base Plate Design Spec

Starting target for the first printable base plate. Tracked vehicle, 2 driven motors at the front (Yahboom encoder TT), 2 idler followers at the rear, Raspberry Pi mounted on top.

> **⚠ Material reconciliation (read first).** This spec predates the framework
> and was written around **Polymaker PETG**. The authoritative design rules are
> now `docs/print-dfm.md`, and the material map is `docs/print-bom.md`
> (buddy tracks robot-scout's palette): the structural material is **PET-CF**,
> with **PETG used only for the first fit-test prototype**. Design the part to
> PET-CF DFM; print proto #1 in PETG, commit the final in PET-CF. Deltas vs the
> PETG assumptions below:
> - **Fillet every internal corner (≥0.5–1 mm)** — CF is notch-sensitive; sharp
>   internal corners are crack initiators. (The rib fillets in §6 already help.)
> - **Shell + ribs, uniform wall** — never a thick solid mass; the 4 mm plate +
>   rib scheme in §6 is the right idea, keep walls uniform.
> - **Fit classes** (per print-dfm): slip/moving **0.3–0.4 mm/side**, snug/press
>   **0.15–0.25 mm**. The "0.2 mm FDM-to-FDM" note below is the *snug* class.
> - **Hardened 0.6 nozzle + dried filament** for the CF run.
>
> **Also not yet in this spec (decide before final):** mounting provisions for
> the **reflex MCU board** (`CAD/library/robot-buddy-reflex-mcu.step`) and the
> ESP32-face board — this spec currently accounts only for the Pi + battery.

## 1. Top-level dimensions

| Dim | Value | Notes |
|---|---|---|
| Length (X) | 180 mm | Long enough for two axle pairs + Pi + a battery |
| Width (Y) | 110 mm | Driven by motor mount footprint + track clearance |
| Thickness | **4.0 mm** | **Set by manufacturing, not load.** Deflection analysis (PET-CF, E=5320 MPa X-Y): a 150 g central payload at 3× dynamic bows the plate only ~0.04 mm at 4 mm; even a 0.2 mm target needs just 2.3 mm — the plate is ~10× overbuilt on stiffness. 4.0 mm is driven by the **M3 counterbore** (2 mm deep, needs ~2 mm of material below) + PET-CF warp resistance over the 180 mm span. Clean 20×0.2 mm layers, ~100 g. (Acrylic's 4.5 mm was brittle-material conservatism; PET-CF doesn't need it.) |
| Print orientation | Flat on bed, top face up | Loads are shear/bending — layer planes aligned to load |
| Print time estimate | ~4 hr at 0.28 mm / 0.6 nozzle | |

The plate fits with margin on the P2S build plate (256 × 256 mm).

Coordinate convention: origin at geometric center of plate top face. +X is forward (drive end), +Y is left, +Z is up.

## 2. Motor mount interface (front)

Front motor pair sits at the +X end. Mounts bolt **through** the base plate from below.

**Measured from the STLs** (`docs/cad/measure_mount_holes.py` — re-runnable on
any mount STL). Each mount footprint is **40 × 38 × 23 mm** (base at Z=0):

| Interface | Measured | Meaning |
|---|---|---|
| **Base-attach holes (vertical, Z)** | **2 × Ø≈3.5 mm, spaced 14.75 mm** (along the mount's long/X axis), sitting near one short edge of the footprint | **This is the plate-side pattern** — 2× M3 per mount, *not* 4 |
| Motor screw holes (horizontal, Y) | 2 × Ø3.05 mm (M3) at **18.0 mm** spacing | TT motor's own mounting screws — not in the plate |
| Shaft bore (horizontal, X) | 1 × Ø4.67 mm at 11 mm height | Gearbox output shaft clearance — not in the plate |

> The earlier "4 × M3, 32 × 17 mm" was a wrong provisional guess — the bracket
> actually attaches with **2 × M3 at 14.75 mm**. L and R are **translated
> copies, not mirrors** (confirmed by their differing absolute STL positions) —
> mirror one in SW for a true L/R pair before placing them.
> Diameters are mesh-derived (±~0.2 mm at 0.3 mm sample res); treat 14.75 and
> 18.00 mm spacings as reliable, confirm Ø on the SLDPRT.

Plate-side layout (each mount contributes a **2-hole, 14.75 mm** pattern):

| Feature | Position (X, Y) | Notes |
|---|---|---|
| Left motor mount center | (+55, +35) | Provisional; Y offset = (plate width / 2) − mount half-width − wall |
| Right motor mount center | (+55, −35) | Mirrored placement (part itself needs mirroring too) |
| Mount-to-mount track centerline gap | 70 mm | Sets the track width |
| **Mount bolt holes** | **2 × M3 through, Ø3.4 mm, 14.75 mm apart** per mount | Orient the 14.75 mm axis along the plate's X (fore-aft) |
| Bolt heads | Counterbored/countersunk on TOP face, 6.0 mm dia × 2.0 mm deep | So Pi sits flush above |

## 3. Idler / rear follower mounts

Same approach as front mounts, but no encoder — simpler L-bracket bolted from below. Plate-side: same M3 through-hole pattern, mirrored about X=0 and translated to the rear.

| Feature | Position (X, Y) | Notes |
|---|---|---|
| Left idler center | (−55, +35) | Mirrors front mount layout |
| Right idler center | (−55, −35) | |
| Mount bolt holes | 4 × M3 through, 3.4 mm dia | |

## 4. Raspberry Pi mounting

Standard Pi 4 / Pi 5 mounting hole pattern: **58 mm × 49 mm**, M2.5 holes. Centered on plate, slightly forward of center (because most of the Pi's mass is in connectors at the rear, and we want CoG forward of the centerline for balance under acceleration).

| Feature | Position (X, Y) | Notes |
|---|---|---|
| Pi mount hole 1 | (+10 + 29, +24.5) = (+39, +24.5) | Front-left |
| Pi mount hole 2 | (+10 + 29, −24.5) = (+39, −24.5) | Front-right |
| Pi mount hole 3 | (+10 − 29, +24.5) = (−19, +24.5) | Rear-left |
| Pi mount hole 4 | (+10 − 29, −24.5) = (−19, −24.5) | Rear-right |
| Hole spec | M2.5 through, 2.9 mm dia | Use M2.5 standoffs (printed or brass) |

Keep-out: 90 × 60 mm rectangle around the Pi for SD card, cables, and connectors clearance. No features (ribs, mounting bosses) inside this zone on the top face.

## 5. Battery / electronics area

Reserve aft of Pi (between rear idler mounts) for a battery pack. **18650 2S2P holder** is ~75 × 38 × 22 mm — a good baseline. Add 2× M3 mounting holes 60 mm apart at (X = −50 to −75, Y = 0) for a strap or holder bracket.

## 6. Stiffening features

A 4 mm × 180 mm × 110 mm flat sheet of PETG will sag under load. Add stiffening:

- **Perimeter rib**: 2 mm tall × 1.8 mm wide rib around the bottom face perimeter, set in 2 mm from edge
- **Cross ribs**: 2 mm tall × 1.8 mm wide ribs on bottom face in a + pattern (one along X axis, one along Y axis), broken to avoid motor/idler mount footprints
- **Fillets**: 2 mm fillet between every rib and the plate; chamfer all top-face hole entries 0.5 × 45° to defeat elephant's foot

## 7. Drainage / wire pass-throughs

Two slots in the plate for routing wires between motors, Pi, and battery:

| Slot | Position | Size | Purpose |
|---|---|---|---|
| Forward wire slot | (+30, 0) | 20 × 6 mm | Motor wires up to Pi |
| Aft wire slot | (−40, 0) | 15 × 6 mm | Battery to Pi |

Round both ends of each slot (radius 3 mm). Add a 1 mm chamfer top and bottom so wires don't chafe on a sharp printed edge.

## 8. Heat-set insert use

Per your stock: M3 heat-sets where joints get re-opened, M2.5 standoffs through-hole + nut for everything else.

| Joint | Method |
|---|---|
| Motor mounts ↔ base plate | M3 through-hole + bolt + locknut, **OR** M3 heat-set into mount + bolt through plate. Either works; pick the heat-set route if you'll be removing motors for tuning. |
| Pi ↔ base plate | M2.5 standoffs (brass, female-female), bolted through plate with M2.5 nut |
| Top shell ↔ base plate (future) | M3 heat-set into base plate edge bosses, M3 bolt down through top shell |

If using heat-sets on motor mount joints: pockets 4.0 mm dia × 5.5 mm deep, oriented downward (insert from bottom face). Confirm dimensions against your specific brand of heat-set datasheet before printing.

## 9. Print-orientation gotchas

- **All bolt holes** in the plate run vertically (Z axis) → they print round, no problem.
- **Slots and wire pass-throughs** are also Z-axis → fine.
- **Rib undercuts** on bottom face: print plate top-face-up so ribs are "down" and print last as bottom features. They're shallow (2 mm) so no support needed.
- Don't print this part on its edge — every bolt would be loading layer-line shear.

## 10. DFM checklist before slicing

- [ ] Every wall ≥ 1.2 mm (preferably 1.8 mm)
- [ ] Every hole ≥ 3.0 mm; M3 = 3.4 mm, M2.5 = 2.9 mm
- [ ] All horizontal-axis holes either teardrop or oversized 0.4 mm
- [ ] Heat-set pockets 4.0 × 5.5 mm and oriented for bottom-face insertion
- [ ] Fillet at base of every load-bearing rib (2 mm min)
- [ ] Top-face hole entries chamfered 0.5 × 45°
- [ ] No FDM-to-FDM mating surface in direct contact — 0.2 mm clearance modeled
- [ ] Interference check passes in assembly
- [ ] Plate fits within 256 × 256 mm
- [ ] Estimated print time and material reasonable (< 6 hr, < 100 g)

## 11. SolidWorks build order

1. Open new part from `RB_part.prtdot`, save as `RB-PRT-001_base_plate.SLDPRT`
2. Sketch the 180 × 110 mm rectangle on Top plane, centered on origin → Extrude 4 mm
3. **Open `TT_Motor_Mount_L.stl` and `TT_Motor_Mount_R.stl` as reference geometry** to confirm bolt hole pattern. Use Insert → Features → Imported, or open as a new part and measure with the measure tool.
4. Sketch motor mount bolt pattern on top face → cut through with 3.4 mm holes + 6 mm counterbore
5. Sketch Pi mount holes → cut through with 2.9 mm holes
6. Sketch wire slots → cut through
7. Sketch bottom-face ribs → extrude downward, add fillets
8. Chamfer top-face hole entries
9. Insert → Reference Geometry → label key points/datums for assembly mating
10. Save part. Create drawing from `RB_drawing_A.drwdot`, dimension only the interfaces.
11. Export STL per the SolidWorks setup doc (binary, 0.01 mm deviation, mm units)
12. Slice in Bambu Studio with the custom Polymaker PETG profile and 0.6 mm nozzle process

## 12. First-print risk list

- Pi mount holes 2.9 mm: may end up undersize (PETG shrinks ~0.4 % on cool). Have a 2.5 mm drill bit ready to clean them.
- Counterbores: confirm bolt head OD before locking 6 mm — M3 socket cap heads are typically 5.5 mm OD; 6.0 mm gives 0.25 mm clearance per side which is tight.
- Mass balance: if the Pi sits this far forward, CoG may be ahead of front axles → robot wants to nose-down on hard stops. Verify in assembly using Mass Properties and consider battery placement to compensate.

## 13. What I had to assume (verify before printing)

- TT motor mount footprint and hole pattern — **MUST be measured from `TT_Motor_Mount_L.stl`** before committing the base plate hole pattern.
- Pi model: assumed Pi 4 / 5 with 58 × 49 mm pattern. If using a Zero or older Pi, hole positions change.
- Track width: 70 mm centerline-to-centerline is a starting point. Depends on the track you're using.
- Idler bracket dimensions: assumed same footprint as motor mount. If you're designing custom idler brackets, update Section 3.
