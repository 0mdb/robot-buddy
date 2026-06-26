#!/usr/bin/env python3
"""
PCB layout for robot-buddy-reflex.
Reads schematic netlist, places all footprints at sensible positions with nets
assigned.  Open the resulting .kicad_pcb in KiCad → route traces, run DRC.

Board outline: 65 × 60 mm
"""

import subprocess
import uuid
import xml.etree.ElementTree as ET
from kiutils.board import Board
from kiutils.footprint import Footprint
from kiutils.items.common import Net, Position
from kiutils.items.gritems import GrRect

PCB = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb"
SCH = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_sch"
KICAD = "/usr/share/kicad/footprints"
LOCAL = "/home/ben/kicad-libs/footprints/robot-projects.pretty"
NETLIST = "/tmp/reflex-netlist.xml"

OX, OY = 0.0, 0.0  # board origin in KiCad drawing (at top-left; move after routing)
W, H = 65.0, 60.0  # board dimensions mm

# ── Regenerate netlist from schematic ────────────────────────────────────
subprocess.run(
    [
        "kicad-cli",
        "sch",
        "export",
        "netlist",
        "--format",
        "kicadxml",
        "--output",
        NETLIST,
        SCH,
    ],
    check=True,
    capture_output=True,
)

# ── Parse netlist: (ref, pad_str) → net_name ─────────────────────────────
tree = ET.parse(NETLIST)
root = tree.getroot()
pad_net = {}
for ne in root.find("nets"):
    name = ne.get("name")
    for node in ne.findall("node"):
        pad_net[(node.get("ref"), node.get("pin"))] = name

all_net_names = sorted(set(pad_net.values()))
net_num = {n: i + 1 for i, n in enumerate(all_net_names)}

# ── Board setup ───────────────────────────────────────────────────────────
# KiCad 10 / pcbnew (post-SES import) writes pad net as (net "name") — name only.
# kiutils expects (net N "name") with a number. Patch to add a dummy number (0)
# before loading; the number is irrelevant since we clear/rebuild all nets below.
import re as _re  # noqa: E402
import tempfile as _tmp  # noqa: E402
import os as _os  # noqa: E402

with open(PCB) as _f:
    _raw = _f.read()
import uuid as _uuid  # noqa: E402

_fixed = _re.sub(r'\(net ("(?:[^"\\]|\\.)*")\)', r"(net 0 \1)", _raw)
_fixed = _re.sub(r"\(tstamp \)", lambda m: f"(tstamp {_uuid.uuid4()})", _fixed)
_tf = _tmp.NamedTemporaryFile(mode="w", suffix=".kicad_pcb", delete=False)
_tf.write(_fixed)
_tf.close()
b = Board.from_file(_tf.name)
_os.unlink(_tf.name)
b.footprints.clear()
b.nets.clear()
b.graphicItems.clear()
# NOTE: traceItems (routing tracks) are intentionally NOT cleared here.
# freerouting uses existing tracks as routing seeds; starting from zero causes
# it to hang indefinitely on this board. Old tracks are re-routed/optimized.
b.zones.clear()  # zones are rebuilt fresh in the pcbnew section below

n0 = Net()
n0.number = 0
n0.name = ""
b.nets.append(n0)
for name in all_net_names:
    n = Net()
    n.number = net_num[name]
    n.name = name
    b.nets.append(n)


def make_net_obj(ref, pad_str):
    name = pad_net.get((ref, pad_str))
    if name is None:
        return None
    n = Net()
    n.number = net_num[name]
    n.name = name
    return n


