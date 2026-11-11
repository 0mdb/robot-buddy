# Robot Buddy — Frame Design Spec — Rev 1

**Status:** decisions locked 2026-10-30; layout numbers marked 🟡 are set once
the envelopes in §9 exist. Supersedes the plate **length** and the
**idler/tension** parts of `03_base_plate_design_spec.md` and
`04_base_plate_hole_coordinates.md`. Everything else in 03/04 still applies.
Design rules: `docs/print-dfm.md`. Materials: `docs/print-bom.md`.
Audio parts and their mounting rules: `docs/audio-hardware.md`.

## 1. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Track tension at the rear followers only.** Motor mounts are fixed (round holes, no slots). | The motor mount carries drive torque reaction plus tension; a friction-clamped slot can creep. One adjustable end means one thing to keep square. Mechanism already specified in `05_follower_spec.md`. |
| D2 | **Body in 3 printed pieces:** base plate, front bulkhead, canopy. | Face, speaker, camera and sonar live on the bulkhead, so opening the canopy drags no cables except the mic FPC. The bulkhead also stiffens the front. |
| D3 | **Plate is 170 (X) × 110 (Y) × 4 mm**, as modelled. One piece; fits the P2S bed. | Keeps the existing model. 03/04 said 180. |

## 2. Coordinate frame and the assembly rebuild

Chassis frame per CLAUDE.md: **origin at the plate top-face centre, +X forward,
+Y left, +Z up.** Plate extents X ∈ [−85, +85], Y ∈ [−55, +55], Z ∈ [−4, 0].

The current `RB-ASM-100_chassis.SLDASM` is not in this frame. Read on
2026-10-30: it is Y-up (the plate's thickness runs along SolidWorks Y), the plate
origin is off-centre (box X[−25.6, 84.4], Z[−30.5, 139.5]), and the other
components float unmated. Two virtual parts (`Part2^…`, `MirrorPart2^…`, the
follower blocks) and an empty `Part8^…` live only inside the assembly.

**Rebuild done 2026-10-30** (`tools/chassis.py rebuild`, engine `tools/swbuild.cs`):

- `CAD/parts/RB-PRT-001_base_plate.SLDPRT`: new plate in the chassis frame, 170 × 110 × 4,
  Ben's outline (20 mm 45° front chamfers, R20 rear corners), top face at Z = 0. Volume
  72,513.3 mm³, matching the independent calculation exactly. Holes and bosses come with §4.
- `CAD/library/TT_Motor_envelope_v2.SLDPRT`: TT motor from the Yahboom drawing. Frame:
  origin at the mounting-hole midpoint on the bracket face, +X to the gearbox/shaft end,
  +Y along the shaft. Widths marked TBD in `chassis.py` are not measured.
- `CAD/assemblies/RB-ASM-101_chassis.SLDASM`: plate (fixed), mounts, motors, each with an
  explicit transform (read back with zero error). Centroid Y = 0.00: the left/right
  placement is symmetric. `RB-ASM-100_chassis.SLDASM` is left untouched until Ben OKs
  deleting it; the follower blocks inside it are still virtual (to be redesigned per 05).
- **Motor orientation** (from the drawing: Ø3.2 holes 17.5 apart parallel to the shaft;
  shaft 19.8 from the hole line toward the gearbox end): motor on the upright's outboard
  side, shaft outboard, gearbox forward against the mount's gusset, can and encoder aft.
  So **`TT_Motor_Mount_L` fits the RIGHT side** (rotated 180° about Z) and its mirror the left.
- **Station:** shaft at X = 52.7, gearbox face flush with the plate edge (|Y| = 55). That is
  as far forward as the mount foot can go and stay inside the 20 mm front chamfer; the
  sprocket tip (Ø54.34) lands 5 mm behind the plate nose. 🟡 review.
- **Interference, both sides (🟡, envelope widths unmeasured):** encoder (25 tall) dips
  1.0 mm into the plate (323 mm³); gearbox (22 wide, guessed) overlaps the mount foot
  (197 mm³). The mount puts the motor centre 11.5 above the plate, so any motor part
  wider than 23 mm touches. Fix after measuring the motor: plate relief under the encoder,
  or raise the mount holes.

## 3. Architecture

| # | Piece | Carries | Material (final / proto) | Print orientation |
|---|---|---|---|---|
| 1 | **Base plate** | Motor mounts, follower slots, reflex board, TB6612 (if off-board), XVF core board, Pi deck posts, bulkhead foot, canopy rear bosses | PET-CF / PETG black | Flat, top face up, ribs down |
| 2 | **Front bulkhead** (upright frame across the front) | Face board, speaker back box, HC-SR04 housing, camera; canopy front bosses | PET-CF / PETG black | On its back face, so face/speaker openings are Z-axis holes |
| 3 | **Canopy** (lift-off cover) | Mic disc on top (grommeted, ported); access cut-outs | **ASA white** / PETG | Open side down, mic ports print as vertical holes |

Separate small parts (unchanged scope): motor mounts L/R, follower carriages +
wheels, Pi deck (the "Pi holder"), speaker back box, mic grommets, gaskets.

### Two-level layout

The boards don't fit side by side on a 110 mm plate: Pi 5 (56 mm) plus reflex
board (60 mm) is 116 mm across. So:

- **Level 0, plate top:** reflex board (52.5 × 46 since 2026-11-09, was 65 × 60; M3 holes at a 45.5 × 39 pattern, `hardware/kicad/board_outline.py`),
  TB6612 if off-board, XVF3800 core board, wiring. Low-profile parts only.
- **Level 1, Pi deck:** the Pi stack on a printed deck (3 mm) standing on 4 posts
  from the plate. Stack, bottom to top (measured 2026-10-30): 6 mm brass standoffs
  → Freenove M.2 NVMe adapter → Pi 5 → UPS HAT (B) with cells. **53 mm** from the
  adapter's bottom to the HAT top (Pi USB tops at 30), **59 mm** with the standoffs.

| Z (above plate top) 🟡 | Level |
|---|---|
| 0 → ~19 | level-0 boards: 5 mm standoffs + PCB + tallest part (~12 mm [assumption]) |
| ~24 → 27 | Pi deck (5 mm clearance, 3 mm deck) |
| 27 → 33 | brass standoffs |
| 33 → 86 | Pi stack |
| ~93 | canopy top inside (5 mm clearance + 1.8 wall); mic disc above |

**Risks from the stack:** the battery cells ride on top, so the CoG is high (check
Mass Properties; keep the stack aft of the motors and low as level 0 allows).
The Pi 5 is sandwiched between the NVMe adapter and the UPS HAT: confirm how it's cooled,
and vent the canopy over the stack. The UPS charge port is at the stack top: the canopy cut-out goes there.

The battery mass rides with the Pi. Place the deck so the CoG sits between the
axles, slightly aft of centre, to offset the front motors (check with Mass Properties).

## 4. Base plate (piece 1)

| Zone | X range 🟡 | Content |
|---|---|---|
| Bulkhead foot | +70 … +85 | Locating slots + 3 × M3 up into bulkhead inserts |
| Drive | +40 … +80, at the Y edges | Motor mounts, **fixed**, 2 × M3 each; counterbored top face (03 §2) |
| Centre | −40 … +60 | Level-0 boards under the Pi deck; deck posts |
| Tension | −85 … −45, at the Y edges | Follower slot pairs: 2 guide slots (anti-yaw) + clamp slot, **10 mm travel along X**, nuts reachable from below |
| Canopy rear | −85 … −75 | 2 × M3 heat-set bosses |

Keep from 03: 4 mm thickness, perimeter + cross ribs on the bottom face, 0.5 mm
bottom-edge chamfer, ≥ 2 mm rib fillets, chamfered wire slots.

**Existing features:** the notch in the left edge is **dropped** (Ben, 2026-10-30).
The upright bracket I first called "rear left" is at the **front left** (Ben's plate has
its chamfered end forward). It carries a horizontal Ø3 pair 18 mm apart, the TT motor bolt
pattern: an older built-in motor mount, now replaced by the separate L-brackets. The
notch was its motor clearance. Ben's plate is also **3.0 mm** thick (spec: 4.0, kept for
the insert under-bosses). The left-rear Ø3.5 × 7 slot pair was an early follower slot.

