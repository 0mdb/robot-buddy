# Questions for Ben

The loop adds questions here and moves on. Answer inline (`**A:** …`); the next tick picks it up.

## Agreed 2026-10-31 (~12:00, Ben)
- **M4 canopy material: PC White (60100) favoured, ASA White (45100) the alternative.** S7 runs both; PC if it bends < 10 mm and S5c still passes (ribs under the top if needed), otherwise ASA. Ben expects PC.
  **Closed (tick 49): PC.** 150 N heel, ribbed canopy: PC SF 2.4 (along-layer), ASA SF 1.45.

## Answered 2026-10-31 (~10:40, Ben)
- **Q17 plate deflection → (b) outboard track frame.** A frame inside each belt loop carries the belt tension between the sprocket's outboard 624 and the idler axle, so the plate no longer sees it. Folds into P2o; 06 §7 gets an amendment before the CAD diverges. The S1m deflection limit stays as written until the frame exists.
- **A1 integrated motor mounts → keep them bolted.** (Integration doesn't help the deflection; a cracked mount stays a 14 g reprint.)
- **Q18 design language → (a) pebble 1 / 3 / 8.** The canopy (P6) and E2 are built to `docs/cad/loop/E1_design_language.md`.
- **Don't print the plate yet**; next leg: canopy, treads, polish.
- **Closed as settled by the work:** Q4 (mount fixed: S2 converged SF 5.3), Q8 (printed TPU), Q10 (rear relief removed, P12), Q11 (stop times set by Ben), Q13 (S5 judged with the canopy holding the lugs, S5c).
- **Defaults standing** (proposed 10:40, no objection): Q5 room for both links, Q6 Pi Camera 3 above the screen, Q7 15° / ~68 mm, Q9 keep old CAD, Q12 propose a recessed grip, Q14 crush ribs, Q15 18 pockets, Q16 road wheels + staggered pads.

## Answered (2026-10-30)
- **Q1 Age band.** **A:** 6–12. → Sharp-edge/point rules apply in full (ASTM F963 tests them for under 8). The under-3 small-parts cylinder is not a hard rule, but loose bits stay screw-captive because of younger siblings.
- **Q2 Material.** **A:** PET-CF or PA6-CF (fpv250's Fiberon PA6-CF20) for structure; PETG for fit/test prints. Bambu **white PC** is a candidate for the shell/canopy (added later the same day). → The loop picks per part by FEA + toughness (workstream M) and records the choice as a 07 amendment.
- **Q3 Integrated motor mounts.** **A:** Acceptable. → A1 may replace the baseline if the variant wins on the metrics.

- **Drivetrain review (eyes before electrons).** **A (Ben, 2026-10-31 ~06:40): reviewed, looks good.** → Sprocket RB-PRT-020 and idler RB-PRT-021 (with the S1c rim round) are cleared for test prints; belt per 08.

## Open (2026-10-30; the loop uses the default until you answer)

- **Q4 Motor mount fix** (S2 fails: 41–46 MPa vs 11.7 allowable, because the drive gear sits 39 mm outboard of a 3 mm upright).
  Options: **(a) outboard axle support**, a bracket and bearing outboard of the gear so the gear is carried on both sides (recommended: removes the cantilever and the side load on the TT gearbox); (b) a thicker upright (6 mm) + root fillet only (simpler, lands near the limit); (c) integrated mount (A1) as a variant either way.
  **Default: (a)**, with (c) built as a variant later. *Tick 6: (b) is built and accepted as the base (deflection 0.039 mm, 11× better); (a) is P2o, blocked until the drive gear's hub is measured.*
- **Q5 Face-board link: side USB-C cable or back UART connector?** `docs/face-uart-transport.md` is still "decision pending". It decides the bulkhead's cable exit. UART (back JST, 4 wires, powers the board too) is cleaner in the bulkhead; USB-C needs ~25 mm of side clearance for the plug. **Default: leave room for both**, so the bulkhead doesn't block either.
- **Q6 Camera: which module, and where?** `CameraMount1` exists, but the spec doesn't name the camera. **Default: Pi Camera Module 3 (25 × 24 mm board) centred above the screen, looking straight ahead**, on the bulkhead. Say if it's a different camera or should sit elsewhere (e.g. low, for obstacle work).
- **Q7 Screen tilt and height.** 06 §5 says 15° back; the face centre provisionally sits ~68 mm above the plate. **Default: keep both.**
- **Q8 Tracks: the kit's tracks or printed TPU?** The 44.2 mm measurement suggests the kit's. **Default: kit tracks**, nothing printed.
  **A (Ben, 2026-10-30): printed TPU system, the plan of record.** Belt, drive sprocket and idler are designed as one system and nothing is shaped to the kit track: centre-lug positive-drive TPU belt (40 lugs × 10 mm pitch, 36 wide, TPU 85A first, 95A fallback), one 18-pocket wheel (Ø54.8) shared by a D-bore sprocket and a 2 × 624 idler. Spec + generator: `docs/cad/08_tpu_track_rnd.md`, `tools/drivetrain.py` on branch `drivetrain-rnd` (commit e7d8659). → BACKLOG P11–P12; P2o unblocked; P5 rescoped. The kit numbers (44.2 track, 45.2 flange gap, Ø49.6 follower, Ø54.34 gear) are obsolete for new work.
- **Q9 Superseded CAD files.** `RB-ASM-100_chassis`, `bottom_plate`, and (once P2 lands) `TT_Motor_Mount_L` / `MirrorTT_Motor_Mount_L` are replaced by generated parts. Delete them, or keep them for reference? **Default: keep; the loop never deletes them.**
- **Q10 Layout changes already in the plate.** Rear corners narrowed to 92 mm behind x −27 (the track hangs ~6 mm inboard of the gear, so the follower wheel would cut the edge); reflex board moved between the motors (0.7 mm to the encoders). **Default: accepted.** Say so if either is a problem.
  *Q8 (2026-10-30): the TPU belt runs 1.5 mm outboard of the plate edge, so the rear relief exists only for the kit track. **P12 (tick 10): relief removed**, plate full width again; Q10's first half is moot.*
- **Q14 Idler bearing retention** (08 §5): crush ribs in the 624 pockets (coupon picks 0.10/0.15/0.20 interference) instead of 05's "slip + printed cap". **Default: crush ribs**, with the cap as the fallback if the coupon fails.
- **Q15 Wheel size** (08 §3–4): 18 pockets (Ø54.8 wheel, 9.9 mm under the plate) vs 16 (Ø48.4, 6.7 mm, about 13 % less pivot torque). **Default: 18**, for rug edges and thresholds. *(08 rev 1: with road wheels and the 3 mm raise, 18 gives 12.9 mm, or 16.9 with the bosses moved up.)*
- **Q16 Suspension and tread (08 rev 1, Ben asked for both 2026-10-30):** two road wheels per side + the idler 3 mm below the TT shaft (P13), and three printed tread variants with **staggered pads** as the default. The trade-off to accept: braking harder than ~0.15 g rocks the robot forward onto the sprocket (≤ 6°), so firmware should cap deceleration at ~0.1 g. **Default: accept**; the loop builds P13, the deceleration cap goes to TODO (reflex motion limits).
- **Q11 Loop stop time.** **Default: 2026-10-31 07:00.**
- **Q12 Carry handle?** Kids will pick it up by the face or the tracks unless there's something better to grab. A recessed grip in the canopy's rear or top is cheap now and hard to add later. **Default: the loop proposes one in E1 with a render; nothing is built until you choose.**

- **Q13 Which restraint does the bulkhead poke test (S5) use?** 07 §3.4 holds the bulkhead only at its foot screws. A 122 mm wall on a 6.5 mm-deep foot can't meet 0.5 mm that way, even with a knee gusset (39 MPa / 8 mm). The canopy screws to the bulkhead's top lugs and a child can't reach the screen without the canopy on; with the lugs held it passes easily (7 MPa / 0.27 mm). **Default: S5 is judged with the canopy fitted (S5c); the standalone number is reported, and the canopy design (P6) must hold the lugs at least that stiffly.** Alternative: require standalone too, which needs a deeper base or side cheeks over the motors (heavier, crowds the front).

- **Q17 Plate deflection under track tension (P3, tick 14).** With the motor mounts bonded on (S1m), 20 N of track tension moves the motor axles ~1 mm (0.97 mm with the new ribs; was 1.54). The 07 limit is 0.2 mm. Stress now passes (SF 3.6). Rails at axle height can't fit (0.7 mm between the reflex board and the encoders), and deeper ribs cost ground clearance.
  Options: **(a) judge S1 deflection on the drive-torque increment only.** The jack screw sets the tension after assembly, so the static bend is tensioned out. The increment (AXLE_F 48.7 N − 2 × 20 N) scales to ~0.18 mm at the inserts, which passes. (b) an **outboard track frame** inside the belt loop, joining the sprocket's outboard 624 (P2o) to the idler axle, so the belt tension never reaches the plate; best structure, but a new part and an 06 §7 change. (c) ribs 4 mm deeper (−12): ~2× stiffer, 6 mm less ground clearance.
  **Default: (a)**, recorded as a 07 amendment only after you agree; until then S1m deflection is reported as failing. (b) stays the long-term candidate, to fold into P2o.

- **Q18 Design language (E1, tick 31):** `docs/cad/loop/E1_design_language.md`. One fillet family **1 / 3 / 8 mm** (1 = every accessible edge, 3 = handled edges and openings, 8 = the silhouette), a soft "pebble" canopy with a slight crown (no big flat white panels), no exposed screw heads on the faces a child sees, openings as one slot/hole pattern, face high and proud as the "head". Options: **(a) as proposed** · (b) crisper robot look (1 / 2 / 4, chamfers, flat panels) · (c) send a reference.
  **Default: (a)**; the loop designs the canopy (P6) and E2 to it, nothing is printed before you look.

- **Q19 Bulkhead poke (S5c) with the real canopy (tick 51).** S5k: the canopy can't hold the lugs (rear apron is a hinge; side walls don't reach the plate), so the bulkhead is back to S5 standalone (8 mm vs 0.5). Options in the session; the loop waits for a pick before changing structure.

## Measurements wanted (not questions; each replaces a 🟡 assumption)
- **Drive gear hub** (for P2o, the outboard axle support): bore / D-flat, the outer face (is there a boss or recess), and whether a stub shaft or screw could be fixed on the outer side. Without it the loop can't design the outboard bearing.
- Track tension at set-up (spring scale). Every S1 and S2 number scales with it (fea.py `TRACK_T` = 20 N).
- TT gearbox width across the screw holes, and the encoder housing's size (the 323 / 197 mm³ envelope overlaps).
- UPS HAT / NVMe adapter overhang beyond the Pi's 85 × 56, and where the HAT's USB-C and switch sit.
- M2.5 / M3 insert stock: OD × length (07 §4.2).
- CE40P-8 frame size and mounting holes, once in hand; XVF3800 Flex boards (audio §7 step 7).
