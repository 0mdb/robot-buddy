# Morning summary: CAD loop (leg 1: 46 ticks to 2026-10-31 11:10 · leg 2: from tick 47, stops 2026-11-01 07:00)

**Nothing is print-ready yet, by your call (don't print before the open items).** Drivetrain (sprocket + idler) is reviewed by you and cleared for test prints.

## Parts that exist (all generated, PET-CF, 0 interferences)
| Part | Mass | Status |
|---|---|---|
| Plate RB-PRT-001 | 111.6 g | S1m SF 3.9 (axle motion 1.03 mm → Q17: outboard track frame next); edges r 1 almost everywhere; min wall 1.19; motor-bell reliefs (your P14); prints flat with 26 cm² perimeter support |
| Bulkhead RB-PRT-002 | 43.6 g | S5c SF 4.7 (with the canopy holding its lugs); side edges r 1; face-side edges open (S1b2) |
| Pi deck RB-PRT-003 | 18.8 g | S1d SF 3.9; rear screws reachable (P4b) |
| Motor mounts 010/011 | 14.0 g each | S2 **converged**, SF 5.3; stay bolted (your call) |
| Sprocket 020 / idler 021 | 35.9 / 34.7 g | your review: good; outboard rims r 1 |
| Carriages 030/031 | 12.7 g each | S6 SF 4.9; one-key track swap (clamp insert) |
| **Canopy 004 (leg 2, new)** | **111.7 g PC** | pebble shell, top 95, rib grid + keels, inner roots r 1; heel S8 1.68 mm SF 2.5; side tongues into plate slots (Q19) so it actually braces the bulkhead: S5k 0.75 mm, S5c ≈ 0.7 mm vs 0.5 (open, P6i). Not yet: openings, outer edges, crown. Renders: `shots/1-P6c/` |
| **Printed total** | **482.3 g** | CoG (−0.1, 0.0, 27.9) |

## Biggest wins this leg
- Motor mount from failing to **converged SF 5.3** (D7–D10, D1).
- Plate: rib layout cleaned of four sliver clashes, whole belly + slots rounded (sharp accessible edges 4.5 m → 0.23 m), two near-zero walls found and fixed (D5b, D5c), insert floors 0.8 → 1.3 (D5).
- New parts: Pi deck, carriages. Tools: `filletface` (faces/loops by normal, box, loops), mass/CoG roll-up, PA6-CF in fea.py, bridge-aware overhang check, edge audit.
- Reviews: assembly order (R1, one trapped pair fixed), service times (R2), fasteners (A2: one 2.5 key), materials (M2: all PET-CF), print orientation (D3), battery (S4), design language (E1 → your pebble choice).

## Leg 2 (your order): canopy → track frame → treads → polish
1. **P6 canopy**: first cut in (tick 47). Next: plate holes (P6b), S7 + S5c with the real canopy (P6c), openings (P6d), edges (P6e), crown (P6f).
2. **Outboard track frame** (Q17): takes belt tension off the plate.
3. **Treads:** native belt part, wrap-fit/stretch check, print package + test pieces.
4. **Polish:** bulkhead face edges, fillets, motor-lead connectors.

## Before you print anything
- PCB: put the reflex USB-C on the board's **rear edge** (TODO updated).
- Coupons first (D6): insert ladder, TT bore, 624 seats.
- Measurements still wanted: track tension, TT shaft/end-screw, insert OD × length, HAT overhang.
