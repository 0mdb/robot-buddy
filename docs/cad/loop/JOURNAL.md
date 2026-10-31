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
