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

## Shrink compensation

TPU contracts along the printed length. Print `belt_strip150` and measure its length cold: shrink % =
(150 − measured) / 150 × 100. Rebuild with `--shrink <that>` and print the belt from
`belt_shrink<pct>.stl`. The fit target is a 400 mm pitch length (40 × 10), with the idler at
x −57.3 ± 5 (08). The jack screw has 4.6 mm of install slack.

## After printing, before fitting

- Hang test (08 §7.3): 1 kg on the strip, length now and after 24 h. Past **1.5 %** total stretch the
  end lugs approach their pocket clearance (T12 `check-wrap`: zero clearance at 1.71 %, Q21).
- `python3 tools/drivetrain.py check-wrap` re-runs the fit check with the current numbers.
