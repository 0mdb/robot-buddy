# Battery Pack Assembly Procedure — 3S4P 21700 (robot-buddy)

**Pack:** 12 × 21700 Li-ion, wired **3S4P** · 11.1 V nominal · **12.6 V full** · ~9.0 V empty
**Holder:** `Inline+2S6P+Halterung+LiPo+21700+FINAL_v2.stl` (ASA, 46 × 137 × 8.9 mm)
**BMS:** Daly 3S Li-ion, 100 A, with NTC
**Charger required:** 12.6 V CC/CV Li-ion charger (do **not** use a LiFePO4 or lead-acid charger)

> ⚠️ These are lithium-ion cells. A shorted tool or a reversed cell can start a fire. Work with insulated tools, remove rings/watch, keep a Li-ion–rated extinguisher or a bucket of sand nearby, and never leave the first charge unattended.

---

## 1. Bill of materials

- 12 × 21700 Li-ion cells, **matched** (same model, same state of charge — see Step 3)
- 1× (or 2×, see note) printed ASA holder
- Nickel strip (pure nickel, sized for current — see Step 5) **or** copper bus bar
- Daly 3S 100 A BMS with balance lead (4-wire: B0…B3) and NTC probe
- Main fuse on the pack positive (size to your load, below the 100 A BMS limit)
- 12.6 V CC/CV charger
- Heat-shrink, fish paper / insulating barrier for the pack ends, kapton tape
- Wire: main leads sized for your current (e.g., 10–12 AWG for tens of amps)

**Tools:** spot welder (strongly preferred over soldering), multimeter, insulated tools, calipers.

> **Two-holder note:** the holder grips only the ~9 mm mid-body, so cells cantilever ~30 mm each side. The end bus-bars/nickel add most of the rigidity, but for a stiffer pack print a **second holder** and space the two along the cell length. At minimum, keep the single holder centered.

---

## 2. Verify the printed holder

1. Confirm cells insert with a light push and the three nubs hold them without force. Target: ~0.1 mm nub grip, ~0.4 mm clearance to the wall for swelling.
2. If tight in ASA, re-slice with horizontal expansion **−0.1 mm** rather than reprinting a new model.
3. Dry-fit all 12 before doing any welding.

---

## 3. Match and prep the cells (do not skip)

1. Measure every cell's voltage. **Parallel cells must be within ~0.05 V of each other before joining** — a bigger gap dumps a large inrush current through the nickel when you connect them.
2. Easiest: charge/discharge all 12 to the **same** voltage (e.g., storage ~3.7 V) individually or on a balance charger, then proceed.
3. Check each cell for physical damage, and confirm the wrap and insulator ring at the positive end are intact (nicked wrap = short risk).

---

## 4. Set cell orientation (3S4P) — CRITICAL

The 12 cells form **three parallel groups of four**, wired in series. Group by row-pairs and **flip the middle group** so the series links are short. Insert cells terminal-up as follows:

| Group | Rows | Terminal facing UP |
|-------|------|--------------------|
| **A** | 1–2  | **+** (positive up) |
| **B** | 3–4  | **–** (negative up, flipped) |
| **C** | 5–6  | **+** (positive up) |

All four cells in a group face the **same** way. Double-check every cell's polarity with the multimeter before welding — a single reversed cell will short its parallel group.

---

## 5. Weld the parallel groups (4P)

1. Size the nickel to the current: a single 0.15 mm strip carries only ~5–7 A. For a high-current pack, use wide/thick pure nickel, multiple parallel strips, or copper bus bar. Your 100 A BMS implies serious current — plan the conductor accordingly.
2. For **each** group (A, B, C), weld one strip joining all four **positive** terminals and another joining all four **negative** terminals. You now have three independent 4P blocks.
3. Spot-weld, don't solder, directly to cells where possible — soldering heat degrades the cell. If you must solder, be fast.

---

## 6. Series links (A → B → C)

With the alternating orientation, each series link is a short bridge on one face:

1. **A– to B+** — both sit on the **bottom** face (A is +up so its bottom is –; B is flipped so its bottom is +). Bridge them with nickel/bus bar.
2. **B– to C+** — both on the **top** face. Bridge them.
3. Pack **positive** = **A top** (the +). Pack **negative** = **C bottom** (the –).

After this the pack should read ~11.1 V (storage-charged) across pack + and pack –, and the three series nodes should step up evenly.

---

## 7. Insulate

Lay fish paper / insulating barrier over both pack ends before adding the BMS, so nothing can bridge a bus bar. Verify no strand or strip is near an adjacent group's opposite polarity.

---

## 8. Wire the Daly BMS

**Wire the balance leads FIRST, main B– LAST, and measure at each step.** The balance connector has 4 wires labelled B0 (most negative) → B3 (most positive):

1. **B0** → pack **negative** (C group –, the most-negative point)
2. **B1** → first series node (**C↔B** junction)
3. **B2** → second series node (**B↔A** junction)
4. **B3** → pack **positive** (A group +, the most-positive point)

As you seat each wire, measure B0→B1, B1→B2, B2→B3 — each should read one cell's voltage (~3.6–3.8 V). Any gap that reads ~0 V or double means a mis-tap; fix before continuing.

Then the power and sense connections:

5. **NTC** probe → tape to the body of a central cell (the one that'll run hottest).
6. **B–** (main) → pack **negative** (same point as B0).
7. **+ / B+** → pack **positive**.
8. **P–** → this is the switched output; your **load and charger negative** both connect here.
9. Add the **main fuse** in the pack positive lead.

Load/charger positive → pack **+ (B+)**. Load/charger negative → **P–**. The BMS sits in the negative path and cuts P– on fault.

---

## 9. Commissioning / first power-up

1. With nothing loaded, measure **P– to B+**: should read pack voltage once the BMS wakes (some Daly units need a momentary charger touch to turn on the output).
2. Confirm the BMS reports/holds: no fault LED, output present.
3. **First charge** on the 12.6 V CC/CV charger, **attended**. Watch that it terminates at 12.6 V and that the three groups converge (the BMS balances near top-of-charge). Feel for any hot cell.
4. Draw a modest load and confirm current flows and cuts on the BMS limits. Verify the over-temp (NTC) and low-voltage cutoffs behave.

---

## 10. Nano / power-board integration

- Your power board already measures **pack voltage** and feeds the Nano — that stays your primary telemetry.
- The BMS handles **protection and balancing autonomously**; it does not need the Nano to function. Keep them independent — the BMS is your safety layer, the Nano is monitoring/logic.
- **Optional, only if this is the Smart/UART board:** the Nano can read per-cell voltages, current, temperature and SOC from the BMS UART (TX/RX/GND, 9600 baud, Daly protocol). This *adds* per-cell visibility on top of the pack voltage you already have. If the board is protection-only (no UART port), skip it — you're not losing safety, only the extra per-cell readout.
- Do **not** route protection decisions through the Nano. If you ever want an MCU-controlled cutoff, it should be *in addition to* the BMS, never instead of it.

---

## Quick reference

- Pack: 3S4P · 12.6 V full · 11.1 V nom · charge with 12.6 V CC/CV only
- Orientation: A(+up) / B(–up) / C(+up), rows 1-2 / 3-4 / 5-6
- Balance: B0=pack–, B1=C↔B, B2=B↔A, B3=pack+
- Power: B–=pack–, +=pack+, P–=load/charger–, fuse on pack+
- NTC on a central cell; first charge attended
