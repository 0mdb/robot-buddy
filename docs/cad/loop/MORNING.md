# Summary: CAD loop leg 3 (from tick 68, 2026-11-01 11:00 MST; no stop time)

Order (Ben): P13 road wheels → P7/P8 → canopy P6d/f/e → T4 slicing → P10/E4 → polish.
**Nothing is print-ready yet** (your call). Coupons/test pieces are ready (below).

## Since leg 2, biggest first
1. **08 rev 1 is finally in `cad-loop` (P13a, tick 68).** 81fd640 (road wheels, idler 3 mm
   below the TT shaft) had never been cherry-picked. Now: belt on the 4-wheel path (400 mm),
   idler/carriage/track-frame slot at z 10.5, taut station −57.18, wheels turned so every lug
   near them clears its pocket. **0 interferences.**
2. **Carriage clamp insert flipped** (found by S6 after the drop: 22.95 MPa, the axle-bolt
   head sat in the clamp boss): insert pressed up from the foot's underside, screw M3 × 12 →
   **M3 × 10**. **S6 7.57 → 6.50 MPa (SF 5.4)**, carriage 12.3 → 11.4 g.
3. **Tread → `belt_bars_stagger`** (your call): 1.5 mm bars split at the centre, halves
   staggered half a pitch, spacing jittered ±15 %; 57.2 g. 08 amended.
4. **Road wheels (P13b, tick 69):** `RB-PRT-022_road_disc` 3.4 g × 8 placed on both axles per side, 0 interferences. Hangers next.
5. **Canopy rear-wall vents (P6d, tick 71):** 2 × 13 vertical slots (intake under the HAT,
   exhaust above it), canopy 114.2 → 112.8 g PC. S8 25.1 MPa / 1.63 mm (< 1.7), S5k lugs 0.77 mm:
   both within 2–3 % of before. Look: `shots/1-P6d/canopy_right.png`.
6. **Headless slicing (T4, tick 72):** `just cad-slice` → `CAD/exports/print/<part>.3mf` (settings
   inside: 4 walls, 40 % gyroid, Engineering Plate) + `sliced.json`. **13 parts 623 g filament, 26.2 h.**
   The canopy printed open side down is 186 g / 9.5 h on tree support (113 g of part): P6f next.
   Bambu's PC preset says density 1.04; overridden to 1.20.
7. **Canopy crown (P6f, tick 74):** top is a 2.5 mm arc front-to-back (no big flat), ribs follow it at
   constant 4 mm depth. **S8 22.8 MPa (SF 2.72, better than flat 25.1), heel 1.43 mm**; S5k unchanged.
   Canopy 114.8 g (+2.0). Took four runs: a micron step where flat-bottom cross ribs met curved
   lengthwise ribs read as 83 MPa; FEA hotspots now print the peak node's xyz. Look: `shots/1-P6f/canopy_right.png`.
8. **Canopy edges (P6e, tick 75):** outer front corners r 1; the canopy is now in the kid-safety edge audit.
   **Q27** (new): the hood-top screw heads can't be recessed where they are (flange already overhangs the
   hood's front edge); default = lugs 3 mm aft + counterbored collar.
9. **Hero renders (E4, tick 76):** `shots/hero/` (three-quarter, face at a 5-year-old's eye height, rear, top),
   re-rendered every rebuild. Start here for the look.
10. **Part numbers (R3, ticks 78–79):** plate, canopy, deck, both track frames carry "RB-0xx r1" cut 0.6 deep on a
    hidden face (each checked by ray-casting the STL from the reading side). Speaker grille slots now round-ended (D2).
11. **Overnight polish (ticks 80–83):** part numbers on both mounts; the S1b +16 % after the labels is mesh
    noise at the jack block's square root (no-label A/B = 3.20); rounding that root (r 2) made S1m/S1a/S1b
    worse (+33/+27/+15 %), **rejected**. **M6:** PA6-CF coupon set in 08 §7, `just cad-slice --mat PA6-CF`
    uses your fpv250 preset (idler 28.5 g, road disc 2.5 g). SW rebuilds have slowed to ~45 min: a restart may help.
12. **Kid-safety edges (ticks 85–88):** canopy vent slots + apron corners, bulkhead grille slots + foot front,
    plate tongue slots. Accessible sharp edges: canopy 1,205 → 405 mm, bulkhead 684 → 236 mm (the rest sits on/in
    other parts). All studies unchanged. **Part cache**: unchanged parts aren't rebuilt (SW rebuilds had reached ~1 h).
13. Backlog: PA6-CF wheel coupons (Fiberon PA6-CF20 in stock); **M3** insert ladder
   ported from fpv250 (its PA6-CF result is M2 Ø3.4 × 5.5; buddy is M3).

Printed total **663.1 g** (incl. belts 117 g, road discs 27 g), CoG (−0.3, 0.0, 22.6). Review-pass studies from
leg 2 stand except S6 (now 6.50).

## Answered 2026-11-02 (Ben): Q24 (a) frame carries road axles · Q25 (a) boxed micro speaker · Q26 (a) canopy rear wall down · Q27 (a) lugs 3 mm aft + counterbore. The loop builds them next (P13c/d, P7, P6f undersides, P6e screw heads).

## Open, for you
- **Q27 hood-top screw heads:** flange overhangs the hood front edge; default lugs 3 mm aft + counterbored collar (bulkhead change).
- **Q26 canopy print orientation:** rear wall on the bed = 149 g / 6.8 h (vs 186 g / 9.5 h as modelled, 83 g of support inside); S8 still SF 2.23 on the datasheet Z strength. Default: rear wall down + 45° rib undersides.
- **Q24 road-wheel axles:** the plate-edge hanger doesn't fit; default = the track frame carries them. P13c/d wait.
- **Q25 speaker:** the CE40P-8 hits the left motor mount 8 mm behind the wall; default = a pre-boxed 8 Ω micro speaker. P7 waits.
- **M3 inserts:** knurl OD + length of the M3 inserts in hand (sizes the ladder coupon).
- **Q21 belt stretch:** lugs bind past 1.71 %; the strip-creep test decides (CLR 0.75 ready).
- **P6i / E1:** S5c with the real canopy ≈ 0.7 mm vs 0.5 (you said accept); hood edge r 1 not r 3.
- Measurements: encoder-motor connector (R2b), UPS HAT ports + heights (P6d, Q23), track tension.

## Print first (cheap, settles numbers)
`python3 tools/drivetrain.py build -o CAD/exports/rnd/drivetrain` (now also writes
`belt_bars_stagger`), then `belt_strip150` + `belt_lug6` in TPU 85A, the coupons (TT bore,
624 seats, 684, band slice) in PET-CF **and PA6-CF** (M6). See `docs/cad/belt_print.md`.

## Next
P6f orientation (Q26) → P6e → P10/E4; P6d rest needs your numbers → T4 slicing; P13c/d and P7 once Q24/Q25 are answered.
