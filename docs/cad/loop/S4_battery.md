# S4 battery access and drop path (tick 35, 2026-10-31)

**Cells:** 2 × 18650 Li-ion in the Waveshare UPS HAT (B), the top layer of the Pi stack: deck top z 27, stack top z 80 (53 mm stack + 6 mm standoffs, 06 §3), footprint x −64.5…22.5, |y| ≤ 28. Canopy inside top ~93 (06 §3), so **13 mm** over the cells.

## Findings

| # | Topic | Status | Requirement / action |
|---|---|---|---|
| 1 | **Tool-only access** | ✓ the only way to the cells is lifting the canopy, held by 4 × M3 button heads that take a 2.0 key (A2: deliberately not the 2.5 everything else uses) | keep the canopy screws on the rear and underside faces (E1) |
| 2 | **Charging without opening** | ✓ planned: canopy cut-outs for the HAT's USB-C and power switch (06 §6) | cut-out edges r 3 (E1), no finger gap reaching the HAT's pins: opening ≤ 12 × 8 mm, set back ≥ 3 mm from any live pad |
| 3 | **Cells stay captive in a tumble** | ⚠️ the HAT holds the cells in spring clips; a drop onto the top can pop one out | **P6:** a TPU pad or two ribs on the canopy's underside sitting 1–2 mm above the cells, so a cell can't leave its clip with the canopy on |
| 4 | **Crush path (stepped on, dropped on its top)** | ⚠️ not checked: 13 mm over the cells under a 1.8 mm shell | **P6:** load path from the canopy top to the frame, not to the cells: the canopy's crown ribs land on the bulkhead lugs at the front and the 2 rear plate bosses at the back; **new FEA case S7** (canopy, 300 N on a Ø 30 heel pad at the worst point): deflection < 10 mm (keeps 3 mm off the cells), SF ≥ 3 in PC/ASA |
| 5 | **No puncture hazards** | ✓ nothing sharp points at the cells today | P6: no screw tips, bosses or ribs ending within 5 mm of the cells; insert bosses face away |
| 6 | **Heat** | ⚠️ the cells sit over the Pi 5 (HAT on top) | S5 (vent path over the stack; canopy vent field per E1); keep the cells out of the Pi's exhaust if the vent order allows |
| 7 | **Cell choice** | doc | use name-brand protected or flat-top cells the HAT is rated for, matched pair; no unknown-brand cells in a child's toy |
| 8 | **Shock to the stack** | ✓ S1b/S1d cover 10 g on the stack (plate 3.6 MPa, deck 8.9 MPa / 0.19 mm) | — |

The battery is safe in the frame as built. Items 3–5 become canopy requirements, since the canopy is what a child's hand, foot or a fall actually meets.
