# SolidWorks Setup for 3D-Printed Robot Parts (Bambu P2S, PETG, 0.6 mm nozzle)

Everything below assumes parts will be printed on the P2S in PETG with a 0.6 mm nozzle. Tolerance, wall thickness, and feature minimums are tuned for that process.

## 1. Document properties (set once per template)

Set these on a new part, then **File → Save As Template** so you don't redo them. Repeat for the assembly and drawing template.

### Units

- **Unit system**: MMGS (millimeter, gram, second)
- Length: millimeters, 2 decimals
- Mass: grams, 2 decimals
- Angle: degrees, 2 decimals

### Tolerance (Document Properties → Dimensions)

- Default precision: 2 decimal places
- Default tolerance type: **Bilateral**, **+0.20 / −0.20 mm**
  - This matches realistic FDM repeatability on the P2S in XY. Holes and shaft fits need tighter tolerance handled per-feature (see DFM below).

### Material

- Set default material to **PETG** (create custom if not in library):
  - Density: 1.27 g/cm³
  - Yield strength: 50 MPa (printed)
  - Tensile modulus: 1700 MPa
  - These are PRINTED PETG values, not bulk. Don't use SW's stock "PET" entry — it overstates strength.

### Sketch settings

- Enable **Automatic relations**
- Default fully-defined sketch color: green (Tools → Options → Colors)

## 2. Templates to create

Save these in a project-level templates folder, e.g. `C:\SW_Templates\robot_buddy\`:

| Template | Filename | Purpose |
|---|---|---|
| Part | `RB_part.prtdot` | All robot parts |
| Assembly | `RB_assy.asmdot` | Sub-assemblies + top-level |
| Drawing — A | `RB_drawing_A.drwdot` | Single-part details, A-size (11×8.5") |
| Drawing — B | `RB_drawing_B.drwdot` | Assembly overviews, B-size (17×11") |

Point Tools → Options → File Locations → Document Templates at this folder.

## 3. File naming and structure

Convention: `RB-<TYPE>-<NUMBER>_<descriptor>`

- `RB-PRT-001_base_plate.SLDPRT`
- `RB-PRT-010_motor_mount_L.SLDPRT`
- `RB-PRT-011_motor_mount_R.SLDPRT`
- `RB-ASM-100_chassis.SLDASM`
- `RB-DRW-001_base_plate.SLDDRW`

Folder layout (matches `CAD/README.md` — this is the live structure):

```
robot-buddy/CAD/
  parts/         ← .SLDPRT — individual components (source of truth)
  assemblies/    ← .SLDASM — assemblies + mates
  drawings/      ← .SLDDRW — dims, print-orientation notes, tolerances
  exports/       ← neutral output: STEP (interchange), STL/3MF (print-ready → Bambu Studio)
  library/       ← vendor/downloaded models, envelopes, templates; vendor/ subfolder for full models
