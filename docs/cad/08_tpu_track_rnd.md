# Robot Buddy — Printed TPU Track System (R&D) — Rev 1

**Status: plan of record (Q8), being integrated by the CAD loop (P11–P13).** Branch
`drivetrain-rnd` holds the R&D; §6 lists what the main design changes.
Generator: `tools/drivetrain.py` (numpy only, no SOLIDWORKS):

```
python3 tools/drivetrain.py report     # system numbers + N/W sweep
python3 tools/drivetrain.py build      # STLs + preview -> CAD/exports/rnd/drivetrain/
```

Scope (Ben, 2026-10-30): design the **belt, drive sprocket and idler as one system**, in
TPU + PET-CF. Ignore the kit track: no part is shaped to fit it. Weigh CG, turning and
proven designs. TPU **85A** (print-bom) and **95A** (fpv250 stock) are both on hand.
Rev 1 (same day): two road wheels per side, the sprocket raised 3 mm, and three tread
variants (Ben: "lugs, grooves, smooth?").

## 1. Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | Drive from the Yahboom TT D-shaft; idler on the 05 follower carriage (624 on a Ø4 shoulder axle, jack-screw tension) | 05, 06 §7 |
| R2 | Halve the drive gear's overhang off the TT gearbox: the kit puts the track centre ~39 mm out, failing S2 | Q4, JOURNAL |
| R3 | Quiet on hard floors (the mic array listens while driving) and grippy, without stalling a TT on a pivot turn | Ben, 2026-10-30 |
| R4 | Kid-safe: no hard rattling links, no pinch gaps 5–12 mm, no flanges to catch fingers | QUESTIONS Q1, BACKLOG S |
| R5 | Every part prints on the P2S without support; the belt in one piece | print-dfm |
| R6 | Clear rug edges and door thresholds without high-centring | CG / clearance §4 |
| R7 | Don't nod forward on normal stops (the face is on the front) | §4 |

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
| Sprocket + idler | **18 pockets**, running Ø54.8 | Wheel size sets ride height (§4); 16 → −3.2 mm clearance, 20 → +3.2 mm |
| Road wheels | **Ø18**, two per side at x −19.7 and +20.6, axle z −8.4; each is two discs (one either side of the lug row) with a 684 on a Ø4 axle | §4b |
| Wheel stations | Sprocket x 52.7, z 13.5 (TT shaft). Idler z **10.5** (3 mm below the shaft), taut at x −57.2 | §4b |
| Belt | **40 lugs = 400 mm**, 36 wide, 2.5 base, lug 9 W × 4 H × 5/3 L; tread §5 | Rounded **down** to whole lugs; the length is the real 4-wheel path |
| Tension | Taut at idler x −57.2. 4.4 mm slack to fit it with the idler forward (−55). Rear travel to −65 absorbs **3.9 %** stretch + creep | 06 §4 travel unchanged |
| Sprocket wrap | 176° = **8.8 lugs engaged** | Skipping needs the slack side to go slack: pretension > 4.4 N at double stall |
| Design tension | **10 N** per track (fea.py keeps 20 N until measured) | §4c |
| Belt strain at 10 N | 85A: 0.44–1.1 % (1.8–4.4 mm). 95A: 0.19–0.44 % (0.7–1.8 mm) | Modulus assumed; the strip test (§7) measures it |
| Track | gauge 149, overall width **185** (kit ~205) | Belt inner edge 1.5 off the plate edge |
| Masses | Belt 50–62 g by tread (TPU, solid). Sprocket 36 g, idler 35 g, road disc 3.4 g (PET-CF, solid). Robot ≈ 1.19 kg | Sliced mass is lower |

## 4. CG, stability, turning

Mass model: 07 §3.3 + metrics.csv + 06 §3 stations, ≈ 1.19 kg.

- **CG**: x **+11.6**, 38 above the plate top, **59 above ground**. The face, bulkhead and
  motors put it forward.
- **Ground clearance: 12.9 mm under the insert bosses, 16.9 under the flat plate.** The
  3 mm raise and the road wheels add 3.0 over rev 0. Moving the bosses to the top face
  (P12) makes it 16.9 everywhere.