# ── Footprint path lookup ─────────────────────────────────────────────────
FP = {
    "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical.kicad_mod",
    "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical.kicad_mod",
    "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.kicad_mod",
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical.kicad_mod",
    "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical.kicad_mod",
    "Resistor_SMD:R_0402_1005Metric": f"{KICAD}/Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod",
    "Capacitor_SMD:C_0402_1005Metric": f"{KICAD}/Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount": f"{LOCAL}/Waveshare_ESP32-S3-Zero_FlatMount.kicad_mod",
    "robot-projects:SparkFun_TB6612FNG_v2": f"{LOCAL}/SparkFun_TB6612FNG_v2.kicad_mod",
    "MountingHole:MountingHole_3.2mm_M3_DIN965": f"{KICAD}/MountingHole.pretty/MountingHole_3.2mm_M3_DIN965.kicad_mod",
    "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm": f"{KICAD}/Capacitor_THT.pretty/CP_Radial_D10.0mm_P5.00mm.kicad_mod",
}


def place(ref, value, fp_id, x, y, angle=0):
    fp = Footprint.from_file(FP[fp_id])
    fp.libraryNickname, fp.entryName = fp_id.split(":", 1)
    fp.libId = fp_id
    fp.position = Position(X=round(x + OX, 3), Y=round(y + OY, 3), angle=angle)
    fp.path = "/" + str(uuid.uuid4())
    fp.tstamp = str(uuid.uuid4())
    fp.properties["Reference"] = ref
    fp.properties["Value"] = value
    for pad in fp.pads:
        net = make_net_obj(ref, str(pad.number))
        if net:
            pad.net = net
    b.footprints.append(fp)
    return fp


# ════════════════════════════════════════════════════════════════════════
# PLACEMENT MAP  (all mm, PCB origin = top-left of board)
#
#  0        10       20       30       40       50       60   65
#  +-MH1-J6(SR04)-J7(Est)---------------------------MH2--------+
#  |                                                   J1(MtrA) |
# J8(pwr)  [R8R9C2]    [U1 ESP32]  [R1R2R3]  [U2 TB6612]      |
# J9(uart) [R5R6R7]    [       ]   [R4,C1 ]  [C4C5  C3]  J2(MtrB)|
#  +-MH3--J5(Qwiic)-------------------------------------MH4------+
#                                                   50mm tall
# ════════════════════════════════════════════════════════════════════

# ── Main ICs ─────────────────────────────────────────────────────────────
#   U1: ESP32-S3-Zero flat-mount (18×23.5mm, top-left-origin footprint)
#   (9,16) keeps module center at ~(18,28) — same physical position as the old Socket
place(
    "U1",
    "Waveshare_ESP32-S3-Zero",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount",
    9,
    16,
)

#   U2: SparkFun TB6612FNG v2 Socket (courtyard ±13mm × ±13mm)
place("U2", "SparkFun_TB6612FNG_v2", "robot-projects:SparkFun_TB6612FNG_v2", 46, 28)

# ── Right-edge connectors (angle=90 → pads along +Y, housing exits →) ────────
#   Courtyard extends 2.45mm ABOVE and 9.95mm (4-pin) / 4.95mm (2-pin) BELOW placement y.
#   x=62.15: housing front at x=65 (right board edge); body extends left to x=58.75.
#   MH2/MH4 moved to x=55 so their courtyard right (58.25) clears body left (58.75).
#   Pad spacing for drill clearance: ≥2.5mm between last pad of upper and first of lower.
#   6-pin B6B courtyard: 2.45mm above, 14.95mm below placement y (pads span 12.5mm).
#   J1 at y=17: courtyard 14.55–31.95; J2 at y=35: courtyard 32.55–49.95.
#   Courtyard overlaps with MH corners and between J1/J2 are expected DRC warnings — pad clearances OK.
place(
    "J1",
    "Motor A",
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
    62.15,
    17,
    90,
)
place(
    "J2",
    "Motor B",
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
    62.15,
    42,
    90,
)