```

**Applying the `RB-…` names:** the parts above were consolidated under their
original filenames so the existing `buddy.SLDASM` still resolves them. Rename to
the `RB-…` convention **from inside SolidWorks** (SOLIDWORKS Explorer → Rename,
or File → Save As with "update references") so the assembly's component
references update at the same time — a plain disk rename breaks the assembly.

**SW reference search paths (do this once):** because parts, assemblies, and
library live in *separate* folders, tell SolidWorks where to look or assemblies
open with missing components. Tools → Options → File Locations → **Referenced
Documents** → add: `CAD\parts`, `CAD\assemblies`, `CAD\library`,
`CAD\library\vendor` (and its subfolders). Enable Tools → Options → External
References → **"Search file locations for external references."**

## 4. DFM rules for FDM (PETG, 0.6 mm nozzle, P2S)

These are minimums. When in doubt, go thicker.

### Walls

- **Minimum wall**: 1.2 mm (2× nozzle). Anything thinner won't extrude reliably.
- **Comfortable wall**: 1.8–2.4 mm (3–4 perimeters). Use this for structural walls.
- **Ribbing**: ribs at 1.8 mm × 5–8 mm tall every 25–40 mm on flat panels — adds stiffness without mass.

### Holes

- **Minimum hole diameter**: 3.0 mm. Smaller holes close up.
- **Axis vertical (Z)** holes print round — fine.
- **Axis horizontal (X/Y)** holes sag at the top. Two options:
  1. Make them teardrop-shaped (point up, sharp top) — prints without supports
  2. Make them 0.4 mm oversize on diameter to compensate, supports still optional
- **M3 through-hole clearance**: 3.4 mm dia (close fit) or 3.6 mm (sloppy fit)
- **M2.5 through-hole clearance**: 2.9 mm dia (close fit)
- **M3 heat-set insert pocket**: 4.0 mm dia × 5.5 mm deep (Voron-style). Verify against insert datasheet.

### Overhangs and bridges

- **Overhang angle**: 45° from vertical is safe. PETG handles up to ~55°.
- **Bridges**: < 15 mm reliable, 15–25 mm with light cooling boost. Above 25 mm, add a chamfer or split the part.
- **Avoid steep overhangs on visible faces** — they look bad even when they "work."

### Fillets and chamfers

- Fillet every base of every feature that takes load — concentrates stress otherwise.
- **Standard inside fillet**: 2 mm
- **Standard outside fillet/chamfer**: 1 mm
- Chamfer first layer edges 0.5 mm at 45° — prevents elephant's foot showing.

### Print orientation (think while modeling)

Model parts so the "natural" print orientation is also the strongest orientation:
- **Base plate**: flat on bed, loads in shear
- **Motor mounts**: bolt face down on bed if possible — bolt threads pull along layer planes
- **Tall thin parts**: model so they print laying down, not standing up

If you can't avoid a part with weak-axis loading, model in 4 wall loops or print the part vertically with more infill.

## 5. Assembly best practices for FDM

- **Mate to origin planes**, not face-to-face when possible. Lets you swap parts without losing mates.
- **Use sub-assemblies aggressively**: drivetrain sub-asm (motor + mount + wheel), electronics sub-asm. Keeps top-level clean.
- **Interference detection**: run **Evaluate → Interference Detection** before exporting STLs. FDM tolerances mean any modeled interference will bind in real life.
- **Add clearance to mating parts**: 0.2 mm gap on all FDM-to-FDM mating faces. Two printed parts modeled flush won't fit.
- **Color-code sub-systems** in the assembly: structure (gray), drivetrain (red), electronics (green). Helps when troubleshooting.

## 6. STL export settings

File → Save As → STL → **Options**:

| Setting | Value |
|---|---|
| File format | Binary (smaller files) |
| Unit | Millimeters |
| Resolution | Custom |
| Deviation | 0.01 mm |
| Angle | 5° |
| Save all components of an assembly in a single file | **Off** (export per-part) |

Lower deviation = larger file but cleaner curves. 0.01 mm is overkill for FDM but file size is trivial.

Save STLs to `CAD/exports/` matching the part name (e.g. `RB-PRT-001_base_plate.stl`).

## 7. Drawing template basics

Even for parts going straight to STL, do one drawing per printed part. It catches modeling mistakes.

- **Sheet format**: A-size, your title block
- **Standard 3-view + isometric**
- **Critical dimensions only** — anything that interfaces with another part. The rest is captured in the 3D file.
- **Note block**: "PRINT PER 3D MODEL. TOLERANCES PER NOTE 1." with Note 1: "TOLERANCES ±0.20 MM UNLESS OTHERWISE SPECIFIED. ALL CRITICAL HOLES MAY REQUIRE LIGHT DEBURRING/REAMING."

## 8. Calibration parts to print first

Before any robot part, print these and confirm:

1. **XYZ calibration cube** (20 mm) — should measure 20.0 ± 0.15 mm on all axes
2. **Bolt hole test piece** — block with 3.0, 3.2, 3.4, 3.6 mm holes. Find which is the right "M3 through" for your printer.

Update your DFM hole values in this doc if calibration shows different results.

---

**Quick reference card (print or pin)**

| Feature | Value |
|---|---|
| Default tolerance | ±0.20 mm |
| Min wall | 1.2 mm |
| Comfortable wall | 1.8 mm (3 perim @ 0.6 nozzle) |
| Min hole | 3.0 mm |
| M3 through | 3.4 mm |
| M2.5 through | 2.9 mm |
| M3 heat-set pocket | 4.0 × 5.5 mm |
| FDM-to-FDM clearance | 0.2 mm |
| Max overhang | 45° |
| Max bridge | 15 mm |
