# ASA Print Setup — 2S6P 21700 Holder (inline, nubs + chamfer)

**File:** `Inline+2S6P+Halterung+LiPo+21700+FINAL.stl`
**Size:** 46.0 × 136.0 × 8.9 mm · 12 cells · 1 mm walls/bridges · 0.3 mm hole-top chamfer
**Retention:** 3× 0.3 mm nubs/hole, tips on a 21.1 mm circle (0.2 mm grip on a 21.3 mm cell)
**Material:** ASA

> Note: inline (un-staggered) 2×6 grid — the four-way grid of 1 mm bridges self-connects, so no edge ribs are needed. A staggered/ribbed variant also exists in this folder if you revert the orientation.

## Orientation & supports
Print **flat, bottom face on the bed** (holes vertical, chamfers facing up) — this is how the STL is already oriented. Ring walls print as strong vertical walls, the 0.3 mm chamfer is a self-supporting 45° funnel, and there are no overhangs.

**Supports: none.** **Brim: yes** (see adhesion).

## Core temperatures
- Nozzle: **250 °C** (range 240–260; go hotter for layer strength on the thin walls)
- Bed: **100 °C** (range 90–110)
- **Enclosure required** — ASA warps badly with drafts, and it emits styrene fumes, so keep it enclosed and ventilated.

## Walls (this is the important part)
The frame is essentially all 1 mm wall, so perimeters *are* the part.
- Nozzle **0.4 mm**
- **Use the Arachne / variable-width wall engine** (default in current PrusaSlicer, Cura, OrcaSlicer). It fills a 1 mm wall cleanly instead of leaving a gap or over-extruding. Without Arachne, set 2 perimeters + "detect thin walls" on.
- Line width 0.4–0.45 mm
- Layer height **0.16 mm** (cleaner holes/chamfer) or 0.20 mm for speed
- Top/bottom layers: 4–5 (≈0.8–1.0 mm)
- Infill: 20 % (barely used given the thin walls)

## Cooling
ASA dislikes cooling (cracks/delaminates). Fan **0 % for the first few layers, then ~20 %** — enough to define the thin walls without killing layer adhesion.

## Adhesion
- **Brim 5–8 mm** — the footprint contacts the bed only along thin rings, and ASA corners lift. A brim (or draft shield) is strongly recommended.
- Clean bed + glue stick / PEI.

## Fit / dimensional notes
- Holes are **21.5 mm** for 21 mm cells → 0.5 mm diametral clearance, matching the original.
- ASA shrinks ~0.4–0.6 %. Over the 121 mm length that's ~0.5–0.7 mm, and holes may print ~0.1 mm undersize. The 0.5 mm clearance should absorb it, **but print one as a fit-test before committing.**
- If cells are tight after printing: apply hole/horizontal-expansion compensation (about −0.1 mm) or scale the model +0.5 % in X/Y. If loose, the reverse.

## Print time / material (approx, 0.2 mm)
Small part — expect roughly 2–3 h and ~25–35 g of ASA depending on slicer settings.
