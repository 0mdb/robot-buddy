# Robot Buddy — Materials, Fasteners, FEA — Rev 1

**Status:** 2026-10-30. Companion to `06_frame_design_spec.md` (layout) and
`docs/print-dfm.md` (print rules). Method and lessons carried over from fpv250:
`~/fpv250/fpv250/docs/simulation.md`, `docs/fasteners.md`, `docs/tolerances.md` §5.5.
Values marked **[TDS]** are Bambu technical data sheets (their own printed
specimens, 100 % infill: use them for comparison, not as guarantees);
**[calc]** are worked here; **[assumption]** are flagged.

## 1. Modelling conventions (SolidWorks)

Use the standard features, driven from **global variables**
(Tools → Equations) so a rule change is one edit:

| Variable | Value | Used by |
|---|---|---|
| `wall` | 2.4 (PET-CF/PC), 1.8 (ASA canopy) | **Shell** thickness |
| `rib_t` | 1.2 | **Rib** thickness (≤ 3 × `rib_t` tall unless filleted/tapered) |
| `fil_in` | 1.0 (2.0 at load roots) | internal fillets (PET-CF is notch-sensitive) |
| `ins_m3_hole`, `ins_m3_depth` | 4.0, 7.2 🟡 | heat-set pockets (coupon decides, §4.2) |
| `ins_m25_hole`, `ins_m25_depth` | 3.6, 7.2 🟡 | " |
| `boss_m3_od`, `boss_m25_od` | 9.2, 8.0 | ≥ 2 × insert OD |
| `clr_m3`, `clr_m25` | 3.4, 2.9 | clearance holes |

- **Mount Boss** (Fastening Features) for every insert boss: hole = `ins_*_hole`, depth =
  `ins_*_depth`, OD = `boss_*_od`, with fins (gussets) on any boss taller than 2 × OD.
- **Hole Wizard** for clearance holes and counterbores (ISO SHCS / ISO 7380 button head).
- **Shell** for the bulkhead and canopy; **Rib** for plate, bulkhead and canopy stiffening.
- Heat-set axis along **Z** in the print orientation (pressed from the top; fpv250 rule).
- One body per printed part; model at nominal; compensation only in holes and fits (print-dfm).

## 2. Filaments on hand: evaluation

