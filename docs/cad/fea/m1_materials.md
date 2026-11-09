# M1: every study in PET-CF, PA6-CF dry and PA6-CF conditioned

Tick 17 (2026-10-31). Linear statics with one uniform material: stress does not depend on E and deflection scales as E_PET-CF / E. Checked with a real run: S2 in PA6CF_COND gave 7.151 MPa (same as PET-CF) and 0.0908 mm motor holes (0.0482 × 3784 / 2006 = 0.0909). The rest are scaled from the latest PET-CF runs. Rerun any study with `python3 tools/fea.py --material PA6CF_DRY|PA6CF_COND <study>`.

| Material | E used (0.8 × XY) | Z UTS | ρ (g/cm³) |
|---|---|---|---|
| PET-CF | 3784 MPa | 35 MPa | 1.29 |
| PA6CF_DRY | 6909 MPa | 54 MPa | 1.17 |
| PA6CF_COND | 2006 MPa | 27 MPa 🟡 | 1.17 |

🟡 Wet Z UTS isn't on the TDS: scaled like XY (54.0 × 54.7 / 109.3).

| Study | σ (MPa) | SF PET-CF | SF PA6 dry | SF PA6 cond | deflection (mm) | PET-CF | PA6 dry | PA6 cond |
|---|---|---|---|---|---|---|---|---|
| S1m track tension, plate+mounts | 9.68 | 3.62 | 5.58 | **2.79** | insert URES (≤ 0.2) | **0.968** | **0.530** | **1.826** |
| S1b deck payload | 2.51 | 13.94 | 21.51 | 10.76 | deck URES | 0.032 | 0.018 | 0.061 |
| S2 mount drive (half-mesh peak) | 9.67 | 3.62 | 5.58 | **2.79** | motor-hole URES | 0.048 | 0.026 | 0.091 |
| S5c face poke, canopy on | 7.01 | 4.99 | 7.70 | 3.85 | bezel URES (≤ 0.5) | 0.266 | 0.146 | **0.502** |

Bold = fails (SF < 3, or over the 07 §3.4 limit).

| Mass (g) | PET-CF | PA6-CF |
|---|---|---|
| plate | 111.6 | 101.2 |
| bulkhead | 43.7 | 39.6 |
| mounts (2) | 27.8 | 25.2 |
| sprockets (2) | 71.8 | 65.1 |
| idlers (2) | 69.4 | 62.9 |
| **printed total** | 324.3 | 294.1 |

## Reading
- **Dry PA6-CF** is better on every count: E 1.8× (deflection ×0.55), Z strength 54 vs 35, and 9 % lighter. Even S1m's 0.97 mm becomes 0.53.
- **Conditioned PA6-CF** (indoor humidity, given time) drops E to 2.0 GPa: every deflection ×1.9 against PET-CF, S1m 1.83 mm, and S5c 0.50 mm right on its limit. SF falls to 2.8 on S1m and S2 (on the assumed wet Z).
- S2's 9.67 is the singular half-mesh peak (D9); on the converged 7.15 MPa conditioned PA6-CF still has SF 3.78.
- So the choice turns on moisture: PET-CF for parts judged on stiffness (plate, bulkhead); PA6-CF only where toughness matters more than stiffness and the wet case still passes (mounts once D9 lands, small parts a child drops). That is M2's decision; no part changes material in M1.
