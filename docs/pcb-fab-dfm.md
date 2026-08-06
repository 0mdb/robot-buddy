# PCB Fab & Assembly DFM — JLCPCB

> **Shared verbatim with `robot-buddy`** (same convention as `print-dfm.md`, which is the
> *3D-printing* DFM doc — unrelated to this one). Both projects share
> `~/kicad-libs/footprints/robot-projects.pretty/` and the same fab workflow, so a defect
> here is a two-project defect.
>
> Origin: issues hit while producing the 2026-07 boards (buddy memory `jlcpcb_assembly_parts`).
> Read this **before** every order. Footprint correctness is a separate axis — see
> `footprint-audit.md`.

---

## 1. Mask opening without copper — *this is what gets your order held*

JLC emails and holds the order when a solder-mask opening has no copper beneath it. Two
independent causes, both fixed 2026-07-20 across all four boards.

### 1a. THT pads: `keep_end_layers no` under `remove_unused_layers yes`

KiCad strips the **outer-layer annular rings** from pads that only route on inner layers,
leaving an orphan mask opening over bare laminate.

**Fix:** `keep_end_layers yes` on every THT pad — keeps top+bottom copper while still
trimming genuinely unused inner layers.

### 1b. NPTH pads listing `*.Mask`

`MountingHole_3.2mm_M3_DIN965` and the ATO fuseholder have `np_thru_hole` pads with
`(layers "*.Cu" "*.Mask")` → a 3.2 mm mask opening with no copper anywhere near it.

**Fix:** strip `*.Mask` from `np_thru_hole` pads **only**. Plated connectors use
`thru_hole` — leave those alone.

### Verification

Re-export with the layer set that produced matching coordinates:

```bash
kicad-cli pcb export gerbers \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts
```

Then parse the D03 flash coordinates and assert **F_Mask positions ⊆ F_Cu positions** on both
outer layers.

Quick source-level check (catches both causes without exporting):

```bash
for b in <board>; do f=$b/$b.kicad_pcb
  grep -c "keep_end_layers no" $f          # must be 0
  python3 -c "
import re;s=open('$f').read();n=0
for m in re.finditer(r'\(pad [^\n]*np_thru_hole',s):
    ly=re.search(r'\(layers ([^)]*)\)',s[m.start():m.start()+500])
    if ly and 'Mask' in ly.group(1): n+=1
print(n)"                                   # must be 0
done
```

**If a board is already ordered:** JLC's "Solution A" (copy the mask openings into copper) is
the equivalent fix — accept it.

### Status (verified 2026-08-05)

| Board | `keep_end_layers` | NPTH+Mask | Verdict |
|-------|-------------------|-----------|---------|
| `robot-buddy-reflex` | 33 yes / 0 no | 0 | ✅ |
| `robot-scout-power` | 22 yes / 0 no | 0 | ✅ working tree |
| `robot-scout-mcu` | 32 yes / 0 no | 0 | ✅ working tree |
| `robot-scout-gimbal` | 11 yes / 0 no | 0 | ✅ working tree |

> ⚠ **On the scout side these fixes were uncommitted as of 2026-08-05** — HEAD still had
> 65 `keep_end_layers no` and 15 NPTH+Mask offenders across the three boards. A `git checkout`
> or branch switch reverts them silently and the next order gets held again. **Commit the
> board files.** (Boards already in hand were fabbed from the fixed geometry — gerber zips
> and `.kicad_pcb` share a 2026-07-20 21:25 mtime.)

---

## 2. Silent wrong-package auto-match — *assembly, not fab*

JLC auto-matches a BOM **value** to the cheapest part when the exact 0402 isn't Basic — often
a **wrong-package Extended part** (01005 or 0603). These are valid C-numbers, so **no
"unmatched" warning ever appears.** The board arrives with the wrong parts on it.

Bugs actually caught this way:

| Intended | Auto-matched to | What it actually was |
|----------|-----------------|----------------------|
| 47k 0402 | `C25819` | **0603** |
| U3 buffer (74LVC1G125) | `C7972` | **an LMV321 op-amp** |
| 120R 0402 | `C560399` | **01005** |

