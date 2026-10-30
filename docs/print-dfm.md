# 3D-Print DFM — Design Rules for FDM (0.6 mm nozzle)

> **Shared reference.** An identical copy lives in both `robot-scout` and
> `robot-buddy` — keep them in sync. These rules are robot-agnostic; they
> describe how to model parts in SolidWorks so they print well on the shop
> printer.

**Target process:** Bambu Lab P2S (enclosed, direct-drive), **0.6 mm hardened
nozzle** as the default (line width ~0.6 mm, layer height 0.2–0.3 mm). Drop to
the **0.4 mm hardened** nozzle only for fine detail (diffuser grids, light pipes,
small text, crisp sealing faces). Material choices live in `docs/print-bom.md`.

**Core principle:** make every feature a whole-number multiple of the **0.6 mm
line width** (walls) and the **layer height** (vertical steps). The slicer then
guesses less and parts come out dimensionally honest.

---

## Walls & features — multiples of 0.6

| Feature | Rule (0.6 nozzle) | Why |
|---|---|---|
| Minimum wall | **1.2 mm** (2 perimeters) | 1× line width (0.6) prints but is weak; 2× is the practical floor |
| Structural wall | **1.8–2.4 mm** (3–4 perimeters) | Load-bearing walls in CF / PC / ASA |
| Wall increments | multiples of **0.6** (1.2 / 1.8 / 2.4 …) | Avoids a thin gap-fill sliver between perimeters |
| Vertical feature heights | multiples of **layer height** (0.2 or 0.3) | Clean steps, text depth, ledges land on a layer |

## Ribs instead of bulk

- **Never model thick solid masses** — CF / PC / ASA warp and sink in thick
  sections. Model a shell + ribs.
- Rib thickness **0.6–1.2 mm** (1–2 line widths); rib height ≤ **~3× thickness**
  (self-supporting). Fillet the rib root.
- Keep **wall thickness uniform** across the part; abrupt thick→thin transitions
  warp and leave sink marks.

## Holes, bosses, pins

| Feature | Rule | Note |
|---|---|---|
| Printed vertical hole | ≥ **2–3 mm**; prints **~0.1–0.3 mm undersized** | Model +0.2–0.3 mm, or drill/ream to final size |
| Horizontal hole | **teardrop / diamond** it, or oversize + drill | Round horizontal holes sag into ovals |
| Heat-set insert boss | hole per insert spec (M3 ≈ **Ø4.0 mm**), boss OD ≥ **2× hole** | Preferred way to take screws |
| Minimum pin / post | ≥ **2–3 mm** dia | Thin tall pins wobble / snap on the layer axis |

**Fasteners:** design joints for **heat-set brass inserts** or **captive nuts +
a clearance hole** — not printed threads. Only model printed threads if coarse
and ≥ M8, and add **0.3 mm** clearance.

## Fits & clearances (mating / assembled parts)

| Fit | Gap per side (0.6 nozzle) |
|---|---|
| Free / slip (moving, lids, sliding) | **0.3–0.4 mm** |
| Snug / press fit | **0.15–0.25 mm** |
| Separate parts printed together | ≥ **0.5 mm** gap |
| Nut pocket | across-flats + **0.2–0.3 mm** |

Don't design features needing tighter than **±0.2 mm** — FDM tolerance is
~±0.2–0.5 mm. Put precision on the hardware (inserts, dowels, bearings, bushings)
or post-machine the critical feature.

## Edges & corners

- **Chamfer the bottom edge 0.5 mm × 45°** to kill elephant's-foot and aid bed
  release (cleaner than fighting it in the slicer).
- **Fillet internal corners ≥ 0.5–1 mm.** CF filaments are **notch-sensitive** —
  sharp internal corners are crack initiators. Most important on load-bearing
  brackets.
- **No draft angles** — FDM isn't injection molding; draft just wastes material
  and time.

## Overhangs & bridges

- Keep overhangs **≤ 45° from vertical** to print support-free. Add a **45°
  chamfer** under any horizontal ledge / boss instead of an unsupported shelf.
- Bridges up to **~5–10 mm** print clean; longer → chamfer, teardrop, or accept
  support.

## Text & markings

- Emboss (raised) **≥ 1 mm** stroke width, **≥ 0.4 mm** proud; deboss grooves
  **≥ 0.6 mm** wide. Fine text doesn't resolve at 0.6 mm — keep it large or move
  that part to the 0.4 nozzle.

## Design-intent habits (SolidWorks-side)

- **Orient for load:** layer adhesion is the weak axis. Model the part so its
  primary load runs *along* the layers, not across them. Call out the intended
  print orientation on the drawing / in the filename. Critical for brackets,
  tensioners, and any impact / bumper part.
- **Model at nominal.** Bake compensation only into holes / press-fits (above);
  leave global scaling to the slicer.
- **Split large or awkward parts** into printable, sensibly-oriented pieces
  joined by inserts / dowels rather than forcing supports.
- **Uniform wall + ribs beats a solid block** for both strength-per-gram and
  print reliability — design like injection-molded plastic, not machined metal.

---

## Material-specific notes

- **CF-filled (PET-CF, etc.) — run the 0.6 nozzle.** Chopped fiber clogs a 0.4.
  Notch-sensitive → fillet every internal corner and rib root. Dry before
  printing.
- **PC / high-temp** — thick sections warp badly; shell + rib religiously, keep
  chamfered bottom edges, and expect an enclosed-chamber print.
- **TPU (gaskets, dampers)** — the 0.6 nozzle flows it well. For sealing faces,
  keep walls ≥ 2 perimeters and design a slight crush (0.1–0.2 mm interference)
  into the mating gap rather than a zero-gap butt.

See `docs/print-bom.md` for which material each part uses.
