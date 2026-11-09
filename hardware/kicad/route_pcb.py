#!/usr/bin/env python3
"""
Auto-routing pipeline for robot-buddy-reflex (4-layer).
  1. Export DSN from PCB
  2. Inject Power / Motor / Signal net classes
  3. Run freerouting (needs: java -jar /tmp/freerouting-2.0.jar)
  4. Import SES back into PCB
  5. Fix trace widths (SES format carries no explicit widths)
  6. Fill copper zones (GND on In1.Cu, +BATT on In2.Cu)

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
JAR = os.environ.get("FREEROUTING_JAR", "/tmp/freerouting-2.0.jar")  # 1.9.0 made the June route

OX, OY = 0.0, 0.0  # board drawing origin (must match layout_pcb.py)
sys_path_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, sys_path_dir)
import board_outline as BO  # noqa: E402

W, H = BO.W, BO.H  # bounding box; the edge (and the planes below) follow BO.outline()

POWER_NETS = {"+BATT", "+5V", "+3V3", "GND"}
MOTOR_NETS = {"AO1", "AO2", "BO1", "BO2"}

POWER_W = 0.40  # mm  (0.50→0.40 to clear NeoPixel cluster; adequate for <500mA 5V rail)
MOTOR_W = (
    0.40  # mm  (matches Power class; motor traces are short, widen manually if needed)
)
SIGNAL_W = 0.25  # mm
PASSES = int(os.environ.get("RB_PASSES", "10"))

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
dsn_power = {f"+{n}" if not n.startswith("+") else n for n in POWER_NETS} | {"GND"}
dsn_motor = {f"/{n}" for n in MOTOR_NETS}
MOVE = dsn_power | dsn_motor


def rebuild_kicad_default(m):
    header = m.group(1)
    netlist = m.group(2)
    trailer = m.group(3)
    tokens = re.findall(r'"[^"]*"|\S+', netlist)
    kept = [t for t in tokens if t not in MOVE]
    return header + "\n      ".join([""] + kept) + "\n      " + trailer


dsn2 = re.sub(
    r"(\(class kicad_default)(.*?)(\(circuit)",
    rebuild_kicad_default,
    dsn,
    flags=re.DOTALL,
)

# Merge motor nets into the Power class — same width/clearance, fewer constraint
# interactions for freerouting. Motor traces are short (U2 → J1/J2) so 0.5mm
# tracks with 250µm clearance are adequate.
dsn_power_and_motor = dsn_power | dsn_motor
NEW_CLASSES = (
    f"(class Power\n"
    f"  {' '.join(sorted(dsn_power_and_motor))}\n"
    f'  (circuit (use_via "Via[0-1]_800:400_um"))\n'
    f"  (rule (width {int(POWER_W * 1000)}) (clearance 200))\n"
    f")\n"
)
dsn2 = dsn2.replace("(class kicad_default", NEW_CLASSES + "(class kicad_default", 1)

# Strip component body outlines: the circular 1000µF THT cap courtyard alone has
# 197 polygon outlines with 609 coord-pairs, causing freerouting to spend O(n²)
# time on clearance checks.  Pads are kept; KiCad DRC catches courtyard violations.
dsn2 = re.sub(r"\n\s*\(outline \(path [^)]+\)\)", "", dsn2)
dsn2 = re.sub(r"\n\s*\(outline \(polygon[^)]+\)\)", "", dsn2, flags=re.DOTALL)
print(f"  Outlines remaining: {dsn2.count('(outline ')}")

# Drop inner copper layers from DSN: only route on F.Cu / B.Cu.
# Inner layers (In1.Cu=GND plane, In2.Cu=+BATT plane) are handled as KiCad
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

# Add GND plane on B.Cu — same pattern as scout-mcu.  freerouting routes GND pads
# via short vias rather than long tracks (fast); non-GND signals still route on B.Cu
# with clearance from the plane.  Vias are through-hole so they land on the
# KiCad In1.Cu GND zone, which fills around them on zone fill.
_PLANE_PTS = BO.inset(BO.outline(), 0.5)  # notched outline, 0.5 in from the edge
_PLANE_PTS = _PLANE_PTS + _PLANE_PTS[:1]
_GND_PLANE = (
    "(plane GND (polygon B.Cu 0  "
    + "  ".join(f"{int(round(x * 1000))} -{int(round(y * 1000))}" for x, y in _PLANE_PTS)
    + "))\n    "
)
dsn2 = dsn2.replace("    (via ", "    " + _GND_PLANE + "(via ", 1)

# Router boundary 0.3 inside the real edge: freerouting keeps only its 0.2 class clearance
# to the boundary, KiCad wants 0.5 copper-to-edge (the notch edges run through the routing).
_BND = BO.inset(BO.outline(), 0.3)
_BND = _BND + _BND[:1]
_bnd_path = "(path pcb 0  " + "  ".join(f"{int(round(x * 1000))} -{int(round(y * 1000))}" for x, y in _BND) + ")"
dsn2, _nb = re.subn(r"\(boundary\s*\(path pcb 0[^)]*\)", "(boundary\n      " + _bnd_path, dsn2, count=1)
assert _nb == 1, "DSN boundary not found"

with open(DSN_CLS, "w") as f:
    f.write(dsn2)
print(f"  3 classes → {DSN_CLS}")

# ── Step 3: Run freerouting ───────────────────────────────────────────────────
print(f"Running freerouting ({PASSES} passes)...")
if not os.path.exists(JAR):
    print(
        f"ERROR: {JAR} not found. Download freerouting v2.0.1 jar first.",
        file=sys.stderr,
    )
    sys.exit(1)

result = subprocess.run(
    ["java", "-jar", JAR, "-de", DSN_CLS, "-do", SES, "-mp", str(PASSES), "-mt", "1"],
    capture_output=True,
    text=True,
)
for line in (result.stdout + result.stderr).splitlines():
    if any(k in line for k in ("pass #", "complet", "Saving", "unrouted", "ERROR")):
        print(" ", line.strip())

if not os.path.exists(SES):
    print("ERROR: freerouting did not produce a SES file.", file=sys.stderr)
    sys.exit(1)

# ── Step 4+5: Import SES and fix trace widths ─────────────────────────────────
print("Importing SES and fixing trace widths...")
b2 = pcbnew.LoadBoard(PCB)
pcbnew.ImportSpecctraSES(b2, SES)

counts = {SIGNAL_W: 0, POWER_W: 0}
for track in b2.GetTracks():
    if track.GetClass() == "PCB_VIA":
        continue
    net = track.GetNetname().lstrip("/")
    if net in POWER_NETS or net in MOTOR_NETS:
        w = POWER_W
    else:
        w = SIGNAL_W
    track.SetWidth(pcbnew.FromMM(w))
    counts[w] += 1

b2.Save(PCB)

print(f"  Signal {SIGNAL_W:.2f}mm: {counts[SIGNAL_W]} segments")
print(f"  Power+Motor {POWER_W:.2f}mm: {counts[POWER_W]} segments")

# ── Step 6: Fill copper zones and report ──────────────────────────────────────
print("Filling copper zones...")
b3 = pcbnew.LoadBoard(PCB)

# Add a GND fill zone on B.Cu to match the B.Cu GND plane declared in the DSN.
# freerouting routes GND pads to the B.Cu plane; without a KiCad zone here those
# B.Cu-only GND pads remain floating after SES import.
# Re-running on a routed board (existing tracks become seeds) must not stack a second zone.
for _z in list(b3.Zones()):
    if _z.GetLayer() == pcbnew.B_Cu and _z.GetNetname() == "GND":
        b3.Remove(_z)
_gnd_zone = pcbnew.ZONE(b3)
_gnd_zone.SetLayer(pcbnew.B_Cu)
_gnd_net = b3.FindNet("GND")
if _gnd_net:
    _gnd_zone.SetNet(_gnd_net)
_go = _gnd_zone.Outline()
_go.NewOutline()
for _cx, _cy in BO.inset(BO.outline(), 0.3):  # notched outline, 0.3 in from the edge
    _go.Append(pcbnew.FromMM(OX + _cx), pcbnew.FromMM(OY + _cy))
_gnd_zone.SetMinThickness(pcbnew.FromMM(0.25))
_gnd_zone.SetLocalClearance(pcbnew.FromMM(0.25))  # 0.1 -> 0.25: KiCad 10 flags pad mask openings that expose the pour
_gnd_zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
b3.Add(_gnd_zone)

try:
    filler = pcbnew.ZONE_FILLER(b3)
    filler.Fill(b3.Zones())
    print(f"  Filled {len(list(b3.Zones()))} zone(s)")
except Exception as e:
    print(f"  Zone fill skipped: {e}")

b3.Save(PCB)

# ── Step 6b: Finishing patches for the 2026-11-09 placement ─────────────────
# freerouting stops once it thinks every net is joined, but leaves a few sub-nets apart on
# this board. Each patch names two pads it must join and is laid only if they aren't joined
# already (connectivity incl. zones), so a re-route that finds its own path skips it.
# Paths were picked from the routed copper; pcb_qc.py (DRC) re-checks them.
PATCHES = [
    # +3V3: U2-VCC/J2/C5 group to the U1/R4/J1/J5 group, F.Cu between J1/J2's pads and the
    # right edge (pads to x 63.12, edge 65: track 63.7-64.1). Not B.Cu: ENC_RB detours round
    # J2-5 at x 63.45 there.
    ("+3V3", ("J1", "3"), ("J2", "3"), pcbnew.F_Cu,
     [(62.15, 12.0), (63.9, 12.0), (63.9, 37.0), (62.15, 37.0)]),
    # +5V to J6 (HC-SR04 VCC): B.Cu down the rear edge, x 1.0 (edge 0.5, MH1 hole from x 2.4).
    ("+5V", ("J6", "1"), ("J9", "1"), pcbnew.B_Cu,
     [(5.0, 3.0), (1.0, 7.0), (1.0, 34.5), (1.5, 36.5)]),
    # +5V: C7/C6 to the R10/U3 run, F.Cu under R11 (pad bottom 51.25) and above the notch
    # edge (y 53; copper <= 52.5).
    ("+5V", ("C7", "1"), ("R10", "1"), pcbnew.F_Cu,
     [(33.0, 50.98), (32.2, 51.78), (27.49, 51.78), (26.72, 51.01)]),
]
bp = pcbnew.LoadBoard(PCB)
bp.BuildConnectivity()
_pp = {(fp.GetReference(), p.GetNumber()): p for fp in bp.GetFootprints() for p in fp.Pads()}
_laid = 0
for _net, _a, _b, _layer, _pts in PATCHES:
    _joined = {
        (i.GetParentFootprint().GetReference(), i.GetNumber())
        for i in bp.GetConnectivity().GetConnectedItems(_pp[_a])
        if i.Type() == pcbnew.PCB_PAD_T
    }
    if _b in _joined:
        print(f"  {_net} {_a}-{_b}: already joined")
        continue
    for (x1, y1), (x2, y2) in zip(_pts, _pts[1:]):
        _t = pcbnew.PCB_TRACK(bp)
        _t.SetLayer(_layer)
        _t.SetNet(bp.FindNet(_net))
        _t.SetWidth(pcbnew.FromMM(POWER_W))
        _t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(OX + x1), pcbnew.FromMM(OY + y1)))
        _t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(OX + x2), pcbnew.FromMM(OY + y2)))
        bp.Add(_t)
    _laid += 1
    print(f"  {_net} {_a}-{_b}: patched on {bp.GetLayerName(_layer)}")
if _laid:
    pcbnew.ZONE_FILLER(bp).Fill(bp.Zones())
bp.Save(PCB)

# ── Step 7: Manual +3V3 patch (R4-1 and U2-10) ───────────────────────────────
# freerouting consistently misses these two pads because the narrow window
# between U1.19/U1.20 (y=21.205..21.595) and the /ESTOP diagonal (x+y=49.47)
# make the F.Cu route hard to discover automatically.
#
# Route on F.Cu only, tapping from the existing +3V3 via at (13.30, 24.27).
# Key clearance constraints:
#   R4.2 (/ESTOP) pad 0.540x0.640mm at (30.00,20.49): right edge 30.270, top 20.170
#   /ESTOP diagonal (26.80,22.67)→(28.98,20.49): line x+y=49.47
#   Use x=30.70 verticals (0.305mm from R4.2 right edge)
#   Use y=19.70 horizontal (0.345mm from R4.2 top edge)
#   Corner at (27.20,21.40): 0.615mm center-to-center from /ESTOP diagonal
print("Applying manual +3V3 patch (R4-1 and U2-10)...")
b4 = pcbnew.LoadBoard(PCB)
_3v3_net = b4.FindNet("+3V3")
b4.BuildConnectivity()
_pads = {(fp.GetReference(), p.GetNumber()): p for fp in b4.GetFootprints() for p in fp.Pads()}
_src = {
    (i.GetParentFootprint().GetReference(), i.GetNumber())
    for i in b4.GetConnectivity().GetConnectedItems(_pads[("U1", "3")])
    if i.Type() == pcbnew.PCB_PAD_T
}
if {("R4", "1"), ("U2", "10")} <= _src:
    print("  +3V3 already reaches R4-1 and U2-10: patch not needed")
elif not os.environ.get("RB_3V3_PATCH"):
    # The patch below is laid for the 2026-11-08 placement (U1 at (9, 16), rot 0); since the
    # 2026-11-09 re-place it would land in the wrong spot. Opt in only after re-deriving it.
    print("  WARNING: +3V3 misses R4-1/U2-10 and the patch is off (RB_3V3_PATCH): route by hand")
elif _3v3_net:
    _patch_segs = [
        # y 21.40 (2026-11-08, KiCad 10 pads): U1 pad 19 bottom 20.88 -> >= 21.205; pad 20
        # top 21.92 -> <= 21.595; UART_RX via (14.49,20.50) -> >= 21.125; ESTOP via
        # (22.10,22.04) -> <= 21.415. (21.15 sat 0.07 from pad 19.)
        ((13.30, 24.27), (13.30, 21.40)),
        ((13.30, 21.40), (27.20, 21.40)),
        ((27.20, 21.40), (28.50, 19.70)),
        ((28.50, 19.70), (30.70, 19.70)),
        ((30.70, 19.70), (30.70, 20.38)),
        ((30.70, 20.38), (53.62, 20.38)),
        ((53.62, 20.38), (53.62, 21.65)),
        ((30.70, 20.38), (30.70, 21.51)),
        ((30.70, 21.51), (30.00, 21.51)),
    ]
    # The previous run's patch survives as a routing seed: don't lay it twice.
    _have = set()
    for _t in b4.GetTracks():
        if _t.Type() == pcbnew.PCB_TRACE_T and _t.GetNetname() == "+3V3" and _t.GetLayer() == pcbnew.F_Cu:
            _a = (round(pcbnew.ToMM(_t.GetStart().x), 2), round(pcbnew.ToMM(_t.GetStart().y), 2))
            _e = (round(pcbnew.ToMM(_t.GetEnd().x), 2), round(pcbnew.ToMM(_t.GetEnd().y), 2))
            _have |= {(_a, _e), (_e, _a)}
    _patch_segs = [sg for sg in _patch_segs if (sg[0], sg[1]) not in _have]
    for (x1, y1), (x2, y2) in _patch_segs:
        _t = pcbnew.PCB_TRACK(b4)
        _t.SetLayer(pcbnew.F_Cu)
        _t.SetNet(_3v3_net)
        _t.SetWidth(pcbnew.FromMM(0.25))
        _t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        _t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        b4.Add(_t)
    b4.Save(PCB)
    print(f"  Added {len(_patch_segs)} patch tracks on F.Cu")
else:
    print("  WARNING: +3V3 net not found, patch skipped")
