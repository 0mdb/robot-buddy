# CAD — robot-buddy mechanical

SolidWorks source + neutral exports for the robot's printed and machined parts.
Design rules: **`docs/print-dfm.md`**. Material-per-part + filament inventory:
**`docs/print-bom.md`** (same printer + palette as robot-scout, plus PLA cosmetic
parts since buddy is indoor).

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

## Workflow (repo is master, SolidWorks driven from WSL) — since 2026-10-30

The repo's `CAD/` is the source of truth. SolidWorks can't open `\\wsl.localhost\`
paths, so it works on a mirror at `C:\Users\Ben\robot-buddy-sw\CAD`:

```bash
just cad-push        # repo -> mirror
just cad-probe       # SolidWorks running and reachable?
# author in SolidWorks against C:\Users\Ben\robot-buddy-sw\CAD\..., Save, close the docs
just cad-pull -n     # preview what comes back
just cad-pull        # mirror -> repo, then commit
```

Both directions skip any file that is newer on the receiving side. Scripted
work (C#/VBScript over COM) follows `.claude/skills/solidworks/SKILL.md` and
`docs/cad/solidworks-api.md`. List what an assembly references with
`python3 tools/sw.py refs CAD/assemblies/<name>.SLDASM`.

Slice on Windows (Bambu Studio / Orca) for the P2S with a **0.6 mm hardened** nozzle
(0.4 for detail), and export print-ready 3MF/STL into `exports/`.

The NAS share (`smb://freenas2.local/dev/Robots/robot-buddy/CAD/`) was the
working store until 2026-10-30. It is now a backup only; don't author there.

## Versioning

Authored CAD (SLDPRT/SLDASM/SLDDRW, STEP/STL/3MF under `CAD/`) is in **Git
LFS** (`.gitattributes`). Run `git lfs install` once per clone. Vendor raw
downloads are gitignored; see `library/README.md`.
