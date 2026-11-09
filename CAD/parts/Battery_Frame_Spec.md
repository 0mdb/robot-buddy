# Battery Frame Spec — 3S4P 21700 two-plate cage (robot-scout)

## Pack it captures
- 12 × Molicel P42A, **3S4P**, cells lying flat, **2 layers × 6**
- Pack envelope on its side: **137.2 (W) × 70 (D, cell length) × 46.4 (H)**
- Cavity: 150 × 96 × 50 mm → W and D fit; **H 46.4 is the tight one** (BMS on top handled by the top-plate bubble)

## Architecture — two-plate cage
- **Two nub plates** (the loosened inline 2×6, `Inline+…FINAL_v2`, 46.4 × 137.2 × 8.9 mm) set at cell-depth **15 mm and 55 mm** → 40 mm apart, gripping each 70 mm cell at two points (no cantilever).
- **Terminals exposed** ~11 mm past each plate (cell ends at depth 0 and 70) → clear access to weld bus bars.
- **Cage ties:** 4 corner posts + a base rail + a top rail bond the two plates into one rigid brick.
- Material: **ASA** (matches the holder) or **PET-CF** for a stiffer frame.

## Mounting (bolt-down, semi-permanent)
- **Flange feet at the base**, M3 clearance holes, screws **down into the bay floor** (heat-set inserts or tapped), accessible from above.
- Feet extend in the **depth** direction (beyond the plates) so they add to footprint, **not height**.
- **Frame defines the hole pattern → drill/insert the bay floor to match.** (Chassis geometry isn't in the files.)
- Charge-in-bot: route the **XT90** to an accessible edge; dock contacts wire to B+/P− (later subsystem).

## BMS mount (on top)
- Daly **Li-ion 3S 40 A common-port**, **123 × 65 × 14 mm**, 4 corner mount holes.
- Sits on a **top platform** (pack top face is 137 × 70 — fits).
- v1: **cradle lip** capturing the 123 × 65 outline (no measured holes needed); **bolt bosses** added once you give the hole-center pitch.
- BMS on top adds ~14 mm → total stack ~60 mm → **top-plate bubble** over this footprint.

## Wiring recap (from the BMS)
- **B−** → pack negative (cells). **B+ / +** → pack positive (pass-through).
- **P−** → protected output; **load + charger both land on B+ / P−**.
- **XT90** = B+ and P− (protected port). Common-port → **charge and discharge share it**; feed a **12.6 V CC/CV** charger. Balance lead B0–B3 per the wiring diagram; NTC taped to a mid-pack cell.

## Assembly order
1. Thread all 12 cells through both plates (nubs retain them).
2. Weld bus bars on the exposed ends (0.2 × 10 pure nickel, series links 2 layers).
3. Insulate ends (fish-paper) + end covers.
4. Bolt BMS on the top platform; wire B−/B+/P−/balance/NTC.
5. Drop the brick into the bay, bolt the feet, connect XT90 + balance/alarm.

## Open items before STL
- Confirm **plate spacing** (40 mm c-c) and terminal exposure (~11 mm).
- BMS: **cradle** (default) or **bolt bosses** — if bosses, need the mount-hole center pitch.
- Foot count/positions vs the bay floor.
