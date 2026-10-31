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

- **Level 0, plate top:** reflex board (65 × 60, M3 holes at a 51 × 45 pattern),
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
| Pi deck posts (F5) | 4 × Ø9.2 × 24 at (30, ±8) and (−48, ±20); Ø4.0 × 7.2 insert pockets at the top | clear the reflex board, mount feet (0.8 mm) and carriages. No fins yet (24 tall > 2 × OD, 07 §1): add after FEA |
| Reflex standoffs (F7) | 4 × Ø9.2 × 5, insert pockets 7.2 deep (into the plate) | at the board's moved station, below |
| Follower slots (05) | per side: guide slots 4.7 wide at \|y\| 31 and 41, x −75…−45; clamp slot Ø3.4 at \|y\| 36, x −65…−55; jack end-stop block 10 × 11 × 10 at x −38…−28 with an Ø4.0 insert bore along X at z 5 (F4b) | axle mid-travel at x −60, ±5 mm; rail length 20 🟡 until the carriage is designed |
| Rear-corner relief | plate half-width 46 behind x −27 | **new:** the 44.2 track hangs ~6.3 inboard of the 31.6 gear, so the follower wheel (flanges at \|y\| ≈ 47) would cut the plate edge |
| Bulkhead foot (F1) | 3 × Ø3.4 at x 81.5, y 0 / ±22, counterbored Ø6.5 × 2 from below; 2 tab slots 4.6 × 10.4 at y ±11 | only x ≥ 78.5 is clear of the mount feet: a 6.5 mm strip. 🟡 review with the bulkhead design |
| Wire slot | 6 wide, x 35…55 on the centreline | between the mount feet |

**Layout changes found while building:** the reflex board moved forward to the space between
the motors (pattern centre (−10.5, −3.5), board x −40…25, 0.7 mm to the encoders), because
the follower carriages (\|y\| 28…44 aft of x −40) left no room aft. The XVF3800 core
board and any off-board TB6612 now go aft, between the carriages (x −85…−40, \|y\| < 28) 🟡.

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

## 6. Canopy (piece 3)

- ASA white: heat-stable over the Pi 5 (PLA softens around 55–60 °C) and tougher when dropped. PLA only for bolt-on accents.
- Mic disc (Ø73, 3 × M3) on the top surface on TPU grommets; Ø1.2 mm ports,
  gasketed, ≤ 2 mm wall (audio §4.2).
- **Tool-only opening:** 4 × M3 into heat-set bosses (2 on the bulkhead top,
  2 at the plate rear). Lithium cells are inside, so the cover must not open by hand.
- Access cut-outs (no need to open the canopy): UPS HAT USB-C charge port, power
  switch, Pi USB/HDMI as needed 🟡. SD card: open the canopy.
- Uniform 1.8 mm wall; 1 mm fillets; vent slots over the Pi cooler, ≤ 2 mm wide.

## 7. Drivetrain parts

**Motor mounts L/R:** keep the current L-bracket (`TT_Motor_Mount_L` + its mirror
`MirrorTT_Motor_Mount_L`, an exact mirror). Round holes, fixed. Measured from the SLDPRT
2026-10-30, part frame: foot **3.0 mm** thick, 50.4 × 38.1 outline; **4 × Ø3.5** foot holes at
(−25.2, −38.9), (−11.2, −38.9), (3.5, −38.9), (−25.2, −23.0), which supersedes the 2-hole/14.75
pattern in 04 §1; upright 3 mm wall, 23 mm tall, motor holes Ø3.0 at 18 mm; side gusset 3 mm
with a wire window. **No root fillet between upright and foot yet**: add ≥ 2 mm after the
S2 study (07 §3) confirms the hot spot. **Print on its side** so the L's root isn't a layer line;
teardrop the horizontal motor-screw holes; ≥ 2 mm fillet at the inside corner. PET-CF.

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
| Reflex board ↔ plate | 4 × M3 on 51 × 45 pattern, printed standoffs with heat-sets |
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
| Reflex board | Have STEP (65 × 60) |
| Camera, HC-SR04 housing | Have parts |

**Envelopes built 2026-10-30** (`tools/chassis.py rebuild`, all volume-checked):

| File (`CAD/library/`) | Frame | Status |
|---|---|---|
| `Pi5_stack_envelope.SLDPRT` | Pi hole-pattern centre, Z 0 at the standoff feet, +X to the USB/Ethernet end; 4 × Ø5 × 6 standoffs + 87 × 56 × 53 block | measured; HAT/adapter overhang 🟡 |
| `FNK0104_face_envelope.SLDPRT` | PCB centre on the back-component plane, +Y to the MIC end, +Z to the viewer; back 4.7 + PCB 1.6 + LCD/touch 4.3; Ø5.6 pad clearances + Ø3.2 holes at 42 × 78 | from the ES3C28P drawing |
| `reflex_board_envelope.SLDPRT` | hole-pattern centre, PCB bottom face Z 0; 65 × 60, holes 51 × 45 | outline + holes from KiCad; heights 🟡 (12 top, 2 bottom) |
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
