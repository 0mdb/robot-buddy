#!/usr/bin/env python3
"""
Auto-routing pipeline for robot-buddy-reflex (4-layer).
  1. Export DSN from PCB
  2. Inject Power / Motor / Signal net classes
  3. Run freerouting (needs: java -jar ~/tools/freerouting-2.1.0.jar)
  4. Import SES back into PCB
  5. Fix trace widths (SES format carries no explicit widths)
  6. Fill copper zones (GND on In1.Cu, +5V on In2.Cu)

Run layout_pcb.py first to regenerate a clean unrouted PCB, then run this.
"""

import subprocess
import re
import os
import sys

PCB = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb"
DSN = "/tmp/reflex.dsn"
DSN_CLS = "/tmp/reflex-classed.dsn"
SES = "/tmp/reflex-routed.ses"
# Freerouting 2.1.0 is the newest release that runs on the installed JDK 21
# (its classes are Java 21 / class v65).  2.2.x is built for Java 25 and dies with
# UnsupportedClassVersionError — bump the JDK before moving past 2.1.0.
# Kept in ~/tools rather than /tmp so it survives a reboot.
JAR = os.path.expanduser("~/tools/freerouting-2.1.0.jar")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_outline as BO  # noqa: E402

OX, OY = 0.0, 0.0  # board drawing origin (must match layout_pcb.py)
W, H = BO.W, BO.H  # board dimensions mm (board_outline.py is the one source)

# ── Net classes come from the .kicad_pro, NOT from constants here ─────────────
# layout_pcb.py writes them; this reads them back. They used to be hardcoded in
# both places and drifted — freerouting was told 200um clearance for motor nets
# while KiCad DRC demanded 300um, producing 72 clearance violations that looked
# like autorouter noise but were a spec mismatch.
import json as _json  # noqa: E402

_PRO = PCB.replace(".kicad_pcb", ".kicad_pro")
with open(_PRO) as _pf:
    _ns = _json.load(_pf)["net_settings"]
NETCLASS = {c["name"]: c for c in _ns["classes"]}
CLASS_NETS = {}
for _pat in _ns["netclass_patterns"]:
    CLASS_NETS.setdefault(_pat["netclass"], set()).add(_pat["pattern"])

SIGNAL_W = NETCLASS["Default"]["track_width"]
# net name -> (width, class) for the post-SES width fixup
NET_W = {}
for _cls, _nets in CLASS_NETS.items():
    for _n in _nets:
        NET_W[_n] = NETCLASS[_cls]["track_width"]

PASSES = 10

# ── Step 0: Drop shorting seed tracks ─────────────────────────────────────────
# Must run BEFORE the DSN export so freerouting sees those nets as unrouted and lays
# them again against the current pad geometry. See finish_pcb.drop_shorting_seeds.
_unshort = subprocess.run(
    [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "finish_pcb.py"),
        "unshort",
    ],
    capture_output=True,
    text=True,
)
for _line in _unshort.stdout.splitlines():
    if _line.strip().startswith("Unshort"):
        print(_line)
if _unshort.returncode != 0:
    print(_unshort.stderr.rstrip(), file=sys.stderr)
    sys.exit(1)

# ── Step 1: Export DSN ────────────────────────────────────────────────────────
print("Exporting DSN...")
import pcbnew  # noqa: E402

b = pcbnew.LoadBoard(PCB)
pcbnew.ExportSpecctraDSN(b, DSN)
print(f"  {os.path.getsize(DSN):,} bytes → {DSN}")

# ── Step 2: Inject net classes ────────────────────────────────────────────────
print("Injecting net classes...")
with open(DSN) as f:
    dsn = f.read()

# Net names that will move out of kicad_default
MOVE = {n for nets in CLASS_NETS.values() for n in nets}


def rebuild_kicad_default(m):
    header, netlist, trailer = m.group(1), m.group(2), m.group(3)
    tokens = re.findall(r'"[^"]*"|\S+', netlist)
    kept = [t for t in tokens if t not in MOVE]
    return header + "\n      ".join([""] + kept) + "\n      " + trailer


dsn2 = re.sub(
    r"(\(class kicad_default)(.*?)(\(circuit)",
    rebuild_kicad_default,
    dsn,
    flags=re.DOTALL,
)