### 4.1 As built, rev 1 (2026-10-30, `tools/chassis.py`, all numbers in `chassis.py`)

`RB-PRT-001_base_plate.SLDPRT`, volume 78,195 mm³ (independent slab integration
78,228, within 0.04 %), ~98 g in PET-CF at 1.25 g/cm³ solid (less as printed).

| Feature | As built | Note |
|---|---|---|
| Motor-mount inserts (F2) | 8 × Ø4.0 × 7.2 pockets from the top, Ø9.2 under-bosses to Z −8 | hole positions from the measured foot; all full-size bosses fit (chamfer line x + \|y\| = 120) |
| Bottom ribs | 1.2 × 3.6: longitudinal at y 0, ±25 (x −80…75); transverse at x −60, −20, 20, 60 (\|y\| ≤ 44) | placement before FEA; S1 decides |
| Pi deck posts (F5) | 4 × Ø9.2 × 24 at (30, ±8) and ~~(−48, ±20)~~ **(−70, ±20)**; Ø4.0 × 7.2 insert pockets at the top | clear the reflex board, mount feet (0.8 mm) and carriages. No fins yet (24 tall > 2 × OD, 07 §1): add after FEA |
| Reflex standoffs (F7) | 4 × Ø9.2 × 5, insert pockets 7.2 deep (into the plate) | at the board's moved station, below |
| Follower slots (05) | per side: guide slots 4.7 wide at \|y\| 31 and 41, x −75…−45; clamp slot Ø3.4 at \|y\| 36, x −65…−55; jack end-stop block 10 × 11 × 10 at x −38…−28 with an Ø4.0 insert bore along X at z 5 (F4b) | axle mid-travel at x −60, ±5 mm; rail length 20 🟡 until the carriage is designed |
| Rear-corner relief | plate half-width 46 behind x −27 | **new:** the 44.2 track hangs ~6.3 inboard of the 31.6 gear, so the follower wheel (flanges at \|y\| ≈ 47) would cut the plate edge |
| Bulkhead foot (F1) | 3 × Ø3.4 at x 81.5, y 0 / ±22, counterbored Ø6.5 × 2 from below; 2 tab slots 4.6 × 10.4 at y ±11 | only x ≥ 78.5 is clear of the mount feet: a 6.5 mm strip. 🟡 review with the bulkhead design |
| Wire slot | 6 wide, x 35…55 on the centreline | between the mount feet |