- **High-centring (rev 0's real problem)**: with two wheels the bottom run spans 113 mm,
  and a mid-span threshold bowed it ~17 mm into a 9.9 mm belly gap. The road wheels cut
  the longest free span to **40 mm**, so the sag is ~6 mm against 12.9. **Fixed.**
- **Step climb** (quasi-static force model in `climb_max`: rigid parts, sharp edge,
  both motors at stall, rear contact pushing): **16 mm at μ 0.5, 34 mm at μ 0.9**. These
  are upper bounds. The step blocks in §7 give the real number; expect ~10–15 mm
  dependable.
- **Nod (R7)**: the support polygon ends at road wheel 2 (x +20.6), 9 mm ahead of the CG.
  Braking harder than **0.15 g** rocks the robot forward onto the sprocket, at most
  **6.2°**. Firmware should cap deceleration at ~0.1 g; that's a 0.3 m/s stop in 0.3 s,
  which is gentle. The sweep in the generator shows the trade: a bigger raise gives a
  better approach and a bigger nod. Smaller road wheels move the support forward but
  leave no room under the lugs for an axle spacer (Ø18 is the floor).
- **Rear tip** 1.16 g, **side tip** 52°.
- **Turning (skid steer)**: τ = μ·W·L/(2·B)·r_pitch per motor. The road wheels sit
  ROCKER (0.5 mm) below the idler, so a pivot loads the 40 mm between them, not the
  78 mm to the idler. Belt compliance shares some load, so the truth is between:

  | μ (floor) | rocker (road wheels) | full span |
  |---|---|---|
  | 0.5 (smooth tread, dusty floor) | 0.023 N·m (9 %) | 0.044 N·m (17 %) |
  | 0.9 (TPU on wood/tile) | **0.041 N·m (16 %)** | 0.079 N·m (31 %) |
  | 1.2 (TPU on rug) | 0.054 N·m (22 %) | 0.105 N·m (42 %) |

  Percentages are of the assumed TT stall (0.25 N·m). Rev 0 (two wheels) needed 45 % on
  tile.
- **L/B** 0.52 (rocker) to 0.76 (full): it turns very easily, and the IMU heading hold
  keeps it straight.
- **Pivot sweep** Ø272.

### 4b. Suspension geometry

| Wheel | x | z (plate top = 0) | Running Ø | Notes |
|---|---|---|---|---|
| Idler (tension) | −57.2 taut (−65…−55) | **10.5** | 54.8 | 3 mm below the TT shaft, so the belt's floor line is set by the road wheels |
| Road 1 | −19.7 | −8.4 | 18 | Fixed to the chassis; ROCKER 0.5 below the idler line |
| Road 2 | +20.6 | −8.4 | 18 | As far forward as a 2.5 mm gap to the sprocket allows |
| Sprocket (drive) | 52.7 | 13.5 | 54.8 | Rides 3.5 mm off the floor: approach ramp + ride height |

Road-wheel axles are at z −8.4, below the plate (underside −4) and outboard of it. Each
needs a **hanger**: a short PET-CF bracket off the plate edge inside the belt loop,
carrying a Ø4 shoulder axle with the inner disc, a Ø7 spacer under the lug row (lug tips
pass 5 mm off the axle), then the outer disc and a nyloc. The hanger lives inside the
loop, so nothing on the floor can reach it.

### 4c. Tension

Keep 05's rigid sliding carriage + jack screw; no spring. **The TPU belt is the spring.**
Snug the belt, then back the idler off by the strip-test figure, about 1–2 mm for 10 N in
85A. Re-tension as it creeps; 95A if it creeps past the travel. A spring idler would need
preload above the stall drive force, and it adds parts and moving gaps near small fingers.

## 5. Parts

All from `drivetrain.py build`; all closed meshes. The meshcheck "overhang" is the 45°
stair ramps and the short pocket-roof bridges.

**Wheel rim (sprocket and idler).** Two running discs at Ø54.8 carry the belt. A centre
band (10.2 wide) has 18 pockets: each lug + 0.6 mm all round. Tooth tops sit 0.6 below the
running surface, so the discs carry the belt. Pocket walls guide it sideways, so no
flanges (R4). Rim walls are 2.4 mm, with a 45° stair from the discs down to the band (R5).

**Sprocket.** Printed outboard face down. Inboard face 1.5 off the TT gearbox. Ø15 hub
tube with the TT double-D (Ø5.4 / 3.7, clearance from the coupon) over its last 8 mm
(TBD: shaft length); the TT's M2 end screw goes in through the axis. **Track centre is
19.5 mm off the gearbox face (kit ~39)** (R2). `sprocket_outrigger` has a 624 pocket in
the outboard face for P2o.

**Idler.** Same rim, hub = **two 624s** (outboard face + just past the centre plane), with
crush ribs (Q14). Open inboard side: the carriage's journal boss reaches in to the hub
tube. `idler_1brg` is the 05-style single-bearing variant.

**Road wheel disc** (`road_wheel_disc`, ×8). Ø18 × 12.9, 684 pocket with crush ribs +
shoulder. Two per axle, straddling the lug row. Coupon `coupon_684_10`.

**Belt.** One piece, printed as an upright ring Ø~132 × 36. Lug ends are chamfered 45°
above a 2 mm ledge, and both outer edges get a 1.2 mm 45° chamfer (bed side, fingers).
Three treads come out of the same lugs and length:

| Variant | Outside face | For |
|---|---|---|
| `belt_pads` | Pads 1.0 mm high with ~3 mm cross grooves. **Split at the centre line with the halves staggered** by half a spacing, and the spacing jittered ±15 % (fixed seed) | ~70 % contact on hard floors; the grooves clear dust and catch rug pile and step edges; staggered landings and varied spacing so it doesn't drum at one pitch (mic); the split eases sideways slide on a pivot |
| **`belt_bars_stagger`** (default) | The 1.5 mm bars split at the centre line, halves staggered half a pitch, spacing jittered ±15 % | Lugged for carpet pile, still fine on hardwood; half the bar lands at a time and not at one pitch, so quieter than `belt_bars` |
| `belt_bars` | Rev 0: full-width 1.5 mm bars, one per lug | Control |
| `belt_smooth` | Plain | Grip and quiet on clean floors, weakest on rugs and edges |

> Amendment (loop, 2026-11-01): default tread `belt_pads` → **`belt_bars_stagger`** (Ben: "we want lugs for the track, will be better on carpet and still work on hardwood"; then "go straight to the staggered version: same performance, less sound"). The `bars` lugs (1.5 high, 3 long, one per lug pitch), split at the centre line like the pads, the halves staggered half a pitch and the spacing jittered ±15 % (same fixed seed): about 22 % contact per half, 57.2 g (bars 57.4, pads 62.0). The A/B/C test (§7 test 5) still runs, now with `belt_bars_stagger` as A.

Not chosen: chevrons (directional, resist the pivot's sideways slide) and lengthwise
ribs (act as rails against it). Colour: lime-green 85A shows fewer scuffs on light floors
than black.

- **TPU 85A vs 95A**: start with 85A (grip, quiet). Go to 95A if 85A lugs ratchet or it
  creeps past the travel. Same STLs.
- Print: external spool, dried, textured PEI, walls only, slow volumetric flow; 0.4
  stainless for crisp lugs and pads.

**Coupons.** `coupon_ttbore_05…20` (D-bore, notches = rung), `coupon_624_10…20`,
`coupon_684_10`, `coupon_band_slice` (6 mm of sprocket band on a TT bore).

## 6. What the main design changes (loop P11–P13)

| Item | Before | TPU system |
|---|---|---|
| Track position | Kit track ~39 out | Belt inner edge 1.5 off the plate edge, centre \|y\| 74.5 |
| Plate rear-corner relief (Q10) | Narrowed to 92 behind x −27 | Not needed for the belt; check the 36-wide idler at \|y\| 56.5…92.5 |
| Follower | 05 wheel, Ø49.6, flanges | Toothed idler Ø54.8 × 36, 2 × 624, **axle z 10.5**; travel unchanged; taut at −57.2 |
| Road wheels | none | 2 per side, hangers off the plate edge, axles at x −19.7 / +20.6, z −8.4 |
| Bosses under the plate | to z −8 | Move to the top face if possible (+4 mm clearance) |
| P2 motor mount / S2 | Gear arm ~39 | ~19.5; re-run S2 |
| fea.py `TRACK_T` | 20 N | Keep 20 until measured; design 10 |
| Firmware | — | Deceleration cap ~0.1 g (nod, R7); note for the reflex MCU motion limits |
| Overall width | ~205 | 185 |

## 7. Test plan (cheap first, eyes before electrons)

1. **TT measurements**: shaft length past the gearbox face, end-screw size, confirm 5.4 / 3.7.
2. **Coupons** in PETG: TT bore ladder, 624 and 684 seats → `BORE_CLR`, crush interference.
   > Result (2026-11-08, Ben, PET-CF): **624 seat: 2 notches = 0.15 crush interference** (already the idler default, `idler(interf=0.15)`; no change). TT bore and 684 not reported yet (`BORE_CLR` 0.10 and the road disc's 0.10 stand).
   > Amendment (loop M6, 2026-11-02, Ben: "add the PA6-CF coupons"): print `coupon_624_10/15/20`
   > and `coupon_684_10` a second time in **Fiberon PA6-CF20** (dry 100 °C / 10 h; 0.4 hardened,
   > the fpv250 preset: `just cad-slice --mat PA6-CF`), next to the PET-CF set as the control.
   > Measure seat Ø and press-in feel twice: (a) straight off the dryer, (b) after 3–5 days in
   > room air (PA6 takes up to 3.3 % water and swells). If the conditioned fit stays inside the
   > crush-rib window, the idler and road discs go PA6-CF (tougher, wears better against the
   > belt); the sprocket stays PET-CF (D-bore on the TT shaft, 0.10/side). Sliced as PA6-CF
   > (tick 83): idler 28.5 g / 1 h 08 each (PET-CF 34.0 g), road disc 2.5 g / 13 min (3.3 g).
3. **TPU strip test**, 85A and 95A: 36 × 2.5 × 150 printed like the belt, hang 1 kg; stretch
   now and after 24 h → replaces `E_TPU` and sets the back-off distance (§4c).
4. **Lug mesh**: `coupon_band_slice` on a motor + a 6-lug belt arc; stall the TT: does a lug
   ratchet?
5. **Tread A/B/C**, one full side on a PETG plate with each of `belt_pads`, `belt_bars`,
   `belt_smooth`:
   - tilt test, forward and sideways μ, on tile, wood, rug;
   - pivot current vs stall;
   - mic noise floor while driving;
   - step blocks 5 / 10 / 15 / 20 / 25 mm (print them), square and with a 1 mm edge.
6. Pick the tread and TPU grade; feed real μ, E and the climb height back into the
   generator constants.

## 8. Open / next

- Wheel weight: ~35 g solid each; web lightening needs SOLIDWORKS (non-axisymmetric).
- Pinch audit (BACKLOG S2): the sprocket–belt nip at the front and the road-wheel entry
  points. A skirt over the top run.
- If 85A creeps too much: a 95A belt, or a 95A carcass with 85A pads (filament swap at a
  layer).
- Drop-off (cliff) sensing: nothing in the repo stops it driving off a stair. Not a
  drivetrain part, but the drivetrain can't save it. Raise in TODO.

> Amendment (loop T12, 2026-10-31): `python3 tools/drivetrain.py check-wrap`. Side clearance lug ↔ pocket 0.68 mm unstretched; the end lugs of the 180° wrap bind past **1.71 %** belt stretch (−0.12 mm at 2 %). Base bending strain 2.40 % on the wraps, 1.96 % on the runs. The belt rides the rim discs with the teeth 0.6 below (no chordal bump). Stretch beyond ~1.5 % needs wider pockets (CLR 0.6 → 0.75) or a new belt: Q21; the §7 strip-creep test decides.
