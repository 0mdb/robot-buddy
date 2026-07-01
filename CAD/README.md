# CAD — robot-buddy mechanical

SolidWorks source + neutral exports for the robot's printed and machined parts.
Design rules: **`docs/print-dfm.md`**. (Material choices track robot-scout's
`docs/print-bom.md` — same printer, same filament palette.)

## Structure

```
CAD/
├── parts/         # .SLDPRT — individual components (source of truth)
├── assemblies/    # .SLDASM — assemblies + mates
├── drawings/      # .SLDDRW — dims, print-orientation notes, tolerances
├── exports/       # neutral output: STEP (interchange), STL/3MF (print-ready)
└── library/       # vendor/downloaded models, shared library features, templates
```

**First parts (frame bring-up):**
- **Frame** — chassis structure → PET-CF (structural, per DFM: shell + ribs,
  filleted internal corners, load along layers).
- **Pi holder** — Raspberry Pi 5 mount → PET-CF; heat-set inserts for the Pi's
  M2.5 holes (design bosses per insert spec, not printed threads).
- **Tank-tread tensioners** — idler tensioner mechanism → PET-CF structure;
  design slip/adjust fits at **0.3–0.4 mm** per side, precision on hardware
  (bearings/bushings), not on printed features.

## Workflow (Ubuntu dev ⇄ Windows SolidWorks)

Software/firmware work happens on Ubuntu; **SolidWorks and slicing run on
Windows**. The working store is the FreeNAS share, and the repo holds a synced
snapshot:

1. **Author** in SolidWorks on Windows against the NAS share:
   `smb://freenas2.local/dev/Robots/robot-buddy/CAD/`
2. **Slice** on Windows (Bambu Studio / Orca) → P2S, **0.6 mm hardened** nozzle
   (0.4 for detail). Export print-ready 3MF/STL into `exports/`.
3. **Sync into the repo** on the Ubuntu box (mount the share, then rsync):
   ```bash
   # mount the SMB share (adjust mount point), then:
   rsync -av --delete /mnt/freenas2/dev/Robots/robot-buddy/CAD/ ~/robot-buddy/CAD/
   ```
4. **Commit** from Ubuntu. `.gitattributes` marks SolidWorks/STEP/3MF files
   binary; `.gitignore` drops SW lock/temp/backup cruft (`~$*`, `*.SLDBAK`, …).

## Versioning note

Native SW files are committed as plain binary for now (NAS remains the live
working store; the repo is the versioned snapshot beside the firmware). If the
native files start bloating history, switch to Git LFS — see the commented
`git lfs track` line in `.gitattributes`. Do the LFS switch *before* committing
large parts, not after.
