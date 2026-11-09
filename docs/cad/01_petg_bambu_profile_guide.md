# Polymaker PETG Black — Bambu P2S Filament Profile Guide

Setup for printing structural robot parts (frame, motor mounts, base plate) in Bambu Studio.

## 1. Prep the spool

PETG is mildly hygroscopic. If the spool has been open for more than a few days in humid conditions, dry it first.

- Bambu AMS dryer or filament dryer: **65 °C for 4–6 hours**
- A wet spool will print stringy, brittle, and pop/hiss at the nozzle. If you hear that, dry it.

## 2. Create a custom filament in Bambu Studio

1. Open Bambu Studio → top-right **Filament** dropdown → **+ Add/Modify** → **Create New**.
2. Base it on **Bambu PETG HF** (closest stock profile), name it `Polymaker PETG Black — Custom`.
3. Set the values below. Polymaker's published range for their PETG is 230–250 °C nozzle and 70–80 °C bed; the values here are starting points inside that window tuned for the P2S.

### Filament tab

| Setting | Value | Notes |
|---|---|---|
| Nozzle temperature (first layer) | 245 °C | Better first-layer bonding |
| Nozzle temperature (other layers) | 240 °C | Drop 5 °C if stringing is bad |
| Bed temperature | 75 °C | Smooth PEI plate |
| Filament diameter | 1.75 mm | |
| Flow ratio | 0.95 | Tune via flow calibration |
| Pressure advance | 0.040 | Start here; run PA calibration |
| Min print speed | 10 mm/s | |
| Max volumetric speed | 12 mm³/s | Polymaker PETG is ~10–14; start conservative |
| Fan speed (overhangs) | 30–50 % | PETG hates strong cooling; layer adhesion suffers |
| Fan speed (other) | 20 % | |
| Min fan speed | 0 % | Off for first 3 layers |

### Cooling notes

PETG needs *less* cooling than PLA. Too much fan = poor layer adhesion and brittle parts. Bridges and steep overhangs are the only places you want fan on.

## 3. Bed prep

- **Smooth PEI** plate, hot. PETG will stick *too well* to PEI if you skip release agent — parts can rip chunks out of the plate.
- Apply a thin layer of **glue stick** (Magigoo, Bambu liquid glue, or basic Elmer's purple) as a release agent. Reapply every 5–10 prints.
- Alternative: textured PEI works without glue but gives a rougher first-layer texture.

## 4. 0.6 mm nozzle process settings

Create a process profile based on **0.20 mm Standard @ 0.6mm nozzle** and tune for structural parts:

| Setting | Value | Why |
|---|---|---|
| Layer height | 0.28 mm | Sweet spot for 0.6 nozzle — fast + strong |
| First layer height | 0.32 mm | Better adhesion |
| Line width (default) | 0.62 mm | |
| Wall loops | 4 | Strength comes from walls, not infill |
| Top/bottom shells | 5 layers | |
| Infill density | 30 % | |
| Infill pattern | Gyroid | Isotropic strength |
| Print speed (outer wall) | 60 mm/s | |
| Print speed (inner wall, infill) | 120 mm/s | Cap by volumetric limit above |
| Print speed (first layer) | 30 mm/s | |
| Retraction (direct drive) | 0.8 mm @ 30 mm/s | P2S has direct drive |
| Z-hop | 0.2 mm, "Slope" | Reduces stringing without scarring |
| Brim | 5 mm, mouse ears on corners | Optional but cheap insurance |

## 5. Calibrate before the first real print

Run these in order. Each takes 10–20 minutes:

1. **Flow dynamics (PA)** — dial in pressure advance for sharp corners
2. **Flow rate** — fine-tunes the 0.95 starting flow
3. **Max volumetric speed** — confirms 12 mm³/s isn't pushing the hot end

Bambu Studio has all three under **Calibration** in the top menu.

## 6. When to switch to the 0.4 mm nozzle

Keep 0.4 mm mounted for anything with:
- Hole diameters < 3 mm
- Wall thicknesses where 2× nozzle (1.2 mm) is too chunky
- Cosmetic top surfaces

The base plate, frame, and motor mounts are all 0.6-mm-appropriate.

## 7. Storage

After printing, return the spool to a sealed bag with desiccant. Polymaker's resealable bags work fine for short-term; for storage > 2 weeks, use a dry box.

---

**Quick troubleshooting**

- *Stringing*: drop nozzle 5 °C, increase retraction to 1.0 mm, dry the filament.
- *Layer separation*: drop fan speed, raise nozzle 5 °C, increase wall loops.
- *Elephant's foot on first layer*: lower bed 5 °C, raise first-layer Z by 0.02 mm.
- *Won't release from PEI*: more glue stick, or let plate cool fully before removing.
