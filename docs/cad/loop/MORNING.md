# Morning summary: CAD loop leg 2 (ticks 47–63, 2026-10-31 11:00 → 2026-11-01 ~01:40 MST)

**⚠️ SolidWorks hung at ~01:36 MST** during the tick-63 rebuild ("not responding", unsaved Part544 open, ~15 GB). Nothing was killed: `swbuild.exe` and `swsim.exe` (S5c) are still attached and waiting. **Restart SolidWorks by hand.** One change is pending re-verification: the bulkhead's top front edge r 1.0 (S1b3). It built clean alone, and it's in `tools/chassis.py`, uncommitted (STATE.md says what to run).

**Nothing is print-ready yet** (your call). Drivetrain coupons/test pieces are ready to print (below).

## Parts (all generated; 0 interferences at the last full rebuild, tick 62)
| Part | Mass | Status |
|---|---|---|
| Plate 001 | 110.9 g | S1m SF 3.95; **S1 passes on your Q20 rule** (drive increment ~0.09 mm vs 0.2 with the track frame); canopy slots + rear screw holes |
| Bulkhead 002 | 43.5 g | S5c SF 4.6 / 0.27 mm (lugs held); face openings r 1 (tick 59); top edge r 1 pending (S1b3) |
| **Canopy 004 (new)** | **~114 g PC white** | pebble shell, top 95, 4 mm rib grid + 2 keels, inner roots r 1, outer rim + hood edge r 1; heel S8 (150 N, your rule) 1.68 mm SF 2.5; side tongues into plate slots brace the bulkhead (S5k 0.75 mm) |
| **Track frames 040/041 (new)** | 8.2 g each | outboard bars, sprocket 624 ↔ idler axle; width ~200 |
| **Belts 050/051 (new, native)** | 58.4 g each TPU | installed shape, lugs in the pockets |
| Pi deck 003, mounts 010/011, sprocket/idler 020/021, carriages 030/031 | unchanged | as leg 1 |
| **Printed total** | **615.4 g** | incl. belts (117 g); CoG (−0.7, 0.0, 24.8) |

## What leg 2 did, biggest first
1. **Canopy from nothing to a strength-checked part** (P6, Q19): PC over ASA on the heel test (SF 2.4 vs 1.45); the bare shell failed badly (19.5 mm), then a rib grid + keels + your top 93 → 97 → 95. S5k showed it couldn't hold the bulkhead (it swung on its apron), so the side tongues were added: 340 mm → 0.75 mm.
2. **Track frame** (Q17 b, P2o): bars only (legs had no room); the plate's axle path is halved; S1 judged on the drive increment (Q20) → pass.
3. **Treads:** native belts (T11), `drivetrain.py check-wrap` (T12), print package `docs/cad/belt_print.md` with strip + 6-lug test pieces (T13).
4. **Engine bug found and fixed:** `box` (CreateCornerRectangle) misbuilt over existing bodies. It explained the 2.4 mm canopy keels and a bulkhead foot built ~110–250 mm³ short since leg 1.
5. Polish: bulkhead face openings r 1, canopy rim + hood edge r 1, motor leads corrected to 6-pin (R2b).
6. Rejected: plate boss-root fillets (S1b +60 %, S1m +19 %: mesh-sensitive peaks).

## Open, for you
- **Q21 belt stretch:** lugs bind past 1.71 % stretch; default = let the strip-creep test decide (pocket CLR 0.6 → 0.75 is the ready fix).
- **P6i:** S5c with the real canopy ≈ 0.7 mm at the bezel vs 0.5 (hand estimate; you said accept, recorded open).
- **E1 vs geometry:** the hood edge got r 1, not r 3 (ceiling 1.8 thick); the two hood-top screw heads are visible from above.
- Measurements: encoder-motor connector (R2b), UPS HAT port positions (canopy cut-outs P6d), TPU shrink (strip), track tension.

## Print first (cheap, settles numbers)
`python3 tools/drivetrain.py build -o CAD/exports/rnd/drivetrain`, then print `belt_strip150` + `belt_lug6` in TPU 85A, plus the coupons (TT bore, 624 seats, band slice). See `docs/cad/belt_print.md`.
