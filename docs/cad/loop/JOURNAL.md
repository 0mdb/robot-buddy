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

## tick 11 · D7 mount insert/chamfer knife edge · accepted · 2026-10-30 22:45
- Hypothesis: end the root chamfer 1 mm short of the lower insert pocket so the through-pocket exits on a flat face; the peak drops and converges.
- Build: 10,796 vs 10,771.5 mm³ (+0.2 %), both sides; 0 interferences.
- S2 pull + torque: 12.6 (tick 10, singular) → 11.38 MPa default mesh, 11.95 at half mesh (+5.0 %: converged, first converged S2 peak); deflection 0.0431 / 0.0432 mm. SF = 35 / 11.95 = 2.93.
- Hot spots: (1) the pocket cylinder, (2) gusset 3's side face at x 13.2: the through-pocket (x 12.5–16.5) cuts 0.7 mm into that gusset's root. Last intersection → D8.
- Accepted: removes the singularity and is ~10 % better, with nothing worse; SF 2.93 recorded as is, not rounded to a pass.
- Next: rotate away from D: T or M/S, then D8.

## tick 12 · P3 step 1 (footprint coupling via split lines) · rejected (tooling) · 2026-10-30 23:15
- Hypothesis: S1a's 17.6 MPa pocket peak is a coupling artefact; spreading the axle load over each mount foot's footprint (split lines on the plate top) would show the plate's real weak point before choosing rails vs ribs.
- Built a `split` engine command. `FeatureManager.InsertSplitLineProject` doesn't exist in this interop (compile error); `IModelDoc2.InsertSplitLineProject(bool, bool)` returns void and created nothing in three variants: coplanar sketch on Front; sketch on a +1 mm reference plane; face picked by SelectByID2 and as an entity (both selections reported true). Face count stayed 254 each time.
- Reverted per PROMPT (patch kept), baseline rebuilt: BUILD OK, 0 interferences. No CAD change committed.
- Better route: T10, a multi-body S1a (plate + both mount bodies bonded), which needs no split lines and models the foot bearing directly.
- Next: rotate (not D/P twice more): T10, then P3 geometry with hotspots.

