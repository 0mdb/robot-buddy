# Robot Buddy — Printed TPU Track System (R&D) — Rev 0

**Status: R&D, not integrated.** Branch `drivetrain-rnd`. Nothing here changes the plate,
mounts, followers or `tools/chassis.py`. §6 lists what the main design would change.
Generator: `tools/drivetrain.py` (numpy only, no SOLIDWORKS):

```
python3 tools/drivetrain.py report     # system numbers + N/W sweep
python3 tools/drivetrain.py build      # STLs + preview -> CAD/exports/rnd/drivetrain/
```

Scope (Ben, 2026-10-30): design the **belt, drive sprocket and idler as one system**, in
TPU + PET-CF. Ignore the kit track: no part is shaped to fit it. Weigh CG, turning and
proven designs. TPU **85A** (print-bom) and **95A** (fpv250 stock) are both on hand.

## 1. Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | Drive from the Yahboom TT D-shaft; idler on the 05 follower carriage (624 on a Ø4 shoulder axle, jack-screw tension) | 05, 06 §7 |
| R2 | Halve the drive gear's overhang off the TT gearbox: the kit puts the track centre ~39 mm out, failing S2 | Q4, JOURNAL |
| R3 | Quiet on hard floors (the mic array listens while driving) and grippy, without stalling a TT on a pivot turn | Ben, 2026-10-30 |
| R4 | Kid-safe: no hard rattling links, no pinch gaps 5–12 mm, no flanges to catch fingers | QUESTIONS Q1, BACKLOG S |
| R5 | Every part prints on the P2S without support; the belt in one piece | print-dfm |
| R6 | Clear rug edges and door thresholds without high-centring | CG / clearance §4 |

## 2. Proven designs considered

| Pattern | Where it's proven | Verdict |
|---|---|---|
| **Centre-lug positive drive**: continuous elastomer belt, one row of inward lugs; sprocket pockets drive the lugs, which also guide the belt between the wheel's two running discs | Rubber tracks on compact track loaders and mini excavators | **Chosen.** One lug row drives *and* guides, so no flanges (R4). Clearance all round tolerates belt stretch better than full-width teeth. Tension can be low because the lugs can't slip like a friction drive. |
| Full-width timing-belt teeth (HTD/GT-style) on a toothed pulley | Timing belts; hobby rubber track sets | Second choice. Simple, but a stretched TPU tooth climbs a fine-pitch pulley, and it needs flanges to stay on. |
| Hard links + pins, optionally with TPU pads | Kit track, Tamiya-style sets | Rejected: noisy (R3), pinch points, many parts. |
| Friction belt on smooth drums | Conveyors | Rejected: slips on a pivot turn unless tension is high, which overloads the TT shaft and the plate (S1). |

Printing the belt as an **upright ring** is the usual hobby method: the belt's tension
runs along the perimeters, its strongest direction, and the whole loop is one part.

## 3. System (from `drivetrain.py report`)

| Item | Value | Why |
|---|---|---|
| Lug pitch | **10.0 mm** on the belt's neutral axis | Lugs about 5 mm long with 5 mm gaps; the pocket floor stays ≥ 2.4 mm |
| Wheel | **18 pockets**, running Ø54.8, belt outside Ø62.8 | 18 → 9.9 mm under the plate; 16 → 6.7, 14 → 3.5 (§4) |
| Belt | **40 lugs = 400.0 mm**, 36 wide, 2.5 base, lug 9 W × 4 H × 5/3 L, 1.5 mm tread bar under each lug | Rounded **down** to whole lugs (see tension) |
| Tension | Belt just taut at idler x −57.3. 4.6 mm slack to fit it with the idler forward (−55). Rear travel to −65 absorbs **3.9 %** stretch + creep | 06 §4 travel unchanged |
| Design tension | **10 N** per track (fea.py uses 20 N; positive drive needs less) | S1 / S2 loads halve |
| Belt strain at 10 N | 85A: 0.44–1.1 %. 95A: 0.19–0.44 % | Modulus assumed; the strip test in §7 measures it |
| Track | gauge 149, contact span 113, **L/B 0.76**, overall width **185** (kit: ~205) | Belt inner edge 1.5 mm off the plate edge |
| Masses | Belt 58 g (TPU, solid). Sprocket 36 g, idler 35 g (PET-CF, solid). Drivetrain ≈ 258 g | Sliced mass is lower; trim in §8 |

