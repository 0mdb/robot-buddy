# CAD loop backlog

Status: `[ ]` todo · `[~]` in progress · `[x]` done/rejected · `[blocked]` waiting on Ben (see QUESTIONS.md).
Tags: `[sw]` needs SolidWorks · `[py]` Python only · `[doc]` docs only. The loop may add, split and reorder items. Never delete an item: reject it with a reason.

Priority order for a pass: **P → T → M → S → W → D → A → R → E**. Ben (2026-10-30): "we need all the parts", so P (a first cut of every missing part) leads, rotating with T so the tooling keeps pace. Material comes next because every FEA verdict depends on it.

## P: Parts (a first cut of every part; Ben 2026-10-30)
Baseline at loop start (commit on `cad`): plate rev 1, envelopes, Ben's imported motor mounts. FEA baseline: S1a FAIL (15.8 MPa upper bound, axle UX 0.22 mm), S1b PASS, S2 FAIL (41–46 MPa, singular at the unfilleted root), S5 not run (no bulkhead). Each new part is generated in `tools/chassis.py`, volume-checked, placed in `RB-ASM-101_chassis`, and gets its FEA study where 07 §3.4 has one.
- [x] P1 `[sw]` **Front bulkhead** (06 §5): upright frame inboard of the tracks; foot with 2 locating tabs into the plate slots and 3 × M3 inserts (F1); FNK0104 standoffs on 42 × 78 with M3 inserts (F11), screen 15° back (Q7); speaker grille (≤ 2 mm openings) + back-box mount below the face (CE40P-8, audio §4.3); HC-SR04 housing seat low centre; camera seat (Q6); canopy front bosses ×2 (F9); face-board cable exit (Q5: leave room for both side USB-C and back UART until answered); ≥ 70 mm speaker-to-mic. PET-CF. Then run S5 (50 N on the bezel). Clear the motor-mount feet (6.5 mm foot strip, D4)
  **Rejected tick 2 (rev 1):** built clean (32,042 mm³ ≈ 41 g, volume within 0.4 %, no new interference) but S5 failed: screen poke 45.9 MPa / 15.5 mm, bezel push 37.7 MPa / 13.0 mm (targets 11.7 MPa / 0.5 mm). A 122 mm wall on a 6.5 mm-deep foot hinges at the foot. Generator code saved in `patches/P1-rev1-bulkhead.patch` (applies to chassis.py, fea.py with S5, 06 §5 as-built note); engine additions kept.
- [x] P1b `[sw]` **Bulkhead rev 2, braced**: apply `patches/P1-rev1-bulkhead.patch`, then (1) two knee gussets from the wall's back face down to the plate inside the |y| < 13.4 corridor between the mount feet (x ~50…78), each with an M3 insert into a plate under-boss; (2) side flanges deeper where they clear the face PCB; (3) S5 second case with the canopy lugs held (the canopy ties the top back). Target S5 ≤ 11.7 MPa, ≤ 0.5 mm standalone if possible, otherwise with the canopy tie. Also consider a level sonar seat (rev 1 tilts it 15° up)
  **Accepted tick 4 (Q13 default):** knee gusset + bolted tail pad, 43.7 g. S5c (canopy lugs held) 7.0 MPa / 0.27 mm PASS; S5 standalone 39.1 MPa / 8.0 mm (reported). S1a unchanged (15.5), S1b 2.61 → 2.88 MPa (+10 %, the new plate bolt hole; SF 12). Square edges until T7. Sonar still tilts 15° up.
- [x] P2 `[sw]` **Motor mount v2, generated** (fixes S2): new `RB-PRT-010_motor_mount_L/R` in the generator replacing Ben's imported L-bracket. Per Q4, default = **outboard axle support**: a bracket from the plate edge carrying a 625/624 bearing outboard of the drive gear, so the gear is supported both sides. Plus upright 4.8–6.0 mm, 3 mm root fillet, gusset. Target: S2 SF ≥ 3, hole deflection ≤ 0.2 mm. Keep the 4 × M3 foot pattern unless the plate changes with it
  **Accepted tick 6 (strength fix, converged measures):** v2 stiffened mount (6 mm upright, 3 gussets, root chamfer, upright inserts, motor raised to z 13.5 / pitch 17.5). Interferences 4 → 0. S2 hole deflection 0.437 → 0.039 mm (converged). Peaks 12.0 → 14.1 MPa on halving the mesh (singular: insert-coupling edge, unfilleted gusset roots); SF ≥ 3 re-judged after T7. 6.6 mm upright tried: peak unchanged, so 6.0 kept. +6.2 g per side. S1a 15.5 → 17.8 MPa (axle 2 mm higher; P3 owns it).
