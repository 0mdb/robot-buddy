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

Rebuild step (first CAD task):

1. Re-base `bottom_plate.SLDPRT` so its origin is the top-face centre and +Z is up
   (sketch the outline on the **Front** plane, whose normal is +Z, and extrude −Z 4 mm).
2. Save the follower blocks out of the assembly as real parts
   (`follower_carriage_L/R.SLDPRT`); delete `Part8^…`.
3. Place every component with an explicit `Transform2` in chassis coordinates
   (skill rule 7), and fix the plate.

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
The upright bracket at the rear left: purpose still to confirm. Keep, move or drop.

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

**Followers:** per `05_follower_spec.md` (carriage in plate slots, clamp from
below, 624 bearing on a Ø4 shoulder bolt).

**Track and drive gear (measured by Ben, 2026-10-30):**

| Item | Value | Consequence |
|---|---|---|
| Drive gear root (minor) Ø | 48.2 mm | — |
| Drive gear tip (major) Ø | 54.34 mm | — |
| Drive gear total width | 31.6 mm | Follower centre plane = drive gear centre plane (same Y) |
| Track outside width | 44.2 mm | Follower flange inner gap **45.2 mm** (width + 1.0); each track takes ≈ 45 mm of overall width |

- **Follower running OD is still open:** it must equal the diameter the track's inner face rests on
  at the drive gear. That is **Ø54.34** if the track has inner lugs that sit between the teeth (inner face
  rides on the tips), or **Ø48.2** if the teeth poke into holes in the track (inner face rides on the root).
- The existing `follower_wheel.SLDPRT` is Ø50 × 45 wide with Ø7.3 / Ø11 bores and no flanges, and 33 cm³
  (~43 g in PET-CF). It doesn't match the 624 pocket (Ø13.1) in 05. Rework it to: running OD per the
  line above, 45.2 mm flange gap, 2 mm flanges standing 2–3 mm proud, 624 pocket, shell + ribs instead
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

## 10. Build order

1. Assembly rebuild in chassis frame (§2).
2. Envelopes (§9).
3. Plate: outline, motor holes, follower slots, bulkhead foot, Pi-deck posts, reflex standoffs, ribs.
4. Pi deck, then bulkhead, then canopy.
5. Interference check + Mass Properties (CoG between the axles).
6. Renders to Ben, then print in PETG to check fit, then PET-CF/ASA.
