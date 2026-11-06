# E1 design language (proposal, tick 31, 2026-10-31) → Q18

A floor robot for ages 6–12, seen mostly from above and from a child's eye level (~40 cm). What it has to read as: **friendly, solid, a little toy-like, not a gadget**. The face (2.8" screen, 15° back) is the focal point; everything else stays quiet.

## Proposal

1. **One fillet family: 1 / 3 / 8 mm.**
   - **1 mm**: every accessible edge on structural PET-CF parts (the kid-safety minimum, already done on the plate, S1a–W3) and inside corners on load paths (`fil_in`).
   - **3 mm**: edges of handled parts a child grabs (canopy rim, bulkhead outer edges, track-guard lips), and the corners of every opening (screen window, speaker grille field, cut-outs).
   - **8 mm**: the silhouette: canopy corners and the bulkhead's outer top corners. It's what makes the "pebble".
   No other radii; a radius between two of these reads as an accident.
2. **"Pebble" silhouette.** Canopy = one soft volume: plan corners r ≥ 20 (they follow the plate's rear R20; the front chamfer was removed 2026-11-06, Ben: square front corners r 3 under the bulkhead), top edges r 8, no flat panel bigger than ~60 × 60 mm (white shows layer lines and dirt on flats; a 2–3 mm crown over the top hides both and stiffens the 1.8 shell). The bulkhead frames the face like a bezel and the canopy wraps behind it, so the robot reads as "head + body".
3. **No exposed screw heads on what a child sees** (front, top, sides above the tracks). Canopy screws go in from below or behind (the 2.0-key buttons from A2 on the rear face only); face-board screws are behind the bulkhead; the plate's screws are on the belly.
4. **Openings as patterns, not holes.** Speaker grille, vents and mic ports as one consistent motif: rows of r 1.5 slots or Ø 2 holes on a 4 mm grid (≤ 2 mm openings, 06 §5), grouped in soft-cornered fields (3 mm radius).
5. **Proportion.** Keep the face high and proud (head height ~122 vs the canopy top ~93): the head-over-body step is the character. Tracks stay visually "chassis" (black), the body sits on them.

## What it costs / changes
- Canopy (P6) designs to this directly; the bulkhead needs E2 (r 3 / 8 on its outer edges; S1b does the r 1 minimum).
- Shell crown and big radii want PC or ASA rather than PET-CF (M4).
- No change to the plate, mounts, carriages or wheels beyond the kid-safety radii already in.

## Options for Ben (Q18)
- **(a) as proposed** (1 / 3 / 8, pebble, hidden screws, slot-pattern openings). *Default.*
- (b) crisper "robot" look: 1 / 2 / 4 family, chamfers instead of big fillets, flat panels with deliberate parting lines (easier to print well in PET-CF, less toy-like).
- (c) something else: a reference image or object helps most.
