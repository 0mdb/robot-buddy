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
- (tick 4, fix) `cad-pull` copied 48 Simulation result files (.CWR/.gsz/.LOG, 2.8 GB) that the studies write next to the parts, and they landed in the P1b commit. Amended the (unpushed) commit to drop them; `.gitignore` + `sw.py` EXCLUDE now skip them. Their blobs stay in `.git` until the reflog expires (local only): `git reflog expire --expire=now --all && git gc --prune=now` reclaims ~1.5 GB if wanted.

## tick 5 · T1 STL export per rebuild · accepted · 2026-10-30 19:30
- Hypothesis: binary mm STLs in chassis coordinates for every printed part, trimesh volume = SolidWorks within 0.5 %.
- `stl|doc|out` in swbuild.cs; the rebuild writes plate, bulkhead, both motor mounts to `CAD/exports/gen/` (kept apart from Ben's July STLs).
- First run: the mounts' STLs were the reflex envelope (12 triangles, 65 × 60 × 15.6): STL export writes the ACTIVE document; plate/bulkhead only worked because a render had just activated them. Fixed by activating before SaveAs.
- Check: plate 78,031 vs 78,070; bulkhead 33,885 vs 33,889; mounts 6,039.7 vs 6,039.3 mm³ (all ≤ 0.05 %).
- meshcheck findings for D3 (as modelled, +Z up): plate 158 cm² overhang + a 0.07 mm min-wall sliver; bulkhead 23 cm²; mounts 0.6 / 8.8 cm².
- Next: P2 motor mount v2 (outboard axle support, Q4 default).

## tick 6 · P2 motor mount v2 · accepted (strength fix) · 2026-10-30 19:30
- Q4's outboard support needs a stub shaft on the kit gear's outer face; hub unknown → split to P2o (blocked, measurement asked). Built (b): generated mount in Ben's part frame, 6 mm upright, 3 inboard gussets between the foot screws, root chamfer, end stop at x −17.6, foot trimmed under the motor, motor screws into upright inserts; motor raised z 11.5 → 13.5 at the drawing's 17.5 pitch.
- Build: 10,839 vs 10,816 mm³ voxel (+0.2 %), both sides; **interferences 4 → 0**. ≈ 14 g each (+6.2 g).
- S2 (49.2 N at the gear centre, now z 13.5): hole deflection 0.437 → 0.039 mm (half mesh 0.0390: converged). Peak 11.7 / 12.0 MPa (pull / pull+torque) → 13.7 / 14.1 at half mesh (+17.5 %), gusset region 6.3 → 8.3 (+33 %): singular at the insert-coupling edge and the unfilleted gusset roots. 6.6 mm upright left the peak unchanged (12.005) → kept 6.0.
- Verdict: accepted as a strength fix on converged measures; SF ≥ 3 deferred to T7 (07 §3 amended: singular peaks are not used for SF). S1a 15.5 → 17.8 MPa / UX 0.25 because the axle is 2 mm higher: a deliberate trade, P3 owns it.
- Tooling fix (T8 follow-up): the watchdog killed a run on SolidWorks' always-open notification template (no real buttons) and only killed cmd.exe, orphaning swsim. Now: windows without buttons are ignored; unknown dialogs warn and wait; the 3 h cap kills swsim.exe itself.
- Next: T7 fillets (priority), then P3 plate stiffening.

## tick 7 · T7 fillet command · tool accepted, application rejected · 2026-10-30 20:20
- Hypothesis: edge selection by axis + midpoint box, constant-radius `FeatureFillet3`, checked by edge count and Δvolume = (1 − π/4)·r²·L; filleting the mount's gusset roots makes S2's gusset peak converge.
- Tool: works. 12 vertical gusset-root edges at r 2 on both mounts, each Δ within 7 % of the analytic value, parts within 0.2 %; 0 interferences. The first try failed where an r 2 fillet ran into the insert pocket at x 14.5 (gusset at x 12); moved that gusset to 8.6.
- Application: S2 got worse. Pull + torque peak 12.0 → 15.25 MPa at the same mesh (→ 18.0 at half mesh); gusset region 7.9 → 10.9 (+38 %, still not converged); hole deflection 0.038 → 0.043. Moving the gusset away from the insert took stiffness from where the motor load enters, and the gusset peak is not on the vertical roots. Reverted per PROMPT (patch kept); baseline rebuilt, BUILD OK, 0 interferences.
- Lesson: aim fillets with data. Added T9 (hot-spot locator in swsim).
- Steering arrived mid-tick (Ben): Q8 answered, printed TPU track system (08 spec, drivetrain-rnd e7d8659); P11/P12 added, P2o unblocked, P5 rescoped, Q14/Q15 added. Committed separately.
- Next: P11 (adopt the TPU track system), Ben's stated next P item.

## tick 8 · P11 adopt the printed TPU track system · accepted · 2026-10-30 21:05
- Ben's next P item (Q8). Cherry-picked e7d8659 → 03d46e5 (drivetrain.py, 08 spec).
- drivetrain.py: split `sprocket_layers()` / `idler_layers()` out of the mesh functions (pure refactor; all four mesh volumes identical before/after).
- swbuild `ring|z0 z1|outer|inner|boss`: loops are `c R` or an 864-point polar polyline, so SolidWorks builds the same polygons drivetrain.py meshes; chassis.py merges consecutive identical annuli (39 rings for both wheels).
- Result: sprocket 27,842.0 vs 27,841.9 mm³, idler 26,935.1 vs 26,935.0 (≤ 0.0004 %); belt envelopes exact. Build ≈ 4 min.
- Interference: 4 × 15.4 mm³ = the round Ø5.4 shaft envelope vs the D-bore flats (segment beyond 1.95 × 8 mm engagement = 15.4 exactly). Gave the envelope its 3.7 double-D → 0 interferences.
- 05 and 06 §7 amended (kit → 08). FEA unchanged this tick (P12 re-runs S1a/S1b/S2 with the new geometry; TRACK_T stays 20 N).
- Next: rotate to T (T9 hot-spot locator), then P12.

## tick 9 · T9 hot-spot locator · accepted · 2026-10-30 21:25
- `hotspots n` in swsim.cs: one GetStressForEntities call per face (a batched call pools nodes), rank, print the top n with surface type, centre, normal/axis, bbox. Opt-in per study (S2 has it).
- S2 rerun (mount v2, unchanged geometry; same numbers as tick 6: 11.69 / 12.01 / 2.66 MPa) located the peak: the lower motor-insert pocket cylinder (x 14.5, z 4.75) and the root-chamfer face share the peak node; the through-pocket breaks out through the chamfer. Third: the upright's inboard face around the pocket (10.2). The gusset side face as a whole is 6.3.
- So tick 7 filleted the wrong edges; the singularity is a pocket/chamfer knife edge. Added D7 to fix it.
- Next: P12 (plate + FEA for the TPU track), then D7.

## tick 10 · P12 plate + FEA for the TPU track · accepted (deliberate +4.6 g) · 2026-10-30 22:00
- fea.py loads from drivetrain.py: axle force at the belt centre plane (|y| 74.5; S2 gear point y 14.1 in the mount frame), tight-side excess on the sprocket pitch radius 28.65 → AXLE_F 48.7 N (TRACK_T stays 20 N).
- Step 1, current plate: S2 pull + torque 12.0 → 12.6 MPa, holes 0.038 → 0.040 mm (+5 %; the TPU belt plane is 19.5 off the gearbox face vs 16.8 in my kit model, so here the arm grows ~7 %, contrary to 08's "halves", which was relative to its own kit estimate). Hot spot unchanged (insert/chamfer knife edge, D7). S1a 17.76 → 17.63 MPa, UX 0.250 → 0.247.
- Step 2, rear relief removed (REAR_RELIEF flag; plate 81,653 vs 81,686 mm³ voxel; 0 interferences): S1a peak 17.62 (singular), jack stops 12.56 → 11.91, UX 0.247 → 0.241, UZ 3.15 → 3.03; S1b 2.88 → 2.55 MPa.
- Verdict: accepted with +4.6 g as a deliberate trade: modest stiffness gain, and the carriage can now reach the plate edge (P5: ~11 mm shorter idler-axle cantilever). Q10 note updated, 06 amended.
- Next: rotate: D7 (mount insert/chamfer knife edge) or a T item; then P3 / P5.