- [ ] P2o `[sw]` `[blocked]` **Outboard axle support** (Q4 default a): a bracket through the open middle of the track loop to a bearing outboard of the drive gear. Needs the kit drive gear's hub: bore, outer-face boss, whether a stub shaft can be fixed to it (QUESTIONS, measurements)
- [ ] P3 `[sw]` **Make S1a pass**: compare (a) side rails ~12 mm tall at axle height from the mount feet to the jack stops, (b) deeper ribs (W3). Pick by mass vs S1a deflection; refine S1a's coupling to the real foot footprint (split face) so the pocket stress stops being an upper bound
- [ ] P4 `[sw]` **Pi deck** (F5/F6): 3 mm deck on the 4 posts; M2.5 clearance on 58 × 49 for the brass standoffs; M3 clearance at the posts; vent slots; cable cut-outs to level 0. Rerun S1b with the deck in the load path
- [ ] P5 `[sw]` **Follower carriages L/R + idler wheel v2** (05, 06 §7): rails in the 4.7 guide slots, clamp boss, jack-screw bearing face, journal boss for the Ø4 shoulder axle; wheel running OD 49.6, flange gap 45.2, 2 mm flanges, 624 pocket Ø13.1, shell + ribs (the current `follower_wheel` is Ø50 × 45, near-solid, no flanges). Check the wheel clears the rear relief at both ends of travel
- [ ] P6 `[sw]` **Canopy** (06 §6): **must hold the bulkhead's two top lugs at least as stiffly as S5c assumes (fixed), or S5 fails;** uniform 1.8 shell (PC or ASA, M4), mic-disc seat with grommet bosses + Ø1.2 ports, vents over the stack, cut-outs for the UPS USB-C charge port and power switch (top of the stack), 4 × F9 bosses; no exposed screw heads on the faces a child sees (E1); tool-only opening (cells inside)
- [ ] P7 `[sw]` **Speaker back box** (PETG, sealed ~30 cc, gasket land) for the CE40P-8; mounts to the bulkhead behind the grille (F12)
- [ ] P8 `[sw]` **Small TPU parts**: mic grommets ×3, speaker gasket, motor-lead strain relief
- [ ] P9 `[sw]` `[blocked]` XVF3800 core-board mount aft between the carriages: needs the board's measured outline and holes (audio bench step 7)
- [ ] P10 `[sw]` **Full assembly**: every part placed, interference clean (except the 🟡 motor-envelope overlaps), assembly mass + CoG, hero renders (E4)

