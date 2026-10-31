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

**Fillets (T7):** the generator can now round chosen edges, with volume checks. Its first use on the motor mounts made the stress worse and was reverted; a hot-spot locator (T9) will aim the next ones.

**TPU track system (P11, done):** sprocket and idler are native SolidWorks parts generated from drivetrain.py's own geometry (volumes match to 0.1 mm³), placed with belt envelopes; the assembly has 0 interferences. Renders: `shots/1-P11/`.

**Hot spots (T9):** FEA now says *where* each peak is. The motor mount's peak is a knife edge where the lower motor-screw insert hole breaks out through the root chamfer (fix queued as D7).

**P12 (done):** FEA loads now sit on the TPU belt's centre line; the plate is full width again at the rear (+4.6 g, slightly stiffer, and it gives the follower carriage room at the plate edge). The motor mount's lever arm grew ~7 % with the 36 mm belt, not halved.

**Motor mount stress, converged (D7):** with the knife edge removed, S2 converges for the first time: 11.95 MPa at the finest mesh, SF 2.93 (2 % short of 3). The last notch is the same insert hole nicking a gusset root (D8).

**Plate test made realistic (T10):** the plate is now analysed with the motor mounts bonded on. The fake pocket peak is gone; the real issue is bending: under 20 N track tension the motor axles move ~0.9 mm back and 1.2 mm up relative to the rear followers (target 0.2). Rails along the sides at axle height (P3) are the fix this points to.

**Plate ribs (P3):** four 2.4 × 4 mm ribs under the plate along the track-tension line (+6.3 g, no ground clearance lost). The plate test now passes on strength (SF 3.6, was 2.6), and axle motion dropped 37 % to ~1 mm, still over the 0.2 mm limit. **Q17** asks whether to judge that limit on the drive-torque increment (~0.18 mm, passes) or build an outboard track frame.

**Motor mount (D8):** gusset 3 moved 2 mm clear of the insert pocket; the mount drive test (S2) is now SF 3.6 (was 2.9), a pass. One sharp inside corner left to round (D9).

**Mass (T3):** every build now prints part masses: printed parts so far 324.5 g (plate 111.6, bulkhead 43.7, sprockets + idlers 141, mounts 27.8).

**Materials (M1):** every study now runs in PA6-CF too (`docs/cad/fea/m1_materials.md`). Dry PA6-CF beats PET-CF everywhere (9 % lighter, 1.8× stiffer); after it soaks up room humidity it is about half as stiff as PET-CF, so the plate and bulkhead stay PET-CF unless you keep PA6 parts dry.

**Kid safety (S1):** an edge audit tool now lists every sharp edge a child can reach (`docs/cad/loop/S1_edge_audit.md`). Nothing is rounded yet: plate 4.5 m, bulkhead 1.6 m, wheels 0.2 m each. Fixes are queued per part (S1a–c).

*(D9, a short chamfer at the mount root, was tried and rejected: it added corners. D10 queues the proper fix.)*

**Next:** S1a / P4, D10, then P2o (plate + FEA for the new track), then P2 motor mount v2 (outboard axle support, Q4 default), P3 plate stiffening.

**Open questions:** Q4–Q12 in `QUESTIONS.md`, each with a default the loop is using.