# One DSN class per KiCad netclass, with ITS width and clearance — so freerouting
# plans against the same numbers DRC will later enforce.
NEW_CLASSES = ""
for _cls in sorted(CLASS_NETS):
    _c = NETCLASS[_cls]
    NEW_CLASSES += (
        f"(class {_cls}\n"
        f"  {' '.join(sorted(CLASS_NETS[_cls]))}\n"
        f'  (circuit (use_via "Via[0-1]_800:400_um"))\n'
        f"  (rule (width {int(_c['track_width'] * 1000)}) "
        f"(clearance {int(_c['clearance'] * 1000)}))\n"
        f")\n"
    )
dsn2 = dsn2.replace("(class kicad_default", NEW_CLASSES + "(class kicad_default", 1)

# Raise the STRUCTURE-level clearance to the strictest netclass value.
# Per-class (rule (clearance N)) alone did NOT prevent violations: freerouting
# plans most pairs against the structure-level rule, which KiCad exports at the
# Default netclass value (200um) plus a very permissive smd_smd rule (50um).
# That is why aligning the per-class numbers changed nothing — actuals as low as
# 0.135mm were being produced against a 0.25mm requirement.
_max_clr = int(max(c["clearance"] for c in NETCLASS.values()) * 1000)
dsn2, _n1 = re.subn(
    r"(\(structure.*?\(rule\s*\n?\s*\(width \d+\)\s*\n?\s*\(clearance )\d+",
    rf"\g<1>{_max_clr}",
    dsn2,
    count=1,
    flags=re.DOTALL,
)
dsn2, _n2 = re.subn(
    r"\(clearance \d+\s*\(type smd_smd\)\)",
    f"(clearance {_max_clr} (type smd_smd))",
    dsn2,
)
print(f"  global clearance -> {_max_clr}um (rule:{_n1} smd_smd:{_n2})")

# Pull the routing boundary in so freerouting honours the board-edge rule.
#
# freerouting keeps only its structure clearance (0.2 mm) from the boundary, while KiCad
# DRC enforces copper_edge_clearance (0.5 mm, board setup). On the 65 x 60 board nothing
# routed near an edge so it never showed; on the 52.5 x 46 board (2026-11-09) the router
# ran /SCL 0.28 mm from the front edge past J5 and dropped a GND via 0.43 mm from the rear
# edge. Inset the boundary by the difference, so router clearance + inset = the DRC rule.
# Pads themselves are placed >= 0.5 mm in (layout_pcb.py), so none fall outside it.
_EDGE_CLR_UM = int(round(b.GetDesignSettings().m_CopperEdgeClearance / 1000))
_edge_inset = max(0, _EDGE_CLR_UM - _max_clr) / 1000.0
_bnd = BO.inset(BO.outline(), _edge_inset)
_bnd_path = "  ".join(
    f"{int(round(x * 1000))} {int(round(-y * 1000))}" for x, y in _bnd + _bnd[:1]
)
dsn2, _n5 = re.subn(
    r"\(boundary\s*\n\s*\(path pcb 0 [^)]*\)",
    f"(boundary\n      (path pcb 0  {_bnd_path})",
    dsn2,
    count=1,
)
print(
    f"  routing boundary inset {_edge_inset:.2f} mm (edge rule {_EDGE_CLR_UM} um): {_n5}"
)

# Give the keepout circles an explicit centre.
#
# KiCad exports mounting-hole keepouts as `(circle F.Cu 3700)` — diameter only. The
# Specctra grammar allows the centre to be omitted (it defaults to 0 0), but
# freerouting does not, and fails the whole package with
#     ERROR Package.read_scope: could not read keepout area of package
#           'MountingHole:MountingHole_3.2mm_M3_DIN965'
# It then routes as if the mounting holes were not there. That error has been
# printed on every run of this script and was treated as noise; it is not. It put
# two /AO1 segments through MH5's 3.2mm hole, which DRC catches as hole_clearance
# but which no amount of router tuning would have fixed.
dsn2, _n3 = re.subn(r"\(circle (\S+) (\d+)\)", r"(circle \1 \2 0 0)", dsn2)
print(f"  keepout circles given explicit centres: {_n3}")

