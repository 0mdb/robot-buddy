# Questions for Ben

The loop adds questions here and moves on. Answer inline (`**A:** …`); the next tick picks it up.

## Answered (2026-10-30)
- **Q1 Age band.** **A:** 6–12. → Sharp-edge/point rules apply in full (ASTM F963 tests them for under 8). The under-3 small-parts cylinder is not a hard rule, but loose bits stay screw-captive because of younger siblings.
- **Q2 Material.** **A:** PET-CF or PA6-CF (fpv250's Fiberon PA6-CF20) for structure; PETG for fit/test prints. Bambu **white PC** is a candidate for the shell/canopy (added later the same day). → The loop picks per part by FEA + toughness (workstream M) and records the choice as a 07 amendment.
- **Q3 Integrated motor mounts.** **A:** Acceptable. → A1 may replace the baseline if the variant wins on the metrics.

## Open (2026-10-30; the loop uses the default until you answer)

- **Q4 Motor mount fix** (S2 fails: 41–46 MPa vs 11.7 allowable, because the drive gear sits 39 mm outboard of a 3 mm upright).
  Options: **(a) outboard axle support**, a bracket and bearing outboard of the gear so the gear is carried on both sides (recommended: removes the cantilever and the side load on the TT gearbox); (b) a thicker upright (6 mm) + root fillet only (simpler, lands near the limit); (c) integrated mount (A1) as a variant either way.
  **Default: (a)**, with (c) built as a variant later.
- **Q5 Face-board link: side USB-C cable or back UART connector?** `docs/face-uart-transport.md` is still "decision pending". It decides the bulkhead's cable exit. UART (back JST, 4 wires, powers the board too) is cleaner in the bulkhead; USB-C needs ~25 mm of side clearance for the plug. **Default: leave room for both**, so the bulkhead doesn't block either.
- **Q6 Camera: which module, and where?** `CameraMount1` exists, but the spec doesn't name the camera. **Default: Pi Camera Module 3 (25 × 24 mm board) centred above the screen, looking straight ahead**, on the bulkhead. Say if it's a different camera or should sit elsewhere (e.g. low, for obstacle work).
- **Q7 Screen tilt and height.** 06 §5 says 15° back; the face centre provisionally sits ~68 mm above the plate. **Default: keep both.**
- **Q8 Tracks: the kit's tracks or printed TPU?** The 44.2 mm measurement suggests the kit's. **Default: kit tracks**, nothing printed.
- **Q9 Superseded CAD files.** `RB-ASM-100_chassis`, `bottom_plate`, and (once P2 lands) `TT_Motor_Mount_L` / `MirrorTT_Motor_Mount_L` are replaced by generated parts. Delete them, or keep them for reference? **Default: keep; the loop never deletes them.**
- **Q10 Layout changes already in the plate.** Rear corners narrowed to 92 mm behind x −27 (the track hangs ~6 mm inboard of the gear, so the follower wheel would cut the edge); reflex board moved between the motors (0.7 mm to the encoders). **Default: accepted.** Say so if either is a problem.
- **Q11 Loop stop time.** **Default: 2026-10-31 07:00.**
- **Q12 Carry handle?** Kids will pick it up by the face or the tracks unless there's something better to grab. A recessed grip in the canopy's rear or top is cheap now and hard to add later. **Default: the loop proposes one in E1 with a render; nothing is built until you choose.**

- **Q13 Which restraint does the bulkhead poke test (S5) use?** 07 §3.4 holds the bulkhead only at its foot screws. A 122 mm wall on a 6.5 mm-deep foot can't meet 0.5 mm that way, even with a knee gusset (39 MPa / 8 mm). The canopy screws to the bulkhead's top lugs and a child can't reach the screen without the canopy on; with the lugs held it passes easily (7 MPa / 0.27 mm). **Default: S5 is judged with the canopy fitted (S5c); the standalone number is reported, and the canopy design (P6) must hold the lugs at least that stiffly.** Alternative: require standalone too, which needs a deeper base or side cheeks over the motors (heavier, crowds the front).

## Measurements wanted (not questions; each replaces a 🟡 assumption)
- Track tension at set-up (spring scale). Every S1 and S2 number scales with it (fea.py `TRACK_T` = 20 N).
- TT gearbox width across the screw holes, and the encoder housing's size (the 323 / 197 mm³ envelope overlaps).
- UPS HAT / NVMe adapter overhang beyond the Pi's 85 × 56, and where the HAT's USB-C and switch sit.
- M2.5 / M3 insert stock: OD × length (07 §4.2).
- CE40P-8 frame size and mounting holes, once in hand; XVF3800 Flex boards (audio §7 step 7).
