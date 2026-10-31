# Robot Buddy — Rear Follower (Tread Tensioner) Spec — Rev 1

> Amendment (loop P11, 2026-10-30): **superseded for the wheel by `08_tpu_track_rnd.md`**
> (Q8: printed TPU track system). The idler is 08's toothed wheel (`RB-PRT-021_idler`,
> Ø54.8 running, 36 wide, no flanges, 2 × 624 with crush ribs per Q14), not the flanged
> wheel below. Axle height **13.5** (level belt with the TT shaft), idler at x −57.3 with the
> belt just taut. The carriage, its rails, clamp and jack screw stay as specified here; the
> kit numbers (44.2 track, 45.2 flange gap, Ø49.6) are obsolete.

Custom rear idler/follower for each track. **Cantilever** design (rev 1): the
tread loops around the idler, so it can only be supported from the **inboard**
side. Two per robot (left + right), sliding in base-plate slots for tread
tension. Material **PET-CF** (proto PETG), rules per `docs/print-dfm.md`.

## Mechanism

A sliding **carriage** rides two guide slots in the base plate (anti-yaw) and
clamps down to lock. An inboard **journal boss** on the carriage carries a long
**Ø4 shoulder bolt (M3 thread, 55 mm overall)** as a through-axle; the 624
bearing pressed into the **flanged idler wheel** spins on the shoulder at the
outboard end. The tread wraps the wheel on the open outboard side.

- **Tension:** loosen the carriage clamp, turn the **M3 jack screw** (in an insert in a plate
  end-stop behind the carriage, axis along X) to push the carriage rearward (−X), re-clamp.
  The screw holds the tension positively; the clamp only locks. Design **8–10 mm** of travel.
  (Added 2026-10-30, `07_materials_fasteners_fea.md` F4b.)
- **Lock:** carriage clamp screw(s) drop through the base slot to a nut (or
  thumb-nut) under the plate.
- **Axle path (outboard → inboard):** head + washer (retains wheel) → bearing →
  **spacer/standoff** → journal boss → **M3 nyloc nut** (inboard, toward robot
  center, out of the tread path). The **spacer length sets the wheel's outboard
  (lateral) position** to line up with the tread; 55 mm overall ≈ the kit's
  53.6 mm axle (+1.4 mm just protrudes past the nut).
- **Spin:** inner race clamped stationary between the head-side washer and the
  spacer/boss; **outer race + wheel spin**, held axially by the bearing itself.
- **Support the overhang:** extend the journal boss **outboard toward the
  bearing** so the Ø4 bore backs up the shoulder right up to it — keep the
  *unsupported* overhang short even though the bolt is long (a bare Ø4 cantilever
  goes marginal past ~35–50 mm: 0.25–0.4 mm flex, 56–93 % of 304 yield at 15–25 N).

## Kinematics / fits (PET-CF, 0.6 nozzle)

| Feature | Spec |
|---|---|
| Bearing → wheel hub | slip pocket **Ø13.1 (+0.1)** + 1.5 mm back shoulder; capture outer race with a printed cap / far flange (don't rely on an FDM press) |
| Hub wall around bearing | ≥ 3 mm → hub OD ~19–20 mm |
| Axle / bearing seat | Ø4 ground shoulder = bearing bore seat **and** journals in the boss. Inner race clamped between the head-side washer and the spacer/boss; **retaining washer OD ≤ ~7 mm** so it bears on the inner race only, not the Ø10 sealed outer race. |
| Journal boss bore | **Ø4.1 (slip)** through-bore for the shoulder; extend the boss outboard toward the bearing to minimize unsupported overhang |
| Axle nut | M3 nyloc on the inboard end; **nut pocket across-flats +0.2–0.3 mm** if captured in the boss, else clearance + external nut |
| Spacer / standoff | Ø4 ID sleeve on the shoulder; **length = wheel lateral offset − bearing width**, sets where the wheel sits under the tread |
| Wheel ↔ boss side clearance | **0.4 mm** so the wheel runs free |
| Carriage rails in base slots | slip **0.35 mm/side** |
| Structural walls | 2.4 mm; clamp foot ~4 mm |
| Boss / carriage body | thick, **1.5–2 mm internal fillets** (CF notch-sensitivity); boss length as long as practical for axle support |
| Bottom (bed) edge | **0.5 mm × 45° chamfer**; print rails-down |
| Flanges | inner gap = tread width **+1.0 mm**; ~2 mm thick, stand 2–3 mm proud of the running surface |

**Tilt note:** a single cantilevered bearing can let the wheel cock slightly
under tread load. If rev 1 wobbles, add a **second 624** spaced on the shank
(the 55 mm bolt has length to spare) — size the hub deep enough to accept it.

## Hardware BOM (per follower — ×2 for the robot, buy spares)

| # | Item | Spec | Source (Amazon.ca) |
|---|------|------|--------------------|
| 1 | Idler bearing | **624-2RS**, 4 × 13 × 5 mm, rubber-sealed | ACROPIX / uxcell 2-packs |
| 2 | Axle | **Ø4 shoulder bolt, M3×0.5, 55 mm overall**, 304 SS, hex socket (matches kit 53.6 mm) | MECCANIXITY 4 mm × 55 mm (B0FDQ6BS38); 45 mm variant if you want an exact 53.6 mm match |
| 3 | Axle nut | **M3 nyloc** on the inboard thread end (+ optional M3 washer) | generic M3 nyloc assortment |
| 4 | Spacer / standoff | **Ø4 ID** sleeve (brass/steel or printed), length = wheel lateral offset − 5 mm; sets wheel position under the tread | Ø4 ID standoff / spacer assortment |
| 5 | Retaining washer | **OD ≤ ~7 mm** (bears on inner race only, not the Ø10 outer race) | small/M3 washer assortment |
| 6 | Carriage clamp | 1–2× **M3 SHCS** (~16 mm, spans plate+foot) + **M3 nyloc** + washer; optional **M3 knurled thumb-nut** for tool-free tension. (Optional **M3 heat-set** in the carriage if you thread the clamp instead of using a nut.) | generic M3 SHCS + nyloc; initeq/ShineNow heat-sets |

*Axle nut is inboard (out of the tread path). Clamp screw stack: base plate 4 mm
+ carriage foot ~4 mm + nut → M3 × 16 mm is about right; confirm against final
carriage height.*

## Kit measurements (Ben, 2026-10-30)

Drive gear root Ø48.2, tip Ø54.34, width 31.6; track outside width **44.2** → flange inner gap **45.2**.
**Running OD Ø49.6** (Ben, 2026-10-30). See `06_frame_design_spec.md` §7.

## Originally needed to finalize the wheel (two measurements off the kit)

1. **Tread width** → flange inner gap = width + 1.0 mm.
2. **Drive sprocket effective OD** (diameter the tread rides) → set the idler
   running-surface OD to match so the tread sits level front-to-rear.
3. Confirm the **tread inner face** is smooth (idler just guides) vs lugged
   (needs clearance grooves). Default: smooth.

## Base-plate impact

The two fixed idler holes per side in `04_base_plate_hole_coordinates.md` §2
become a **tension-slot pair** (guide slots for the carriage rails + a clamp slot
to a nut under the plate), ~8–10 mm travel along X. Update §2 once the carriage
footprint is fixed.
