# Belt print package (T13, 2026-10-31)

Files: `python3 tools/drivetrain.py build -o CAD/exports/rnd/drivetrain [--shrink <pct>]`

| File | What | Print |
|---|---|---|
| `belt.stl` | the belt as printed: upright ring Ø133 × 36, lugs in, bars out | one per side |
| `belt_shrink<pct>.stl` | the same, diameter grown by the measured shrink | once the strip test gives a number |
| `belt_strip150.stl` | 150 × 2.5 × 36 plain band (08 §7.3 hang/creep test) | one per TPU grade |
| `belt_lug6.stl` | straight 6-lug length (08 §7.4): wrap by hand round `coupon_band_slice`, stall-test on a TT | one per TPU grade |

## Orientation and settings (starting points 🟡, Bambu Studio by hand until T4 slices headless)

- **Upright**, as exported: belt width = Z, so tension runs along the layers. No supports. The lug end
  chamfers (45°) make the lower lug ends print as a ledge.
- **Walls only**: the base is 2.5 mm, so set enough wall loops to fill it (no sparse infill in the
  band). Lugs and bars are solid.
- **Seam**: paint it onto the lug inner faces (the faces that sit in the pockets, not the running
  surface or the tread). Avoid a seam on the inner running face: it's what the wheels roll on.
- **Material**: TPU 85A first, 95A as the fallback (08). Dry it. Feed it from the external spool,
  not the AMS (print-bom.md). Print slowly; tune on the strip first.
- **Plate**: textured PEI (print-bom.md).

## Orca setup (P2S, 0.6 hardened nozzle, 2026-11-01)

Bambu's TPU 85A profile for the P2S is only for the **0.6 nozzle**. Select:
- Printer: **Bambu Lab P2S 0.6 nozzle**
- Filament: **Bambu TPU 85A @BBL P2S** (stock: 225 °C, 2.2 mm³/s cap), loaded on the **external spool**
- Process: **robot-buddy belt TPU85A 0.6**, a user preset (`%APPDATA%\OrcaSlicer\user\default\process`) on top of *0.24mm Balanced Quality @BBL P2S 0.6 nozzle*, with 4 walls (0.62 lines ≈ the 2.5 base, no infill), 0 % sparse infill and a 5 mm outer brim.
- Plate: textured PEI. Keep the strip standing (36 mm up).

**Strip print 1 (stock filament profile, 0.24 layers, classic walls): outer walls delaminated down
the strip's edge.** The stock profile runs the part fan at 100 % (layer time ~40 s, well under its
100 s full-fan threshold) plus the auxiliary fan at 70 %, at 225 °C: each layer lands on cold TPU.
The classic wall generator also leaves an uneven seam between the two sides' walls in a 2.5 mm
band. Revised presets (2026-11-01), for strip print 2:
- Filament: **robot-buddy belt TPU85A hot** (user preset on *Bambu TPU 85A @BBL P2S*): 240 °C
  (235 first layer, the grade's top), part fan 10–30 %, auxiliary fan off, flow 1.05, fan off for 3 layers.
- Process: the same **robot-buddy belt TPU85A 0.6**, now 0.20 layers (more squish per line),
  Arachne walls (even lines across the band, no centre seam), seam at the back.

## Shrink compensation

TPU contracts along the printed length. Print `belt_strip150` and measure its length cold: shrink % =
(150 − measured) / 150 × 100. Rebuild with `--shrink <that>` and print the belt from
`belt_shrink<pct>.stl`. The fit target is a 400 mm pitch length (40 × 10), with the idler at
x −57.3 ± 5 (08). The jack screw has 4.6 mm of install slack.

**Measured (strip print 1, TPU 85A, 0.6 nozzle): 149.16 mm → 0.56 % shrink** (≈ 2.2 mm on the 400 mm
belt, inside the jack slack, but compensated anyway): print the belts from `belt_shrink0.56.stl`.
Re-measure on strip print 2 if the hotter settings move it by more than ~0.2 %.

## After printing, before fitting

- Hang test (08 §7.3): 1 kg on the strip, length now and after 24 h. Past **1.5 %** total stretch the
  end lugs approach their pocket clearance (T12 `check-wrap`: zero clearance at 1.71 %, Q21).
  **Strip print 1: stretch under 1 kg negligible (Ben, 2026-11-01): Q21 closed, pockets stay CLR 0.6.**
- `python3 tools/drivetrain.py check-wrap` re-runs the fit check with the current numbers.