**01005 matches also silently force ENIG + standard board**, changing finish and price.

**Rule: eyeball `Package = 0402` on every line in match review.** Value matching is not part
matching.

### Part-selection caveat

**1.8k 0402 1% has no Basic option.** Use **`C163481`** (Yageo, ~630k stock) — *not* Uniroyal
`C25871` (~31 stock, shortfalls). Verified Basic 0402 1% resistors and other confirmed parts
are listed in the buddy memory `jlcpcb_assembly_parts`.

---

## 3. Rotation review

JLC's part-orientation reference can differ from KiCad by **90° or 180° on any 3+ pin part**.
2-terminal 0402 R/C are symmetric — ignore those.

Always check in the 3D placement preview before releasing:

| Board | Check rotation on |
|-------|-------------------|
| `robot-buddy-reflex` | U3 (SOT-23-5), J5 (Qwiic JST-SH) |
| `robot-scout-mcu` | U2 (SOIC-8), J1/J2/J3 (Qwiic JST-SH) |
| `robot-scout-gimbal` | U2 (SOIC-8), J3 (Qwiic JST-SH) |

Per-board upload steps live in each `hardware/kicad/<board>/jlcpcb-assembly/README.md`.
Those directories are **untracked in robot-scout** — commit them so the fab package is
versioned alongside the gerbers it was generated from.

---

## The three shared gates — run all of them, on every board

Canonical copies live in `~/kicad-libs/tools/`; **both repos symlink them**, so a
fix lands in both. Do not fork them. All three are wired into `fab_export.py`,
which aborts rather than emit gerbers.

| Tool | Asks | Written after |
|------|------|---------------|
| `check_pcb_routing.py` | *Is it connected?* | `robot-scout-mcu` was fabricated with **zero traces** |
| `check_board_review.py` | *Is it connected to the RIGHT thing, and can a human tell?* | 12 V and 5 V on interchangeable connectors with no silk (A1/A2/A3); **polarity** added after F10 |
| `check_pcb_ampacity.py` | *Can it CARRY the current?* | F9 — 15 A crossed to a plane on one 0.4 mm via |

Each was written because the previous set passed a board that was broken. They
are cumulative, not alternatives.

### What `check_pcb_ampacity.py` checks

It has no table of real load currents and does not want one. It treats the
**netclass track width as the statement of design intent**: put a net in a 4.0 mm
class and you asserted it carries what 4.0 mm carries, so every part of that
net's path must live up to it. Two rules:

1. **A layer transition must not be the weak link.** At an SMD pad on a power net
   whose only egress is vias, `sum(via ampacity) >= net ampacity`. A via barrel
   is `pi * drill * plating` of copper — a 0.4 mm via at 20 µm is ~1.5 A. A router
   places exactly one because connectivity needs exactly one.
2. **A power rail must have outer copper of its own** (register F4). A net rated
   above the threshold with zero tracks, relying entirely on a plane, fails.
   Dedicated ground/return planes are exempt — a ground plane *is* the intended
   conductor, and its pads reach it through their own THT barrels.

Defaults assume **2 oz outer, 20 µm via plating, 30 °C rise**; override with
`--outer-oz / --plating-um / --rise-c`. It skips unrouted boards and defers to
`check_pcb_routing.py`, which owns that failure and is louder.

### What the POLARITY rule checks

A footprint that silks `+` and `-` is making a machine-readable assertion about
which pad is which. The rule finds the nearest pad to each marker and fails if
the `-` pad is not a ground net. **This is how F10 was missed for a whole
revision:** `XT90PW-F` is pin 1 = `+`, KiCad's `AMASS_XT30UPB-F` is pin 1 = `−`,
and the schematic assumed one convention for both families — putting the positive
rail on the pad silked `−` on all three XT30s.

> **Never assume two connector families share a pin-1 convention**, even from the
> same manufacturer, even on the same board.

---

## Pre-order checklist

