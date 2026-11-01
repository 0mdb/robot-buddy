# S2 pinch-point audit, track path (tick 64, 2026-11-01)

Rule (BACKLOG kid-safety): no reachable gap between 5 and 12 mm next to a moving part; a gap < 5 mm doesn't
take a finger, > 12 mm doesn't trap one. Numbers from the generators (`chassis.py`, `drivetrain.py`).

| Place | Gap | Verdict |
|---|---|---|
| Plate edge (|y| 55) ↔ belt inner edge (56.5) | 1.5 | ✓ |
| Canopy side / front lips (|y| 53) ↔ belt | 3.5 | ✓ |
| Frame bar (|y| 93.5) ↔ wheels' outboard faces (92.5) | 1.0 | ✓ (bar static, wheel face smooth) |
| Canopy skirt (z 30) under the top run (belt top z 44.9) | covered by the belt from the side | ✓ |
| **F1: front corners**, bulkhead side (|y| 47) ↔ belt inner edge (56.5), x ≈ 74…85, z 0…30 (above z 30 the canopy lips close it) | **9.5** | ❌ finger-size, beside the sprocket |
| **F2: inside the belt loop** from outboard: frame bar top (z 20.5) ↔ top-run lug tips (z 36.9); bar bottom (6.5) ↔ bottom-run lug tips (−9.9) | **16.4 / 16.4** | ⚠️ > 12 doesn't trap, but it lets a finger reach the **lug ↔ pocket nips** at the wheel tangent points, the real pinch on a track |
| Idler rear (x −88.7) behind the plate (−85) | belt wraps outboard | ✓ (same nip as F2) |

## Fixes (proposed, Q22)
- **F1:** close the slot to < 5: a bulkhead side cheek (2.4 PET-CF, |y| 47 → 52, x 74…85, z 0…30, part of the bulkhead) or the canopy lips continued down to the plate there. The cheek is simpler (one part, no new joint), ~3 g per side.
- **F2:** grow each frame bar into a **side plate** covering the loop window (z −8 … 35 between the wheels, x −30 … 25), outboard of the wheels; the lug ↔ pocket nips are then behind it. ~+12 g per side, and the track looks "enclosed" (E1: tracks read as chassis). Keep ≥ 1 mm off the wheel faces.
