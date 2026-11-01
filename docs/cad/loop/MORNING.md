# Morning summary: CAD loop leg 2 (ticks 47–67 + a review pass, 2026-10-31 11:00 → 2026-11-01 06:15 MST)

SolidWorks hung at ~01:36 MST during a rebuild; you restarted it ~04:00 and the pending bulkhead top-edge round (S1b3) was re-verified and committed (S5c unchanged). **At 06:12 it went 'not responding' again** during the review re-run of the two canopy studies (canopy open, orphan swsim.exe; nothing killed). If it doesn't come back, close it and restart; nothing unsaved matters (every part is regenerated from the generators).

**Nothing is print-ready yet** (your call). Drivetrain coupons/test pieces are ready to print (below).

## Parts (all generated; 0 interferences at the last full rebuild, tick 67)
| Part | Mass | Status |
|---|---|---|
| Plate 001 | 110.9 g | S1m SF 3.5 (review pass 9.97 MPa; 8.87 at tick 52 with the same plate: the jack-stop peak is mesh-sensitive); **S1 passes on your Q20 rule** (drive increment ~0.09 mm vs 0.2 with the track frame); canopy slots + rear screw holes |
| Bulkhead 002 | 43.5 g | S5c SF 4.7 / 0.27 mm (lugs held); face openings + top front edge r 1 (ticks 59, 63); side cheeks close the front-corner finger slot 9.5 → 4.5 mm (Q22, tick 65) |
| **Canopy 004 (new)** | **~114 g PC white** | pebble shell, top 95, 4 mm rib grid + 2 keels, inner roots r 1, outer rim + hood edge r 1; heel S8 (150 N, your rule) 1.68 mm SF 2.5; side tongues into plate slots brace the bulkhead (S5k 0.75 mm) |
| **Track frames 040/041 (new)** | 19.1 g each | outboard side plates (Q22): tie the sprocket 624 to the idler axle and cover the lug ↔ pocket nips; width ~200; outline r 1 |
| **Belts 050/051 (new, native)** | 58.4 g each TPU | installed shape, lugs in the pockets |
| Pi deck 003, mounts 010/011, sprocket/idler 020/021, carriages 030/031 | unchanged | as leg 1 |
| **Printed total** | **638.1 g** | incl. belts (117 g); CoG (−0.7, 0.0, 24.8) |

## What leg 2 did, biggest first
1. **Canopy from nothing to a strength-checked part** (P6, Q19): PC over ASA on the heel test (SF 2.4 vs 1.45); the bare shell failed badly (19.5 mm), then a rib grid + keels + your top 93 → 97 → 95. S5k showed it couldn't hold the bulkhead (it swung on its apron), so the side tongues were added: 340 mm → 0.75 mm.
2. **Track frame** (Q17 b, P2o): bars only (legs had no room); the plate's axle path is halved; S1 judged on the drive increment (Q20) → pass.
3. **Treads:** native belts (T11), `drivetrain.py check-wrap` (T12), print package `docs/cad/belt_print.md` with strip + 6-lug test pieces (T13).
4. **Engine bug found and fixed:** `box` (CreateCornerRectangle) misbuilt over existing bodies. It explained the 2.4 mm canopy keels and a bulkhead foot built ~110–250 mm³ short since leg 1.
5. Kid safety (Q22): bulkhead side cheeks (front-corner slot 9.5 → 4.5 mm) and the frame bars grown into side plates over the lug nips (`shots/1-S2/`).
6. Polish: bulkhead face openings r 1, canopy rim + hood edge r 1, motor leads corrected to 6-pin (R2b).
7. Rejected: plate boss-root fillets (S1b +60 %, S1m +19 %: mesh-sensitive peaks).

## Review pass (06:00 MST, final geometry, every study once)
| Study | Part | Peak | SF (Z UTS) | Note |
|---|---|---|---|---|
| S1m | plate + mounts, track tension | 9.97 MPa | 3.5 | was 8.87 (same plate): mesh scatter at the jack stops |
| S1b | plate, 10 g stack | 3.20 MPa | 10.9 | deck 0.13 mm |
| S1d | Pi deck | 8.93 MPa | 3.9 | |
| S2 | motor mount, pull + torque | 6.10 MPa | 5.7 | converged (leg 1) |
| S6 | carriage | 7.57 MPa | 4.6 | |
| S5c | bulkhead, lugs held | 7.48 MPa | 4.7 | 0.27 mm |
| S8 | canopy heel 150 N (PC) | 24.8 MPa | 2.5 (XY) | 1.61 mm (re-run 07:40 after the restart) |
| S5k | canopy at the lugs (PC) | 9.5 MPa | — | 0.75 mm (re-run 07:40) |

## Open, for you
- **Q21 belt stretch:** lugs bind past 1.71 % stretch; default = let the strip-creep test decide (pocket CLR 0.6 → 0.75 is the ready fix).
- **P6i:** S5c with the real canopy ≈ 0.7 mm at the bezel vs 0.5 (hand estimate; you said accept, recorded open).
- **E1 vs geometry:** the hood edge got r 1, not r 3 (ceiling 1.8 thick); the two hood-top screw heads are visible from above.
- Measurements: encoder-motor connector (R2b), UPS HAT port positions (canopy cut-outs P6d), TPU shrink (strip), track tension.

## Print first (cheap, settles numbers)
`python3 tools/drivetrain.py build -o CAD/exports/rnd/drivetrain`, then print `belt_strip150` + `belt_lug6` in TPU 85A, plus the coupons (TT bore, 624 seats, band slice). See `docs/cad/belt_print.md`.