# Strip component body outlines: the circular 1000µF THT cap courtyard alone has
# 197 polygon outlines with 609 coord-pairs, causing freerouting to spend O(n²)
# time on clearance checks.  Pads are kept; KiCad DRC catches courtyard violations.
dsn2 = re.sub(r"\n\s*\(outline \(path [^)]+\)\)", "", dsn2)
dsn2 = re.sub(r"\n\s*\(outline \(polygon[^)]+\)\)", "", dsn2, flags=re.DOTALL)
print(f"  Outlines remaining: {dsn2.count('(outline ')}")

# Drop inner copper layers from DSN: only route on F.Cu / B.Cu.
# Inner layers (In1.Cu=GND plane, In2.Cu=+5V plane) are handled as KiCad
# copper-fill zones after SES import; freerouting routing 4 layers is very slow.
dsn2 = re.sub(
    r"\n\s*\(plane\s+\S+\s+\(polygon\s+\S+\s+[\d\s\-]+\)\)", "", dsn2, flags=re.DOTALL
)
dsn2 = re.sub(
    r"\n\s*\(layer In\d\.Cu\s+\(type signal\)\s*\(property\s*\(index \d+\)\s*\)\s*\)",
    "",
    dsn2,
    flags=re.DOTALL,
)

# ...and drop the keepouts that referenced those now-nonexistent layers.
# This is the other half of the mounting-hole bug: giving the circles an explicit
# centre was necessary but not sufficient. Four keepouts are emitted per hole, one
# per copper layer; the In1.Cu/In2.Cu ones point at layers stripped just above, and
# freerouting rejects the ENTIRE package when it cannot resolve a keepout's layer —
# so the F.Cu and B.Cu keepouts were being discarded along with them and the holes
# were invisible to the router. Exactly 2 errors per run for 4 keepouts, which is
# what identified it.
dsn2, _n4 = re.subn(r"\n\s*\(keepout \"\" \(circle In\d\.Cu [^)]*\)\)", "", dsn2)
print(f"  keepouts on stripped inner layers removed: {_n4}")

# Add GND plane on B.Cu — same pattern as scout-mcu.  freerouting routes GND pads
# via short vias rather than long tracks (fast); non-GND signals still route on B.Cu
# with clearance from the plane.  Vias are through-hole so they land on the
# KiCad In1.Cu GND zone, which fills around them on zone fill.
_W_UM = int(W * 1000)  # board width in µm
_H_UM = int(H * 1000)  # board height in µm
_INS = 500  # plane inset from board edge (µm)
_GND_PLANE = (
    f"(plane GND (polygon B.Cu 0  {_INS} -{_INS}  {_W_UM - _INS} -{_INS}  "
    f"{_W_UM - _INS} -{_H_UM - _INS}  {_INS} -{_H_UM - _INS}  {_INS} -{_INS}))\n    "
)
dsn2 = dsn2.replace("    (via ", "    " + _GND_PLANE + "(via ", 1)

with open(DSN_CLS, "w") as f:
    f.write(dsn2)
print(f"  4 classes (Rail/Power/Motor/default) → {DSN_CLS}")

# ── Step 3: Run freerouting ───────────────────────────────────────────────────
print(f"Running freerouting ({PASSES} passes)...")
if not os.path.exists(JAR):
    print(
        f"ERROR: {JAR} not found. Download the freerouting 2.1.0 jar first "
        f"(2.2.x needs JDK 25; installed JDK is 21).",
        file=sys.stderr,
    )
    sys.exit(1)

