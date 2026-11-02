# 3D-Print BOM — Robot Buddy

Printed-parts list, material-per-part mapping, and filament inventory for the
robot-buddy build. Companion to `docs/print-dfm.md` (design rules) and the
mechanical CAD under `CAD/`.

Buddy shares robot-scout's material philosophy (see `robot-scout/docs/print-bom.md`):
**PET-CF** as the structural workhorse, TPU for flex/damping, ASA/PC where
needed, PETG/PLA for prototyping. The difference: **buddy is an indoor companion
robot** (face + personality), so UV-stability matters less and PLA is fair game
for cosmetic shells and accents.

## Printer setup

| Item | Value |
|------|-------|
| Printer | Bambu Lab **P2S** (enclosed, direct-drive, heated chamber) |
| AMS | **AMS 2** present — run PLA / PETG / ASA / PC through it; run **PET-CF and TPU 85A external** from the spool holder (CF is abrasive, soft TPU can jam AMS feed) |
| Dryer | **SUNLU** filament dryer on hand — **dry PET-CF, TPU, and PC before printing** (and PETG if it's been open a while). The AMS is not a dryer. |
| Nozzles | **0.6 mm hardened** (default; required for PET-CF / abrasive) · **0.4 mm hardened** (fine detail on CF/abrasive) · **0.4 mm stainless** (fine detail on non-abrasive: PLA/PETG/TPU/ASA/PC — do **not** run CF through the SS nozzle, it wears fast) |
| Plates | **Engineering plate** (PET-CF / PC / ASA — high-temp, needs the grippier plate) · **Textured PEI plate** (PLA / PETG / TPU — matte bottom finish, easy release) |

**Nozzle/plate quick rule:** structural CF part → 0.6 hardened + engineering
plate. Cosmetic/detail non-CF part → 0.4 stainless + textured plate. Detail on a
CF part → 0.4 hardened + engineering plate.

## Material palette

What each material is for on this robot, and why.

| Material | Role | Notes |
|----------|------|-------|
| **PET-CF** | Primary structural | Stiff, dimensionally stable, low moisture uptake. Workhorse for the chassis, mounts, brackets, tensioners. Hardened nozzle + dry + engineering plate. Notch-sensitive → fillet internal corners. |
| **PC** | High-stress / high-temp structural | Tougher and higher-temp than PET-CF. Use where a joint takes repeated shock or runs warm (near motors/drivers). Warps in thick sections — shell + rib, enclosed chamber. |
| **ASA** | Durable cosmetic covers | Tougher and more heat-stable than PLA for shells that get handled. (UV-stability is a bonus buddy rarely needs indoors.) |
| **TPU 85A** | Flex: tracks, gaskets, damping, feet | Tank treads, vibration isolators, bumpers, strain reliefs, non-slip feet. Run external, slow, low infill for damping. |
| **PETG** | Prototyping / fit-test rigid | Cheap iteration before committing a structural part to PET-CF. Also fine for non-structural functional parts. |
| **PLA** | Cosmetic shells + accents, jigs | Indoor companion aesthetics — face bezel, canopy, ears/antenna, name badge. Also throwaway prototypes and print jigs. Not load-bearing, not near heat. |

## Filament inventory (on hand)

### Purchased this order
| Material | Brand | Color (code) | Qty | Primary use |
|----------|-------|--------------|-----|-------------|
| PET-CF | Bambu | Black (71100) | 1 kg | **Structural — final parts** |
| PC | Bambu | White (60100) | 1 kg | High-stress / high-temp structural |
| ASA | Bambu | White (45100) | 1 kg | Durable cosmetic covers |
| TPU 85A | Bambu | Lime Green (51501) | 1 kg | Tracks, gaskets, damping, feet |
| PETG | SUNLU | Transparent | 1 kg | Prototyping / light pipes / windows |
| PETG | Polymaker | White | 1 kg | Prototyping (high-speed formula) |
| PLA Basic | Bambu | Pumpkin Orange (10301) | 1 kg | Cosmetic |
| PLA Basic | Bambu | Hot Pink (10204) | 1 kg | Cosmetic |

> Also on hand (Ben, 2026-11-01): **Fiberon PA6-CF20**, plenty (shared with fpv250; calibrated P2S presets there). Candidate for impact/wear parts (idler, road wheels) pending the M6 coupons; dry before printing, hardened nozzle. Slicer: `just cad-slice --mat PA6-CF` uses the fpv250 calibrated preset (0.4 hardened, 290 °C, bed ≤ 50 °C, fan off, flow 0.97, ρ 1.17). Strength derate when conditioned (moist): 60 % 🟡 until the M6 coupons say otherwise.
| PLA Glow | Bambu | Glow Green (15500) | 1 kg | Cosmetic accents (glows) |
| PLA Wood | Bambu | Black Walnut (13107) | 1 kg | Cosmetic accents (wood look) |

### Already on hand
| Material | Color | Qty | Notes |
|----------|-------|-----|-------|
| PETG | Black | 2 kg | Prototyping workhorse (structural fit-tests) |
| PLA Basic | Red, Blue, White, Black, Grey, Yellow | 1 kg each | Prototypes, jigs, cosmetic |

**Summary:** 1× PET-CF, 1× PC, 1× ASA, 1× TPU 85A, 4× PETG (transparent, white,
2× black), 10× PLA (8 basic colors + glow + wood). Structural + flex + cosmetic
all covered; the only "add-if-needed" gaps are **PAHT-CF** (impact/heat beyond
PC) and a **softer TPU (~70A)** if 85A under-isolates the camera.

Datasheet numbers, the per-part verdicts and the FEA material model: `docs/cad/07_materials_fasteners_fea.md` §2–3.

## Printed parts → material

| Part | Material (final) | Prototype in | Nozzle / plate | Status |
|------|------------------|--------------|----------------|--------|
| **Base plate / chassis** | **PET-CF** | PETG black | 0.6 hard / eng | design next — see `CAD/…03_base_plate_design_spec.md` |
| Motor mounts L/R (TT) | PET-CF | PETG black | 0.6 hard / eng | CAD exists (`TT_Motor_Mount_L/R`) |
| Idler / rear follower brackets | PET-CF | PETG black | 0.6 hard / eng | placeholder in base-plate spec |
| Track tensioners (rear follower carriages) | PET-CF | PETG | 0.6 hard / eng | only tension point (`06_frame_design_spec.md` D1); slip fits 0.3–0.4 mm/side |
| **Front bulkhead** | **PET-CF** | PETG black | 0.6 hard / eng | face, speaker box, sonar, camera; print on its back |
| Speaker back box | **PETG** | — | 0.6 hard / textured | sealed ~30 cc, solid walls (`docs/audio-hardware.md` §4.3) |
| Mic grommets / speaker gasket | TPU 85A | — | 0.6 hard / textured | `docs/audio-hardware.md` §4.2 |
| Tank tracks / treads | **TPU 85A** | — | 0.6 hard / textured | if printing treads; run external, low infill |
| Raspberry Pi 5 holder / standoffs | PET-CF | PETG | 0.6 hard / eng | heat-set M2.5 bosses |
| Reflex MCU board mount | PET-CF | PETG | 0.6 hard / eng | `CAD/library/robot-buddy-reflex-mcu.step` |
| ESP32-face board mount | PET-CF | PETG | 0.6 hard / eng | TBD |
| Camera mount | PET-CF | PETG | 0.6 hard / eng | CAD exists (`CameraMount1`) |
| Face screen bezel / surround | **PLA** (or ASA) | — | 0.4 SS / textured | cosmetic; ILI9341 320×240 |
| Top shell / canopy | **PC white (60100)** (2026-10-31, was ASA: the heel test S8 passes at SF 2.4 in PC, 1.45 in ASA; dry first, enclosed) | PETG | 0.4 SS / eng | PLA for bolt-on accents only |
| Cosmetic accents (ears, antenna, badge) | PLA Glow / Wood / colors | — | 0.4 SS / textured | fun parts |
| Vibration isolators / feet | TPU 85A | — | 0.6 hard / textured | low infill gyroid |
| Cable strain reliefs / bumpers | TPU 85A | — | 0.6 hard / textured | |
| Battery holder | PET-CF | PETG | 0.6 hard / eng | size to pack; see `docs/power.md` |

## Open items

- **Base plate material decision — DECIDED:** prototype in **PETG black** (verify
  hole patterns / motor + Pi fit / clearances), then commit final in **PET-CF
  black**. Both in stock.
- Confirm whether tank tracks are printed (TPU 85A) or a purchased belt.
- Canopy: **PC white** (`07` §2 amendment: S8 heel test, PC SF 2.4 vs ASA 1.45). ASA white is the fallback if PC won't print well. Face bezel: PLA or ASA, still open.
- Camera isolator approach if vision needs it: TPU 85A grommets vs silicone ball
  dampers — test on the bench.
- PAHT-CF / TPU ~70A remain add-if-needed only.
