# CAD/library — envelopes and vendor models

- `*_envelope.SLDPRT`: simplified keep-out bodies we design around (tracked, LFS).
- `robot-buddy-reflex-mcu.step`: reflex board, exported from KiCad.
- `vendor/`: full vendor models. **Native SolidWorks files are tracked** (LFS),
  because `RB-ASM-100_chassis.SLDASM` references the Pi 5 and Yahboom parts.
  **Raw downloads are gitignored** (STEP/STL, Pi 5 renders/photos). Fetch them again if needed:

| Model | Ignored files | Source |
|---|---|---|
| Raspberry Pi 5 | `RaspberryPi5/STEP/`, `RaspberryPi5/NEW STEP/`, `RENDERS/`, `Photo/` | not recorded; copy from the NAS backup below |
| DM9095 enclosure | `DM9095/DM9095_enclosure.STL` | not recorded; copy from the NAS backup below |

The NAS backup (`smb://freenas2.local/dev/Robots/robot-buddy/CAD/library/vendor/`)
has all of them.