- [ ] **All three shared gates pass** (routing, board-review incl. polarity, ampacity)
- [ ] `keep_end_layers no` count = 0 on every board
- [ ] `np_thru_hole` pads listing `*.Mask` count = 0
- [ ] Gerbers re-exported with the full layer set above; F_Mask ⊆ F_Cu asserted
- [ ] **Copper weight on the ORDER PAGE matches the board's own silkscreen.**
      `robot-scout-power` v2 = **2 oz outer / 1 oz inner, 4-layer**. Screenshot
      the order page. See §4 — this is not a preference, the board is unsafe at
      1 oz outer.
- [ ] Every BOM line: **Package verified**, not just value matched
- [ ] No 01005 substitutions (they force ENIG + standard board)
- [ ] 1.8k → `C163481`, not `C25871`
- [ ] Rotations checked in 3D preview for every 3+ pin part
- [ ] Board files **committed** — not sitting in a dirty working tree
- [ ] Custom footprints signed off in `footprint-audit.md`
- [ ] **Every footprint test-fitted against the ACTUAL ordered part** — not a
      same-family part. A footprint can be internally correct and still model a
      different manufacturer's component (`robot-scout-power` F8: Littelfuse/Pudenz
      footprint vs Keystone 3557 in the BOM). **Scrapped boards from the previous
      revision are free test coupons** — but confirm the pad geometry is unchanged
      between the as-fabbed commit and the current board first, because a shared
      footprint *name* is not a shared footprint.
- [ ] **Every photo-derived or otherwise unverified PIN ORDER resolved against the
      physical part.** Geometry and pin order are separate claims: a vendor drill
      guide carries holes, not net names. `robot-scout-power` B2 (D36V50F5
      VIN/VOUT) is this item — reversed, the copper is wrong and the board is
      scrap, so it blocks the ORDER, not the soldering iron. Use an asymmetric
      physical feature as the datum, and remember back-side silk mirrors.

---

## §4 Copper weight — specify it, then verify it on the order

**This section exists because v1 didn't have one.** "Order 2oz copper" was
written in `BOM.md` and three separate places in `TODO.md`, and
`TODO.md:235` — *"Confirm the fab order specified 2 oz outer copper"* — sat as
an **open checkbox through an entire fab cycle**. Nobody ever established what
was actually ordered. An instruction written in a doc is not a specification;
it becomes one when it's on the order and verified.

### Outer copper is load-bearing on the power board

`robot-scout-power` routes `+VBAT` / `VBAT_FUSED` at **4.0 mm** (IPC-2221
external, k = 0.048):

| Outer copper, 4.0 mm | ΔT at 15 A (pack peak) | Verdict |
|---|---|---|
| **2 oz** | ~20 °C | ✅ and ~39 °C at the 20 A fuse rating |
| 1 oz | **~64 °C** | ❌ — E1 would need ~9.4 mm |

`F1` is 20 A and a 20 A ATO passes 15 A indefinitely, so the conductor has to
carry 15 A *continuously*. **Fuse rating < conductor rating** — that's the rule
E1 exists to enforce, and at 1 oz it inverts.

### Inner copper: specify it too

Every previous mention said *outer*. Nobody specified inner, and JLCPCB's
standard 4-layer stackup is **0.5 oz inner**. Running IPC-2221 for **internal**
conductors (k = **0.024**, half the external constant) at 15 A / 30 °C rise:

| Inner copper | Unbroken plane width needed for 15 A |
|---|---|
| 0.5 oz (JLC 4-layer default) | **33.1 mm** |
| 1 oz | 16.5 mm |
| 2 oz | 8.3 mm |

The power board is THT-heavy, so its `In2.Cu` `+VBAT` plane is perforated by
antipads and the **necks between them**, not the bulk width, are the constraint.

**Design rule: the outer trace carries the rated current on its own. A plane is
margin, never the safety case.** A plane whose copper weight you did not specify
is a plane whose ampacity you do not know.

### Consequence for minimum features

2 oz outer raises JLCPCB's minimum trace/space to roughly **6 mil (0.152 mm)**.
Check it against the tightest netclass on the board — `robot-scout-power`'s is
`Default` at 0.25 mm track / 0.2 mm clearance, which clears it. A board designed
at 1 oz minimums and then ordered at 2 oz will not.
