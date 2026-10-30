# CAD loop journal

Newest at the bottom. One entry per tick.


## tick 0 · preflight · 2026-10-30 17:05
- Baseline = `cad` after plate rev 1 + FEA tooling (`tools/fea.py`, `tools/swsim.cs` ported from fpv250: native part, position-filtered faces, remote loads, reaction-sum equilibrium check, UX/UY/UZ/URES readback).
- Tooling facts learned: `AddForce2(…, 0, …)` applies the value to EACH face (reaction = n × value) → swsim splits totals; `CreateMesh` units 0 = mm; displacement units 0 = mm, stress Pa; reactions are per node, stride 9; blind cuts need Dir=true; a cut tangent to an edge fails.
- FEA baseline (PET-CF, 0.8·E_xy, allowable 35/3 = 11.7 MPa, TRACK_T 20 N TBD → 49.2 N per axle):
  S1a plate/tension 15.8 MPa (upper bound: load coupled to the 4 pockets only), axle UX 0.22 mm, nose UZ 1.4–2.8 → FAIL.
  S1b plate/deck 25.5 N: 2.6 MPa, 0.04 mm → PASS.
  S2 mount/pull 49.2 N at gear centre: 46.0 MPa @2 mm… 41.1 MPa @0.5 mm (singular unfilleted root), holes 0.43 mm → FAIL ×3.5.
  S5 not run (no bulkhead).
- Plate 78,195 mm³ ≈ 100.9 g PET-CF solid; Ben's motor mounts 6.04 cm³ ≈ 7.8 g each. 4 interferences (motor envelope widths 🟡).
- Ben 2026-10-30: design the bulkhead and every missing part → workstream P added and leads pass 1. Questions Q4–Q12 written with defaults.
- S1a half-mesh convergence run was still meshing at handover; tick 1 records it.