# Delete any SES from a previous run BEFORE invoking the router.  Without this,
# a freerouting failure leaves the stale file in /tmp, the existence check below
# passes, and the script imports last run's routing while reporting success.
# Same failure class that fabricated robot-scout-mcu with zero traces: the
# toolchain reported success for work that did not happen.
# freerouting is not deterministic: on the 52.5 x 46 board (2026-11-09) the same DSN gave
# 0 unrouted on one run and 8 on the next. Retry until a run reports none, keeping the
# best SES seen; the DRC gate at the end decides whether what was imported is good.
ROUTE_TRIES = int(os.environ.get("RB_ROUTE_TRIES", "6"))
SES_BEST = SES + ".best"
_best = None
for _try in range(1, ROUTE_TRIES + 1):
    if os.path.exists(SES):
        os.remove(SES)
    result = subprocess.run(
        [
            "java",
            "-jar",
            JAR,
            "-de",
            DSN_CLS,
            "-do",
            SES,
            "-mp",
            str(PASSES),
            "-mt",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    _out = (result.stdout + result.stderr).splitlines()
    # 2.1.0 prints no "Auto-routing was completed" line (2026-11-10: every try then
    # scored the 99 placeholder, so the retry loop could not tell runs apart). It ends
    # with a JSON summary carrying "incomplete_count"; older builds had the line.
    _final = [ln for ln in _out if "Auto-routing was completed" in ln]
    _inc = [ln for ln in _out if '"incomplete_count"' in ln]
    for line in _final or _inc or [ln for ln in _out if "ERROR" in ln]:
        print(f"  try {_try}:", line.strip())
    if result.returncode != 0 or not os.path.exists(SES):
        continue
    if _inc:
        _m = re.search(r'"incomplete_count":\s*(\d+)', _inc[-1])
    else:
        _m = re.search(r"\((\d+) unrouted", _final[-1]) if _final else None
    _unrouted = int(_m.group(1)) if _m else (0 if _final else 99)
    if _best is None or _unrouted < _best:
        _best = _unrouted
        os.replace(SES, SES_BEST)
    if _unrouted == 0:
        break
if _best is not None:
    os.replace(SES_BEST, SES)
    print(
        f"  best: {_best} unrouted (freerouting's count; planes connect some of these)"
    )

if result.returncode != 0:
    print(
        f"ERROR: freerouting exited {result.returncode} — board NOT routed.",
        file=sys.stderr,
    )
    sys.exit(1)

if not os.path.exists(SES):
    print("ERROR: freerouting did not produce a SES file.", file=sys.stderr)
    sys.exit(1)

# ── Step 4+5: Import SES and fix trace widths ─────────────────────────────────
print("Importing SES and fixing trace widths...")
b2 = pcbnew.LoadBoard(PCB)
pcbnew.ImportSpecctraSES(b2, SES)

counts = {}
for track in b2.GetTracks():
    if track.GetClass() == "PCB_VIA":
        continue
    w = NET_W.get(track.GetNetname(), SIGNAL_W)
    track.SetWidth(pcbnew.FromMM(w))
    counts[w] = counts.get(w, 0) + 1

b2.Save(PCB)

for _w in sorted(counts):
    print(f"  {_w:.2f}mm: {counts[_w]} segments")

# ── Step 6: Fill copper zones and report ──────────────────────────────────────
print("Filling copper zones...")
b3 = pcbnew.LoadBoard(PCB)

# Add a GND fill zone on B.Cu to match the B.Cu GND plane declared in the DSN.
# freerouting routes GND pads to the B.Cu plane; without a KiCad zone here those
# B.Cu-only GND pads remain floating after SES import.
# REUSE an existing B.Cu GND zone rather than removing and re-adding one.
#
# Running route_pcb.py twice in a row used to stack a second identical zone on the
# first (DRC: zones_intersect) — the same accumulation family as the duplicate
# tracks, where a step that ADDS must either be idempotent or clear its own output.
# But clearing it with b3.Remove() traded one bug for a worse one: the removal
# poisons the SWIG layer, and the very next pcbnew.ZONE(...).Outline() came back as
# a bare SwigPyObject, so route_pcb.py died before filling any zone. Reusing the
# existing object touches nothing and is idempotent by construction.
_gnd_zone = next(
    (z for z in b3.Zones() if z.GetLayer() == pcbnew.B_Cu and z.GetNetname() == "GND"),
    None,
)
_fresh = _gnd_zone is None
if _fresh:
    _gnd_zone = pcbnew.ZONE(b3)
    _gnd_zone.SetLayer(pcbnew.B_Cu)
    _gnd_net = b3.FindNet("GND")
    if _gnd_net:
        _gnd_zone.SetNet(_gnd_net)
    _go = _gnd_zone.Outline()
    _go.NewOutline()
    _inset_nm = pcbnew.FromMM(0.3)
    _ox_nm = pcbnew.FromMM(OX)
    _oy_nm = pcbnew.FromMM(OY)
    _ow_nm = pcbnew.FromMM(OX + W)
    _oh_nm = pcbnew.FromMM(OY + H)
    for _cx, _cy in [
        (_ox_nm + _inset_nm, _oy_nm + _inset_nm),
        (_ow_nm - _inset_nm, _oy_nm + _inset_nm),
        (_ow_nm - _inset_nm, _oh_nm - _inset_nm),
        (_ox_nm + _inset_nm, _oh_nm - _inset_nm),
    ]:
        _go.Append(int(_cx), int(_cy))
_gnd_zone.SetMinThickness(pcbnew.FromMM(0.25))
# Carve at the DESIGN clearance, not a hardcoded 0.1mm.
#
# This zone covers all of B.Cu, so every non-GND track routed there needs the fill to
# pull back around it. At 0.1mm the copper pour stopped 0.1mm short while DRC demanded
# the netclass 0.2mm — so each such track was a clearance error against the zone.
# It stayed hidden while B.Cu carried almost no signal routing, then appeared the
# moment /SDA and /ENC_LB were re-routed there (and produced 121 errors in a
# from-scratch route, which is what exposed it as systemic rather than local).
_gnd_zone.SetLocalClearance(pcbnew.FromMM(NETCLASS["Default"]["clearance"]))
_gnd_zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
if _fresh:
    b3.Add(_gnd_zone)

try:
    filler = pcbnew.ZONE_FILLER(b3)
    filler.Fill(b3.Zones())
    print(f"  Filled {len(list(b3.Zones()))} zone(s)")
except Exception as e:
    print(f"  Zone fill skipped: {e}")

b3.Save(PCB)

# ── (removed) Manual +3V3 patch ──────────────────────────────────────────────
# A hand-tuned 9-segment F.Cu patch used to force R4-1 and U2-10 onto +3V3,
# because freerouting missed them on the v1 layout. Its coordinates were pinned
# to v1 geometry ("clears ESTOP via at (22.10,22.04)", a run to x=53.62 where C3
# now sits) and it was applied unconditionally — so on the v2 board it was laying
# nine stale tracks across a layout it no longer described. Verified obsolete
# 2026-08-06: routing completes with 0 unconnected items without it.

# ── Step 6.5: Post-route finishing ────────────────────────────────────────────
# Dangling stubs and silk placement can only be settled once the copper is final,
# so they run here rather than in layout_pcb.py. Encoded in the pipeline, never
# done by hand in a KiCad session — see register P1.
print("\nFinishing (dangling tracks, silkscreen)...")
_fin = subprocess.run(
    [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "finish_pcb.py"),
    ],
    capture_output=True,
    text=True,
)
print(_fin.stdout.rstrip())
if _fin.returncode != 0:
    print(_fin.stderr.rstrip(), file=sys.stderr)
    print("ERROR: finishing pass failed.", file=sys.stderr)
    sys.exit(1)

# ── Step 7: Verify the board is actually routed ───────────────────────────────
# The router must not exit 0 on a board it failed to route.  Delegates to the
# shared gate (~/kicad-libs/tools/check_pcb_routing.py, symlinked into both
# repos) so there is exactly one definition of "routed".
print("\nVerifying routing...")
_gate = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
    "check_pcb_routing.py",
)
_res = subprocess.run([sys.executable, _gate, PCB], capture_output=True, text=True)
print(_res.stdout.rstrip())
if _res.returncode != 0:
    print(
        "ERROR: routing gate failed — board is NOT fully routed. "
        "Do not export gerbers.",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Step 8: DRC gate — errors and unconnected items, from KiCad itself ───────────
# The shared routing gate above passed a board with 8 DRC-unconnected items on
# 2026-11-09 (it checks the routing it can see, not KiCad's connectivity incl. zones).
# KiCad's own DRC is the oracle for "routed", so it gets the last word here.
import json as _json_g  # noqa: E402
import tempfile as _tmp_g  # noqa: E402

with _tmp_g.TemporaryDirectory() as _td:
    _rep = os.path.join(_td, "drc.json")
    subprocess.run(
        ["kicad-cli", "pcb", "drc", "--format", "json", "-o", _rep, PCB],
        capture_output=True,
        text=True,
    )
    _d = _json_g.load(open(_rep))
_errs = [v for v in _d.get("violations", []) if v.get("severity") == "error"]
_unc = _d.get("unconnected_items", [])
_warn = [v for v in _d.get("violations", []) if v.get("severity") != "error"]
print(f"\nDRC: {len(_errs)} errors, {len(_unc)} unconnected, {len(_warn)} warnings")
for v in (_errs + _unc)[:20]:
    print("  ", v["type"], [i["description"][:60] for i in v["items"]])
if _errs or _unc:
    print("ERROR: DRC gate failed — do not export gerbers.", file=sys.stderr)
    sys.exit(1)
