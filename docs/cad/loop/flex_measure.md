# reSpeaker Flex XVF3800: check the boards against the model (2026-11-06)

The boards arrived 2026-11-06. Every number the CAD uses came from Seeed's STEP/DXF
(`docs/audio-hardware.md` §3, `CAD/library/vendor/ReSpeakerFlex/`). Fill in **Measured**
(calipers, mm). **Slack** is how far off the value can be before the model has to change.
Anything outside it gets changed in `tools/chassis.py`, rebuilt, interference-checked, and
the study named in the last column re-run before it's accepted.

## Mic disc (circular-4)

| # | Dimension | Datasheet / STEP | Measured | Slack | In the model | Re-check |
|---|---|---|---|---|---|---|
| M1 | Board Ø | 72.5 | | ±1.0 | `MIC_D`; keel windows clear the edge by `MIC_WIN` 1.0 | S8 |
| M2 | PCB thickness (DXF also shows 1.2) | 1.5 | | −0.5 / +0.3 | `MIC_PCB_T`; window height 3.1, washer stack | S8 |
| M3 | Tallest part, component face | 1.4 | | +0.6 | `MIC_COMP_H`; 0.7 over the Pi stack top | interference |
| M4 | Tallest part within 7.6 mm of the edge, on the two sides where the keels cross (see note) | 0.6 (0402 caps) | | +0.0 | `MIC_COMP_EDGE`; the keel windows (S8 failed at 3.9 tall) | S8 |
| M5 | Mounting holes: Ø / PCD / angles | Ø3.3 / 62.5 / 0°, 120°, 240° | | PCD ±0.4 | `MIC_PCD`; M2.5 shank in Ø3.3 has 0.4 radial | interference |
| M6 | Mic port centres: square side, and angle to the holes | 44.0, 45° | | ±0.5 | `MIC_SQ`; Ø1.2 skin ports in Ø3.2 tubes, foam ring | none (port alignment) |
| M7 | Which face the ports open on (look for the holes under each mic) | logo (bare) face | | none | the bare face is up, against the tubes | none |
| M8 | FPC connector: centre (radius, angle from a hole), which face, which way the cable leaves | not in STEP | | — | not modelled yet: needs a path to the core board | interference |

Note for M4: hold the disc with one mounting hole at 12 o'clock. The keels cross the board at
3 and 9 o'clock in a band about 15 mm wide (|y| ≥ 28.6 from the centre). Measure the tallest
part in those two bands, on both faces.

## Core board

Reference: component side facing you, connector edge (USB-C, 3.5 mm jack) at the bottom,
**x measured from the end nearest the 4-pin JST**.

| # | Dimension | Datasheet / STEP | Measured | Slack | In the model | Re-check |
|---|---|---|---|---|---|---|
| C1 | Board L × W | 70.5 × 52.2 | | ±0.5 | `CORE_PCB` | interference |
| C2 | PCB thickness | 1.5 | | ±0.3 | `CORE_PCB` | interference |
| C3 | Holes: Ø, c-c L × W, edge distance | Ø3.3, 62.5 × 44.2, 4.0 | | c-c ±0.4 | `CORE_HOLES`; 3 standoffs on the deck wall | S1e |
| C4 | Tallest part, component side (header / 470 µF caps) | 9.0 | | +1.5 | `CORE_COMP_H`; 2.0 to the canopy wall, 1.16 drop sway | S1e, interference |
| C5 | Lead / part stand-off, back side | 1.6 | | +3.0 | `CORE_LEAD_H`; 5.0 standoff | interference |
| C6 | USB-C: x from–to, proud of the edge, top above the PCB | 29.5–38.4, 1.3, 4.9 | | x ±1.0 | `CORE_USB`; over the pocket for the right-angle plug | interference |
| C7 | 3.5 mm jack: x from–to, proud, top | 54.8–62.1, 2.0, 7.1 | | x ±1.0 | `CORE_JACK` | interference |
| C8 | JST PH 4-pin: x from–to | 8.6–20.6 | | ±1.0 | envelope only | — |
| C9 | Speaker JST PH 2-pin: x from–to, y from the connector edge | 11.4–17.4, 46.9–51.6 | | — | not modelled: plug + lead room toward the canopy | interference |
| C10 | FPC connector: position, latch side, cable exit | not in STEP | | — | not modelled: route to the disc | interference |

## Also wanted

| # | Dimension | Assumed | Measured | Used by |
|---|---|---|---|---|
| I1 | M2.5 × 4 insert: knurl OD, small end OD, length | knurl ~Ø4.0, length 4 (07 §4.2; pocket Ø3.6 × 5.0) | | `MIC_INS`, `CORE_INS_D`, ladder row B |
| I2 | 24-pin FPC length (as shipped) | 200 | | disc → core-board route |