## tick 13 · T10 multi-body S1a (S1m) · accepted · 2026-10-30 23:55
- Plate + both mount v2 bodies merged into one PET-CF body (= bonded) in an analysis-only part, `CAD/fea/FEA-plate_mounts.SLDPRT`: 103,386 vs 103,229 mm³ (plate + 2 × mount, +0.15 %). No InsertPart3 needed.
- S1m: remote axle load (48.7 N per side at the belt centre) into each mount's motor face + two inserts; held at the jack bores; 403 k nodes; equilibrium exact. Caught a sign bug in a dry run first: the left load selected the right mount's face.
- Results: the pocket artefact is gone (plate top 11.3 MPa vs S1a's 17.6); peak 13.3 / 12.6 MPa on the jack-stop blocks' root faces (fixture-adjacent, unfilleted); motor inserts UX −0.16…−0.91 mm, UZ +1.13…+1.27 mm. The mounts' eccentric moment bends the plate between mounts and jack stops, 4× what pocket-coupled S1a showed.
- 07 gets S1m as the verdict study for P3. Evidence points to P3 (a): rails at axle height from the mount feet to the jack stops.
- Next: P3 (a) side rails, judged on S1m.

## tick 14 · P3 (b) load-path ribs · accepted (strength fix, +6.3 g) · 2026-10-31 00:40
- (a) rails at axle height don't fit: the reflex board edge (|y| 30) and the encoder (|y| 30.7, z 1) leave 0.7 mm between the jack stops and the mount feet. Beam check: S1m's motion is whole-plate XZ bending from the 15.5 mm load offset (EI 782 mm⁴ gives ~1.1 mm, matching the FEA). 0.2 mm would need ~6× EI.
- Change: `LOAD_RIBS`, two ribs per side 2.4 × 4.0 under the plate at |y| 36.5 (x −42…72) and 47 (x −78…70), bottom at −8 (same as the insert bosses, so no clearance loss). Plate 81,595 → 86,489 mm³ (numeric), BUILD OK, 0 interferences.
- S1m: peak 13.33 → 9.68 MPa (SF 2.63 → 3.62, passes); inserts UX −0.91 → −0.59, UZ 1.27 → 0.79, URES 1.54 → 0.97 mm. S1b 2.55 → 2.51 MPa. Equilibrium exact.
- Verdict: accepted as a strength fix (stress gate now passes). Deflection still 5× over → Q17 (judge on the drive increment ≈ 0.18 mm; or an outboard track frame folded into P2o).
- Next: rotate off P: T/M/S/W item, or D8.

## tick 15 · D8 gusset 3 off the insert pocket · accepted · 2026-10-31 01:30
- Hypothesis: the through-pocket (x 12.5–16.5) nicking gusset 3's root (x 10.8–13.2) set S2's 11.95 MPa peak; gusset 3 → x 10.0 leaves 1.3 mm.
- Build OK, 0 interferences, mass ≈ unchanged.
- S2 pull + torque: default 11.38 → 7.15 MPa; half mesh 11.95 → 9.67 (+35 %). The new peak is singular: the sharp inboard root corner (upright y −34 / foot top z 3) between the chamfer end (x 11.5) and the upright end (x 20). The pocket drops out of the half-mesh top 5. Motor holes 0.0432 → 0.0483 mm (+12 %).
- Verdict: accepted. SF ≥ 35 / 9.67 = 3.62 even on the singular peak (was 2.93); the +12 % deflection is a deliberate trade, 0.05 mm being far inside 07 §3.4. Next for that corner: D9 (fillet or short chamfer x 11.5–20).
- Next: rotate: T3 (mass/CoG line) or M1.

## tick 16 · T3 per-part mass / CoG line · accepted · 2026-10-31 01:55
- Engine: `SavePart` prints `MASS|<file>|<vol mm³>|<com mm>`. chassis.py: `PART_MATERIAL` + `RHO` → grams; the printed-part total and CoG come from the `comp|` transforms in the manifest. Checked on dummy lines first, then a live rebuild (BUILD OK, 0 interferences, geometry unchanged).
- Reading: plate 111.6 g, bulkhead 43.7, mounts 13.9 each, sprockets 35.9 each, idlers 34.7 each → 324.5 g printed, CoG (12.8, −0.1, 13.8) mm; the hand sum agrees.
- Housekeeping: 34 Simulation `*-BenchMark-Solver.txt` logs had been committed under CAD/parts; untracked (files kept), gitignored, added to sw.py EXCLUDE.
- Next: rotate: M1 (PA6-CF in fea.py) or S1 edge audit; D9 after.

## tick 17 · M1 PA6-CF in fea.py · accepted · 2026-10-31 02:30
- Added PA6CF_DRY (E 0.8 × 8636, Z 54, ρ 1.17) and PA6CF_COND (E 0.8 × 2508, Z 27 🟡 scaled like XY) from the Fiberon TDS fpv250 uses; `--material` flag; output dirs get a `_<material>` suffix.
- Instead of eight more runs: one material, linear, so σ is independent of E and δ ∝ 1/E. Checked on S2 in PA6CF_COND: 7.151 MPa (same), motor holes 0.0908 mm vs 0.0909 predicted.
- Table in `docs/cad/fea/m1_materials.md`: dry PA6-CF −9 % mass, δ ×0.55, SF ×1.54 on everything; conditioned PA6-CF δ ×1.89 (S1m 1.83 mm, S5c 0.502 vs 0.5) and SF 2.79 on the S1m / S2 peaks (S2 converged: 3.78).
- No part changes material: that is M2 (doc, needs the moisture call).
- Next: rotate: S1 edge audit (kid safety), then D9.

## tick 18 · S1 accessible-edge audit · accepted · 2026-10-31 02:50
- New `tools/edgeaudit.py`: meshcheck's sharp-edge test (convex, > 30°) on the generated STLs, filtered per part by where a hand reaches with the canopy on (plate perimeter + belly; bulkhead face side + outer sides; wheel outboard faces; mounts covered). Output: `docs/cad/loop/S1_edge_audit.md`.
- Finding: no generated part has a fillet yet. Accessible sharp edges: plate 4.5 m, bulkhead 1.6 m, sprocket / idler 0.21 m each, mounts 0 (0.8 m covered).
- Split the fixes into S1a (plate), S1b (bulkhead), S1c (wheels via drivetrain.py). No geometry change this tick.
- Next: rotate: D9 (mount root corner), then S1a.

## tick 19 · D9 stub root chamfer · rejected · 2026-10-31 00:35
- Hypothesis: chamfering the bare root corner x 17.5–20 (past the insert pocket) removes S2's singular half-mesh peak (9.67).
- Result: worse. S2 default 7.15 → 9.54 MPa, half mesh 9.67 → 10.61 (+11 %, still singular); holes 0.0482 → 0.0457 mm. The peak moved onto the 2.5 mm stub's own top edge and end faces.
- Reverted (patch kept), baseline rebuilt: BUILD OK, 0 interferences, mount 10,785.1 mm³ = D8.
- Lesson: short chamfer segments add corners. The pocket has to stop crossing the root first → D10 (blind pocket in a local boss, then a full-length chamfer or fillet).
- Next: rotate off D: S1a or P4.

## tick 20 · P4 Pi deck · accepted · 2026-10-31 01:10
- New part `RB-PRT-003_pi_deck` (PET-CF): 3 mm on the four posts, z 24–27; wide part x −66…25 × |y| ≤ 29.5 (0.7 mm inside the encoders would be too tight, so 1.2), tongue to x 36 × |y| ≤ 14 for the front posts, clear of the mount uprights. M3 clearance at the posts, M2.5 at the Pi holes, 5 vent slots, rear and front cable cut-outs.
- Took four builds: three failed at "prof … all feature null" and I blamed the sketch plane / cut direction (moved the deck to its own frame, then flipped it). Building the part alone showed every cut passed except the last: the front cable slot's end was tangent to the tongue's front edge. Ended it 1 mm short → BUILD OK, 12,981.5 vs 12,981.4 mm³. The deck keeps its own frame (top at z 0, placed at z 27); harmless. Lesson: build a failing part alone and read every line before theorising.
- Full rebuild: 0 interferences; printed parts 341.3 g, CoG (11.4, −0.1, 14.4).
- S1d (new): deck held at the post holes, 25.5 N via the M2.5 holes: 6.30 MPa (SF 5.6), Pi holes 0.10 mm (limit 0.5); equilibrium exact.
- Next: rotate: S1a (plate edges) or W/A items; D10 after.

## tick 21 · S1a plate outline edges r 1.0 · accepted · 2026-10-31 01:30
- `fillet` only takes straight edges by axis/box; the outline has arcs. New engine command `filletface|r|nz|z|box|n|dvol tol`: outer loop of each matching planar face. The belly (z −4) is 11 faces (the rib grid makes closed cells), so `n = max` keeps the largest.
- Tested the plate alone first (P4's lesson): top −111.50 vs −111.46 mm³, then the bottom; plate 86,547 → 86,325 mm³ (−0.2 g). One miss on the way: my string replace skipped a ruff-wrapped line (the manifest still said `1`); fixed with sed on the line.
- Full rebuild: 0 interferences. S1m peak 9.68 → 8.88 MPa (SF 3.94), inserts 0.968 → 0.970 mm; S1b 2.51 → 2.38 MPa. Edge audit: plate accessible sharp edges 4,506 → 3,466 mm (−1,040 = 2 × the 519 mm outline).
- Next: S1a2 (rib bottoms + boss rims) later; rotate now: D10 or P5.

## tick 22 · D10 blind insert pocket + full root chamfer · accepted · 2026-10-31 02:10
- Hypothesis: with the lower insert pocket blind (inside a local boss) nothing crosses the root, so one full-length chamfer removes S2's singular corner.
- Built the mount alone first: 10,874 vs 10,850.7 mm³ voxel; full rebuild 0 interferences; +0.1 g per mount.
- S2 pull + torque: default 7.15 → 5.26 MPa, half mesh 9.67 → 6.63 MPa (SF 5.28); motor holes 0.0482 → 0.0417 mm.
- Convergence still short: the root region 5.26 → 6.53 (+24 %, the boss/chamfer intersection), and the half-mesh max is now the end-stop step corner (x −17.6, z 22.5), untouched by D10. Both go to D1 (fillets). Accepted: every gate improves; SF taken on the half-mesh peak.
- Next: rotate: P5 (carriages + idler mounting) or W/A/R items.

## tick 23 · P5 follower carriages · accepted (new parts) · 2026-10-31 02:50
- New `RB-PRT-030/031_carriage_L/R` from `carriage_features`: foot + rails in the existing guide slots, clamp hole, jack pad, pedestal at the plate edge, journal boss into the idler's open inboard side (to 0.5 short of the hub tube, |y| 69). Built both alone first (BUILD OK, 5,734 vs 5,736 mm³), then the full rebuild: 0 interferences.
- New study S6 (left carriage, held at the jack face + clamp hole, 48.7 N at the belt centre via the bore). Three iterations inside the tick: 12 × 9 pedestal + Ø12 boss 16.5 MPa (twist at the pedestal root) → full-length pedestal 12.9 (boss root) → Ø15 boss + pedestal to the boss top 6.83 MPa (SF 5.1), bore 0.026 mm; equilibrium exact. Mass 7.4 → 12.3 g each.
- One slip: launched the first rebuild with a bare `&` (no completion notice); it ran fine, checked by a timed wakeup.
- Printed parts now 365.9 g, CoG (6.8, −0.1, 14.0).
- Next: rotate: S1a2 / W2 / R1; the carriage joins D1 (fillets) and the edge audit.

## tick 24 · R1 assembly sequence · accepted (doc) · 2026-10-31 03:00
- Walked every joint (06 §8 + deck, carriages, idlers) against the generated geometry: `docs/cad/loop/R1_assembly.md`.
- Trapped fastener: the Pi deck's rear M3s at (−48, ±20) lie under the Pi board (x −64.5…22.5, |y| ≤ 28) → P4b (move the rear posts to ~(−70, ±20)).
- Order constraints: motor → mount before the sprocket (heads 21.6 from the shaft, sprocket r 31.4); mounts before the bulkhead (its 15° lean puts the top over x ≈ 50, above the foot screws at x 43.9–72.6).
- Service: the jack screw head has 18 mm to the encoder; ball-end key or a knurled thumb screw (R2).
- No CAD change. Next: P4b (a real fix), then S1a2 / W2.

## tick 25 · P4b deck rear posts out from under the Pi · accepted (deliberate trade) · 2026-10-31 03:15
- R1-F1 fix: rear deck posts (−48, ±20) → (−70, ±20), deck to x −75; 06 amended. Screw heads 2.75 clear of the Pi board (with ports) in plan.
- Rebuild: 0 interferences; deck 12,981 → 14,574 mm³ (+2.1 g; the 9 × 59 × 3 extension), plate volume unchanged.
- S1b 2.38 → 3.34 MPa, deck-post tops 0.032 → 0.145 mm (the rear posts now sit further aft of the jack-bore fixture); S1d 6.30 → 8.93 MPa (SF 3.92), Pi holes 0.10 → 0.19 mm (longer span). Worse than the baseline by more than 10 %, but this is an assembly fix and every limit holds.
- Next: rotate: S1a2 or W (a deck rib).

## tick 26 · S1a2 plate belly edges · accepted (partial, kid-safety trade) · 2026-10-31 03:30
- `filletface` options: `any` face count, `|all` for inner loops. Built the plate alone after each step.
- r 1.0 on the four load-rib bottom faces (2 per side: the |y| 47 rib, the |y| 36.5 rib merged with its boss): −117.0 / −117.3 vs −118.05 mm³ by hand; the 1.2 cross ribs crossing them didn't stop the fillet. r 1.0 on the six inboard under-boss rims: −34.4 vs −34.8.
- The 1.2 grid ribs (z −7.6, 24 faces, 153 edges incl. the cells' inner loops) at r 0.5 returned nothing; dropped, → W3 (widen to 2.4, then round).
- Full rebuild 0 interferences, plate 111.4 → 111.0 g. S1m 8.88 → 9.37 MPa (SF 3.74), inserts 0.970 → 0.996 mm; S1b 3.34 → 3.88 MPa (+16 %, SF 9.0, deck 0.145 → 0.147 mm). Accepted as a kid-safety trade. Plate accessible sharp edges 3,466 → 2,212 mm.
- Next: rotate: W3 (which also unblocks the grid-rib rounding) or A/M.

## tick 27 · W3 2.4 grid ribs + whole belly r 1.0 · accepted (+3.9 g, strength + safety) · 2026-10-31 03:50
- Grid ribs 1.2 × 3.6 → 2.4 × 4.0 (bottom −8 like the load ribs / bosses); one r 1.0 `filletface` over every −8 face incl. inner loops, expected volume from a raster of the footprint.
- Failed twice; added an engine diagnostic (on failure, retry face by face and print which faces fail). Culprits were slivers, all pre-existing layout flaws: the x −60 cross rib cut into 0.6–1 mm pieces by the follower slots; the ±25 long ribs' edges 0.1 mm past the boss edges; the y 0 rib against the wire slot and the knee counterbore; the x 60 cross rib against that counterbore. Fixed the layout (rib through the boss centres at ±21.5, y 0 rib to x 30, cross ribs −60 trimmed to |y| 26 and 60 → 66) → BUILD OK, −536.7 vs −532.1 mm³.
- Full rebuild 0 interferences. Plate 111.0 → 114.9 g. S1m 9.37 → 8.64 MPa (SF 4.05), inserts 0.996 → 0.900 mm; S1b 3.88 → 3.61 MPa, deck 0.147 → 0.125 mm. Accessible sharp edges 2,212 → 735 mm.
- Next: rotate: A/M/E doc items or D1; S1a3 (slot edges) later.

## tick 28 · A2 fastener consolidation · accepted (doc) · 2026-10-31 04:00
- Bill of every fastener from 07 F1–F13 + the knee screw, carriages, moved deck posts: `docs/cad/loop/A2_fasteners.md`.
- Found: F4b's M3 × 20 jack screw can't cover the travel (block-to-carriage gap 7–17 mm + 10 mm block) → × 30. Unified F7/F8/F11 × 6 → × 8. One 2.5 key for every M3 SHCS; the canopy's 2.0 button heads kept as a deliberate small barrier. F12 suggested M3. 07 amended (dated note).
- No CAD change. Next: rotate to D1 or S1a3 (SW), or E1 (doc).

## tick 29 · perimeter flange (W + D3) · rejected · 2026-10-31 04:30
- Hypothesis: a rim under the outline in place of the |y| 47 ribs ends the free ledges at the plate edge (printable without support) and adds stiffness.
- Engine: `a` token for clockwise arcs (the rim's inset rear corners); a per-loop fillet diagnostic. Three builds: rim ending at x 78 (acute end + the (72.6, ±37.4) boss poking past it) failed; rim to |y| 30 on the front failed (boss merged into the rim); boss kept 1 mm clear (r 3.67, under 07's Ø 8) built: belly fillet −601 vs −539 mm³.
- Full rebuild 0 interferences. S1m 8.64 → 8.79 MPa, inserts 0.900 → 0.908 mm; S1b 3.61 → 3.62; +1.7 g; meshcheck overhang 158 → 150 cm² (it counts bridged bays as overhang, so it can't show the gain); front-middle ledge remains.
- Rejected: no strength gain, heavier, a new boss-size violation, partial DFM gain. Generator restored, baseline rebuilt (plate 89,049.1 mm³), repo CAD restored; engine tooling kept. Patch saved.
- Next: D3 needs a bridge-aware overhang check before more printability geometry. Rotate: E1 / S3 (doc) or D1.

## tick 30 · D3 bridge-aware overhang check + print orientations · accepted · 2026-10-31 04:45
- meshcheck: `overhang_split` (bridge / ledge / floating / steep) from horizontal ray casts 0.3 mm under each flat downward face; `--bridge` 40 mm. Guarded the no-hit case (crashed on the deck).
- Plate +z: 151 cm² overhang = 106 bridged + 17 steep + 27.5 ledge (perimeter strips outside the outer ribs, and the 40.6 mm front-centre bay) + 0.1 floating.
- All six orientations for every part → `docs/cad/loop/D3_print_orientation.md`, chosen strength first: plate +z (27.6 cm² perimeter support), bulkhead face down (1.0), deck / mounts +z (0), wheels +z (1.3–1.4), carriages front face down (0.4). The support-minimum for the plate is on edge; rejected (bending across layers).
- No CAD change. Next: D3b (perimeter ledges) or D1; rotate first.

## tick 31 · E1 design language · accepted (doc → Q18) · 2026-10-31 04:55
- Proposal: fillet family 1 / 3 / 8 (accessible edges / handled edges + openings / silhouette), a pebble canopy with a 2–3 mm crown (no flat white panel > 60 × 60), no exposed screw heads on child-facing faces, one slot/hole pattern for grille, vents and mic, face high as the "head". Written so P6 and E2 can be built to it.
- Q18 asks for the taste call with options (a) as proposed / (b) crisper 1 / 2 / 4 robot look / (c) reference. Default (a).
- No CAD change. Next: SW items: D1 (mount internal fillets) or S1b (bulkhead edges, now that the family exists).

## tick 32 · S1b bulkhead outer side edges r 1.0 · accepted · 2026-10-31 05:10
- `filletface` normal field now `axis:sign` (legacy number = z); the box spans the other two axes. Expected volume from the side faces' boundary in the generated STL: 266.6 mm each, all convex. First try missed the plane (voxel bbox gives 46.9, the face is at 47.0): use BH_W / 2.
- Bulkhead alone: −56.9 / −56.8 vs −57.2 mm³. Full rebuild 0 interferences. S5c 7.01 → 7.52 MPa (+7 %, SF 4.7), bezel 0.266 mm unchanged; 43.6 g. Accessible sharp edges 1,647 → 1,113 mm.
- Left: the face side (window rim, grille slots too narrow for r 1, foot front) → S1b2.
- Next: rotate: D1 or a doc item (S3 small parts / S4 battery).

## tick 33 · M2 material per part · accepted (doc) · 2026-10-31 05:20
- Rescaled M1 to today's stresses: conditioned PA6-CF now passes SF 3 on S1m (3.1), S2 (4.1), S6 (4.0), S1d (3.0, no margin) but deflects ×1.9: plate axles 1.7 mm, S5c bezel 0.50 (on the limit).
- Decision (07 §2 amended): all structural parts PET-CF this pass. Plate / bulkhead / deck on stiffness; mounts and carriages because their screws clamp through them (wet PA6 creeps, fpv250); wheels for bore stability. PA6-CF reserved for impact parts and as the mounts' fallback. Canopy PC/ASA stays M4.
- No CAD change. Next: SW: D1 or S1b2 / S1a3.

## tick 34 · S1c wheel outboard rims r 1.0 · accepted · 2026-10-31 05:30
- The bed-face layer is a true circle (r 27.40), so one `filletface` on the outboard face's outer loop does it. Both wheels alone: −36.6 vs −36.9 mm³ each; volumes 27,805.4 / 26,898.4 vs expected.
- Full rebuild (ran past the 10-minute command limit; finished in the background): 0 interferences, printed parts 371.1 g.
- Accessible sharp edges per wheel 213 → 41 mm (hub bore edge left). drivetrain.py's meshes now differ from the printed parts by the round; the SW export is the print file.
- Next: rotate: D1 (mount fillets) or a quick doc (S3/S4).

## tick 35 · S4 battery access and drop path · accepted (doc) · 2026-10-31 05:40
- The 2 × 18650 sit in the UPS HAT at the stack top (z ≤ 80) under ~13 mm of canopy clearance. Access is tool-only (A2's 2.0-key canopy screws); charging via cut-outs.
- Gaps, all on the canopy: cells can pop from their clips in a tumble; a stepped-on canopy has no defined load path; puncture clearance. → P6 requirements + a new FEA case S7 (300 N heel pad, < 10 mm, SF ≥ 3). Cell choice note (name-brand, protected, matched).
- `docs/cad/loop/S4_battery.md`. No CAD change. Next: SW: D1, or S1a3.

## tick 36 · D1 end-stop step fillet · pending (SolidWorks hung) · 2026-10-31 06:25
- r 2.0 on the concave step where the mount's end stop meets the upright (S2's half-mesh hot spot after D10); not the vertical corner, where the gearbox bears. Built alone: +5.15 vs +5.15 mm³.
- S2 showed `disp motorholes: 3 faces`: the r 2.0 fillet is a y-cylinder of radius 2.0, which S2's insert selector (and its remote-load coupling) also picks. Run invalid; killed. Lesson: never give a fillet the radius of a feature a study selects by shape (or make the selectors box-limited).
- r 2.2: the rebuild failed to save RB-PRT-010 (the killed swsim left it open), S2 reran on the old part, killed again. A close-documents manifest then hung: SLDWORKS at ~41 GB and no longer answering the probe. Not killing it (Ben starts SolidWorks; his own documents may be open).
- Generator restored, change parked as a patch. sw: DOWN in STATE. Ben extended the stop to 12:00 (message ~06:20).
- Next: doc / py items until SolidWorks is back; then rebuild the baseline, reapply D1, S2 pair.

## tick 37 · R2 service tasks on paper · accepted (doc) · 2026-10-31 06:35
- SolidWorks has exited (no SLDWORKS process; probe fails). sw: DOWN; doc/py items only.
- Timed battery / track / motor / reflex-USB service against the geometry: `docs/cad/loop/R2_service.md`. Battery ✓; track needs two tools (blind nyloc under the plate) → R2a (insert in the carriage); motor ~8–10 min because its lead ends on the reflex board under the deck → R2b (inline connector); reflex USB reachable only if the connector faces the rear bay → R2c, a PCB layout note before the board is ordered.
- No CAD change.

## tick 38 · R2c reflex USB-C note into TODO · accepted (doc) · 2026-10-31 06:45
- Ben: SolidWorks restarted; drivetrain reviewed and good (logged in QUESTIONS as the sign-off for the sprocket and idler test prints).
- The probe still can't see SolidWorks (no SLDWORKS.exe in this session; "not running"). D1 stays a patch; tree clean.
- R2c: the reflex PCB verify item in docs/TODO.md now carries the connector exits: USB-C on the rear edge (x −40), motor leads on inline connectors.
- Next: retry the probe; if up, rebuild + D1 + S2 pair.

## tick 39 · D1 mount end-stop fillet r 2.2 · accepted · 2026-10-31 07:25
- SolidWorks back (Ben restarted it). Rebuilt the baseline with D1 reapplied from the patch: BUILD OK, 0 interferences, mounts +6.23 mm³ (fillet exactly as predicted).
- S2 now selects 2 motor-hole faces (the r 2.2 fillet isn't mistaken for an insert). Pull + torque: default 6.42 MPa, half mesh 6.63 MPa: +3.2 %, converged for the first time. SF 5.28 (= D10's half-mesh value, now trustworthy); holes 0.0416 mm (=). The end-stop spot left the top 5; the peak sits on the boss/chamfer face.
- Next: rotate: S1a3 / S1b2 / R2a.

## tick 40 · R2a carriage clamp into an insert · accepted (serviceability) · 2026-10-31 07:50
- Clamp screw from below through the plate's clamp slot into an M3 insert in a Ø9.2 boss on the carriage foot (insert z 2.8–10). Two slips on the way: a str-replace that missed a ruff-wrapped line (the build ran the old part; caught by the unchanged volume), and a comment placed before a list comma in fea.py (it joined two manifest lines; caught by the dry run).
- Carriages alone: 9,872.5 vs 9,878.2 mm³; full rebuild 0 interferences; 12.7 g each.
- S6 (fixture moved to the insert pocket): 6.83 → 7.58 MPa (SF 4.6), peak on the boss top beside the fixture; bore 0.026 → 0.0235 mm. Accepted as a serviceability trade (track swap: one 2.5 key). 07 F4 amended (M3 × 12 into the insert).
- Next: rotate: S1b2 / S1a3 / D1b / R2b.

## tick 41 · S1a3 belly slot edges · accepted (partial) · 2026-10-31 08:15
- New `filletface` option `loops:<box>`: only inner loops whose centre falls in the box (curve sampling so full circles count). Two compile slips (a clashing local name, `Environment` ambiguous with the SW interop).
- Rounded r 1.0: guide + clamp slots both sides (−38.4 vs −38.7 mm³ each), knee counterbore (−4.40 vs −4.38). The wire slot, tab slots and bulkhead counterbores aren't loops of any z −4 face (debug print showed only the knee cbore in that region); dropped for now → S1a4.
- Full rebuild 0 interferences, plate 114.8 g. S1m 8.64 → 8.69 MPa, inserts 0.900 mm (=); S1b 3.61 → 3.74 MPa, deck 0.126 mm. Plate accessible sharp edges 735 → 351 mm.
- Next: rotate: S1b2 / D1b / R2b.

## tick 42 · S1a4 wire + tab slot edges · accepted · 2026-10-31 08:40
- SWB_DEBUG listing showed the loop filter computing bogus boxes for some lines (curve-param sampling); fixed to vertices + circle centre ± r. Wire slot and tab slots then rounded r 1.0 within 2 % of hand volumes.
- The bulkhead counterbores still aren't z −4 loops because they break the plate outline: x 81.5 + 3.25 = 84.75 vs the front at 85, a 0.25 mm wall (tick 5's 0.24 min wall) → D5b.
- Full rebuild 0 interferences; S1m 9.00 MPa (+3.6 %), inserts 0.900 mm; S1b 3.57 MPa. Plate accessible sharp edges 351 → 259 mm.
- Ben (~08:15): add a 2 mm motor-bell depression in the plate under each motor's can/encoder (P14), next.

## tick 43 · P14 motor-bell relief (Ben) · accepted · 2026-10-31 09:05
- Ben: the motors don't sit flat; the can/encoder end would bear on the plate and lever the bracket. Added a 2 mm deep relief under each (x −11…20, |y| 31…53, clear of the reflex standoff and 2 mm in from the edge), floor edge r 1.0.
- Plate alone: each relief −1,364 mm³ (31 × 22 × 2), floor fillets +22.3 vs +22.75 mm³. Full rebuild 0 interferences; plate 111.3 g (−3.4 g).
- S1m 9.03 MPa (=), inserts 0.900 → 1.033 mm (+15 %: thinner plate in the tension path); S1b 3.68 MPa. Accepted as Ben's fix; W7 queued to win the stiffness back.

## tick 44 · D5b plate thin walls · accepted · 2026-10-31 10:00
- Bulkhead-foot counterbores removed (0.25 mm wall at the front; the foot can't move back): low-head M3 on the belly; their holes excluded from the slot fillets so the heads seat on a square edge. 07 F1 amended.
- meshcheck still said 0.23 mm: located with rays at (57.8, 1.2, −2…−3.4), the wire slot's end against the knee counterbore (I'd only checked they don't overlap in S1a4). WIRE_SLOT x1 55 → 53.
- Min wall 0.23 → 0.8 mm (the designed floor under the insert pockets: noted on D5). S1m 8.99 MPa / 1.033 mm, S1b 3.49 MPa, 0 interferences, plate 111.5 g.

## tick 45 · D5 hole table + plate insert floors · accepted · 2026-10-31 10:30
- Hole table vs DFM: `docs/cad/loop/D5_holes.md`. The plate's motor-mount insert pockets (7.2 in an 8 mm stack) left 0.8 mm floors → 6.7 deep, floor 1.3. 07 F2 amended.
- Rebuild 0 interferences; S1m 8.71 MPa, inserts 1.032 mm (=). meshcheck min wall 0.86: located at the 0.95 mm webs between the guide slots and the clamp slot (thinned by S1a3's fillets) → D5c (spread the guide slots to |y| 30.5 / 41.5).
- Slip: launched the rebuild with a bare `&` again (no notification); checked by timer.

## tick 46 · D5c carriage slot webs · accepted · 2026-10-31 11:05
- Guide slots (and carriage rails) |y| 31 / 41 → 30.5 / 41.5: webs to the clamp slot 0.95 → 1.45 mm. Plate + carriages alone: BUILD OK; full rebuild 0 interferences.
- meshcheck min wall 0.86 → 1.19 mm. S1m 8.87 MPa, inserts 1.032 mm; S6 7.13 MPa, bore 0.024 mm.
- Ben (~10:40): don't print yet; answered Q17 (outboard track frame), A1 (keep the mounts bolted), Q18 (pebble 1/3/8); next leg = canopy, treads, polish. This leg ends here.

## tick 47 · P6 canopy first cut · accepted (new part) · 2026-10-31 11:55
- Leg 2 starts (stop_after 2026-11-01 07:00). `RB-PRT-004_canopy`, ASA 1.8 shell to E1 (a): side profile extruded |y| 53; body top z 93 over the stack (top 86); a **hood** behind the head whose ceiling (square to the 15° wall) sits 0.1 over the two lugs and takes the front screws (S5c); front open over the bulkhead (|y| ≤ 47.3); skirt stops at z 30 (mount tops 26.5); rear apron + 2 insert bosses, screws up from the belly (07 F9 amended, 06 §6 as-built note).
- Engine: `shell` (faces by normal/plane/box, judged by feature count + dvol) and filletface `skip:<box>` (leave out the concave hood junction). Rounds r 20 plan / r 8 hood + top.
- Slip: the hood back-top edge is 105° interior, not 75° (dvol −1793 vs −3767 → vs −1907 after the fix). Every other step within its formula: shell −955,132 vs −955,023 mm³; part 77,690 vs 77,563.
- First assembly: 2 × 0.1 mm³ bulkhead/canopy (ceiling on the tilted lug tops) → CAN_LUG_GAP 0.1 → **0 interferences**. Canopy 83.2 g; printed parts 368.6 → 451.8 g, CoG z 14.0 → 24.7.
- meshcheck: min wall 1.77; overhang 133 cm² open side down (the ceiling: orientation → D3); 2.0 m sharp edges (skirt rim, front lips, apron: first-cut square edges, like P1) → P6e.
- Next: P6b plate holes for the rear screws, then P6c S7 (300 N heel) + S5c with the real canopy.

## tick 48 · P6b plate holes for the canopy's rear screws · accepted · 2026-10-31 12:15
- 2 × Ø3.4 through at (−80.4, ±12) (M3 × 10 button up from the belly into the canopy apron inserts, 07 F9); clear of the belly ribs (y 0, ±21.5; cross ribs x ≥ −60), 2.9 mm to the rear edge, square edge for the head.
- Plate alone: each hole −36.3 mm³ (= π 1.7² × 4); 86,426.7 vs 86,465.9 (tol 346). Slip: a trailing `close` after `save` (save already closes) failed the standalone run; harmless.
- Full rebuild 0 interferences. S1m 8.87 → 9.03 MPa (SF 3.88), inserts 1.032 mm (=); S1b 3.49 → 3.76 MPa (+7.7 %, the holes are 13 mm from the rear deck posts; SF 9.3), deck 0.126 mm.
- Ben (~12:00): canopy material M4: PC White 60100 favoured, ASA White 45100 the alternative; S7 runs both (ribs under the top if needed). Mass roll-up now uses PC (ρ 1.20 🟡): canopy ~93 g, printed total ~461.6 g.
- Next: P6c S7 (both materials) + S5c with the real canopy.

## tick 49 · P6c canopy heel test (S8) + material · accepted (strength fix, Ben's calls) · 2026-10-31 17:00
- Study: canopy alone held at its 4 screws, heel on a Ø30 pad (analysis copy `FEA-canopy_S8`; pad because split lines don't work). Found the S4 premise wrong: stack top is z 86, not 80, so the ceiling cleared it by 5.2 mm, not 13 (S4 corrected). 07's "S7" is the modes run, so the heel case is **S8** (07 amendment).
- 300 N, bare 1.8 top: PC 19.5 mm / 78.5 MPa, ASA 17.1 / 78.0. Ben: top 93 → 97 for ribs. 4 mm rib grid (1.6 thick): PC 7.0 / 74. Keels |y| 31.5 to z 75: 3.6 / 83.7 (free ends) and a 2.4-thick `box` keel inside the canopy (exact in a fresh part; cause unknown) → keels as Top-plane profiles, tied into the rear wall, tapered at the front: 3.4 / 50.7 (SF 1.2 XY).
- Ben: relax S8 to **150 N, SF ≥ 2 on XY UTS** (300 N = no-break). Top 97: PC 1.70 mm / 25.3 MPa (SF 2.4), **ASA SF 1.45 → canopy = PC (M4 closed)**. Ben: top 97 → **95** (rib bottoms 3.2 over the stack, limit 1.7 mm; ribs may touch the HAT at 300 N). 95: 1.82 mm → keels to z 73: **1.706 mm** (Ben: accept, no hair-splitting), top 25.7 MPa SF 2.4, hood ceiling 28.9 SF 2.15.
- Canopy 83.2 g ASA → **109.6 g PC**. Rebuild 0 interferences.
- Next: P6d openings / P6e edges / P6f crown / P6g internal fillets (Ben), then the track frame.

## tick 50 · P6g canopy internal fillets (Ben), rib/keel roots · accepted · 2026-10-31 18:00
- r 1.0 at every rib and keel root on the ceiling underside: one filletface over the 33 cell faces at z 93.2 (outer loops, 122 edges), skipping the tangent seams into the inner rounds (x −77, |y| 45) and the ceiling's front end at the hood (x 36.2). Engine: `skip:` now takes several `;`-separated boxes.
- dvol +391.8 vs +400.9 mm³ (concave, (1 − π/4) r² × 1,868 mm); canopy 91,742 mm³ (109.8 g PC).
- S8 (150 N heel, PC): 1.706 → **1.675 mm** (now under 1.7), top 25.7 → 24.4 MPa (SF 2.41 → 2.54), hood ceiling 28.9 → 29.0 (SF 2.14). Rebuild 0 interferences, printed 478.6 g.
- Not done (P6g remainder): vertical rib-crossing corners, keel-to-rear-wall edges, the hood ceiling/lug zone (now the S8 peak).
- Next: P6h S5c with the real canopy (rotation: strength), then P6e edges.

## tick 51 · P6h does the canopy hold the bulkhead lugs? · finding (no geometry change) · 2026-10-31 18:35
- New study **S5k**: canopy alone (PC), held at its rear insert pockets + apron/boss feet, the full 50 N poke (S5 direction) into the two lug screw holes (upper bound).
- Result: lug holes move ~340 mm (linear; i.e. a mechanism), 208 MPa at the rear apron. The canopy's only tie to the frame is the rear apron, a 1.8 wall loaded face-on; the side walls (stiff in their own plane) stop at z 30 and never reach the plate. **S5c's premise (lugs fixed) does not hold** → the bulkhead is effectively at S5 standalone (8.0 mm / 39 MPa vs 0.5 mm). Q19 to Ben.
- Next: per Q19.

## tick 52 · Q19 canopy side tongues into plate slots (Ben) · accepted (strength fix, partial) · 2026-10-31 20:50
- Each canopy side wall drops a 1.8 web to the plate in the free strip between the carriages (front <= x −45) and the motors (can end x −10), ending in a 3 mm tongue in a plate slot (0.1 clearance): the side walls become shear panels, no screws, canopy still lifts straight off. Screws from the belly were out: the heads would hit the |y| 47 load rib.
- S5k (canopy alone, full 50 N poke into the lugs, upper bound; tongue ends held in x): ~340 mm (tick 51) → 16 mm webs 0.91 mm → **30 mm webs (x −44…−14) 0.75 mm**, 12.1 MPa (SF ~5). Remaining give: hood-ceiling junction and the side lips. Target 0.2: **not met**. By hand the real S5c bezel ≈ 0.27 + 0.7 × 0.64 ≈ 0.7 mm vs 0.5 (canopy takes ~90 % of the poke). Accepted per Ben ("no hair-splitting"); open item P6i.
- Plate slots: S1m 8.98 → 8.87 MPa (SF 3.95), inserts 1.038 mm (=); S1b 3.20 MPa. Rebuild 0 interferences. Canopy 111.7 g, plate 111.3 g, printed 482.3 g. The `box` webs built exact (the tick-49 keel anomaly didn't recur).

## tick 53 · P2o-a outboard track frame spec (06 §7 amendment) · accepted (doc) · 2026-10-31 20:45
- Concept per side: outer bar |y| 93.5–97 at axle height from the idler axle (slot + nyloc clamp after jack-screw tensioning) to the sprocket's outboard 624 (Ø4 shoulder bolt); two legs through the loop window (x −30…25, z −10…37 clear of the lug tips) to plate-belly inserts at x ≈ −22…−14 and 14…22; road wheels (P13) can hang from the legs. Width 185 → ~194. New study S9 judged on 0.2 mm at the axles. ~14 g/side.
- Split into P2o-b (part + plate inserts + placement) and P2o-c (S9).

## tick 54 · P2o-b outboard track frame bars L/R · accepted (Q17 b, first cut) · 2026-10-31 21:15
- Legs dropped: a belly screw at the rear leg crosses the |y| 47 load rib or the canopy tongue slots, the front leg sits under the motor; and a bar pinned on two parallel axles is already a tie. Bar = 3.6 × 14 stadium at |y| 93.5–97.1 (1.0 off the wheel faces), x −69.3…59.7; sprocket end: steel Ø4 dowel through the bar + Ø10 × 3 boss, 5 mm into the 624; idler end: x-slot ±5 over the shoulder axle's M3 end, nyloc clamp. 06 §7 amended (overall width ~200).
- Alone: 6,349.8 vs 6,349.8 mm³ each (8.2 g). Rebuild 0 interferences; printed 498.7 g.
- S9 by statics, not FEA (one material per study; the steel shafts can't be modelled): each axle is a lever with the belt load between the inboard support and the bar, so with pinned ends each takes ~half → plate path ~half of S1m: **axle motion ~0.52 mm** (was 1.03; target 0.2), bar stretch ~0.03 mm. The TT shaft's two gearbox bearings make the inboard end partly moment-stiff, which can shift the split either way. Q20 to Ben.
- Ben (Q20): judge the drive increment → 8.7 N/side → ~0.09 mm with the bars vs 0.2: **S1 passes**. 07 amended; Q17/Q20 closed.

## tick 55 · T11 native installed belt · accepted (tooling/fit) · 2026-10-31 22:05
- `RB-PRT-050/051_belt_L/R`: the 08 belt wrapped on the wheels (pitch-line stadium round the sprocket and the idler at x_fit), base T_BASE, grouser bars outboard, trapezoid lugs in the LUG_W band (end chamfers left out). Lug centres at s = 5 + 10 k from the sprocket top tangent = 20 k° on both wheels = the pockets (straights = 11 pitches exactly). Built as one outer boss + three inner cuts (plain / lugged / plain) from 800-point XZ polylines; ~1 min.
- Volume by shoelace 48,158 vs SolidWorks 48,157.7 mm³ (47,877.8 with the 0.02 gap); printed ring (drivetrain.belt) 47,657 (−1.05 %, the chamfers). Replaces the stadium envelopes in the assembly.
- First rebuild: 816 × 0.0 mm³ belt/wheel (the inner face sits ON the rim; its chords dip ~0.001 inside) → modelled 0.02 off → **0 interferences**: lugs clear every pocket, the frame bars and the plate. Belts 58.4 g each TPU (now in the roll-up): printed 615.5 g.
- Ben asked how the belts print: as an upright closed ring (Ø133 × 36, lugs in, bars out), flexed onto the wheels; T12 checks the strain and lug clearance.

## tick 56 · T12 `drivetrain.py check-wrap` · accepted (tooling) + finding · 2026-10-31 22:15
- New command: lug ↔ pocket side clearance over the 9 engaged lugs per 180° wrap vs belt stretch (both profiles as their rounded trapezoids, the lug rigid in mm on the wheel, pattern best-centred), base bending strain (ring R0 63.7 → wheel 28.65 / straight), tooth tops vs running surface.
- Results: side clearance 0.684 mm at 0 %; +0.48 / +0.28 / +0.08 at 0.5 / 1 / 1.5 %; **−0.12 mm at 2 % (end lugs bind)**: zero clearance at **1.71 %** stretch. Tip to pocket floor 0.60. Strain 2.40 % wraps / 1.96 % runs (limit 5 % 🟡, TPU 85A). Teeth 0.6 below the rim discs: smooth rolling.
- Finding: the jack screw can take up more creep (belt_fit creep allowance 3.85 %) than the pockets tolerate (1.71 %). Fix = wider pockets (CLR 0.6 → ~0.75 gives ~2.1 %), but the sprocket/idler are Ben-reviewed → Q21. The strip/creep bench test (08 §7) decides how much stretch is real.

## tick 57 · T13 belt print package · accepted (tooling/doc; slicing waits on T4) · 2026-10-31 22:30
- drivetrain.py: `test_pieces()` (belt_strip150 150 × 2.5 × 36; belt_lug6 straight 6-lug length, convex prisms that the slicer merges: there's no boolean engine in tools/.venv), `belt_scaled()` + `build --shrink <pct>` (ring diameter only). All meshes closed; bounds checked with trimesh.
- `docs/cad/belt_print.md`: upright, walls only, seam on the lug inner faces, 85A first, external spool, PEI; shrink from the strip; the T12 1.5 % stretch watch.
- Not done: sliced .3mf (T4, Bambu CLI not ported yet).

## tick 58 · R2b motor-lead connector · accepted (doc) · 2026-10-31 22:40
- The R2 note said "inline 2-pin": wrong. Reflex J1/J2 are JST-XH 6-pin (motor + encoder power + A/B). Fix: use the encoder TT motor's own socket if it has one (to check on the motors in hand), else an inline 6-pin XH pair near the mount. Motor swap ~4 min, no deck removal. R2_service.md, TODO, measurement list updated.

## tick 59 · S1b2 bulkhead face-opening rounds + engine fix (`box`) · accepted · 2026-10-31 23:40
- r 1.0 on the window rim, both sonar holes and the camera hole, applied BEFORE the 15° tilt while the front face is the plane x 85 (`filletface x:1`, loops with centre y <= 10; the 2 mm grille slots at y 24 left). −74.8 vs −73.4 mm³. The front perimeter waits (it meets the S1b side rounds).
- Found on the way: the bulkhead came out 250 mm³ under its prediction, all of it in the post-tilt foot `box` (+1,660 vs +1,819 last build vs **+1,873** when the same rectangle is drawn as `prof` lines). **`box` used CreateCornerRectangle, which misbuilds when the body already crosses the sketch plane** (the tilted wall at z 0); the tick-49 canopy keels (2.4 thick, not 1.8) were the same bug. Engine: `box` now draws four lines. Full rebuild: every other part identical, bulkhead 33,750.8 vs 33,815 (was 114–250 short), 0 interferences.
- A Python STL occupancy diff (4M points) was stopped by the harness for low system memory while idle; not re-run (the prof-vs-box build answered it in one SolidWorks run).
- S5c 7.55 MPa (SF 4.6) / bezel 0.27 mm (=).

## tick 60 · D1b plate boss-root fillets · rejected · 2026-11-01 00:50
- r 1.0 at the roots of the deck posts + reflex standoffs on the plate top (one filletface, loops box). 8 bosses: +51.6 vs +52.0 mm³ but 2 × 0.0 mm³ with the motor-mount feet (the front posts at (30, ±8) sit beside the feet) → 6 bosses: +38.6 vs +39.0, 0 interferences.
- Strength got worse: S1b 3.20 → **5.11 MPa** (midplate; posts 4.54), S1m 8.87 → **10.60** (jackstops, beside the reflex standoff at (−36, −26)). Both still pass SF (6.9 / 3.3), but > +10 % on a change meant to lower stress → **rejected**, generator restored, mirror rebuilt.
- Learned: the plate's peaks there are mesh-sensitive (fillet faces change the mesh near the fixtures/standoffs) rather than set by the boss roots; a root fillet isn't a free win on the plate. If D1b comes back, check with a half-mesh run first (S2 pattern) to see whether either value is converged.
- W7 closed as moot: P2o bars + Q20 increment criterion (~0.09 mm vs 0.2).

## tick 61 · P6e canopy outer skirt rim r 1.0 · accepted (kid safety) · 2026-11-01 01:20
- r 1.0 on the OUTER edge of the skirt's bottom rim (z 30): rear outside the apron, the r 20 corners, both sides, the front lips (75° wedge). Inner edge left square (both would eat the 1.8 wall). One filletface over the 4 rim faces, `skip:` boxes for the inner edges, inner arcs and the concave junctions with the tab webs / apron (16 edges skipped).
- −67.7 vs −67.5 mm³; canopy 95,216 mm³. Rebuild 0 interferences, min wall 1.6. meshcheck sharp length only 4,158 → 4,133 mm (the inner rim edge stays; meshcheck may also count the r 1 round's STL facets): not chased.
- Left in P6e: hood front edge r 3 (E1), window/lip edges, hood-top screw heads (E1 §3), rib/keel bottom edges.

## tick 62 · P6e hood front top edge r 1.0 · accepted (kid safety) · 2026-11-01 01:45
- The hood's front top edge (E, along y, right behind the head) r 1.0: −19.8 vs −19.3 mm³. E1 asks r 3 here, but the ceiling over the window is 1.8 thick: r 1 is what fits (r 3 would need the hood ceiling thickened locally). Rebuild 0 interferences.

## tick 63 · S1b3 bulkhead top front edge r 1.0 · PENDING (SolidWorks hung) · 2026-11-01 01:40 MST
- r 1.0 on the wall's top front edge pre-tilt (`fillet` on the line at x 85, z 126): alone −20.17 vs −20.17 mm³, the side rounds then take 5 edges each (they blend), part 33,730.7 vs 33,795.1.
- The full rebuild hung: SLDWORKS "not responding" with an unsaved Part544 open, ~15 GB; the rebuild's 30 min timeout killed only the Python wrapper (empty log), leaving swbuild.exe attached; S5c then started and waits on it. Nothing killed (lesson: don't kill mid-run; restart is Ben's). sw: DOWN. Generator change left uncommitted, documented in STATE.
- **Resumed 04:00 MST** (Ben restarted SolidWorks). The orphan swsim exited by itself; clean rebuild: S1b3 −20.17 vs −20.17 mm³, 0 interferences, printed 615.3 g; S5c 7.50 MPa (SF 4.7) / bezel 0.27 mm (=). **S1b3 accepted.**

## tick 64 · S2 pinch-point audit (track path) · accepted (doc) · 2026-11-01 04:30 MST
- `S2_pinch.md`: plate/canopy/bar gaps to the belt 1.5 / 3.5 / 1.0 ✓. **F1** 9.5 mm slot at each front corner (bulkhead side |y| 47 ↔ belt 56.5, z 0…30) ❌. **F2** 16 mm loop window above/below the frame bar reaches the lug ↔ pocket nips ⚠️. Q22: cheeks for F1 (default, next), side plates for F2 (waits for Ben: it changes the look).

## tick 65 · S2a bulkhead side cheeks (Q22 F1) · accepted (kid safety) · 2026-11-01 04:45 MST
- The wall (3 mm, not the flange: the mounts reach x 77.8) continued sideways |y| 47 → 52 from the bottom to z 30 (pre-tilt 31.1): the front-corner finger slot 9.5 → **4.5 mm**. Side-face rounds now take 7 edges (two concave cheek junctions), the cheek outlines r 1.0: −42.8 / −14.3 mm³ per side vs −42.6 / −14.6.
- Slip: bulkhead_volume_numeric's grid stopped at |y| 47.9 (missed the cheeks: −682 mm³, box 4.1 mm off) → widened; then 34,663 vs 34,728.
- Rebuild 0 interferences, printed 616.5 g; S5c 7.48 MPa (SF 4.7), bezel 0.27 mm (=).

## tick 66 · S2b frame bars → side plates over the belt loop (Q22 F2) · accepted (kid safety) · 2026-11-01 05:00 MST
- Each frame bar grew into a 2.4 PET-CF side plate (rounded rectangle x −69.3…59.7, z −10…38, r 8, outboard of the wheels at |y| 93.5–95.9) round both axles; the lug ↔ pocket nips are now behind it; gaps from its edges to the runs ~3–4 mm diagonally; 8 mm over the ground line. Dowel boss, slot unchanged.
- 14,795.0 vs 14,795.0 mm³ each (19.1 g, was 8.2); rebuild 0 interferences; printed 638.3 g. Renders `shots/1-S2/`.

## tick 67 · S2c side-plate outline r 1.0 · accepted (kid safety) · 2026-11-01 05:15 MST
- r 1.0 round each side plate's outline on its outer face (8 edges: straights + the four r 8 corners): −72.72 vs −72.72 mm³ per side. Rebuild 0 interferences; printed 638.1 g. Slot and boss rims left (the boss sits under the dowel head / the slot under the nyloc).

## review pass · every study once on the final geometry · 2026-11-01 06:15 MST
- PET-CF: S1m 9.97 MPa (SF 3.5; 8.87 at tick 52 with an unchanged plate: the jack-stop peak is mesh-sensitive, as tick 60 showed), S1b 3.20, S1d 8.93, S2 6.10 (pull + torque), S6 7.57, S5c 7.48. All pass.
- PC (S8, S5k): the run passed its 40 min wrapper timeout while SolidWorks was still solving (responding); left to finish, nothing killed. MORNING uses ticks 50/52 for those.
- Leg 2 ends here (stop_after 07:00): 21 ticks, the canopy / track frame / treads / polish list done except the measurement- and style-gated items (P6d, P6f, P6i, D1b others, Q21).

## tick 68 · P13a adopt 08 rev 1 (idler z 10.5, 4-wheel belt) · accepted · 2026-11-01 11:35 MST
- Leg 3 start. Found 81fd640 (08 rev 1: road wheels, idler RAISE 3 mm) was never cherry-picked (P11 said "before placing"); P13 needs its `wheels()`. Merged: drivetrain.py auto-merged with T12/T13, 08 doc conflict resolved (rev 1 open list + the T12 amendment). Sprocket/idler meshes and check-wrap unchanged; taut station −57.3 → **−57.18**.
- Chassis: belt native on `belt_path(wheels(x_fit))` (400.000 mm, 4 wheels); idler, carriage boss, track-frame slot, S6 axle at **z 10.5**. `wheel_phase` turns sprocket/idler so pockets sit on the lugs: first from the wrapped lugs → 2 × 0.0 mm³ sprocket/belt (the lug entering from road wheel 2 on the 6° climb grazes its pocket), then max-min over every lug near the wheel (±1°): worst radial gap 0.38 / 0.59 mm → **0 interferences**.
- S6 then **failed: 22.95 MPa** (7.57): the axle bore now exits at the clamp-insert boss top (z 10), and the axle bolt head (Ø8, z 6.5–14.5 on the |y| 40 face) clashes with that boss — not visible to interfere (no fasteners modelled). Fix: clamp insert pressed **up from the foot underside** into an open boss to z 6.0; screw M3 × 12 → **× 10** (07 F4, A2, R1 amended). **S6 6.50 MPa (SF 5.4), bore 0.024 mm** (0.026).
- Carriage 12.3 → 11.4 g; printed 638.1 → 635.5 g. Shots `shots/1-P13a/`.
- Ben, mid-tick: tread → **`belt_bars_stagger`** (new: 1.5 bars split + staggered + jittered, 57.2 g; 08 amended); M6 PA6-CF wheel coupons (Fiberon PA6-CF20 in stock, print-bom); M3 insert ladder ported from fpv250 (its PA6-CF sizing is M2: Ø3.4 × 5.5; buddy is M3, needs the insert's knurl OD).
- Next: P13b road-wheel discs native + placement. Note for P13d: the side plate's bottom edge (z −10) now sits ~3.4 over the bottom-run lug tips (was 2.4) and the ground line dropped to ~−21.4.

## tick 69 · P13b road-wheel discs native + placed · accepted · 2026-11-01 11:55 MST
- `drivetrain.road_wheel_layers()` (road_wheel() now meshes it) → native `RB-PRT-022_road_disc` through `wheel_lines` (684 crush-rib pocket on the bed face, r 3.7 shoulder, Ø18 × 12.9, bed rim r 1): 2,628.7 vs 2,628.2 mm³, **3.4 g** PET-CF (M6: PA6-CF candidate).
- 8 placed (2 per axle at road1 x −19.72 / road2 x +20.55, z −8.40 from `dt.wheels()`): bed faces flush with the belt edges |y| 56.5 / 92.5, 0.6 off the lug row. Axle envelope (library, interference only): Ø4 over the belt width + Ø7 spacer inner race to inner race (lug tips 1.5 off it).
- Full rebuild **0 interferences**; printed 635.5 → **662.7 g** (+27.2, new parts), CoG z 23.7 → 22.4. Shots `shots/1-P13b/`.
- For P13c: the outer disc's face is 1.0 from the side plate (|y| 93.5): no room for a nyloc there. Carry each road axle in the side plate (Ø4 bore + a boss outboard, like the sprocket dowel) and in an inboard hanger off the plate edge / belly, so the axle is supported both sides.

## tick 70 · P13c + P7 checked, both need Ben · Q24, Q25 · 2026-11-01 12:10 MST
- **P13c (Q24):** 08 §4b's plate-edge hanger doesn't fit: the plate prints standing on its ribs (a lug below z −8 lifts it off the bed); road wheel 2 (x +20.6) sits under the TT gearbox + bell pocket (no screw access, no insert depth); road wheel 1 beside the canopy tongue slot; the outer disc is 1.0 from the side plate (no nyloc room). Default (a): the track frame carries the road axles (side-plate boss + a blade dropping between the discs above the lug tips). Changes the load path from the plate to the frame, so it's Ben's.
- **P7 (Q25):** CE40P-8 datasheet (Dayton): Ø40 × 23, cutout 35.5, 2 holes, Vas 0.01 L. Point-sampled against the left mount/gearbox at the bulkhead's speaker seat (y 24, z 26, tilt 15°): basket into the mount end stop from **7.9 mm** behind the wall, upright + gearbox from 10.4. Not caught before because the speaker was never modelled (06 §9: no measured dims). No other seat on the wall. Default (a): a pre-boxed 8 Ω rectangular micro speaker behind the same grille.
- 0 g, no geometry. Next: P6d canopy openings (rotation; P8 mostly waits on Q25 / R2b / the mic disc).

## tick 71 · P6d canopy rear-wall vents · accepted · 2026-11-01 14:55 MST
- Where: the rear wall only. Sides face the belt 3.5 mm off (grit); the top would blow Pi heat over the cells and is the mic disc's place. Two fields of **13 vertical slots, 2 × 24 on a 4 pitch** (E1 slot motif, vertical = no bridges): **z 36–48** intake at the Pi's port end under the HAT, **z 70–84** exhaust above the HAT. `canopy_vents()` in chassis.py, one Right-plane cut through the wall.
- Cut 1,176.7 vs 1,176.6 mm³ predicted; canopy 114.2 → **112.8 g** PC. Rebuild **0 interferences**, printed 662.7 → **661.2 g**.
- **S8 (PC)** 24.4 → **25.1 MPa** (+2.9 %, SF 2.47 XY), heel disp 1.675 → **1.626 mm** (< 1.7). **S5k (PC)** lug ures 0.75 → **0.77 mm** (+2.4 %), 9.68 MPa. Both inside 10 %.
- Tooling: the first run of both studies went without `--material PC` (fea.py default PET-CF, stress usable, deflection not); then the wait loop `pgrep -f "fea.py S5k"` matched its own shell and spun ~1 h. Lesson: canopy studies always `--material PC`; wait on a PID, not a pgrep of the same string.
- Shots `shots/1-P6d/` (canopy_right shows both fields). P6d remaining: mic-disc seat (disc dims), barrel jack + switch (Q23), cell ribs (HAT heights), HAT buzzer vs rear wall.

## tick 72 · T4 headless slicing, a .3mf per part · accepted · 2026-11-01 15:00 MST
- Rotation (four P ticks in a row; P6f's crown needs non-planar face selection in swbuild + ribs/keels/heel pad reworked, a bigger tick, next).
- `tools/slice.py` (`just cad-slice [--only plate,canopy] [--no-3mf]`), ported from fpv250 (slicer_env / gen_presets / slicemass): OrcaSlicer 2.4.2 CLI through a `.bat` on C:\ (the rc 99 seen earlier is gone run that way). Presets flattened here from Orca's BBL system + user dirs; 07 §4 pinned (4 walls, 40 % gyroid, 5 top / 4 bottom); TPU uses Ben's belt presets. Orientation = D3 (trackframes: inner face down, meshcheck 0 cm² support either side); STL turned + dropped on the bed.
- Trap found: **Bambu's PC preset density is 1.04** (PC 1.20): canopy read 159.7 g. Every filament now gets the spool density; the G-code header is checked (layer, walls, infill, density, support) and a mismatch is printed.
- `.3mf`: `--export-3mf` is joined to `--outputdir` (full path → "Unable to open the file …/C:\…"): bare name. The 3mf carries project_settings (walls 4, 40 % gyroid, 0.24, PET-CF 1.29, Engineering Plate) checked by unzip. No thumbnails (no OpenGL from the CLI).
- **13 parts × qty: 623.1 g filament vs 544.2 g solid, 26.2 h.** Plate 127.0 g / 4 h 40 (perimeter tree support), bulkhead 44.2 / 1 h 36, sprocket 35.2, idler 34.0, discs 3.3 × 8, carriages 9.7 (0.85 of solid: the 40 % infill shows), **canopy 186.0 g / 9 h 29 on support vs 112.8 solid**: printed open side down the ceiling and hood sit on ~70 g of tree support. P6f decides its orientation with this.
- G-code (113 MB) gitignored; 3mf (1 MB) + sliced.json committed. Nothing printed (Ben's eyes first; MORNING says not print-ready).

## tick 73 · P6f canopy print orientation sliced · Q26 · 2026-11-01 15:15 MST
- With T4: canopy (PC, 0.4, 4 walls / 40 % gyroid, tree auto) +z 186.0 g / 9 h 29; **+x (rear wall down) 149.2 g / 6 h 49**; −x 190.9 / 9 h 52; +y 191.2 / 10 h 32; −z 145.6 / 7 h 37 (hood top touches first, body top hangs 28 mm); no support 101.5 g / 3 h 28. `bridge_no_support` and `support_on_build_plate_only` change nothing (the floating rib/keel bottoms drag support under every cell).
- meshcheck: +z 77 cm² bridges + 17 ledge/float; +x 14 bridges + 24 ledge/float (the cross ribs become 4 mm horizontal fins, the hood back wall a 106-wide ceiling).
- +x turns the top's x-bending across the layers: S8 on PC Z UTS 56 → SF 2.23 (≥ 2, datasheet). Strength basis + finish → **Q26**, default (a) +x with 45° undersides on the cross ribs and a ramp under the hood back wall. 0 g, no geometry. Next: the crown (independent of Q26).

## tick 74 · P6f canopy crown 2.5 mm · accepted · 2026-11-01 20:35 MST
- Body top is now an arc in XZ (sagitta **2.5** over rear wall → hood, R 714.2, centre x −25.3; E1 §2 no flat > 60 × 60). `canopy_crown` / `can_top_z`; ribs and keels follow it (tops 0.5 into the skin, **constant 4 mm depth**, bottoms on the concentric arc); heel pad's flat top over the highest skin point (`canopy_heel`).
- swbuild: `filletface|r|cyl|R|…` picks faces by cylinder radius (the crowned top and ceiling are no longer planes); `prof` arcs carry **6 decimals** (a 4-decimal centre at R 714 gave a null extrude on asymmetric arcs) and continue from the arc's actual end. swsim: `hotspots` now prints the **peak node's coordinates** (CWMesh.GetNodes, [x y z] by node number).
- Four S8 runs to get here, all 0 interferences / BUILD OK:
  - a: flat-bottom ribs (6.5 deep mid-span): **38.4 MPa**, 0.94 mm. Peak on the rear ceiling panel.
  - b: constant-depth ribs: **83.0 MPa**, 1.44 mm, same panel.
  - c: ribs ending on the crowned rear seam (x −77.45, not −77: the crown moves it; a 0.45 sliver was left behind the rib ends): **82.7 MPa**, now named on the x −22 cross rib.
  - d (diagnostic, peak node): **(−22.80, 15.80, 91.69)**, the bottom corner of a crossing: flat-bottomed cross-rib boxes vs arc-bottomed lengthwise ribs left a micron step at every crossing. #2 at (−77.45, 31.2): keels still met the ceiling at −77.
  - e: cross ribs as arc profiles (same arcs), keels ending on the seam: **22.8 MPa (SF 2.72 XY, was 25.1)**, heel **1.434 mm** (< 1.7, was 1.626). Peaks now spread over the rib bottoms near the heel (21–23 MPa, no single spike).
- **S5k (PC)** lugs ures 0.762 mm (was 0.768), hood 9.52 MPa (was 9.68). Probe hood in S8 22.8 vs 21.0 (+8.6 %: the box now catches the long rib-bottom face; inside 10 %).
- Canopy 112.8 → **114.8 g** PC (95,627 mm³), printed total 661.2 → **663.2 g**, CoG z 22.6. Shots `shots/1-P6f/`.
- Lesson: on curved ribs, every rib face that meets another must lie on the same surface; flat vs arc at a crossing makes a micron step that FEA reads as an 80 MPa singularity. Peak-node coordinates found it in one run after three guesses.

## tick 75 · P6e canopy front corners r 1 + canopy in the edge audit · accepted · 2026-11-02 00:20 MST
- **Hood-top screw heads → Q27:** the hole (x 45.65) is 3.25 from the hood's front edge, so the ISO 7380-2 flange (r 3.45) already hangs ~0.5 past the flat onto the 15° slope; no counterbore fits under a 1.8 ceiling with the lugs 0.1 below. Default (a) lugs 3 mm aft + counterbored collar (bulkhead change: Ben's).
- `edgeaudit.py` now audits the canopy (outer skin: within 1 mm of the side profile with the crown sampled, the sides, the rear wall/apron; not the skirt's inner rim, not the window lips' inner edges beside the bulkhead). First read: front corners 88 mm each, window lips, rear vent slots, apron/tab corners.
- Tried r 1 on the window lips' outer edges (y ±47.3): S5k 9.56 → **11.1 MPa (+16 %)** at the window's top corner (47.9, ±47.3, 120.4). A concave r 1 / r 0.5 there selects its edge (found with the new `edges|box` listing) but SW returns no fillet. Dropped: the lips sit in a 0.3 × 3 slot beside the bulkhead (3 proud of the lip face), not reachable.
- Kept: **r 1 on the canopy's outer front corners** (|y| 53, rim to the hood's r 8 side round, 2 × 18.8 mm³). Rebuild **0 interferences**, canopy 114.7 g, printed **663.1 g**. **S5k** 9.61 MPa (=), lugs 0.764 mm (=); **S8** 22.68 MPa (=), heel 1.435 mm.
- Tooling: swbuild `edges|box` (list edges by mid-point: type, ends) and `fillet|r|curve|…` (curved edges by mid-parameter point). Gate bug fixed in the run line: `grep -q "BUILD OK"` matched "did not report BUILD OK" (one S5k/S8 ran on a stale model); now `grep -qx`.
- Canopy audit left: rear vent slot edges (2 mm slots, z 36–48 / 70–84), apron + tab corners at z 16, the hood's inner front edge (over the bulkhead top, not reachable: rule to refine). Shots `shots/1-P6e/`.

## tick 76 · E4 hero renders · accepted · 2026-11-02 00:45 MST
- swbuild `view|doc|out.bmp|eye|up|persp`: sets `IModelView.Orientation3` from an eye direction + up (matrix columns = view x, y, z; the transposed form rendered the robot on its side, checked by eye), perspective on, zoom to fit, 1600 × 1200. The named `*Front` view in the old `shot` looks down our +z (SW's Front plane is our XY), so `shot`'s labels don't match the robot frame; the hero views do.
- `HERO_VIEWS` in chassis.py, rendered every rebuild after the assembly shot: **three_quarter**, **face** (a 5-year-old's eye ~40 cm up, ~1 m away: eye (1, 0, 0.3)), **rear_quarter**, **top** (front up). `shots/hero/*.png`.
- Read from them: the canopy crown and the rear vents read well; the hood-top screw heads sit right on the hood's front edge in the top view (Q27); the rear apron leaves the carriage bays open beside it (by design, tick 47).
- P10: every part that exists is placed (33 components, 0 interferences); left are the blocked ones (speaker Q25, XVF3800 P9, TPU smalls P8) and fasteners. 0 g, no geometry.

## tick 77 · D2 speaker grille slots full-radius ends · accepted · 2026-11-02 01:05 MST
- The 6 grille slots (2 wide, on the bulkhead's face side) were square-ended boxes. Now box + two Ø2 `cylx` ends, same overall length (corner on the Ø34 grille circle as before). Bulkhead 44.7 g (34,678.6 mm³, voxel expect passed).
- Rebuild **0 interferences**, printed 663.1 g. **S5c** 7.47 MPa (SF 4.7, =), bezel 0.265 mm (=).
- D2 audit of the rest: plate guide/clamp/wire slots and the canopy vents were already `slot` (full radius). Left square by function: bulkhead tab slots + canopy tongue slots (rectangular mating fits, 0.1–0.3 clearance; a radius would need dog-bones), the plate's bell pockets (blind reliefs under the motors, hidden). Shots `shots/1-D2/`.

## tick 78 · R3 part numbers on plate + canopy · accepted · 2026-11-02 03:15 MST
- swbuild `text|plane|u v|a0 a1|h|text|opts[|angle]`: `InsertSketchText`, bold, char height h, cut a0..a1 along the plane normal. Checked by ray-casting the exported STL (not SW views, which only see outer faces).
- What SW does, found on test walls (all four mirror/angle combinations): **escapement turns each glyph in place, not the line**; "mirror" flips the whole line; seen from the far side a plane's text is the whole line turned 180° (Top plane, v = −z). So a label read from inside the canopy's +y skirt = mirror + 180° + the string reversed. The reversed string with a hyphen cut nothing (twice), so the canopy reads "RB 004 r1" (advance widths come out in typed order: it renders "RB 004r 1"; readable).
- **Plate:** "RB-001 r1" on the belly cell x −11.5..11.5, y −8.5..−1 (clear area found by ray-scanning the plate STL), reads right from below, −22.3 mm³. **Canopy:** inner face of the +y skirt, x −30..−8, z 40..44, −23.4 mm³. FEA copies drop the labels.
- Rebuild **0 interferences**, printed 663.1 g. Shots `shots/1-R3/` (ray-cast images). Left for R3: bulkhead (tilted faces: the foot underside is 6.5 wide, needs text along y), mounts, carriages, wheels, deck, track frames.

## tick 79 · R3 part numbers on deck + track frames · accepted · 2026-11-02 03:55 MST
- Pi deck "RB-003 r1" on the underside (faces the plate), x −11.5..11.5, y −21..−17 (clear cell by STL scan), mirror (read from below): −23.9 mm³.
- Track frames on the plate's inner face (|y| 93.5, behind the belt), x ≈ −10..12, z 12..16: L "RB 040 r1" (mirror + 180° + reversed, as the canopy), R "RB 041 r1" (seen from its front: plain + 180° + reversed). −23.4 / −21.4 mm³. `trackframe_label(side)`.
- All three ray-cast from the reading side (`raylabel.py` in the scratchpad: below / +y / −y modes) and read right. Rebuild **0 interferences**, printed 663.0 g.
- R3 left: bulkhead (tilted faces), motor mounts, carriages, sprocket/idler/road discs (revolved: a flat hub face each), belts (TPU, from drivetrain.py).

## tick 80 · R3 motor mounts + FEA re-check of every labelled part · accepted · 2026-11-02 05:45 MST
- **Missed in ticks 78–79:** S1a/S1b load the real plate, S1d the deck, S5k the canopy, S2 the right mount, so the labels were in those meshes and I hadn't re-run them. Re-run now (S8 and S1m use FEA copies without labels):
  - S1a 11.63 MPa (last recorded 17.6 singular, tick 13: S1a was superseded by S1m in tick 18); S1d 9.05 (8.93, +1 %); S5k 9.66 / lugs 0.764 (=); S2 6.36 (6.10, +4 %).
  - **S1b 3.71 MPa vs 3.20 last recorded (tick 67 review), +16 %.** New `hotspots` + a `label` probe in S1a/S1b: the peak is at (−37.4, −30.8, 0) on the plate's TOP face by the jack block (a corner the journal already calls mesh-sensitive), the label region reads **1.42 MPa**. Not the label; the drift since tick 67 is open (SF > 9). Logged, not chased tonight.
- Motor mounts: "RB-010 r1" / "RB-011 r1", 3 mm, foot underside, read from below. First placement cut through two screw holes: I'd taken the midpoint of the *range* of valid window centres, and the holes split the clear region. Fixed by taking the middle of the valid set itself (26 × 8 window, per-part STL scan): centres (−5.15 / 5.25, −32.4). SW renders from below confirm (`shots/1-R3/mount_*_underside.png`).
- Lesson: STL ray-casts of 3 mm text show tessellation slivers; check small text in a SW render instead.
- Rebuild **0 interferences**, printed 663.0 g. R3 left: bulkhead (tilted), carriages (no flat hidden face), wheels (only the outboard face is flat), belts.

## tick 81 · S1b drift explained (A/B + half mesh) · accepted (doc + fea --part) · 2026-11-02 06:20 MST
- `fea.py --part \CAD\fea\X.SLDPRT` runs a study on another part (A/B checks).
- A: plate built without the R3 label (temporary FEA copy, deleted after): **S1b 3.199 MPa**, peak (−36.4, −30.8, 0), = the tick-67 value. B: labelled plate, half mesh: **4.97 MPa**, peak (−38.0, −31.0, 0.5) on the jack block's root face. Label probe 1.414 / 1.420 / 1.491 MPa (no label / full / half mesh): converged.
- So the +16 % is mesh noise: the label re-meshes the plate and the S1b peak sits on the jack block's unfilleted root corner, which climbs on refinement (singular, 3.2 → 3.7 → 5.0). Not a real change; the label is accepted. The jack-block root joins D1b as a fillet candidate (it is S1b's and S1m's peak).

## tick 82 · D1b jack-block root r 2 · REJECTED · 2026-11-02 09:20 MST
- r 2 concave round on each jack block's 4 root edges (one feature, corners blended), aimed at S1b/S1m's singular peak at the square root (tick 81). Built: +37.9 / +39.2 mm³ (first estimate subtracted the corners; concave corner blends add: full perimeter 36.0).
- Results (PET-CF): **S1m 9.97 → 13.26 MPa (+33 %)**, **S1a 11.63 → 14.78 (+27 %)**, **S1b 3.71 → 4.28 (+15 %); half mesh 4.97 → 7.91**. Every peak moved to the vertex where the fillet's corner blend runs out onto the plate, (−40 / −26, ±29, 0), and it still climbs on refinement: the blend's toe is a sharper singularity than the square root was. Same outcome as tick 60's boss roots.
- **Rejected**, generator restored (a comment records why), rebuild to put the mirror back. A rounded block with its own corner radius (r ≥ 3 on the vertical edges first, then the root) would be the next try, not tonight.
- Tooling: the first rerun's 40 min build timeout killed the Python wrapper while swbuild kept going (SW was just slow: 25 → ~45 min a rebuild now); build timeout 60 min.

## tick 83 · M6 PA6-CF coupons + slicer preset · accepted (doc + tool) · 2026-11-02 10:25 MST
- Ben (2026-11-01): "yes add the PA6-CF coupons". 08 §7 amended: `coupon_624_10/15/20` + `coupon_684_10` again in Fiberon PA6-CF20 beside the PET-CF control, measured dry and after 3–5 days in room air; the decision rule (idler + road discs → PA6-CF if the conditioned fit holds; sprocket stays PET-CF).
- `slice.py`: MATS "PA6-CF" = Ben's fpv250 calibrated user preset on the 0.4 hardened nozzle (not Bambu's PA6-CF profile, a different material), ρ 1.17; `--mat` slices a part in another material into `<part>@<mat>` files and records. Idler 28.5 g / 1 h 08 each, road disc 2.5 g / 13 min; G-code header: 290 °C, plate 50 °C, fan 0, flow 0.97, ρ 1.17, 0.4 nozzle.
- print-bom: the slicer route + a 60 % 🟡 conditioned derate until the coupons say otherwise. 0 g, no geometry.
- Note: SW rebuilds now take ~45 min (were ~25); SW has been up since 06:40 yesterday. A restart (Ben's) may bring that back.

## tick 84 · T13 belt print package sliced headless · accepted (tool) · 2026-11-02 10:55 MST
- `slice.py`: the drivetrain exports join PARTS (SRC → `CAD/exports/rnd/drivetrain`); qty 0 marks a test piece (out of the robot total). Aliases: `belts`, `tests`, `m6`.
- Rebuilt the drivetrain exports (bars_stagger tread) and wrote `belt_shrink0.56.stl` (Ø133.6 × 36, the 0.56 % strip-1 shrink); `drivetrain.py build` then dies in its matplotlib preview (not in the venv), after the STLs.
- Sliced (TPU = Ben's belt presets, 0.6; coupons PET-CF): **belt 59.9 g / 7 h 11 × 2**, strip 17.3 g / 1 h 55, lug6 10.4 g / 1 h 19, ttbore / 624 / 684 coupons 1.3–1.6 g / ~9 min, band slice 11.1 g / 28 min. No header mismatches. `.3mf` per piece in `CAD/exports/print/`.
- Robot total with the belts: 623.1 + 119.8 = **742.9 g filament, 26.2 + 14.4 h** (the belts' 14.4 h; the coupons are separate). belt_print.md updated.

## tick 85 · P6e canopy rear edges: vent slots r 0.5, apron corners r 1 · accepted · 2026-11-02 11:50 MST
- From the canopy edge audit (tick 75): r 0.5 on the 26 vent slots' outer edges (`filletface x:-1 … loops:` on the rear face, 104 edges, −40.4 vs −39.5 mm³) and r 1.0 on the rear apron's two outer vertical corners (−6.5 / −6.5 vs −6.2). `canopy_rear_edges()`.
- Rebuild **0 interferences**, printed 662.9 g. **S8 (PC)** 22.53 MPa (=), heel 1.44 mm (=); **S5k (PC)** 9.53 MPa (=), lugs 0.765 mm (=).
- Canopy accessible sharp edges **1,205 → 405 mm**. Left: the hood's inner front edge (over the bulkhead top: not reachable, rule to refine), the side tongues' corners (in the plate slots), the apron's bottom edge (on the plate). Shots `shots/1-P6e/*_t85.png`.

## tick 86 · bulkhead speaker-grille slot edges r 0.5 · accepted · 2026-11-02 12:50 MST
- The bulkhead's biggest accessible sharp cluster (edgeaudit 330 mm at (78, 23, 27)) was the 6 grille slots' face-side edges, left square in tick 59 (2 wide: r 1 rounds through). r 0.5 pre-tilt with `filletface x:1 … loops:` round the grille (24 edges, −20.4 vs −20.1 mm³).
- Rebuild **0 interferences**, printed 662.9 g. **S5c** 7.48 MPa (=), bezel 0.265 mm (=). Bulkhead accessible sharp 684 → 309 mm; left: the lower front band at z 0–9 (x 85: the foot's front edges on the plate, 74 + ~160 mm in short runs) and the knee pad (66, 7, 4).

## tick 87 · bulkhead foot front edges r 1 · accepted · 2026-11-02 14:15 MST
- The foot (x 78.5–85, |y| 29.5, z 0–9) stands ~2.4 proud of the 15°-tilted wall at its top, leaving a square top front edge (59 mm) and two vertical front corners (9 mm each) on the face side. Listed with `edges|box` (11 edges), then one r 1.0 feature on the three (−16.1 vs −16.5 mm³). The bottom edge sits on the plate.
- Rebuild **0 interferences**, printed 662.9 g. **S5c** governing (screen) case 7.48 MPa (=), bezel 0.266 mm (=); its secondary bezel-load case 3.11 → **4.30 MPa** in the foot probe (the fillet's corner blend next to the fixed foot underside; SF still > 8). **S5** standalone 38.8 MPa (= ~39, Q19 context). Accepted on the governing numbers; the case-level rise is recorded here. Bulkhead accessible sharp 309 → 236 mm; left: edges at z 0–1 on the plate line (sit on the plate) and the knee pad (66, 7, 4, behind the wall).

## tick 88 · plate canopy-tongue slot belly edges r 0.5 + part cache · accepted · 2026-11-02 17:00 MST
- r 0.5 on the two tongue slots' belly edges (28.2 × 2.0: r 1 rounds through), `filletface -1 … loops:` (4 edges each, −3.30 vs −3.24 mm³). Rebuild **0 interferences**, printed 662.9 g.
- **S1m 9.22 MPa** (9.97), **S1b 3.45** (3.71), **S1a 11.37** (11.63): all at the same singular corners as before, all a little lower (re-meshing).
- **Part cache** (`chassis.py` `cache_parts`, swbuild `mass|`): each part block is hashed with swbuild.cs; unchanged parts whose file exists aren't rebuilt (their MASS line is read back) and their STL isn't re-exported; asm, interference and shots always run; `rebuild --full` ignores it. Seeded by this full build (SW took ~60 min for it; it had crept from ~25 since yesterday: a SW restart is Ben's call). Build timeout 2 h.
- The R3 label's grooves now show in the plate audit (109 mm at (−1, −3, −4)): 0.6 deep engraving, not a hazard; the audit counts any sharp edge.

## tick 89 · D6 follower-slide fit coupon · accepted · 2026-11-02 17:40 MST
- Two native parts (not in the assembly or the robot mass): `RB-CPN-001_slide_strip` (52 × 60 × 4 plate section, three guide-slot pairs 4.5 / 4.7 / 4.9 wide at the real 11 mm spacing and rail+travel length, each with its M3 clamp slot and its width engraved) and `RB-CPN-002_slide_rail` (the carriage foot section: 20 × 20 × 4 foot, two 4.0 × 3.6 rails, M3 clamp hole). Slide the stub in each pair: the narrowest free slide over the full travel sets GUIDE_W (now 4.7).
- Built to their expects (8,407.5 / 2,139.7 mm³), STL to `exports/gen`, sliced: strip 9.8 g / 26 min, rail 2.5 g / 11 min (`just cad-slice --only slide`).
- **Part cache, first use: 22 unchanged parts skipped, rebuild 2 min** (was ~60). Totals unchanged (662.9 g) from the read-back MASS lines; 0 interferences.
- D6 left: the insert ladder (needs the M3 insert dims, M3) and the motor-hole pair (the TT's holes are 🟡 until measured).

## tick 90 · D1b retry: jack block r 3 corners + r 2 tangent root · REJECTED · 2026-11-02 18:20 MST
- Vertical corners r 3 first (4 edges, −77.3 mm³ exact), then the root as one tangent loop of 4 lines + 4 arcs, r 2 with the `curve` fillet mode (8 edges, +33.2 / +34.0 vs +31.6). Rebuild 24 min (plate + its FEA copy rebuilt, 22 parts cached), 0 interferences, 662.7 g.
- 2 mm mesh: **S1m 9.22 → 8.41 (−9 %), S1b 3.45 → 2.93 (−15 %), S1a 11.37 → 11.60 (+2 %, peak elsewhere)**. Half-mesh S1b: **23.0 MPa** at (−35.0, −30.9, 1.3), the toroidal blend face's tangent seam with the straight run. The coarse gain doesn't converge; the blend seam is a worse singularity than the square root (4.97 half mesh).
- **Rejected**, generator reverted (comment records both tries). D1b closes for the jack blocks: their roots stay square; the S1 peaks there are singular and SF is judged on converged measures (07 §3).

## tick 91 · P13c/P13d road axles carried by the track frame (Q24 a) · accepted (Q28 for the cost) · 2026-11-02 19:30 MST
- SW restarted by Ben (18:40): the restore rebuild took **7 min** (24 before), part-cached rebuilds now 1–7 min.
- `road_axle_carrier(side)`: per axle an r 5 boss below the side plate's z −10 edge round a Ø4.1 bore; one 5 mm **shelf** over both outer discs (z 1.6–6.6, 1.0 over the disc tops), from the plate's inner face to the lug row; a **4 mm blade** per axle dropping from it between the discs (3.1 to each) into the lug row, its bottom 1.0 over the lug tips (z −13.4), carrying the axle mid-span in a second Ø4.1 bore. The road-axle envelope's Ø7 spacer is now two tubes either side of the blade.
- New study **S9** (fea.py): left frame held at the sprocket dowel and the idler slot, each road axle +10.3 N (¼ × 1.4 kg 🟡 × g × 3) as a remote load through its two bores. Iterations (rebuild 1 min + S9 ~5 min each):
  - 3 mm arms, 2.4 plate: **22 MPa (arm root) / 1.24 mm**; the plate twists (load 20 mm inboard), uy −0.85.
  - 5 mm shelf + 4 mm blades: 17 MPa / 0.82 mm, and 2 interferences (shelf corner on the sprocket rim, 3 mm³): carrier ±6 → ±5 in x.
  - + frame plate 2.4 → 3.6 (outboard): **0 interferences, bores 0.33 mm (< 0.5), blade 9.5 MPa (SF 3.7)**; peak 12.2 MPa at the idler slot's edge next to the restraint (fixture-adjacent).
- Cost: frame 18.9 → **35.8 g** each, printed **662.9 → 696.5 g**, +1.2 mm width per side → **Q28** (default: keep). Frames now print outer face down with tree support: 43.8 g / 1 h 45 each sliced (was 18.5 g).
- Open: 07 §3.4 amendment (S9), S2 pinch re-check of the side plate's bottom edge near the bosses.

## tick 92 · P7 speaker pocket on the bulkhead + grille re-centred (Q25 a) · accepted · 2026-11-02 20:40 MST
- Free depth behind the wall mapped by ray-casting the left mount, motor and face envelopes (+ the bulkhead) along the tilted wall's back normal: y 7–27 / z′ 10–46 is open (≥ 24 mm, mostly unbounded); the left mount starts at y ≈ 28 (8–10 mm there). So the module goes beside the mount, not in front of it.
- Bulkhead (pre-tilt, back face): a 1.6 rim standing 7.2 off the wall (gasket 1 + module 6 + 0.2) round a 30.6 × 20.6 pocket for a 🟡 30 × 20 × 6 sealed 8 Ω module (`SPK_MOD`), centred y 16, z′ 26; two M3 insert bosses above it (y 9 / 23, z′ 46.9) for the clamp plate (no room below or beside). First build: the bosses' tangent contact with the rim gave a null feature → 0.6 overlap.
- S5c with the old Ø34 grille: **7.48 → 9.02 MPa** (+21 %), peak where the rim crossed the bottom slot (78.1, 27.9, 14.5). **Grille re-centred on the module**: six equal slots y 7.5–24.5 (`BH_GRILLE_HALF` 8.5), all inside the pocket. Then **S5c 6.12 MPa (−18 % vs 7.48), bezel 0.164 mm (0.266)**. S5 standalone 38.8 → 50.5 MPa at the horizontal rib's end against the top boss (65.4, 4.2, 46.7): reported only (Q13: S5c governs).
- Bulkhead 47.2 g (+2.5), printed 699.6 g, 0 interferences. S5/S5c now carry `hotspots 5` and a `speaker` probe. Next: the clamp plate (P7 part) + TPU gasket (P8). (Tooling slip: one run was started with a bare `&`; checked by file, not left orphaned.)

## tick 93 · P7 speaker clamp + P8 gasket (+ module envelope) · accepted · 2026-11-02 21:00 MST
- `RB-PRT-060_speaker_clamp` (PET-CF, 2.0 g): 1.6 plate over the pocket rim and both boss faces, two Ø3.4 holes for M3 × 8 into the bosses' inserts, a 0.15 pad meeting the module's back. `RB-PRT-061_speaker_gasket` (TPU 85A, 0.2 g): 1 mm ring, 2 mm band, between the module face and the wall round the grille. `speaker_module_envelope` (library, 🟡 30 × 20 × 6). All modelled in the bulkhead's pre-tilt frame and placed with `speaker_tilt()` (15° about BH_PIVOT); the tilt was confirmed by the parts seating in the pocket.
- Interference: the plate's outboard edge hit the left mount's end-stop corner (3.6 → 1.2 → 0.0 mm³ as it was trimmed). Located by sampling the clamp's volume against the mount STL (pre-tilt y 26.4–26.9, z′ 23.5–25.3); fixed with a notch (edge back to y 25.6 over z′ 21–28, still over the module's edge at 26.0). **0 interferences**, printed **701.9 g**.
- Sliced: clamp 2.0 g / 10 min (flat, pad up), gasket 0.5 g / 9 min (TPU). Assembly: module face-down into the pocket on the gasket, clamp over it, 2 × M3 × 8 into the bosses (A2 SHCS; 07 list: +2 M3 inserts, +2 M3 × 8).
- P8 left: mic grommets × 3 (mic-disc dims 🟡), motor-lead strain relief (R2b).