## 4. CG, stability, turning

Mass model: 07 §3.3 + metrics.csv + 06 §3 stations, about 1.17 kg in total.

- **CG**: x **+11.5** (15 mm ahead of the contact patch's middle), 39.6 above the plate
  top, **57.5 above ground**. The front wheels carry **63 %**. That's good for a front
  drive (traction where the torque is), and the face and bulkhead put it there.
- **Pitch-over limits**: braking 0.72 g, accelerating 1.24 g. A TT robot can't brake at
  0.7 g, so hard stops won't tip it. Side tip 52°.
- **Ground clearance** is set by the wheel size, because the TT shaft is fixed at 13.5
  above the plate. With 18 pockets the plate's lowest point (bosses, z −8) clears the
  floor by 9.9 mm: enough for rug edges, marginal for 15–20 mm thresholds. More
  clearance needs bigger wheels (more torque per pivot) or a higher TT mount (higher CG).
- **Turning (skid steer)**: L/B 0.76 is short and wide. Steering resistance per motor
  τ = μ·W·L / (k·B) · r_pitch (k = 4 for even ground pressure, k = 2 when the weight sits
  under the wheels):

  | μ (floor) | even pressure | wheels only |
  |---|---|---|
  | 0.5 (hard plastic links, smooth floor) | 0.031 N·m | 0.062 N·m |
  | 0.9 (TPU on wood/tile) | 0.056 N·m | **0.112 N·m (45 % of stall)** |
  | 1.2 (TPU on rubber mat or carpet) | 0.074 N·m | 0.149 N·m (60 % of stall) |

  With only two wheels per side, the weight really is under the wheels, so read the
  "wheels only" column. A pivot on TPU works but uses half the TT's stall torque. Two
  cheap mitigations, both proven on skid-steer robots:
  1. **A middle road wheel per side, set 1–1.5 mm low.** The robot rocks onto the middle
     wheels, and on a pivot it turns about them, so turning resistance roughly halves.
     The bottom run between two wheels also no longer bows up. This can be added later
     as a separate part, no plate change (§8).
  2. **Tread bars as narrow strips, not a full-width pad.** They give grip forwards, and
     sideways the belt can slide at the bar ends. The current bars are full width; a
     chevron or split bar is a later variant.
- **L/B 0.76** makes straight-line driving more sensitive to yaw than L/B ≥ 1. The
  reflex MCU's IMU heading hold covers this; it's the price of a short plate.
- **Pivot sweep circle**: Ø277 (plate corners + belt ends about the CG). Narrower
  tracks change it little (Ø270 at 30 mm). The plate length dominates.

## 5. Parts

All of these come from `drivetrain.py`. All are closed meshes and pass `meshcheck.py`
(walls ≥ 2.4 mm; the "overhang" area it reports is the 45° stair ramps and the short
pocket-roof bridges).

**Wheel rim (shared by sprocket and idler).** Two running discs at Ø54.8 carry the belt.
A centre band (10.2 wide) has 18 pockets: each lug + 0.6 mm all round. The tooth tops
sit 0.6 below the running surface, so the discs carry the belt, not the teeth. The pocket
walls guide the belt sideways, so no flanges (R4). The rim wall is 2.4 under the discs and
2.4 under the pocket floors; the step between them is a 45° stair (R5). A toothed idler
(rather than a plain one) also keeps the belt in phase and guided at the rear.

**Sprocket.** Printed outboard face down. The inboard face sits 1.5 mm off the TT gearbox
face. The hub is a Ø15 tube with the TT double-D (Ø5.4 / 3.7 flats, clearance from the
coupon) along its last 8 mm (TBD: shaft length), retained by the TT's M2 end screw
through the axis. The **track centre is 19.5 mm off the gearbox face (kit: ~39)**, halving
S2's bending moment and the side load on the TT gearbox (R2). Variant
`sprocket_outrigger` has a 624 pocket in the outboard face for Q4(a) / P2o: the outboard
bracket carries a Ø4 shoulder bolt into it, the same hardware as the followers. This
removes the "gear-hub data" block on P2o.

**Idler.** Same rim. Hub = **two 624s**, one at the outboard face and one just past the
belt's centre plane, so the belt load sits between the bearings and the wheel can't cock
(05 tilt note). There are **crush ribs** in the bearing pockets (coupon picks
0.10/0.15/0.20). This deviates from 05's "slip + printed cap", which needs Ben's OK.
The inboard side is open, so the carriage's journal boss can reach into the wheel up to
the tube, shortening the unsupported axle a lot (05 "support the overhang").
`idler_1brg` is the 05-style single-bearing variant.

**Belt.** One piece, printed as an upright ring Ø133 × 36. The lugs' lower ends are
chamfered 45° above a 2 mm ledge, so it prints without support.
- **TPU 85A vs 95A**: 85A grips more and is quieter, but stretches ~2.5× more (§3) and
  its lugs are softer: start here. 95A is the fallback if 85A ratchets out of the pockets
  or creeps past the 3.9 % travel. Same STL for both.
- Print: external spool, dried first (print-bom), textured PEI, walls-only (the 2.5 base
  is all perimeters), slow volumetric flow. Use the 0.4 stainless for crisp lugs or the
  0.6 for speed.

**Coupons.** `coupon_ttbore_05…20` are D-bore rings at 0.05–0.20 per side; the number of
notches = the rung. `coupon_624_10…20` are the crush-rib bearing seats. `coupon_band_slice`
is a 6 mm slice of the sprocket band on a TT bore: push it onto a motor and mesh it with a
belt test piece.

## 6. What the main design would change (not applied)

| Item | Now (main) | With this system |
|---|---|---|
| Track position | Kit track hangs ~6.3 inboard of the gear, track centre ~39 out | Belt inner edge 1.5 off the plate edge, centre \|y\| 74.5 |
| Plate rear-corner relief (Q10) | Narrowed to 92 behind x −27 | Not needed for the belt; check against the 36-wide idler at \|y\| 56.5…92.5 |
| Follower | 05 wheel: Ø49.6, flanges, gap 45.2 | Toothed idler Ø54.8 × 36, no flanges, 2 × 624; slot travel unchanged; idler at fit −57.3 |
| Axle heights | Drive 13.5; follower axle height not yet fixed | Both 13.5 (level belt); carriage boss height follows |
| P2 motor mount / S2 | Gear moment arm ~39 | ~19.5; re-run S2 at 10 N tension |
| fea.py `TRACK_T` | 20 N | 10 N if the set-up spring-scale reading confirms |
| Overall width | ~205 | 185 |
| Ground clearance | Not computed for the kit | 9.9 mm under the plate (wheel Ø62.8 outside the belt) |

## 7. Test plan (cheap first, eyes before electrons)

1. **TT measurements** (replace TBDs): shaft length past the gearbox face, the end-screw
   size, and confirm the double-D 5.4 / 3.7.
2. **Coupons** in PETG: TT bore ladder, 624 ladder → set `BORE_CLR` and the crush
   interference.
3. **TPU strip test**, 85A and 95A: a 36 × 2.5 × 150 strip printed like the belt, hang
   1 kg (≈ 10 N): measure stretch now and after 24 h (creep) → replaces `E_TPU`.
4. **Belt test piece** (a 6-lug arc) + `coupon_band_slice` on a motor: check the mesh by
   hand, then drive it against a stalled TT: does a lug ratchet out?
5. **Full set, one side**, on a PETG plate: tilt test for μ on tile, wood and rug; pivot
   current vs stall; mic noise floor while driving vs the kit track.
6. Only then propose the §6 changes to the loop as backlog items.

## 8. Open / next

- Weight: wheels are ~35 g solid each; lightening pockets in the web need SOLIDWORKS
  (non-axisymmetric), or 3–4 walls + gyroid in the slicer.
- Middle road wheel (§4) as a bolt-on to the plate edge; decide after test 5.
- Tread pattern variants (split bars or chevrons) for side slip vs grip.
- Pinch audit (BACKLOG S2) for the sprocket–belt nip at the front: a skirt over the
  top run.
- If 85A creeps too much: 95A belt, or a 95A carcass with 85A tread bars (two-material
  print; one external spool, so a filament swap at a layer).
