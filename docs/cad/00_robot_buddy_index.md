# Robot Buddy — Mechanical Project Index

Tracked rover. 2× Yahboom encoder TT motors driving the front, 2× rear idler followers, Raspberry Pi on top, printed in Polymaker PETG Black on a Bambu P2S.

## What's where

Consolidated into the `robot-buddy` framework repo (mechanical lives beside
firmware). SolidWorks source + exports under `CAD/`; planning docs under
`docs/cad/`.

```
robot-buddy/
  docs/
    print-dfm.md                       ← AUTHORITATIVE FDM design rules (shared w/ robot-scout)
    cad/
      00_robot_buddy_index.md          ← this file
      01_petg_bambu_profile_guide.md   ← Bambu Studio filament + 0.6 mm nozzle setup
      02_solidworks_setup_for_3dp.md   ← Templates, units, project-level setup
      03_base_plate_design_spec.md     ← First printable part — full spec to drive into SW
      05_follower_spec.md              ← rear follower = the track tensioner
      06_frame_design_spec.md          ← FRAME: 3-piece body, layout (start here)
      07_materials_fasteners_fea.md    ← filament evaluation, SW modelling conventions, fasteners, FEA plan
      motor_mount_split_topdown.svg    ← Visual confirmation of the L/R split
      split_stl.py                     ← Script that did the split (run again on any pair file)
  CAD/                                  ← see CAD/README.md for structure + SW search-path setup
    parts/
      bottom_plate.SLDPRT              ← base plate (in progress in SolidWorks)
      TT_Motor_Mount_L.SLDPRT / _R.SLDPRT / MirrorTT_Motor_Mount_R.SLDPRT
      CameraMount1.SLDPRT              ← camera mount
      MountA.SLDPRT                    ← (in progress)
    assemblies/
      buddy.SLDASM                     ← chassis assembly (top level)
    drawings/                          ← (empty — one .SLDDRW per printed part, per §7 of setup doc)
    exports/
      TT+Gear+Motor+Mount.stl / .3mf   ← original combined STL/3MF (preserved, do not delete)
      TT_Motor_Mount_L.stl             ← split, 1266 triangles, 40 × 38 × 23 mm
      TT_Motor_Mount_R.stl             ← split, 1268 triangles, 40 × 38 × 23 mm
      robot-buddy-reflex.step          ← reflex MCU board (KiCad export)
    library/
      RaspberryPi5_envelope.SLDPRT     ← simplified Pi 5 envelope
      Yahboom_TT_Motor_envelope.SLDPRT ← simplified motor envelope
      robot-buddy-reflex-mcu.step      ← reflex MCU board — design the frame around this
      vendor/                          ← full downloaded models (Pi 5, Yahboom motor, DM9095)
```

> **Note:** the chassis assembly file is currently `RB-ASM-100_chassis.SLDASM`
> (open/locked in SW at consolidation time); component parts were renamed back to
> their original names so the assembly resolves. Apply the `RB-…` naming
> convention (§3 of the setup doc) from *inside* SolidWorks — see CAD/README.md.

## Workflow for today

1. **Set up the filament profile** — open `docs/01_petg_bambu_profile_guide.md` and create the Polymaker PETG Black profile in Bambu Studio. Run the three calibrations (flow dynamics, flow rate, max volumetric speed) on a small calibration cube before the real prints.

2. **Set up SolidWorks** — once per project, walk through `docs/02_solidworks_setup_for_3dp.md` to create the part/assembly/drawing templates and document properties. Save them to a `templates/` folder you point SW at.

3. **Open both split STLs in SolidWorks** — open `CAD/exports/TT_Motor_Mount_L.stl` and `_R.stl`. Each is a single connected solid. Measure the mounting hole pattern so you can lock the base plate hole positions. **Modify them for the Yahboom encoder TT motors** — the encoder housing typically extends past the motor body, so the rear of the mount may need a relief slot or an extended cradle. Compare the mount's motor pocket geometry against the Yahboom motor body length and encoder PCB clearance.

4. **Verify the L/R split** — open `docs/motor_mount_split_topdown.svg` in a browser to see the two halves overlaid in their original positions. Note: they're **translated copies, not mirror images** — you'll need to mirror one in SolidWorks to make a proper L/R pair for the chassis.

5. **Build the base plate** — `docs/03_base_plate_design_spec.md` has everything: dimensions, hole positions, fastener choices, DFM checks, and an 11-step SolidWorks build order. **Don't lock motor mount hole positions until you've measured the actual mounts from step 3.**

6. **Assemble** — bring base plate + both motor mounts into an assembly. Run interference check. Verify total mass and CoG with Mass Properties.

7. **Export + slice + print** — STL export settings are in the SW setup doc. Slice in Bambu Studio with the PETG profile, 0.6 mm nozzle, 0.28 mm layers, 30% gyroid, 4 perimeters. Estimated print time for base plate: ~4 hours.

## Open assumptions (verify before printing)

- TT mount bolt-hole pattern — must measure from the split STL
- Pi model is Pi 4 / Pi 5 (58 × 49 mm hole pattern)
- Track width: 70 mm centerline-to-centerline (provisional)
- M3 heat-set insert pocket: 4.0 × 5.5 mm (check your insert datasheet)

## What's NOT here yet

- Top shell / canopy
- Track tensioner mechanism
- Idler bracket model (treated as L-bracket placeholder in the base plate spec)
- Camera mount (if you're adding vision)
- Battery holder model

Each of these is a follow-up part once the base plate prints and fits.
