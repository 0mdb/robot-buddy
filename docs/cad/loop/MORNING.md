# Morning report

_Pass 1 starting (2026-10-30 17:05). Rewritten every tick._

**Print-ready:** nothing yet. The plate is modelled but fails S1a, and the motor mounts fail S2.

**Baseline FEA** (PET-CF, allowable 11.7 MPa, track tension assumed 20 N):
| Study | Peak | Deflection | Verdict |
|---|---|---|---|
| S1a plate, track tension | 15.8 MPa (upper bound) | axle 0.22 mm, nose lifts 1.4–2.8 mm | FAIL |
| S1b plate, deck payload | 2.6 MPa | 0.04 mm | PASS |
| S2 motor mount v2, pull + torque | 12–14 MPa (singular, not converged) | 0.039 mm | deflection PASS; SF after fillets (T7) |
| S5c bulkhead rev 2, screen poke, canopy fitted | 7.0 MPa | 0.27 mm | PASS (standalone 39 MPa / 8 mm: Q13) |

**Tooling so far:** `tools/meshcheck.py` (T2) measures overhang, min wall and sharp edges from an STL; validated on test shapes. FEA runs now have a watchdog (T8) that answers the solver's "excessive displacement" pop-up, so the loop can't hang on it overnight. Every rebuild now exports STLs of the printed parts to `CAD/exports/gen/` (T1); meshcheck on them flags the plate's underside as 158 cm² of unsupported overhang in its planned print orientation, which D3 has to solve.

**Bulkhead rev 2 (accepted, P1b):** 43.7 g PET-CF, face board behind a window, sonar + speaker grille + camera hole, one knee gusset bolted to the plate. Passes the screen poke with the canopy fitted; alone it still flexes 8 mm (Q13). Renders in `shots/1-P1b/`. Not print-ready: square edges (needs T7), sonar tilted 15° up.

**Motor mount v2 (accepted, P2):** generated, 6 mm upright with gussets, ~14 g each; deflection 11× better than the original and all assembly interferences gone (motor raised 2 mm). Stress peaks sit at sharp corners and won't settle until the parts have fillets (T7, now top priority). The outboard axle support waits on a drive-gear measurement.

**Next:** T7 fillets, then P2 motor mount v2 (outboard axle support, Q4 default), P3 plate stiffening.

**Open questions:** Q4–Q12 in `QUESTIONS.md`, each with a default the loop is using.
