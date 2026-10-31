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

## tick 1 · T2 meshcheck · accepted · 2026-10-30 17:25
- SolidWorks busy (S1a half-mesh study still solving, 1.3 GB, one core) → took the top [py] item instead of P1.
- `tools/meshcheck.py` (+ `cad` extra in tools/pyproject.toml: trimesh, scipy, rtree): orientation, watertight, volume/grams, bed fit, overhang > 45°, min wall by inward ray-cast, convex sharp edges.
- Positive controls: 1.0 mm slab → wall 1.00, 12 sharp edges, 164.0 mm; 128-facet cylinder → only the 2 rims flagged (62.8 mm); floating cube → overhang 1.00 cm².
- First real part: Ben's `CAD/exports/TT_Motor_Mount_L.stl` → 4,708 mm³, min wall 1.0 (p1 2.45), overhang 0.23 cm² up +z (5.31 up +y), 627 mm of sharp edge. The STL is stale (SLDPRT is 6,040 mm³), so T1 (STL export per rebuild) is next for tooling.
- Next: P1 bulkhead once SolidWorks is free; T1 after.
- (tick 1, after commit) S1a half-mesh convergence finished: peak 15.8 → 18.9 MPa (+20 %, not converged: singular at the pocket edge where the load is coupled), nose displacement 2.77 → 2.79 mm (converged). S2 half-mesh: 46.0 → 41.1 MPa, holes 0.434 → 0.437 mm. Both verdicts stand (FAIL). Peaks will only settle once P2/P3 add root fillets and couple the load over the real foot footprint.

## tick 2 · P1 front bulkhead rev 1 · rejected · 2026-10-30 18:25
- Hypothesis: 3 mm PET-CF wall tilted 15°, face board behind a window, sonar + speaker side by side below, camera above, foot on the plate strip → S5 ≤ 11.7 MPa / 0.5 mm at ~40 g.
- Built clean: 32,042 mm³ vs 32,159 voxel-integrated (−0.36 %), bbox within 0.18 mm, ≈ 41 g; interferences back to the baseline 4 after trimming the side flanges to the 4.3 standoff depth (the AA-centred face PCB clipped them by 0.7 mm).
- S5 (new study: 50 N into the robot along the wall normal, held at the foot underside + its 3 insert pockets; reactions balance exactly): screen poke 45.9 MPa @foot, 15.5 mm; bezel push 37.7 MPa, 13.0 mm → FAIL by ~4× on stress and ~30× on deflection. The wall hinges about its 6.5 mm-deep foot.
- The run hung ~50 min on a solver dialog ("Excessive displacements … use Large Displacement?", owned by star.exe, not SLDWORKS); answered No via Win32 BM_CLICK after identifying it by its KB link. → T8 watchdog.
- Reverted chassis.py / fea.py / 06 per PROMPT; saved them as `patches/P1-rev1-bulkhead.patch`. Kept the engine additions (Right-plane profiles, `rotbody` Move/Copy rotation, verified by the bbox check). Baseline rebuilt: BUILD OK, 4 interferences.
- Next idea (P1b): knee gussets to the plate in the |y| < 13.4 corridor between the mount feet + a canopy-tied S5 case.

## tick 3 · T8 Simulation dialog watchdog · accepted · 2026-10-30 18:40
- Hypothesis: polling for the solver's modal dialog while swsim runs stops FEA runs hanging overnight (tick 2 lost ~50 min).
- `tools/swdialog.ps1`: EnumWindows → visible #32770 dialogs owned by star.exe / SLDWORKS → title, readable texts, buttons; with -Answer it clicks No only on the identified excessive-displacement prompt (title "Simulation" + KB link QA00000118617). `fea.py run_watched`: Popen + reader thread, poll every 20 s, unknown dialog still up after 3 polls → kill + fail loudly, 3 h cap.
- Controls: two real MessageBoxes titled "Simulation": the KB-text one was answered No (its return value says No), the other was reported only (closed afterwards with Cancel by WM_CLOSE).
- Regression: S1b through the watchdog = 2.612 MPa, equilibrium exact, identical to baseline.
- Next: P1b braced bulkhead (rotation: P after T).

## tick 4 · P1b braced bulkhead · accepted (Q13 default) · 2026-10-30 19:10
- Re-applied the rev 1 patch; behind the lower band only y 1.2…3.6 is free (sonar sleeves to y 0.8, speaker from y 4), and the face board sits above z ~47 → one central 2.4 mm knee gusset (tail x 56, top z 44) with a 10 × 9.2 × 9 pad, M3 up through a new counterbored plate hole at (61, 2.4).
- Build: bulkhead 33,889 vs 34,003 mm³ voxel (−0.34 %), plate 78,070 vs 78,104 (−0.04 %); 4 baseline interferences. ≈ 43.7 g bulkhead.
- FEA (watchdog answered the excessive-displacement prompt live at 41 s): S5 standalone screen 39.1 MPa / 8.0 mm (rev 1 45.9 / 15.5), bezel 29.1 / 6.8 → still FAIL; **S5c canopy lugs held: screen 7.0 MPa / 0.27 mm, bezel 3.2 / 0.12 → PASS**. S1a 15.5 (baseline 15.8); S1b 2.61 → 2.88 MPa (+10.1 %, the knee bolt hole; SF 12, deliberate).
- Q13 asks Ben which S5 restraint counts; default = canopy fitted (07 amended). P6 now carries the lug-stiffness requirement.
- Next: rotate to T (T1 STL export or T3 mass/CoG), then P2 motor mount v2.