| Material | E X-Y / Z (MPa) | UTS X-Y / Z (MPa) | Heat (HDT 0.45 MPa) | Verdict for buddy |
|---|---|---|---|---|
| **PET-CF** (Bambu) | **4730 / 2160** [TDS] | **74 / 35** [TDS] | 205 °C (annealed figure on the TDS; as-printed lower) | **Structure:** plate, bulkhead, Pi deck, motor mounts, follower carriages. Stiffest we have, low moisture uptake. Brittle (4.5 % elongation) → fillets, no snap fits. |
| **PC** (Bambu) | 2110 / 1450 [TDS] | 62 / **56** [TDS] | ~115 °C [assumption] | **Best Z strength by far** (56 vs PET-CF 35) and tough. Use where a part is loaded *across* layers and can't be reoriented, or takes shock: **follower wheels and motor mounts are candidates if PET-CF cracks.** Warps in thick sections; enclosed, dried. |
| **ASA** (Bambu) | 2450 / ~2120 | ~37 / ~31 (third-party sheet matching Bambu's E/HDT) | 100 °C [TDS] | **Canopy** and handled covers: tough, heat-safe over the Pi 5. Takes heat-set inserts (solid ASA, not the Aero foam). |
| **PETG** (SUNLU, Polymaker) | ≈1460 / 1120 (Bambu PETG Basic as proxy) | ≈48 / 39 | ~70 °C | **Fit-test prototypes** (geometry only: about a third of PET-CF's stiffness, so don't judge stiffness on a PETG print). **Speaker back box** (seals well). Transparent: light pipes. |
| **PLA** (Bambu Basic, Glow, Wood) | 2680 / 2160 [TDS] | 39 / 35 [TDS] | ~55 °C | **Accents only**, bolt-on, away from the Pi and motors. Not structure, not near heat. |
| **TPU 85A** (Bambu) | very low | ~12 | — | Mic grommets, speaker gasket, bumpers, feet; tracks only if printed. |

**Correction to 03 §1:** its deflection check used E = 5320 MPa, which is PET-CF's
**bending** modulus. FEA uses Young's modulus: **4730 X-Y**, with a knockdown (§3.2).

**Spool budget (PET-CF, 1 kg):** plate ~100 g, bulkhead ~60 g, Pi deck ~30 g, mounts +
carriages ~60 g → **~250 g per robot**, enough for one remake. Buy a second spool before the
final print run. ASA canopy ~150–200 g of 1 kg.

> Amendment (loop M2, 2026-10-31): **material per part, pass 1.** From `docs/cad/fea/m1_materials.md` rescaled to the current stresses (S1m 8.64, S2 6.63, S1d 8.93, S5c 7.52, S6 6.83 MPa) with conditioned PA6-CF (E 2.0 GPa, Z UTS 27 🟡):
>
> | Part | Material | Why |
> |---|---|---|
> | Plate RB-PRT-001 | **PET-CF** | stiffness rules: wet PA6 would move the axles 1.7 mm (S1m; PET-CF 0.90, Q17) |
> | Bulkhead RB-PRT-002 | **PET-CF** | wet PA6 puts S5c's bezel at 0.50 mm, on its limit |
> | Pi deck RB-PRT-003 | **PET-CF** | wet PA6 SF 3.0 on S1d, no margin |
> | Motor mounts RB-PRT-010/011 | **PET-CF** (PA6-CF the fallback if one cracks in drop tests) | wet PA6 passes (SF 4.1, 0.08 mm), but the motor screws clamp through it: PA6 creeps and loses preload when wet (fpv250's clamp lesson), and it sits next to the motor can |
> | Carriages RB-PRT-030/031 | **PET-CF** | held by the jack-screw preload and the clamp: creep again |
> | Sprocket / idler RB-PRT-020/021 | **PET-CF** (08) | the D-bore and the 624 seats need dimensional stability; PA6 swells 0.035–0.07 mm/side |
> | Canopy | PC or ASA (M4 open) | toughness and heat over the Pi; no CF on handled faces |
> | Future impact parts (bumpers, track guards) | PA6-CF candidates | toughness, no clamped joints |
>
> One structural filament this pass: one spool, one calibrated profile. PA6-CF stays on the table where a part is hit rather than clamped.

## 3. FEA plan (SolidWorks Simulation, as in fpv250)

### 3.1 Tooling

Port `~/fpv250/fpv250/design/swsim.cs` to `tools/swsim.cs` (C# 5, `[STAThread]`, interop
DLLs beside the exe, SolidWorks started by hand, one COM client). Keep the fpv250 lessons:

- Read stress back on **named hot-spot faces in batches of ≤ 10** (`GetStressForEntities`), never the whole mesh.
- An all-zero force is refused; unloaded cases get 1 µN.
- Check every body has nodes (a body that won't mesh drops out silently).
- Pin each study to the part's STEP sha256; write results to CSV.
- **Convergence:** halve the mesh-control size once; top-5 hot spots must move < 10 %.

> Amendment (loop, 2026-10-30, tick 6): **singular peaks are not used for SF.** A peak
> that rises > 10 % when the mesh is halved sits at a re-entrant corner or a load-coupling
> edge (S1a pockets +20 %, S2 v2 insert/gusset roots +17.5 % / +33 %). Until parts carry
> real fillets (backlog T7), a strength verdict uses converged quantities (deflection,
> comparison against the previous geometry on the same mesh), and the SF ≥ 3 check is
> re-run once T7 lands.

### 3.2 Material model

Linear isotropic, per part material:

- **Stiffness:** E = **0.8 × E X-Y** [assumption: perimeters/infill and layer-line
  compliance]. PET-CF 3780 MPa, PC 1690, ASA 1960. ν 0.35.
- **Strength:** judge peak von Mises against the **Z** tensile strength wherever the stress
  crosses layers (bosses, uprights, roots), else X-Y. Static safety factor **≥ 3**; sustained
  loads (preload, standing weight) ≥ 5 for creep.
- Results are **comparative** first (geometry A vs B, feature vs feature), absolute second.
- Print structural parts to match the model: **≥ 4 walls, ≥ 40 % gyroid**, solid around inserts
  (slicer modifier).

### 3.3 Mass (for loads)

[assumption, update from the assembly's Mass Properties]: Pi 5 + NVMe + UPS HAT + 2 × 18650
~260 g; motors ~100 g; tracks + wheels ~120 g; plate + bulkhead + deck ~200 g; canopy ~180 g;
face, audio, misc ~150 g → **m ≈ 1.0 kg**, W ≈ 10 N.

### 3.4 Load cases and pass criteria

| Case | Part(s) | Load | Restraint | Pass |
|---|---|---|---|---|
| **S1 Track tension** | Plate + motor mounts + follower carriages | T per track, both sides: 20 N [assumption, measure with a spring scale at set-up], at the shaft / axle | Inertia relief, or fix the far end | Shaft/axle deflection **< 0.2 mm**; F4b jack end-stop ≤ Z / 3 |
| **S1m Track tension, plate + mounts bonded** (T10) | Plate with both mount v2 bodies merged (`CAD/fea/FEA-plate_mounts`) | as S1, remote at each belt centre, into each mount's motor face + inserts | Jack-screw bores | Axle (insert) displacement **< 0.2 mm**; ≤ Z / 3. Supersedes S1a for verdicts (S1a's pocket coupling over-reads stress, under-reads bending) |
| **S2 Drive torque** | Motor mount upright | Stall torque reaction 0.25 N·m [assumption, Yahboom 1:48 TT] + S1 | Mount foot at the 2 M3 | Upright root ≤ Z allowable / 3 |
| **S3 Pick-up by the canopy** | Canopy + its 4 inserts | 3 W = 30 N through the canopy (the whole robot hangs from it) | Hand grip region on canopy sides | Insert pull-out ratio ≥ 3 (§4.3); canopy ≤ Z / 3 |
| **S4 Hand press on top** | Canopy | 100 N on a Ø40 patch on the top centre | Canopy screw bosses | Deflection < 3 mm (clearance to the stack); stress ≤ UTS / 2 |
| **S5 Poke the screen** | Bulkhead | 50 N normal to the face TFT bezel | Bulkhead foot screws | Deflection < 0.5 mm; ≤ Z / 3 |

> Amendment (loop, 2026-10-30): S5 is judged with the canopy fitted (lugs held, study S5c) per the Q13 default; standalone is reported only. Standalone rev 2: 39.1 MPa / 8.0 mm; S5c: 7.0 MPa / 0.27 mm. Old → new restraint: foot screws → foot screws + canopy lugs. Why: the screen can't be reached with the canopy off.
| **S6 Drop** | Whole assembly | 0.75 m table drop, as 20 g quasi-static on each heavy mass (stack, motors) in turn [assumption] | Contact face fixed | Comparative: find the weakest joint; nothing above Z UTS. Confirm with a physical drop of the PETG prototype |
| **S7 Modes** | Plate + deck + stack | Free-free | — | First mode clear of motor/gear excitation (report; no hard target yet) |

Run S1, S2 and S5 on the plate/mount/bulkhead **before** the first PET-CF print; S3, S4 with
the canopy. Fillets and ribs are added *after* the first S-run picks where they go (fpv250's
"simulate first, then fillet, then print").

> Amendment (loop P2o, 2026-10-31, Ben, Q17 (a) + (b) / Q20): **S1 axle deflection (0.2 mm) is judged on the drive-torque increment**, not the static tension. Why: the jack screw sets the belt tension after assembly, so the static bend is tensioned out; only the tight-side excess from motor torque moves the axles while driving. Increment = AXLE_F − 2 × TRACK_T = 48.7 − 40 = 8.7 N per side → S1m's 1.03 mm × 8.7 / 48.7 = 0.18 mm without the track-frame bars, **~0.09 mm with them** (they take ~half, statics, tick 54). Static value reported only: ~0.52 mm with the bars. Old → new: static S1m vs 0.2 mm → increment vs 0.2 mm.

> Amendment (loop P6c, 2026-10-31, Ben): **new S8 Heel on the canopy** (the loop's "S7" in BACKLOG/S4; renamed, 07's S7 is the modes run). Canopy alone, held at its 4 screws (lug holes, rear insert pockets, apron feet); **150 N on a Ø30 pad in a rib cell of the top; < 1.7 mm** (canopy top 95, Ben: the 4 mm rib bottoms sit 3.2 mm over the Pi stack top at z 86, so 1.5 mm stays clear; at 300 N the ribs may touch the HAT top, accepted); SF ≥ 2 on the XY UTS** (skin and ribs bend along the layers, printed open side down). 300 N (a full heel) is reported ×2 as a no-break check (SF ≥ 1). Old → new: 300 N / SF 3 / < 10 mm (S4's draft, which assumed 13 mm over the cells). Why: a 1.8 shell held at 4 screws reached only 3.4 mm / 50.7 MPa at 300 N after three revisions (rib grid, top 93 → 97, two keels); posts to the frame or a 2.4 skin were the alternatives. S8 at 150 N is stricter than S4's hand press (100 N on Ø40), which it supersedes for the canopy top.

## 4. Fasteners

### 4.1 Standards

**Selection rule (Ben, 2026-10-30): the best fastener for each joint; buy what's missing.**
Ben has a wide M2/M3/M4 range on hand, so stock doesn't constrain any choice.

- Screws: **A2 stainless SHCS ISO 4762** inside (strength is never the limit into plastic;
  A2 doesn't rust or stain). **ISO 7380-2 flanged button head** on the canopy outside: the flange
  spreads load on the ASA without a loose washer, and nothing sharp stands proud where kids touch.
- Inserts: **Ruthex** brass heat-set, tapered knurl: **M3 × 5.7** (RX-M3x5.7) and **M2.5 × 5.7**
  (RX-M2.5x5.7). Consistent geometry and a published hole spec, which the coupon (§4.2) starts from.
  Amazon.ca stocks both.
- **No M4.** No joint needs it: M3 inserts carry ~820 N pull-out against single-digit-newton
  working loads, and an M4 insert needs a ~11 mm boss that doesn't fit the walls.
- **M2.5 only where a board dictates it** (Pi stack, possibly FNK0104); M3 everywhere else, so
  one driver and one insert size cover almost the whole robot.
- Nuts: M3 nyloc DIN 985 where a through-bolt is unavoidable (TT motor, follower axle).
- Threadlocker: **Loctite 222 only steel-to-brass on motor-side joints**, a small drop, kept
  off the plastic (anaerobics craze PC and ASA). None on serviced joints.

### 4.2 Insert pockets: coupon first

Placeholder geometry (typical datasheet values) until a coupon says otherwise:

| Insert | OD × L | Drawn hole | Pocket depth | Boss OD |
|---|---|---|---|---|
| M3 | 4.6 × 5.7 | 4.0 | 7.2 (L + 1.5 relief) | 9.2 |
| M2.5 | 4.0 × 5.7 | 3.6 | 7.2 | 8.0 |

Rule I1 (fpv250): drawn hole = datasheet hole **+0.00 for PET-CF**. Then print a **ladder
coupon** (drawn −0.3 … +0.3 in 0.1 steps) in **PET-CF and ASA**, press at ~245 °C (PET-CF) /
~230 °C (ASA), and pick the **largest hole that seats with no spin** at the §4.3 torque. The
coupon result replaces the placeholders, as it did in fpv250 (Ø3.1 drawn there for M2).

### 4.3 Torque [calc]

Preload F = T / (0.2 d). Insert pull-out capacity ≈ 10 MPa × knurl area (fpv250 §3):
M3 ~820 N, M2.5 ~720 N.

| Into | Max torque | Preload | Margin |
|---|---|---|---|
| M3 brass insert | **0.30 N·m** | 500 N | 1.6 |
| M2.5 brass insert | **0.20 N·m** | 400 N | 1.8 |
| M2.5 brass standoff (Pi stack) | 0.30 N·m | — | metal thread |
| M3 through-bolt + nyloc | 0.50 N·m | — | clamp on PET-CF ≤ 20 MPa bearing with a washer |

0.3 N·m is "snug with a short L-key held by the short arm". Use the preset driver from fpv250.

### 4.4 Joint table

Lengths assume the thicknesses shown. **Re-check each length against the modelled grip**
before ordering (screw engagement ≥ 1.3 d, tip ≥ 0.5 mm short of the pocket floor).

| # | Joint | Screw | Into | Grip → engagement | Qty |
|---|---|---|---|---|---:|
| F1 | Plate → bulkhead foot | M3 × 8 SHCS, up from below | M3 inserts in bulkhead foot | plate 4 → 4.0 | 3 |

> Amendment (loop D5b, 2026-10-31): F1's three bulkhead-foot screws are **low-head M3 × 8 (DIN 7984) with no counterbore**: at x 81.5 an Ø6.5 counterbore left 0.25 mm to the plate's front edge. The knee screw (61, 2.4) keeps its counterbore.
| F2 | Motor mount → plate | **M3 × 8** SHCS + ISO 7089 washer, down from the top | M3 inserts in plate under-bosses (plate 4 + boss 4) | foot **3.0** (measured) → 5.0 | **8** (4 per mount) |

> Amendment (loop D5, 2026-10-31): F2's insert pockets in the plate under-bosses are **6.7 deep** (not 7.2): the plate + boss stack is 8 mm, so 7.2 left a 0.8 mm floor a hot insert could push through; 6.7 = insert 5.7 + 1.0 for melt, floor 1.3.
| F3 | TT motor → mount v2 | **M3 × 28 SHCS** through the motor into **M3 inserts pressed through the 6 mm upright** from the motor face (amended tick 6: no nuts, which used to sit against the foot) | M3 inserts | motor 22.6 → 5.4 | 4 |
| F4 | Follower axle + clamp | per `05_follower_spec.md`: Ø4 shoulder bolt (M3 thread) as the axle; clamp M3 × 16 SHCS + washer + nyloc from below | — | — | 2 + 2–4 |

> Amendment (loop R2a, 2026-10-31): the carriage clamp is an **M3 × 12 SHCS up from under the plate into an M3 insert in a boss on the carriage foot** (05's option), not M3 × 16 + nyloc: the nut sat blind under the plate and made a track swap a two-tool job (R2, `docs/cad/loop/R2_service.md`).

> Amendment (loop P13a, 2026-11-01): 08 rev 1 drops the idler axle 13.5 → **10.5**, which put the axle bolt's head (pedestal inboard face, Ø8, z 6.5–14.5) into the clamp-insert boss (z 4–10). The clamp insert is now **pressed up from the carriage foot's underside** into an open Ø9.2 boss (top z 6.0), and the clamp screw is **M3 × 12 → M3 × 10** (tip flush with the boss top; a 12 would reach into the bolt head). The clamp then pulls the insert's brass face onto the plate. S6 7.57 → 6.50 MPa.
| **F4b** | **Follower tension jack** (new) | ~~M3 × 20~~ **M3 × 30 SHCS** (A2) in an M3 insert in a plate end-stop, tip bearing on the carriage (cup point: set screw ISO 4029 if preferred) | M3 insert, axis along X | screw sets tension; clamp only locks | 2 |
| F5 | Pi deck → plate posts | M3 × 8 SHCS, down from the top (service with the canopy off) | M3 inserts at post tops | deck 3 → 5 | 4 |
| F6 | Pi stack → deck | M2.5 × 6 SHCS, up through the deck | the existing **6 mm brass standoffs** | deck 3 → 3 | 4 |
| F7 | Reflex board → plate standoffs | ~~M3 × 6~~ **M3 × 8** SHCS (A2) | M3 inserts in 5 mm printed standoffs | PCB 1.6 → 4.4 | 4 |
| F8 | XVF3800 core board → plate | ~~M3 × 6~~ **M3 × 8** SHCS (A2) | M3 inserts, printed standoffs | PCB 1.6 → 4.4 | 4 |
| F9 | Canopy → body | M3 × 8 **ISO 7380-2 flanged** button head | M3 inserts: bulkhead top ×2, plate rear posts ×2 | canopy 1.8 + boss land 1.2 → 5 | 4 |
| F10 | Mic disc → canopy | M3 × 10 SHCS through TPU grommets | M3 inserts in ASA canopy bosses | PCB 1.6 + grommet 3 🟡 → 5.4 | 3 |
| F11 | Face board FNK0104 → bulkhead | ~~M3 × 6~~ **M3 × 8** SHCS (A2) through the PCB (Ø3.2 holes, **42.0 × 78.0** c-c per the ES3C28P drawing; PCB 50 × 86 confirmed by Ben) | M3 inserts in bulkhead standoffs | PCB 1.6 → 4.4 | 4 |
| F12 | Speaker box → bulkhead | M2.5 × 8 SHCS through the gasket | M2.5 inserts in bulkhead | 🟡 | 4 |
| F13 | HC-SR04 housing, camera | as their existing models (M1.6 countersunk in the HC-SR04 housing) | — | — | — |

> Amendment (loop A2, 2026-10-31): F7 / F8 / F11 M3 × 6 → **× 8** (the 7.2 pockets take 6.4 of engagement; one length fewer). F4b jack screw M3 × 20 → **× 30**: the block-to-carriage gap runs 7–17 mm over the travel plus 10 mm through the block. F12 could go M3 too (P7). Bill and driver notes: `docs/cad/loop/A2_fasteners.md`.

> Amendment (loop P6c, 2026-10-31): **canopy material = PC White (60100)** (M4 closed; Ben favoured PC, S8 decided). Heel 150 N on the ribbed canopy (top 97): PC 25.3 MPa top / 1.70 mm → **SF 2.4** on XY UTS 62; ASA 25.5 MPa / 1.48 mm → SF 1.45 on XY 37, fails SF 2. PC: dry first, enclosed, engineering plate, brim as needed. ρ 1.20 g/cm³ in the mass roll-up 🟡 until checked against the TDS.

> Amendment (loop P6, 2026-10-31): F9's two **rear** joints turn round: **M3 × 10 button head up from the belly through Ø3.4 plate holes at (−80.4, ±12) into M3 inserts in two Ø9.2 bosses on the canopy's rear apron** (pocket 7.2, 6 mm engaged), instead of inserts in plate rear posts with the head on the canopy. Why: E1 §3, no screw heads on the faces a child sees, and the plate keeps no posts. The two **front** joints are unchanged (M3 × 8 flanged button down through the hood ceiling into the bulkhead lugs); those heads sit on the hood top behind the head, visible from above (open point for E2).

**Totals (per robot, +20 % spares when ordering):** M3 inserts ~34 (F1, F2, F5, F7, F8,
F9, F10, F11), M2.5 inserts 4 (F12); M3 × 6 ×12, M3 × 8 ×15, M3 × 8 button ×4,
M3 × 10 ×3, M3 × 30 ×4 (kit), M2.5 × 6 ×4, M2.5 × 8 ×4, M3 nyloc ×8, M3 washers ×8.

### 4.5 The Pi stack (measured by Ben, 2026-10-30)

Bottom to top: 6 mm brass standoffs (M2.5, female down) → Freenove M.2 NVMe adapter → Pi 5
→ UPS HAT (B) with cells on top.

| From the adapter's bottom | Height |
|---|---|
| Top of Pi USB ports | 30 mm |
| Top of UPS HAT (stack top) | **53 mm** |
| With the 6 mm standoffs | **59 mm** overall |

**Keep the standoffs:** they give a metal thread for F6 and clear the adapter's underside.
Pi PCB height inside the stack (for side cut-outs) comes from the vendor Pi 5 model when the
envelope is built.

## 5. Measure / decide before ordering

1. Order Ruthex M3 × 5.7 (~45) and M2.5 × 5.7 (~10); everything else in §4.4 from Ben's range or bought to length.
2. Track tension at set-up with a spring scale (replaces the 20 N in S1).
