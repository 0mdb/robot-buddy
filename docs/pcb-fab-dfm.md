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

## Lessons — 2026-08-06 power-board session

A day that found four hardware-destroying defects on a board that passed DRC and
every gate. **All four were found by a human looking at the render**, and the
verification tooling gave a confidently wrong answer three separate times about
boards that were fine. Both halves of that are the lesson.

### Verification

- **"Is there 2 oz copper NEAR this pad" is not "is the PATH on 2 oz."** Every
  wrong "confirmed on 2 oz" in this project came from answering the first while
  reporting the second. A pad can carry a fat trace that goes somewhere else
  entirely while the actual A→B route detours through a plane or a thin stub.
  Trace paths (`trace_path.py`), don't sample proximity.
- **A gate that cannot reproduce its own defect is worthless**, and worse than
  none because it is trusted. Test every gate in BOTH directions: it must FAIL
  the known-bad board and PASS the known-good one. The first cut of the ampacity
  gate passed the very board it was written to catch.
- **A plane is always exactly one hop**, so a shortest-path search reports the
  plane every single time — even when a complete outer-copper path exists.
  Search outer-only first, fall back to the plane.
- **Fewest hops is not the widest path.** Current divides by conductance, so the
  meaningful route is max-bottleneck, not shortest. A fewest-hop search called a
  1.00 mm bulk-cap stub the "weakest link" of a rail with a 3.8 mm trunk beside it.
- **Endpoint-only adjacency misses T-junctions** — a track ending part-way along
  another. KiCad treats that as connected and hand routing produces them
  constantly; an endpoint-only test called a perfectly good rail NOT CONNECTED.
- **Pad coordinates are FOOTPRINT-LOCAL; tracks and vias are absolute.**
  Comparing them raw makes every distance meaningless.
- **Net references come in three encodings** and all occur on shipped boards:
  `(net 5 "+VBAT")`, `(net 5)`, and post-SES-import `(net "+VBAT")`. Handle all
  three or silently find nothing.

### Specification

- **Declare the stackup in the board.** A board that SILKSCREENS "2oz outer" and
  does not declare it forces every tool to guess — ours guessed 1 oz and computed
  a rail at 10.6 A that carries 14 A. This is **F4 recurring one revision later**:
  an instruction in a document is not a specification; it becomes one when it is
  in the artifact.
- **Netclass width IS the statement of design intent.** Put a net in a 4.0 mm
  class and you asserted it carries what 4.0 mm carries — so every element on its
  path, vias included, must live up to that. This makes ampacity self-consistent
  instead of dependent on a current table nobody maintains.
- **A trace cannot be wider than the destination pin pitch allows.** 4.0 mm on a
  2.54 mm Pololu row overlaps the pads either side and shorts; 2.8 mm leaves
  0.29 mm against a 0.30 mm rule and fails; 2.6 mm leaves 0.39 mm and works. Size
  the rail, then check it can actually land.
- **Never assume two connector families share a pin-1 convention** — even from one
  manufacturer, even on one board. XT90PW-F is pin 1 = `+`; AMASS XT30UPB-F is
  pin 1 = `−`. That inverted three connectors (F10).
- **A "Mounting Detail" hole callout is not a recommended plated-hole diameter.**
  Keystone's drawing says Ø1.6 mm; their own KiCad land uses 1.7272. The pin is a
  1.57 mm tab whose diagonal is 1.62 mm — wider than the drawing's hole.
- **A bulk capacitor is a STUB across the rail, never a junction in it.** Routing
  load current through the cap's pad burdens it with current it was never sized
  for and puts the decoupling at the end of a series path.
- **An SMD pad exists on ONE layer.** Copper on the other layer at its coordinates
  can never reach it — and DRC will not say so, because a dangling same-net track
  is not "unconnected".

### Workflow

- **Duplicate pad numbers do not survive Specctra DSN.** The format keys pins by
  name, so two pads numbered "2" export as one and the router never joins them.
  Bridge them explicitly after import.
- **Rotating a routed footprint invalidates every trace touching it.** The pads
  swap which net sits where while the copper stays put — 12 shorts, instantly.
  Clear those traces at the same time as the rotation, and RE-RUN DRC: track
  count and spot-checks will not show it.
- **The tree you assume is not the tree the router builds.** Widths solved against
  an assumed topology are wrong when the router picks a different one. Verify the
  topology, then size it.
- **Script-generated boards and hand routing cannot both be the source of truth.**
  `layout_*.py` and `route_*.py` wipe every trace. Once a board is hand-routed the
  `.kicad_pcb` is authoritative and the scripts are history — say so in the commit
  message, because nothing in the files enforces it.
- **Visual review finds what gates structurally cannot.** DRC checks that copper
  is self-consistent; it has no opinion on whether the intent is right. Reversed
  polarity, an 8× overloaded via, a cap wired in series and orphaned copper were
  all DRC-clean.

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