# ── Top-edge connectors (angle=0 → pads along +X, housing front at y≈0) ─────
#   Footprint origin = pad1 at (x,y); housing extends from y-2.85 (≈top edge) to y+3.9
place("J6", "HC-SR04", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical", 5, 3)
place("J7", "E-Stop", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 22, 3)

# ── Left-edge connectors (angle=270 → pads along -Y, housing exits ←) ────────
#   At angle=270: pad1 at (x,y), pad2 at (x, y-2.5)
#   x=1.5: housing exits left (front at x=-1.35), pads at x=1.5 inside board
#   Courtyard right edge = 1.5+3.9=5.4 → clears left passives at x=6.5
place(
    "J8", "PWR In", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 1.5, 20, 270
)
place(
    "J9", "UART/Pi", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical", 1.5, 34, 270
)

# ── Bottom-edge Qwiic (angle=0, adjust orientation in KiCad if needed) ───────
place(
    "J5",
    "Qwiic",
    "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical",
    13,
    56,
)

# ── Passives in gap between U1 and U2 (x: ~29–38, y: ~20–38) ────────────────
#   angle=90 → pad1 at top (lower Y), pad2 at bottom (higher Y)
#   PWMA/PWMB/STBY pulldowns: pad1 = signal, pad2 = GND
place("R1", "100k", "Resistor_SMD:R_0402_1005Metric", 30, 33.0, 90)  # PWMA pd
place("R2", "100k", "Resistor_SMD:R_0402_1005Metric", 30, 35.5, 90)  # PWMB pd
place("R3", "100k", "Resistor_SMD:R_0402_1005Metric", 30, 26.0, 90)  # STBY pd
#   ESTOP: R4 pullup (pad1=+3V3, pad2=ESTOP), C1 debounce (pad1=ESTOP, pad2=GND)
place("R4", "10k", "Resistor_SMD:R_0402_1005Metric", 30, 21.0, 90)  # ESTOP pu
place("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 23.5, 90)  # ESTOP debnc

# ── Passives left of U1 (x: ~5–9) ────────────────────────────────────────────
#   Battery sense divider: R8 (top, +BATT→BAT_SENSE), R9 (bot, BAT_SENSE→GND)
#   HC-SR04 echo divider: R5 (top, ECHO_IN→MID), R6 (bot, MID→GND),
#                         R7 (series ESD, MID→ECHO_DIV)
# x=6.5: crtyd right=7.235 → clears U1 crtyd left (7.5) by 0.265mm
#         crtyd left=5.765  → clears J8/J9 crtyd right (5.4) by 0.365mm
place("R8", "100k", "Resistor_SMD:R_0402_1005Metric", 6.5, 22, 90)  # bat top
place("R9", "47k", "Resistor_SMD:R_0402_1005Metric", 6.5, 25, 90)  # bat bot
place("C2", "100n", "Capacitor_SMD:C_0402_1005Metric", 6.5, 28, 90)  # bat filter
place("R5", "10k", "Resistor_SMD:R_0402_1005Metric", 6.5, 31, 90)  # echo div top
place("R6", "20k", "Resistor_SMD:R_0402_1005Metric", 6.5, 34, 90)  # echo div bot
place("R7", "100", "Resistor_SMD:R_0402_1005Metric", 6.5, 37, 90)  # echo ESD

# ── Capacitors: VM bulk + rail decoupling ─────────────────────────────────────
#   C3 1000µF polarized THT: below U2 on VM/VBAT rail (back-EMF bulk)
#   10mm dia, 5mm lead pitch; placed at y=44 angle=0 (pads horizontal toward right)
#   Minor courtyard overlap with U2 (bottom at y=43.5) — OK, different stack heights.
place("C3", "1000µF", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", 46, 50)
#   C4/C5 100nF: VBAT and 3V3 rail decoupling, in center-passive cluster
place("C4", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 38.5, 90)
place("C5", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 41.5, 90)

# ── M3 mounting holes (3.2mm drill, mechanical — no net connections) ──────────
#   Positioned to avoid connector drills; minor courtyard touches are OK
#   TL: (4,11)  TR: (55,11)  BL: (4,56)  BR: (55,56)
place("MH1", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 4, 11)
place("MH2", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 55, 11)
place("MH3", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 4, 56)
place("MH4", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 55, 56)

# ── Board outline (Edge.Cuts) ─────────────────────────────────────────────────
edge = GrRect()
edge.start = Position(X=OX, Y=OY)
edge.end = Position(X=OX + W, Y=OY + H)
edge.layer = "Edge.Cuts"
edge.width = 0.05
b.graphicItems.append(edge)

# ── Write PCB ────────────────────────────────────────────────────────────────
b.to_file(PCB)

# ── Fix text positions via pcbnew ─────────────────────────────────────────────
# kiutils doesn't transform footprint-local text coords through placement rotation,
# so REF/VALUE and other SilkS text end up far off-board.  Fill empty tstamps too
# (pcbnew 10 refuses to load files with empty tstamps from kiutils round-trips).
import pcbnew as _pn  # noqa: E402, F811

with open(PCB) as _f2:
    _raw2 = _f2.read()
_raw2 = _re.sub(r"\(tstamp \)", lambda m: f"(tstamp {_uuid.uuid4()})", _raw2)
_tf2 = _tmp.NamedTemporaryFile(mode="w", suffix=".kicad_pcb", delete=False)
_tf2.write(_raw2)
_tf2.close()
_b = _pn.LoadBoard(_tf2.name)
_os.unlink(_tf2.name)
_BOARD_OX, _BOARD_OY, _BOARD_W, _BOARD_H = OX, OY, W, H


def _in_board(x_nm, y_nm):
    return _pn.FromMM(_BOARD_OX) <= x_nm <= _pn.FromMM(
        _BOARD_OX + _BOARD_W
    ) and _pn.FromMM(_BOARD_OY) <= y_nm <= _pn.FromMM(_BOARD_OY + _BOARD_H)


for fp in _b.GetFootprints():
    pos = fp.GetPosition()
    px, py = pos.x, pos.y

    # REF → F.SilkS, positioned just above footprint center, clamped on-board
    ref = fp.Reference()
    ry = max(_pn.FromMM(0.5), min(_pn.FromMM(_BOARD_H - 0.5), py - _pn.FromMM(1.5)))
    ref.SetPosition(_pn.VECTOR2I(px, ry))
    ref.SetTextSize(_pn.VECTOR2I(_pn.FromMM(0.7), _pn.FromMM(0.7)))
    ref.SetTextThickness(_pn.FromMM(0.1))
    ref.SetVisible(True)
    ref.SetLayer(_pn.F_SilkS)

    # VALUE → F.Fab (not on physical silkscreen), positioned just below center
    val = fp.Value()
    vy = max(_pn.FromMM(0.5), min(_pn.FromMM(_BOARD_H - 0.5), py + _pn.FromMM(1.0)))
    val.SetPosition(_pn.VECTOR2I(px, vy))
    val.SetTextSize(_pn.VECTOR2I(_pn.FromMM(0.7), _pn.FromMM(0.7)))
    val.SetTextThickness(_pn.FromMM(0.1))
    val.SetVisible(True)
    val.SetLayer(_pn.F_Fab)

    # Any other text items (footprint artwork, fab notes) that landed off-board → hide
    for item in fp.GraphicalItems():
        try:
            ipos = item.GetPosition()
            if not _in_board(ipos.x, ipos.y):
                item.SetVisible(False)
        except AttributeError:
            pass

# ── 4-layer stackup + copper fill zones ──────────────────────────────────────
_b.SetCopperLayerCount(4)


def _add_zone(board, net_name, layer, clearance_mm=0.1):
    z = _pn.ZONE(board)
    z.SetLayer(layer)
    net = board.FindNet(net_name)
    if net:
        z.SetNet(net)
    outline = z.Outline()
    outline.NewOutline()
    inset = _pn.FromMM(0.3)
    for cx, cy in [
        (_pn.FromMM(OX) + inset, _pn.FromMM(OY) + inset),
        (_pn.FromMM(OX + W) - inset, _pn.FromMM(OY) + inset),
        (_pn.FromMM(OX + W) - inset, _pn.FromMM(OY + H) - inset),
        (_pn.FromMM(OX) + inset, _pn.FromMM(OY + H) - inset),
    ]:
        outline.Append(int(cx), int(cy))
    z.SetMinThickness(_pn.FromMM(0.25))
    z.SetLocalClearance(_pn.FromMM(clearance_mm))
    z.SetPadConnection(_pn.ZONE_CONNECTION_FULL)
    board.Add(z)
    return z


_add_zone(_b, "GND", _pn.In1_Cu)  # solid GND plane
_add_zone(_b, "+BATT", _pn.In2_Cu)  # solid VBAT plane

try:
    _filler = _pn.ZONE_FILLER(_b)
    _filler.Fill(_b.Zones())
except Exception:
    pass  # zones will fill when user opens in KiCad

_b.Save(PCB)
# ── Write net class settings to project file ──────────────────────────────────
# KiCad stores net classes in .kicad_pro, not in .kicad_pcb.
import json as _json  # noqa: E402

PRO = PCB.replace(".kicad_pcb", ".kicad_pro")
with open(PRO) as _pf:
    _pro = _json.load(_pf)
_pro["net_settings"]["classes"] = [
    {
        "name": "Default",
        "priority": 2147483647,
        "clearance": 0.2,
        "track_width": 0.25,
        "via_diameter": 0.6,
        "via_drill": 0.3,
        "bus_width": 12,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "tuning_profile": "",
        "wire_width": 6,
    },
    {
        "name": "Power",
        "priority": 100,
        "clearance": 0.25,
        "track_width": 0.5,
        "via_diameter": 0.8,
        "via_drill": 0.4,
        "bus_width": 12,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "tuning_profile": "",
        "wire_width": 6,
    },
    {
        "name": "Motor",
        "priority": 100,
        "clearance": 0.3,
        "track_width": 0.8,
        "via_diameter": 1.0,
        "via_drill": 0.5,
        "bus_width": 12,
        "diff_pair_gap": 0.25,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "tuning_profile": "",
        "wire_width": 6,
    },
]
_pro["net_settings"]["netclass_patterns"] = [
    {"netclass": "Power", "pattern": "+5V"},
    {"netclass": "Power", "pattern": "+BATT"},
    {"netclass": "Power", "pattern": "+3V3"},
    {"netclass": "Power", "pattern": "GND"},
    {"netclass": "Motor", "pattern": "/AO1"},
    {"netclass": "Motor", "pattern": "/AO2"},
    {"netclass": "Motor", "pattern": "/BO1"},
    {"netclass": "Motor", "pattern": "/BO2"},
]
with open(PRO, "w") as _pf:
    _json.dump(_pro, _pf, indent=2)

print(f"PCB written: {PCB}")
print(f"  Footprints : {len(b.footprints)}")
print(f"  Nets       : {len(b.nets)} ({len(all_net_names)} signals + 1 empty)")
print()
print("Next steps in KiCad:")
print(
    "  1. Open .kicad_pcb (do NOT run Update PCB from Schematic — incompatible with scripted layout)"
)
print("  2. Review placement, adjust connector orientations as needed")
print("  3. Route → Interactive Router  (or use freerouting via File → Export → DSN)")
print("  4. Run DRC (Inspect → Design Rules Checker)")
print()
print("Notes:")
print(
    f"  Board: {int(W)}×{int(H)}mm (4-layer; origin in drawing at ({int(OX)},{int(OY)}))"
)
print("  In1.Cu = GND plane, In2.Cu = +BATT plane")
print(
    "  U1 flat-mount: BIN1=GPIO38(pad15), BIN2=GPIO39(pad14), SDA=GPIO17(pad17), SCL=GPIO18(pad16)"
)
print(
    "  Cluster pads (10-17) are THT Φ1.43mm — reflow solder from above or hand-inject."
)
print("  GPIO14/15/16 (pads 27-29) are NOT accessible on this module — schematic NCs.")
print(
    "  C3 1000µF THT: pad1(+)=VBAT at (46,50), pad2(-)=GND at (51,50). Verify polarity."
)
print(
    "  MH1-MH4: M3 mounting holes (no nets) — minor courtyard overlaps near connectors are OK."
)