## T: Tooling (measure before optimising)
- [x] T1 `[sw]` `stl|<doc>|<out>` command in swbuild.cs; export every printed part to `CAD/exports/` on each rebuild
  **Done tick 5:** `stl|doc|out` in swbuild.cs (binary, mm, fine, chassis coordinates, no positive shift); the rebuild exports plate, bulkhead and both mounts to `CAD/exports/gen/` (Ben's originals untouched). Trimesh volumes match SolidWorks within 0.05 %. Gotcha: STL export writes the ACTIVE document, so the command activates it first.
- [x] T2 `[py]` `tools/meshcheck.py`: from the STL, report overhang area >45° (in print orientation), min wall (ray-cast), sharp convex edges (dihedral angle), bounding box vs the P2S bed, and volume → grams at the infill/wall settings in print-bom.md. Add `trimesh` to tools/pyproject.toml. **Done tick 1**: controls pass (1.0 mm slab wall, 12 sharp edges / 164 mm, cylinder rims only, floating-cube overhang 1.0 cm²); grams are solid-ρ only, as-printed grams wait for T4. Sharp-edge count includes hole rims (true unchamfered edges)
- [ ] T3 `[sw]` per-part mass/volume/CoG line in the build output, and assembly CoG
- [ ] T4 `[py]` headless slice with the installed Bambu Studio CLI: real print time, grams and support volume per part. The output is a `.3mf` per part = the "print ready" file. **Port, don't rediscover:** `~/fpv250/fpv250/docs/print-settings.md` §3 (the CLI prints nothing; it ignores `inherits` and reports success anyway, so pass flattened presets), `tools/slicemass.py`, and its calibrated P2S PA6-CF presets (`docs/print-calibration.md`). Check sliced grams against CAD volume × ρ: a mismatch means a bad preset
- [ ] T5 `[py]` `metrics.csv` writer that gathers T1–T4 + FEA into one row
- [x] T8 `[py]` **Simulation dialog watchdog**: a modal dialog from the solver process (`star.exe`, title "Simulation", e.g. "Excessive displacements … Large Displacement?") blocks the run indefinitely, with SolidWorks idle and not responding. fea.py should poll for it while swsim runs, log it, and answer **No** (keep linear results) via Win32 (`EnumWindows` → `#32770` "Simulation" owned by star.exe → BM_CLICK on "No"; the message text isn't readable cross-process, so match the KB link QA00000118617). Also raise fea.py's subprocess timeout or make it poll. Tick 2 did this by hand
  **Done tick 3:** `tools/swdialog.ps1` + `fea.run_watched` (poll every 20 s, answer the known excessive-displacement prompt No, fail on an unknown dialog after 3 polls, 3 h cap). Controls: a test "Simulation" box with the KB text was answered No (the box returned No); one without it was reported, not touched. S1b through the watchdog reproduces the baseline exactly.
- [ ] T7 `[sw]` **(priority: gates every stress verdict, see 07 §3 tick-6 amendment)** **fillet / chamfer command** in swbuild.cs: select edges by geometry (e.g. all convex edges of a body, or edges inside a box) and apply `FeatureFillet3` / chamfer, with a volume check. S1, D1 and E2 all depend on it; until it exists, every generated part has square exterior edges and fails the kid-safety edge rule (recorded per part, fixed in S1)
- [ ] T6 `[sw]` FEA S5 (drop / 10 g deck shock) and a tip/tumble load case if 07 §3 doesn't already cover them

## M: Material per part (PET-CF vs PA6-CF20; PETG = test prints only)
Data: PET-CF in 07 §2 (E 4730/2160, UTS 74/35 Z, ρ 1290, brittle 4.5 %). PA6-CF20 from fpv250 `docs/simulation.md`: E 8.6 GPa, Z 54 MPa **dry**, ρ 1180, much tougher.
**Design basis for PA6 here = conditioned, not dry.** fpv250 assumed dry filament and flight right after printing. A toy sits in a bedroom and absorbs moisture. Until measured, derate PA6-CF E and strength to ~60 % of dry `[assumption]`, and flag it in every result.
- [ ] M1 `[py]` add `PA6CF_DRY` / `PA6CF_COND` to `tools/fea.py`; run every study in both materials; table SF, deflection and mass per part
- [ ] M2 `[doc]` pick per part: PET-CF where stiffness rules (plate, Pi deck); PA6-CF where impact/fatigue or the Z direction rules (motor mounts/saddles, followers, bumpers, anything a child drops). Consider printability too: PA6 warp, drying, P2S presets proven in fpv250. Amend 07 with the choice
- [ ] M3 `[doc]` inserts in PA6-CF vs PET-CF: boss sizes per 07 §4; the insert ladder coupon (D6) gets a PA6-CF strip
- [ ] M4 `[sw]` **shell/canopy: Bambu PC (white) vs ASA.** PC (07 §2: E 2110/1450, UTS 62/**56 Z**, HDT ~115 °C) is the toughest option, heat-safe over the Pi 5, and has no CF: no scratchy fibre ends, and it doesn't shatter into sharp pieces. That suits the faces a child handles. Costs: it warps in thick or long flat sections, so keep the shell uniform at 1.8–2.4, add generous corner radii and no big flat panels; print it dry and enclosed. Run S3/S4 in PC; check insert bosses in PC; amend 07 (canopy ASA → PC) if PC wins
- [ ] M5 `[doc]` CF surface finish on any other handled face (bumpers, grab points): PC or PA6-CF there instead of PET-CF?

## S: Kid safety (ages 6–12)
Rules the loop enforces from here on (ASTM F963 / EN 71-1 / IEC 62115 as design guidance, not certification):
- Accessible edges: external radius ≥ 1.0 mm, no corners at points; no burrs from support-contact faces on handled surfaces. ASTM F963's sharp edge and point tests apply to under-8s, so this is in scope
- Fracture: a dropped or stepped-on part must not break into sharp shards. PET-CF is brittle, so impact-exposed parts favour PA6-CF (M2), or ribs/radii that stop cracks from running
- Pinch / finger traps: no accessible gap between **5 and 12 mm** that closes or moves (tracks↔sprockets, followers, canopy hinge). Guard it or make it < 5 / > 12
- Small parts: the 31.7 mm cylinder is an under-3 rule (not binding at 6–12), but younger siblings exist: anything that can come off without a tool stays screw-captive
- Battery (2× 18650 in the UPS HAT): enclosure needs a tool to open, vented, no crush path in a drop
- No accessible surface over ~48 °C (Pi 5 lid, motor cans)
- [ ] S1 `[sw]` accessible-edge audit: list every exterior edge without a fillet/chamfer per part → fix in generators
- [ ] S2 `[sw]` pinch-point audit around the track path, drive sprockets and follower slots; propose track skirts/guards
- [ ] S3 `[doc]` small-parts / removable-parts inventory (what comes off without a tool?)
- [ ] S4 `[doc]` battery access + drop path review against the Pi-stack envelope
- [ ] S5 `[doc]` thermal: Pi 5 vent path through the canopy; where hot surfaces sit relative to small hands

## W: Weight vs strength
- [ ] W1 `[sw]` baseline: mass per part + FEA SF/deflection per study → first metrics row
- [ ] W2 `[sw]` plate: pockets / isogrid between ribs where FEA stress < 20 % of allowable; keep load paths from motor-mount inserts → follower slots continuous
- [ ] W3 `[sw]` rib height/thickness sweep (keep ≤ 3× t, 0.6 multiples). Plot mass vs S1a deflection, pick the knee
- [ ] W4 `[sw]` plate thickness 4.0 → 3.0/3.6 with deeper ribs: same stiffness, less mass?
- [ ] W5 `[sw]` deck posts: fins vs hollow posts (TODO open item "fins on deck posts")
- [ ] W6 `[py]` check whether wall/infill choices in the slicer profile beat geometry changes for the same grams

## D: Stress risers, printability, DFM
- [ ] D1 `[sw]` fillet every internal corner on a load path (insert bosses, rib roots, slot ends, bulkhead foot); `fil_in` 2.0 at load roots
- [ ] D2 `[sw]` slot ends and wire slot: full-radius ends, no square ends
- [ ] D3 `[py]` print-orientation decision per part — **meshcheck (tick 5) in +Z as modelled: plate 158 cm² overhang (the underside between the bottom ribs floats 3.6 mm over the bed when printed top-up, ribs down) and a 0.07 mm min wall (p1 0.95) to locate; bulkhead 23 cm²; mounts 0.6 / 8.8 cm² (the mirror part is Z-flipped)**, written into the part list; chamfer (not fillet) the bed-side edges; teardrop the horizontal holes
- [ ] D4 `[sw]` bulkhead foot strip 6.5 mm (TODO open item): widen or re-route
- [ ] D5 `[doc]` hole-size table vs print-dfm.md (insert bores, clearance, M3 jack screws), checked against the measured insert stock
- [ ] D6 `[sw]` fit coupons: a small printable coupon per critical fit (insert ladder, motor hole pair, follower slide, bearing seat). Cheap prints that de-risk the expensive ones

## A: Simplification & integration
- [ ] A1 `[sw]` **variant**: motor mounts integrated into the plate (`RB-PRT-001b`). Compare mass, part count, fasteners, FEA S1/S2, print time, support volume, and repair cost (a cracked mount now means reprinting the plate)
- [ ] A2 `[doc]` fastener consolidation: one screw family (M3?) + one driver; count inserts and screws per assembly
- [ ] A3 `[sw]` hybrid: integrated mount saddles + bolt-on caps (repairable *and* fewer parts)?
- [ ] A4 `[doc]` part-count review across plate / bulkhead / canopy / followers: which joints exist only because of the build volume?
- [ ] A5 `[sw]` cable routing: channels, clip points, strain relief at the motor leads and the reflex board

## R: Assembly & repair
- [ ] R1 `[doc]` assembly sequence: can every screw be reached in order? Any blind or trapped fastener?
- [ ] R2 `[doc]` service tasks timed on paper: swap a motor, swap a track, swap the battery, reach the reflex USB port. Target: one tool, < 5 min each
- [ ] R3 `[sw]` embossed part numbers + revision on hidden faces (0.6 deep, 0.4 nozzle only if needed)
- [ ] R4 `[sw]` self-locating features (pins/keys) so parts only go together one way
- [ ] R5 `[doc]` spares list + which parts are consumables (tracks, followers)

## E: Aesthetics
- [ ] E1 `[doc]` design language: one fillet family (e.g. 1 / 3 / 8 mm), soft "pebble" silhouette, no exposed screw heads on the faces a child sees. Proposal → QUESTIONS for Ben's taste call
- [ ] E2 `[sw]` exterior edge radii to the chosen family (after S1)
- [ ] E3 `[doc]` colour scheme from the materials: a **white PC shell over a black CF chassis** is the default palette. Where can the black show on purpose (track guards, face bezel), and where should it hide? Any accent (AMS second colour) must not add parts. Proposal + render → QUESTIONS for Ben's taste call. White shows dirt and layer lines: favour textured or curved surfaces over large flat ones
- [ ] E4 `[sw]` hero renders each pass: iso, front-face (eye level of a 5-year-old ~40 cm off the floor), top

## Ideas parking lot (promote to an item when ready)
- Drop test from table height (0.75 m) via SolidWorks drop-test study, if licensed
- Topology study on the plate as a guide for W2's pockets (Simulation topology, if licensed)
- Tip-over angle from the assembly CoG + track footprint; a high CoG = falls over when a child pushes it
- Splash resistance: drip edges over the reflex board, no open slots on top faces
- Exploded-view assembly drawing per subassembly for the build guide
- Light pipe / status LED window (PETG translucent) integrated in the bulkhead
- Handle or grab-point so kids pick it up by the body, not the face or the tracks
- Track tension check: spring-scale measurement → replace the TBD 20 N in fea.py
