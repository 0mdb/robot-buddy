# R1 assembly sequence (tick 24, 2026-10-31)

Every joint in 06 §8 plus what the loop has built (deck, carriages, idlers), checked against the generated geometry for driver access. Coordinates are the chassis frame (mm).

## Sequence

| # | Step | Fastener / tool | Access check |
|---|---|---|---|
| 1 | Heat-set inserts into the plate: 8 mount under-bosses, 4 deck posts, 4 reflex standoffs, 2 jack blocks (along X); 3 + 1 into the bulkhead foot; 2 per mount (motor face) | iron, Ruthex M3 | all from open faces ✓ |
| 2 | **Motor → mount** (on the bench): 2 × M3 through the gearbox into the mount inserts | M3 × 28 (22.6 gearbox + 5.4; the lower pocket is now blind at 6.6, D10) | **must precede the sprocket**: the screw heads are 21.6 from the shaft, under the sprocket (r 31.4). To swap a motor, the sprocket comes off first (M2 end screw) |
| 3 | **Mount → plate**: 4 × M3 down into the under-boss inserts | M3 × 8, 2.5 hex | heads on the inboard side, open from above ✓. **Must precede the bulkhead**: its wall leans back 15° and its top sits over x ≈ 50, above the holes at x 43.9–72.6 |
| 4 | Reflex board onto its standoffs (4 × M3) | 2.5 hex | open until the deck goes on ✓ |
| 5 | Bulkhead onto the plate: tabs in the slots, 3 × M3 up through the counterbored plate + the knee screw at (61, 2.4) | M3 from below, 2.5 hex | belly open ✓ |
| 6 | **Pi stack → deck** (bench sub-assembly): 4 × M2.5 up from under the deck into the brass standoffs | M2.5, 2.0 hex | only possible before the deck is mounted (the underside is blind after) |
| 7 | **Deck → posts**: 4 × M3 down into the post inserts | M3, 2.5 hex | ❌ **rear pair (−48, ±20) is under the Pi board** (x −64.5…22.5, \|y\| ≤ 28): trapped once the stack is on. Front pair (30, ±8) is clear (board ends at 22.5) |
| 8 | Sprockets onto the TT shafts, M2 end screw | M2, 1.5 hex | outboard face ✓ |
| 9 | Carriages into the guide slots, clamp screw down to a nut under the plate (finger-loose) | M3 × 16 + nyloc | top + belly ✓ |
| 10 | Idler axle: Ø4 shoulder bolt from outboard through the 2 × 624 into the boss bore; nyloc on the pedestal's inboard face (\|y\| 40, z ~~13.5~~ **10.5**, 08 rev 1; the clamp insert below it is pressed from underneath since tick 68) | 2.5 hex + 5.5 spanner | under the canopy, open from above ✓ |
| 11 | Belt on, tension with the jack screw, clamp | M3 jack screw, 2.5 hex | ⚠️ the head sits between the jack block (x −28) and the encoder housing (x −10 … 3.3, \|y\| 30.7–56.7, z 1–26): **18 mm** for a key along X at \|y\| 36.5. A straight driver can't reach; a ball-end L-key can |
| 12 | Face board onto the bulkhead, cables, canopy (4 × M3) | 2.5 hex | P6 not designed yet; the 2 rear canopy bosses on the plate don't exist yet |

## Findings → backlog
- **R1-F1 (fix):** the deck's rear screws are trapped under the Pi stack. Move the rear posts outside the board, e.g. (−70, ±20) with the deck extended to x −74 (clear of the carriages, |y| ≥ 28, and the guide slots), or turn them into screws from below (inserts in the deck, screws up through the posts). → **P4b**.
- **R1-F2 (order):** motor before sprocket; mounts before bulkhead. Not trapped, but the service order for a motor swap is sprocket → motor screws (mount stays on). Goes into the build guide.
- **R1-F3 (service):** tensioning needs a ball-end 2.5 L-key in 18 mm. Cheaper fix: a knurled-head M3 thumb screw (05 lists one for the clamp already), or move the head side. → R2 (service timing).
- One driver size covers almost everything (2.5 hex for M3); M2.5 (2.0) and M2 (1.5) are bench-only. → A2.
