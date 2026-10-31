# Morning report

_Pass 1 starting (2026-10-30 17:05). Rewritten every tick._

**Print-ready:** nothing yet. The plate is modelled but fails S1a, and the motor mounts fail S2.

**Baseline FEA** (PET-CF, allowable 11.7 MPa, track tension assumed 20 N):
| Study | Peak | Deflection | Verdict |
|---|---|---|---|
| S1a plate, track tension | 15.8 MPa (upper bound) | axle 0.22 mm, nose lifts 1.4–2.8 mm | FAIL |
| S1b plate, deck payload | 2.6 MPa | 0.04 mm | PASS |
| S2 motor mount, pull | 41–46 MPa | 0.43 mm | FAIL ×3.5 |
| S5c bulkhead rev 2, screen poke, canopy fitted | 7.0 MPa | 0.27 mm | PASS (standalone 39 MPa / 8 mm: Q13) |

**Tooling so far:** `tools/meshcheck.py` (T2) measures overhang, min wall and sharp edges from an STL; validated on test shapes. FEA runs now have a watchdog (T8) that answers the solver's "excessive displacement" pop-up, so the loop can't hang on it overnight.

**Bulkhead rev 2 (accepted, P1b):** 43.7 g PET-CF, face board behind a window, sonar + speaker grille + camera hole, one knee gusset bolted to the plate. Passes the screen poke with the canopy fitted; alone it still flexes 8 mm (Q13). Renders in `shots/1-P1b/`. Not print-ready: square edges (needs T7), sonar tilted 15° up.

**Next:** a tooling item (T1/T3), then P2 motor mount v2 (outboard axle support, Q4 default), P3 plate stiffening.

**Open questions:** Q4–Q12 in `QUESTIONS.md`, each with a default the loop is using.