> Amendment (Ben, 2026-11-08): **rev 2, flat 6 mm plate with top pockets.** Rev 1 printed
> ribs down and Orca supported every cell between the ribs (31 g, 1 h 25 on the plate alone;
> tree support ignores the bridge settings, and with normal support the edge strips and some
> closed cells still drew 12.6 g). Rev 2 has **nothing below the belly**: the plate is 6 mm
> (z −6…0) and prints belly down with no support; the ribs and the Ø9.2 under-bosses go, and
> the motor-mount insert holes go through (the 5.7 insert sits flush with the top). Stiffness
> comes from the thickness (a flat 6 mm section is 1.23 × rev 1's ribbed one in X bending)
> less 14 **top pockets** 3 deep (floor 3, r 3 corners, r 1 floor edge) cut where nothing rests:
> placed by an offline map of the contact footprints at z 0…1 (mount feet, carriages over
> their travel, bulkhead, canopy seat) and the plate's own posts, standoffs, jack blocks and
> openings, each grown by a 2.4 web, plus a 3 mm edge band, in cells between the old rib
> lines (`TOP_POCKETS`). Belly 2 mm higher than rev 1's rib bottoms (z −8 → −6). Screws
> up from the belly get 2 mm longer (07 §4.4 amendment). **Verdicts (2026-11-08, 2 mm mesh,
> PET-CF):** S1m 9.01 → **9.65 MPa**, inserts 1.04 → **1.03 mm** (drive increment 0.185 mm
> without the frame bars, ~0.09 with: < 0.2 ✓); S1b 3.20 → **2.64 MPa**, deck 0.127 →
> **0.097 mm**; S1a 11.76 → **9.84 MPa**. Peaks on a pocket's top corner (−3.4, 20.2, 0) and
> the bell-pocket rim (singular edges, 07 §3); SF ≥ 3.6 on the Z UTS. 0 interferences.
> Volume 100,704 mm³; sliced **105.1 g / 3 h 27 with 0.1 g support** (rev 1 128 g / 4 h 42
> with 31 g of tree support).

**Layout changes found while building:** the reflex board moved forward to the space between
the motors (pattern centre (−10.5, −3.5), board x −40…25, 0.7 mm to the encoders), because
the follower carriages (\|y\| 28…44 aft of x −40) left no room aft. The XVF3800 core
board and any off-board TB6612 now go aft, between the carriages (x −85…−40, \|y\| < 28) 🟡.

> Amendment (loop, 2026-11-06, Ben): **front chamfers removed.** Plate outline 20 mm 45°
> front chamfers → square front corners, plan r 3 (`FRONT_R`); rear R20 unchanged. The
> bulkhead and its S2a cheeks span |y| 52 at x 82–85 and hung over the cut corners (an
> unfinished-looking gap under the face). The motor station stays where the old chamfer line
> put it (`MOUNT_CHAMFER_REF` 20 → `mount_tx` 47.4): no drivetrain change. Plate 110.9 →
> 112.9 g. The bulkhead's side-flange bottoms, which the 15° tilt swings ~1 mm under the
> plate top at |y| 45–47, are trimmed 0.3 mm above the plate top (`BH_FLANGE_GAP`; they used to hang over the chamfer). The gap matters: trimmed flush at z 0, the flat faces were bonded by the FEA "fix plane z 0" and S5c read 9.9 MPa.

## 5. Front bulkhead (piece 2)

- Spans the plate width, inboard of the tracks; foot bolts to the plate (§4) with
  2 locating tabs into plate slots so it stands square without relying on the screws.
- Front face, top to bottom 🟡: camera; **face TFT**, tilted back 15° (a child
  looks down at a floor robot); **speaker grille** (≤ 2 mm openings + mesh, per
  audio §4.3); **HC-SR04** low at the front (existing housing).
- Speaker back box (PETG, sealed ~30 cc) mounts behind the grille through a gasket.
- **≥ 70 mm from speaker cone centre to the nearest mic** (audio §4.1).
- Rear face: cable tie points; face board USB/UART exit routed down to level 0.
- Uniform 2.4 mm walls, ribbed; fillet every internal corner ≥ 1 mm (PET-CF is notch-sensitive).

> Amendment (loop, 2026-10-30): bulkhead rev 1 built (P1). As built, `RB-PRT-002_bulkhead`
> (generated, `tools/chassis.py`), ~41 g PET-CF:
> - 94 wide × 126 tall (pre-tilt) × 3.0 wall, tilted 15° back about its back-bottom edge;
>   front face at x 85 at plate level. Side flanges 1.8 × 4.3, horizontal rib at z 50.
>   Wall 2.4 → **3.0**: the face inserts need a 1.3 mm skin in front of a 6.0 pocket.
> - Lower band: HC-SR04 holes Ø16.6 at y −35/−9, z 26 with 6 mm sleeves; speaker grille,
>   6 slots × 2.0 mm inside Ø34 at y +24, z 26. Sonar and speaker sit **side by side**: a
>   40 mm speaker under a 50 mm-tall face would push the head to ~150 mm.
> - Face board **behind** a 59.6 × 45.2 window (active area + 1 mm), LCD stack bearing on
>   the wall's back face, 4 × Ø7 × 4.3 standoffs with Ø4.0 × 6.0 insert pockets, so
>   F11 is **M3 × 5** (not × 6).
> - Camera lens hole Ø9 at z 113 (Q6 default); camera bosses 🟡 until the module is chosen.
> - Canopy lugs: 2 × Ø9.2 at y ±38 on the top back, insert pockets from the top (F9).
> - Foot: 59 × 6.5 × 9 block at x 78.5…85 with 2 tabs into the plate slots and 3 × M3
>   insert pockets from below (F1). The pocket's rear wall is only 1.0 mm (D4).
> - 🟡 for review: the sonar and speaker also tilt 15° up with the wall (sonar should
>   probably look level); head height ~122 above the plate vs the ~93 canopy over the stack.
> - **Rev 2 (P1b, tick 4):** one central knee gusset (2.4 thick at y 1.2…3.6, from the
>   wall's back face down to x 56, top at z 44: the only slot clear of the sonar sleeves
>   and speaker, and below the face board) with a 10 × 9.2 × 9 tail pad bolted down
>   through a new plate hole at (61, 2.4) (M3 up into an insert, counterbored). ≈ 43.7 g.
> - S5 standalone (foot only) still fails: 39.1 MPa / 8.0 mm. **With the canopy holding
>   the two lugs (S5c) it passes: 7.0 MPa / 0.27 mm.** The canopy (P6) must therefore
>   hold the lugs at least that stiffly. Q13 asks Ben which S5 restraint is the criterion.

> Amendment (Ben, 2026-11-09): **foot, head height, camera, HC-SR04.**
> - **Foot front** follows the wall's 15° above z 6.3 (it stood 2.4 proud of the wall at
>   its top; now ~1.6). Fully flush is impossible: the F1 pockets (x 81.5, Ø4.1 × 7.2)
>   keep `BH_FOOT_SKIN` 1.2 in front of them, and moving them aft hits the motor-mount
>   feet (0.7 behind the foot).
> - **Head +4 mm:** `BH_H` 126 → 130, `BH_TOP` 127.9 → 131.9 (the canopy follows). The
>   camera board must sit above the face board, whose edge-entry plugs (speaker, I2C, IO)
>   stand on its back along the top edge (ES3C28P drawing; Ben). Canopy S5k / S8 re-run
>   on PC: pass.
> - **Camera:** Arducam IMX708 75° = Raspberry Pi Camera Module 3 geometry (RPi
>   mechanical drawing). Lens at z 117; the Ø5.75 barrel passes through a Ø6.2 hole (tip
>   at the face: full 75°, no vignetting) and the lens block bears on the wall's back
>   face. 4 × Ø4.4 bosses take **M2 × 5 thread-forming** screws (F16). FFC connector at the
>   top (image rotation in software), 2.4 mm under the roof for its fold; 200 mm cable.
>   Envelope `camera_module3_envelope`.
> - **HC-SR04:** Ben's off-the-shelf holder (`CAD/Sensorgehäuse_Sensorhalter_
>   Ultraschallsensor_HC-SR04.3mf`) merged into the wall 1:1 (front plate with 2 × Ø17
>   and the crystal slot, 46 × 21 PCB pocket with its 0.67 snap ridges), replacing the
>   Ø16.6 sleeves. Its front stands 4.85 proud of the face (the right motor mount allows
>   the PCB back no further aft than ~76); the box is trimmed at x 74.5 (its ears
>   dropped), upside down so the pins (bent straight back, Ben) sit at the top. r 2 on its
>   outer edges, r 0.5 on the hole edges. 4 × **M1.6 × 6 thread-forming** from behind into
>   corner bosses (F17); no screws face forward. Envelope `hcsr04_envelope`: the Dupont
>   plug's tail touches the right mount's upright by ~0.5 (2.3 mm³) — route the wires
>   inboard, use a short / right-angle plug or solder them.
> - S5 / S5c to re-run on this bulkhead.

> Amendment (Ben, 2026-11-09, later): **the HC-SR04 holder is split out as RB-PRT-070.**
> Merged, it took the bulkhead's flat face-down print face (D3). Now the box passes through
> a window in the wall (0.2 a side) and the front frame gets lips that bear on the face: 6
> on top (z 38.5–44.5, pre-tilt), 3 below (z 10.5–13.5, 1.5 over the foot ledge). Held by
> 2 × M2 × 8 pan head thread-forming from the front through the top lip (y −4 / −40, z 41.5)
> into Ø4.4 bosses behind the wall (07 F18); the box in the window takes the moment. The
> sensor still snaps in from behind, F17 unchanged. The holder prints front face down.
> - **Knee gusset:** the holder runs through its plane (y 0–3 vs 1.2–3.6) back to x 74.5,
>   so the gusset is notched round it (0.2 clear) and its top's rear corner moves from the
>   wall (x 70.8) to x 60: a ≥ 5 mm band wraps behind the holder, so the wall above it
>   (z 37–44) still braces to the bolted tail. A plain notch would have cut the gusset in
>   two between z ≈ 27 and 37. The notch also takes the inner side flange's 2 mm at
>   y −47…−45.2 over the holder's height.
> - S5 / S5c (front push) to re-run with the new gusset before the bulkhead prints.

## 6. Canopy (piece 3)

- ASA white: heat-stable over the Pi 5 (PLA softens around 55–60 °C) and tougher when dropped. PLA only for bolt-on accents.
- Mic disc (Ø73, 3 × M3) on the top surface on TPU grommets; Ø1.2 mm ports,
  gasketed, ≤ 2 mm wall (audio §4.2).
- **Tool-only opening:** 4 × M3 into heat-set bosses (2 on the bulkhead top,
  2 at the plate rear). Lithium cells are inside, so the cover must not open by hand.
- Access cut-outs (no need to open the canopy): UPS HAT USB-C charge port, power
  switch, Pi USB/HDMI as needed 🟡. SD card: open the canopy.
- Uniform 1.8 mm wall; 1 mm fillets; vent slots over the Pi cooler, ≤ 2 mm wide.

> Amendment (loop P6, 2026-10-31): canopy first cut built, `RB-PRT-004_canopy`
> (generated, `tools/chassis.py`), 1.8 shell, ~108 g in **PC white** (S8 decided it over ASA,
> 07 §2 amendment), to E1 / Q18 (a):
> - Body over the Pi stack: x −85 (flush with the plate's rear edge) to the bulkhead,
>   |y| ≤ 53 (3.5 inboard of the belt), top z 93 (stack top 86). Plan corners r 20,
>   top edges r 8.
> - **Hood** behind the head: rises to the wall top; its ceiling (perpendicular to the
>   15° wall) sits 0.1 over the two canopy lugs and takes the two front screws, so the
>   canopy holds the lugs (S5c). Hood depth 15 behind the wall's back face covers the
>   face board's back. Back edges r 8.
> - Open at the front where the bulkhead closes it (|y| ≤ 47.3); side lips at |y| 47.3–53.
> - **Skirt stops at z 30** (old: down to the plate): the motor mounts (top 26.5) and
>   the carriages sit at the plate edge, and the tracks cover the sides below z 30.
> - Rear apron to the plate between the carriages (|y| ≤ 26) with 2 insert bosses;
>   rear screws come up from the belly (07 F9 amendment). Old: 2 plate rear posts.
> - Not yet: crown, mic-disc seat, vents, USB-C / switch cut-outs, cell-retention ribs
>   (S4), S7 / S5c with the real canopy.
> - Later in leg 2 (ticks 49–52): PC white; top 93 → **95** with a 4 mm rib grid and two
>   keels (heel test S8, 07); inner roots r 1; **side tongues** (x −43…−15, 3 mm) into
>   plate slots so the side walls brace the bulkhead's lugs (Q19).

> Amendment (loop, 2026-11-06, Ben): **rear corners closed.** The rear apron (|y| ≤ 26,
> z 0–30) → a rear wall to the plate across the full width and round both R20 plan corners,
> ending on a radial face whose inner surface is 1.0 aft of the carriages' aft-most position
> (x −72.2 = taut station − 10 − 5 travel): end at |y| ≈ 49.3 inner / 50.9 outer, r 1 on the
> outer end edge. The open corners showed the carriages and jack blocks from behind and let
> a finger reach the idler. Tensioning is done canopy-off, so nothing needed the opening.
> What's left is a ~5.6 mm sliver per corner between the wall's end and the belt's inner
> edge (56.5), behind the track; the carriages (|y| to 53) rule out closing it further.
> Canopy 120.9 → 124.5 g.

> Amendment (loop P6m, 2026-11-07, Ben): **mic disc → a separate mic pod on the canopy
> top** (`RB-PRT-005_mic_pod`, PC, generated `pod_lines()` in `tools/chassis.py`), so the
> mics sit at the robot's highest point instead of 27 mm under the head (audio §4.1 amendment).
> - Round cap Ø77.6 (disc Ø72.5 + 0.75 + 1.8 wall), centre (−5, 0): front 0.6 behind the
>   hood's back wall (x 34.4), clear of the hood screw collars. Roof 1.8 at **z 123.5** (hood
>   front top edge 123.54), r 3 outer edge. Rim cut to the canopy's crown + 0.5 gap.
> - Under the roof: 3 spokes (full diameters at 0/60/120°, 1.6 × 3.8), 3 Ø8 bosses with
>   M2.5 × 4 inserts (on the 0/120/240° spokes), 4 port tubes; all end at z 117.9.
>   Prints **roof down**, no support (every inner feature hangs from the roof).
> - Canopy, per disc hole: an Ø8 boss under the skin down to z 89.5 (3.5 over the Pi stack)
>   with an Ø5 counterbore to the head seat (z 91.9), an Ø7 post on the skin up to z 114.4,
>   Ø2.9 clearance through. FPC slot 15 × 4 at (−12, −23). Disc rotation unchanged (0° hole
>   on the y 0 rib): the only pattern (searched over x and rotation) that keeps every screw
>   head off the keels.
> - Removed: tick 98's keel windows + doublers, the 3 hanging bosses and 4 tubes under the
>   ribs. Canopy 124.5 → 124.7 g; pod 24.3 g; printed total 728.5 → 752.9 g; CoG z 23.3 → 26.3.
> - Why a separate part: built into the canopy (printed rear wall down), the pod's back
>   wall would be an unsupported ceiling and its inside would need support that can't come out.
> - Studies: see the loop journal (P6m) and 07 F10.

> Amendment (loop P6m2, 2026-11-08, Ben): **the pod becomes part of the canopy.** Ben: a
> streamlined, sturdy body and a well-protected mic over optimal mic placement; the top still
> beats the front (people speak down to it). Replaces P6m's RB-PRT-005, its posts and the
> M2.5 × 30 screws.
> - The canopy's top in side view is one tangent chain: the crown to a **45° ramp** (x −58 to
>   −52), a **hump roof crowned 1.5** at **z 110** (ends; x −42 to 20), and a **45° slope**
>   from the roof up to the hood's back top edge D, which replaces the hood's 25 mm back step
>   (Q29: the step's support goes). Rounds in the profile: r 12 (ramp foot), r 15 (ramp top),
>   r 10 (roof to slope); r 8 down both side edges of the whole chain. Full width (|y| 53).
> - Inside, open to the canopy. The disc (Ø72.5) hangs under the roof: per hole an
>   **M2.5 × 8 SHCS** up through a TPU washer, the disc and a TPU washer into an M2.5 × 4
>   insert in a roof boss (Ø8, bottoms at z 104.2); 4 port tubes with Ø1.2 ports through the
>   roof. It goes in from below with the canopy off; the FPC drops straight down (no slot).
> - Ribs: the lengthwise ribs (y 0, ±15) follow the top from the rear seam to x 32 on the
>   slope, 4 deep (under the roof their bottoms are 1.0 over the disc); cross ribs at x −62,
>   −40, −18, 3 (through the ±27 roof bosses, clear of the port tubes); keels end at x −27,
>   aft of the disc.
> - Prints rear wall down as before: both 45° faces and the roof need no support; the ports
>   print as horizontal Ø1.2 holes.

> Amendment (loop P6m3, 2026-11-08, Ben): **the bulkhead is the robot's rounded front cap**
> (Ben: the face plate looked angular and the canopy framed it; everything round, the body
> blending into the face). §5's wall becomes:
> - Full canopy width (106) up to the hood top (pre-tilt z 127.9), with 3 mm return flanges
>   9 mm deep (front face to the seam) along the top and both sides down to the skirt line;
>   **r 8** on its front edges and top corners (the canopy's side/hood rounds), r 5 inside.
>   Below the skirt line the plate is 104 wide (replaces the S2a cheeks); the r 8 corner runs
>   on down to the plate as an r 8 plan arc through the 3 mm plate, r 1 on its back edge.
> - The canopy's front is now a flush seam 0.1 behind the cap's flanges: no lips, no frame
>   (the front opening is the full width between the side walls); hood 17.5 deep (was 15).
> - Hood screws (F9 front pair) **flush**: counterbores square to the hood top over 2 mm
>   bosses under the hood ceiling, r 0.5 rims, no collars (Q27's collars retired). The lugs
>   move 4.9 aft and their tops 2 lower to meet them.
> - Bulkhead 48.6 → 55.5 g, canopy → 113.6 g. S5c 5.34 MPa / 0.13 mm, S5k 7.66 / 0.25 mm.

> Amendment (loop P6m4, 2026-11-08, Ben: "start P6m4"): face details and the seam.
> - Screen window corners **r 2.4** in the face plane (the AA corner, 1 mm in, stays clear up to r 3.4); the r 1 face-side round follows them.
> - Seam: **r 0.5 edge break on both seam edges** (cap back, cowl front): sides, r 8 corners and top, a ~1 mm V shadow line that hides print mismatch. Cap side flanges' bottom ends **r 1** (back, outer and inner edges).
> - Foot ledge: top front edge **r 2** (was r 1; it stands 2.5 proud of the wall there); vertical front corners stay r 1.
> - Fix found on the way: the cut that opens the cowl's front end had square top corners, 8.77 from the r 8 corner's axis, so they broke through the 1.8 skin (a 0.8 deep notch at both front top corners, 0.5 long). The cut's corners now follow the shell's inner r 6.2.
> - Masses: bulkhead 55.4 g, canopy 113.6 g. S5c 6.15 MPa / bezel 0.13 mm (gate 11.7 / 0.5).

> Amendment (P6m4b, 2026-11-09, Ben: boss showing through the cowl top): the front mic-disc boss (x 26.25, on the rise to the hood) is an 8 x 8 column whose top follows the roof 0.3 into the skin; a flat Ø8 top broke 0.37 mm out of the outer skin. The rear two stay Ø8.

## 7. Drivetrain parts

**Motor mounts L/R:** keep the current L-bracket (`TT_Motor_Mount_L` + its mirror
`MirrorTT_Motor_Mount_L`, an exact mirror). Round holes, fixed. Measured from the SLDPRT
2026-10-30, part frame: foot **3.0 mm** thick, 50.4 × 38.1 outline; **4 × Ø3.5** foot holes at
(−25.2, −38.9), (−11.2, −38.9), (3.5, −38.9), (−25.2, −23.0), which supersedes the 2-hole/14.75
pattern in 04 §1; upright 3 mm wall, 23 mm tall, motor holes Ø3.0 at 18 mm; side gusset 3 mm
with a wire window. **No root fillet between upright and foot yet**: add ≥ 2 mm after the
S2 study (07 §3) confirms the hot spot. **Print on its side** so the L's root isn't a layer line;
teardrop the horizontal motor-screw holes; ≥ 2 mm fillet at the inside corner. PET-CF.
> Amendment (Ben, 2026-11-08): **foot holes (−25.2, −38.9), (−11.2, −38.9), (3.5, −38.9) →
> y −41.5** (`MOUNT_FOOT_HOLES`, one source for the mount's holes and the plate's inserts).
> At −38.9 the two inside the upright's run (x −11.2, 3.5) sat under the 3.6 root chamfer
> (toe y −37.6): an M3 head (Ø5.5) or washer (Ø7) landed on the slope and couldn't seat.
> At −41.5 the head edge is at −38.75 and the washer's at −38.0, clear; 3.8 mm stays to the
> foot's outer edge. Chamfer and gussets unchanged. The plate's insert holes move with them
> (chassis |y| 21.5 → 18.9).

> Amendment (loop P2, 2026-10-30): **motor mount v2 is generated** (`RB-PRT-010` right,
> `RB-PRT-011` left = X-mirror placed at identity) in Ben's part frame, so the plate's 4-hole
> pattern and placements carry over. Upright 3 → 6 mm, three inboard gussets between the
> foot screws, a 3.6 mm root chamfer, end stop at the gearbox end (x −17.6, drawing), foot
> trimmed under the motor. **Motor centre z 11.5 → 13.5 and hole pitch 18 → 17.5**
> (drawing): clears the encoder/gearbox interferences with the plate and foot. Motor
> screws go into inserts in the upright (F3). ≈ 14 g each (Ben's 7.8 g). S2: hole
> deflection 0.437 → 0.039 mm; peaks 41 → 12–14 MPa, not converged (singular), see 07 §3.

> Amendment (loop P11, 2026-10-30): **kit track → printed TPU track system (`08`, Q8).**
> `tools/drivetrain.py` owns the drivetrain numbers; `chassis.py` imports them. Generated
> native parts: `RB-PRT-020_sprocket` (08 outrigger variant, D-bore on the TT shaft, 624
> pocket outboard for P2o) at x 52.7, and `RB-PRT-021_idler` (2 × 624) at x −57.3, both at
> z 13.5, outboard faces at |y| 92.5, inboard 56.5 (belt inner edge 1.5 off the plate edge).
> SolidWorks volumes equal drivetrain.py's meshes (27,842.0 / 26,935.1 mm³ vs 27,841.9 /
> 26,935.0). Belt as an envelope (stadium annulus, lugs omitted) for interference. The TT
> shaft envelope now has its double-D flats (3.7). Interferences: 0. Track/drive-gear
> numbers below (44.2, 31.6, Ø49.6) are the kit's and obsolete for new work.

> Amendment (loop P12, 2026-10-30): **rear-corner relief removed** (plate back to 110 wide
> its full length, 81,653 mm³ ≈ 105 g PET-CF solid, +4.6 g). It existed only because the
> kit track hung inboard of its gear; the 08 belt and idler sit outboard of |y| 56.5. The
> follower carriage may now reach the plate edge (|y| 55), shortening the idler-axle
> cantilever by ~11 mm for P5. FEA loads now act at the belt centre plane (|y| 74.5) with
> the sprocket's pitch radius 28.65 (`TRACK_T` still 20 N): S2 pull + torque 12.6 MPa
> (singular, D7) / 0.040 mm; S1a 17.6 MPa (singular) / axle UX 0.241 mm; S1b 2.55 MPa.

> Amendment (loop P2o, 2026-10-31, Q17 (b) Ben): **outboard track frame, one per side**
> (`RB-PRT-040` L / `041` R, PET-CF), so belt tension closes through a stiff bar between
> the two axles instead of bending the plate (S1m: axle motion 1.03 mm vs 0.2). Old → new:
> each axle carried only from inboard (TT shaft in the gearbox; idler shoulder axle
> cantilevered from the carriage journal) → **both axles also carried outboard**.
> - **Outer bar** at |y| 93.5…97 (1.0 off the wheels' outboard faces at 92.5), axle
>   height z 13.5, ~16 tall, from the idler axle (x −57.3 ± 5 travel) to the sprocket axle
>   (x 52.7). At the sprocket end a Ø4 shoulder bolt goes through the bar into the
>   sprocket's outboard 624 (08 `sprocket_outrigger`). At the idler end the bar has an x-slot
>   over the idler's Ø4 shoulder axle; its outboard thread takes an M3 nyloc that
>   clamps the bar after tensioning.
> - **Two legs** inward through the belt loop's open window (x −30…25 between the
>   wheels, z −10…37 between the runs' lug tips, the lug row only at |y| 70…79 above/below
>   that band) to the plate. Rear leg at x ≈ −22…−14 (belly between the carriage slots,
>   which end at x −45, and the motor's can end at x −10); front leg at x ≈ 14…22 onto the
>   belly outboard of the |y| 47 load rib. Each leg foot bolts up into plate inserts
>   (under-boss, as F2). The legs are where P13's road wheels hang (x −19.7 / +20.6, z −8.4).
> - **Tensioning order:** set the belt with the carriage jack screw (05, unchanged), then
>   tighten the idler-end nyloc. The bar then carries the tension axially (stiff), and the
>   plate/mount path only sees what the inboard halves share.
> - **Width:** overall 185 → **~194** (2 × 4.5 for the bars). 08 §6's 185 is superseded here.
> - **Kid safety:** the bars cover the wheels' outboard faces (no reachable spokes or
>   pockets). The bar sits 1.0 mm off the rotating wheel face, below the 5 mm finger rule. All
>   edges r 1; the bar's outer face takes the E1 r 3 on its ends.
> - **FEA:** new study **S9** (frame + plate + mounts bonded; S1m's loads), judged on
>   S1m's 0.2 mm at the axles. Est. ~14 g per side.
> - **Rev (tick 54): bar only, no legs.** Pinned on two parallel axles the bar is already
>   a tie; the legs had no room (a belly screw at the rear leg crosses the |y| 47 load rib or
>   the canopy tongue slots; the front leg sits under the motor). Sprocket end: a **steel
>   Ø4 h8 dowel** pressed through the bar + a Ø10 × 3 outboard boss, 5 mm into the 624's
>   inner race (a shoulder bolt can't work there: its nut would be inside the turning
>   sprocket). Bar 3.6 × 14 stadium at |y| 93.5–97.1, ~8 g per side. Width: boss + idler
>   nyloc reach |y| ~100–101 → **overall ~200** (not ~194).
>   Amendment (Ben, 2026-11-08): **outboard boss removed; the dowel hole is blind from the
>   inboard face (0.8 mm skin outboard).** The frames print outer face down, and the Ø10 × 3
>   boss was the only thing on the bed: the whole 5,746 mm² outer face floated 3 mm and was
>   supported. Now the outer face is flat on the bed (no support). The dowel presses in from
>   inboard, can't walk out outboard, and grips 2.8 mm (was 6.6). Outboard width now set by
>   the idler nyloc only.
>   Rev (tick 66, Q22 F2): each bar is now a **side plate** (2.4 PET-CF, rounded rectangle
>   x −69.3…59.7, z −10…38, r 8) over the belt loop's window, so the lug ↔ pocket nips are
>   behind it (kid safety, `docs/cad/loop/S2_pinch.md`). 19.1 g per side.
>   Amendment (Ben, 2026-11-10): **road-axle retention.** Until now nothing held the road
>   axles or the inner discs along y: the inner 684 sat flush with the axle's inboard end and a
>   pivot turn's lug thrust would push it off, the axle could walk out of either bore, and the
>   outer disc could slide 1 mm onto the Ø10 boss and drag. Now:
>   - the side-plate road bores are **blind press bores** (Ø3.95, as the dowel, 0.8 mm skin
>     outboard): the axle presses in from inboard through the blade's Ø4.1 slip bore, can't
>     walk outboard or turn, and the outer face stays plain;
>   - **one DIN 6799 E-clip (size 3.2) per axle** in a groove at the inboard end, on the inner
>     684's inner race (y 55.86…56.46, 0.04 float); the axle runs on to y 54.3, under the
>     plate edge (its top 0.4 below the belly). It fits the 1.5 mm SIDE_GAP: the clip is 0.86
>     off the plate edge;
>   - a **Ø6 × 0.9 land** on the side plate's inner face round each road bore takes the outer
>     684's inner race only (0.1 float), so the outer disc can't reach the boss.
>   Axle: **Ø4 × 42 ground shaft, one E-ring groove ~1.9 from the inboard end** (07 F20).
>   Assembly: hold the outer disc + its spacer in the gap, push the axle from inboard through
>   the blade into the press bore, then the inner spacer + disc, then the clip.
>   FEA (2026-11-10, 1 mm mesh, PET-CF, `fea.py S9 S9i`): **S9** (centred, as tick 91): blade
>   9.38 MPa, bores 0.35 mm ✓ (unchanged by the blind bores). **S9i** (the whole ×3 bump on
>   the inner disc of both axles): blade **16.7 MPa (SF ~2.1)**, bores **0.63 mm** (0.42 of it
>   the plate leaning outboard), over S9's SF 3 / 0.5 mm gates. Accepted (Ben to confirm): it
>   stacks two worst cases (one-edge loading and the ×3 bump); at ×1 it is 5.6 MPa / 0.21 mm.
>   Both runs' peak (13.0 / 23.1 MPa) sits on the idler slot's fixture edge, which S9 reports
>   but doesn't judge. If wanted: a thicker shelf (RA_ARM_T) is the stiffening lever.

**Followers:** per `05_follower_spec.md` (carriage in plate slots, clamp from
below, 624 bearing on a Ø4 shoulder bolt).

**Track and drive gear (measured by Ben, 2026-10-30):**

| Item | Value | Consequence |
|---|---|---|
| Drive gear root (minor) Ø | 48.2 mm | — |
| Drive gear tip (major) Ø | 54.34 mm | — |
| Drive gear total width | 31.6 mm | Follower centre plane = drive gear centre plane (same Y) |
| Track outside width | 44.2 mm | Follower flange inner gap **45.2 mm** (width + 1.0); each track takes ≈ 45 mm of overall width |

- **Follower running OD: Ø49.6** (Ben, 2026-10-30). This is the diameter the track's inner face runs on.
- The existing `follower_wheel.SLDPRT` is Ø50 × 45 wide with Ø7.3 / Ø11 bores and no flanges, and 33 cm³
  (~43 g in PET-CF). It doesn't match the 624 pocket (Ø13.1) in 05. Rework it to: running OD **Ø49.6** (was Ø50), 45.2 mm flange gap, 2 mm flanges standing 2–3 mm proud, 624 pocket, shell + ribs instead
  of near-solid.
- Overall robot width = plate 110 + 2 × (track 44.2 + running clearance) ≈ **205 mm** if the tracks run
  outboard of the plate; confirm from the drive gear's position on the shaft in the rebuilt assembly.

## 8. Fasteners

**Superseded by `07_materials_fasteners_fea.md` §4** (sizes, lengths, torques, coupon).
The table below is the joint list only.

| Joint | Method |
|---|---|
| Plate ↔ bulkhead | 3 × M3 up through the plate into heat-sets in the bulkhead foot + 2 locating tabs |
| Plate ↔ motor mounts | 4 × M3 × 8 each, down from the top into heat-sets in plate under-bosses (07 F2) |
| Plate ↔ Pi deck | 4 × M3 down into heat-sets at the plate post tops (07 F5); Pi stack to deck by M2.5 into its brass standoffs (07 F6) |
| Reflex board ↔ plate | 4 × M3 on 45.5 × 39 pattern (was 51 × 45), printed standoffs with heat-sets |
| Canopy ↔ body | 4 × M3 SHCS into heat-sets (bulkhead top ×2, plate rear ×2) |
| Follower clamp | per 05 spec (M3 + nyloc / thumb-nut from below) |

Heat-set pockets per the insert datasheet (M3 ≈ Ø4.0, M2.5 ≈ Ø3.5); boss OD ≥ 2× hole.

## 9. Envelopes needed before layout numbers lock

| Envelope | Source |
|---|---|
| Face board + TFT | **Freenove FNK0104** (confirmed from `esp32-face/main/pin_map.h`) = QDtech **ES3C28P** geometry: Ben measured the PCB at 50 × 86 and holes Ø3.28, matching the drawing (`lcdwiki.com/res/ES3C28P/ES3C28P_Size.pdf`, V1.0 2025-06-11). Use the drawing: PCB 50 × 86 × 1.6, R3.5 corners; **4 × Ø3.2 at 42.0 × 78.0 c-c** (4.0 from the side edges, 4.0 from the top/bottom edges), Ø5.6 pads; 10.6 overall (LCD/TP stack 5.9 front, SMD 4.7 max back); LCD active area 43.2 × 57.6, its top edge 11.12 from the PCB top (the MIC end); backlight/touch outline 50 × 69.2 starts 8.22 down |
| Pi 5 + NVMe adapter + UPS HAT (B) | **Measured:** 53 mm stack (59 with the 6 mm standoffs), Pi USB tops 30 mm above the adapter's bottom. Still need: footprint if the HAT/adapter overhangs 85 × 56; Pi PCB Z from the vendor model |
| XVF3800 Flex mic disc + core board | Audio bench step 7 |
| CE40P-8 + back box | Datasheet + audio §4.3 |
| Reflex board | Have STEP (52.5 × 46, regenerated 2026-11-09) |
| Camera, HC-SR04 housing | Have parts |

**Envelopes built 2026-10-30** (`tools/chassis.py rebuild`, all volume-checked):

| File (`CAD/library/`) | Frame | Status |
|---|---|---|
| `Pi5_stack_envelope.SLDPRT` | Pi hole-pattern centre, Z 0 at the standoff feet, +X to the USB/Ethernet end; 4 × Ø5 × 6 standoffs + 87 × 56 × 53 block | measured; HAT/adapter overhang 🟡 |
| `FNK0104_face_envelope.SLDPRT` | PCB centre on the back-component plane, +Y to the MIC end, +Z to the viewer; back 4.7 + PCB 1.6 + LCD/touch 4.3; Ø5.6 pad clearances + Ø3.2 holes at 42 × 78 | from the ES3C28P drawing |
| `reflex_board_envelope.SLDPRT` | hole-pattern centre, PCB bottom face Z 0; 52.5 × 46, holes 45.5 × 39 (was 65 × 60 / 51 × 45; rebuild pending) | outline + holes from KiCad; heights 🟡 (12 top, 2 bottom) |
| `TT_Motor_envelope_v2.SLDPRT` | see §2 | widths 🟡 |
| XVF3800 Flex disc + core board, CE40P-8 + back box | — | **not built**: no measured dimensions yet (audio bench step 7) |

Provisional placements in `RB-ASM-101_chassis` (set properly with the plate layout, §4):
Pi stack Rz180 at (−10, 0, 27), ports aft; reflex at (−44.5, −3.5, 5), aft of the motor
cans with 0.7 mm to the encoders; face board at (72, 0, 68), screen forward, tilted 15° back.
No new interferences.

## 10. Build order

1. Assembly rebuild in chassis frame (§2).
2. Envelopes (§9).
3. Plate: outline, motor holes, follower slots, bulkhead foot, Pi-deck posts, reflex standoffs, ribs.
4. Pi deck, then bulkhead, then canopy.
5. Interference check + Mass Properties (CoG between the axles).
6. Renders to Ben, then print in PETG to check fit, then PET-CF/ASA.

> Amendment (Ben, 2026-11-10, IMU): the **BMI270 IMU breakout** (SparkFun Qwiic, cabled to the
> reflex board's J5) hangs **under the Pi deck, centred at (−54, 0)**, parts down, its back at
> z 21 on 3 mm spacers (07 F19), in the bay aft of the reflex board (x −66.7 … −41.3, |y| ≤ 12.7;
> the deck over the reflex board has only 5.4 of headroom). The parts layer (z ≥ 16.4) stays
> 4.9 above the reflex USB-C plug (z ≤ 11.5). Consequences for the deck: the USB cable's
> pass-through moves from the slot at x −62 … −54 (now under the IMU) to an **open notch in the
> rear edge, x −75 … −68, |y| ≤ 4** (the cable drops in from behind; the plugs never pass
> through), and the vent slots start at x −38 (was −45) to clear the IMU's front insert bosses.
> Board dimensions are TBC (25.4 square, Ø3.3 on a 20.32 square: measure before printing).

> Amendment (loop P4b, 2026-10-31): rear deck posts (−48, ±20) → (−70, ±20), deck rear edge x −66 → −75. At −48 the deck's M3 screws sat under the Pi board and could not be reached with the stack fitted (R1-F1, `docs/cad/loop/R1_assembly.md`).
