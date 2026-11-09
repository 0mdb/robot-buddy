#!/usr/bin/env python3
"""
PCB layout for robot-buddy-reflex.
Reads schematic netlist, places all footprints at sensible positions with nets
assigned.  Open the resulting .kicad_pcb in KiCad → route traces, run DRC.

Board outline: 65 × 60 mm with two encoder-connector notches (board_outline.py)
"""

import subprocess
import uuid
import xml.etree.ElementTree as ET
from kiutils.board import Board
from kiutils.footprint import Footprint
from kiutils.items.common import Net, Position
from kiutils.items.gritems import GrLine

import board_outline as BO

PCB = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb"
SCH = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_sch"
KICAD = "/usr/share/kicad/footprints"
LOCAL = "/home/ben/robot-buddy/hardware/kicad/lib/robot-projects.pretty"  # recovered from the board 2026-11-08 (~/kicad-libs was gone)
NETLIST = "/tmp/reflex-netlist.xml"

OX, OY = 0.0, 0.0  # board origin in KiCad drawing (at top-left; move after routing)
W, H = BO.W, BO.H  # board bounding box mm; the real edge is BO.outline()

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
# Notches (2026-11-08): drop routing seeds that fall outside the new outline (+0.3 edge
# clearance). Stubs left dangling (here, or on moved pads) are pruned in the pcbnew pass.
_EDGE = BO.inset(BO.outline(), 0.3)


_SEED_M = 1.0  # KiCad wants 0.5 copper-to-edge, plus a via's 0.3-0.4 radius


def _inside(x, y):
    """On the board and >= _SEED_M from the notch edges (outer edges: BO.contains)."""
    near_notch = BO.NOTCH_X[0] - _SEED_M < x < BO.NOTCH_X[1] + _SEED_M and (
        y < BO.NOTCH_D + _SEED_M or y > H - BO.NOTCH_D - _SEED_M
    )
    return BO.contains(x, y) and not near_notch


def _seed_ok(t):
    pts = []
    for a in ("start", "mid", "end", "position"):
        p = getattr(t, a, None)
        if p is not None:
            pts.append((p.X, p.Y))
    if len(pts) >= 2:  # sample along straight segments too
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        pts += [(x1 + (x2 - x1) * k / 8, y1 + (y2 - y1) * k / 8) for k in range(1, 8)]
    return all(_inside(x, y) for x, y in pts)


_n0 = len(b.traceItems)
if _os.environ.get("RB_NO_SEEDS"):  # route the whole board from scratch
    b.traceItems = []
b.traceItems = [t for t in b.traceItems if _seed_ok(t)]
print(f"routing seeds: {_n0} -> {len(b.traceItems)} (dropped outside the notched outline)")
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
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical": f"{KICAD}/Connector_PinHeader_2.54mm.pretty/PinHeader_1x04_P2.54mm_Vertical.kicad_mod",
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical.kicad_mod",
    "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical.kicad_mod",
    "Resistor_SMD:R_0402_1005Metric": f"{KICAD}/Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod",
    "Capacitor_SMD:C_0402_1005Metric": f"{KICAD}/Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount": f"{LOCAL}/Waveshare_ESP32-S3-Zero_FlatMount.kicad_mod",
    "robot-projects:SparkFun_TB6612FNG_v2": f"{LOCAL}/SparkFun_TB6612FNG_v2.kicad_mod",
    "MountingHole:MountingHole_3.2mm_M3_DIN965": f"{KICAD}/MountingHole.pretty/MountingHole_3.2mm_M3_DIN965.kicad_mod",
    "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm": f"{KICAD}/Capacitor_THT.pretty/CP_Radial_D10.0mm_P5.00mm.kicad_mod",
    "Package_TO_SOT_SMD:SOT-23-5": f"{KICAD}/Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod",
    "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm": f"{KICAD}/Capacitor_THT.pretty/CP_Radial_D5.0mm_P2.00mm.kicad_mod",
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
        # A pad's (at x y angle) in a .kicad_pcb is its absolute orientation, footprint rotation
        # included; kiutils doesn't add it. Without this, rotated parts keep unrotated pads
        # (harmless on the near-square JST pads; U1's 2.76 x 1.5 pads overlap at angle 90).
        if angle:
            pad.position.angle = ((pad.position.angle or 0) + angle) % 360
        net = make_net_obj(ref, str(pad.number))
        if net:
            pad.net = net
    b.footprints.append(fp)
    return fp


# ════════════════════════════════════════════════════════════════════════
# PLACEMENT MAP  (all mm, PCB origin = top-left of board)
#
#  0        10       20    28.5               51   55      65
#  +-MH1-J6(SR04)-J7(Est)-+   (encoder notch)  +-MH2--------+
#  |                      +--------------------+   J1(MtrA) |
# USB=[U1 ESP32, rot 90 ]   [R4,C1,R3]  [U2 TB6612, rot 180] |
#     [  USB-C at x 0  ]    [R1R2C4C5]  [                  ] J2(MtrB)
# J9(uart) [R8R9C2R5R6R7]      U3  C6  J11                     |
#          C3          +--------------------+             J10 |
#  +-MH3--J5(Qwiic)-J8(pwr)-+   (encoder notch)  +-MH4--------+
#  60 mm tall; notches x 28.5-50, 7 deep (board_outline.py, 2026-11-08)
#  2026-11-09 (order QC): U1 turned so its USB-C (the Pi link, USB-Serial-JTAG) exits the
#  rear edge (KiCad x 0 = chassis x -40, the open bay; R2c). J8 moved to the bottom edge, the
#  left passives to a row under U1. U2 turned 180: the corrected SparkFun pinout puts the
#  VM/motor row on the footprint's left (chip up), so it now faces J1/J2.
# ════════════════════════════════════════════════════════════════════

# ── Main ICs ─────────────────────────────────────────────────────────────
#   U1: ESP32-S3-Zero flat-mount (18×23.5mm, top-left-origin footprint, USB-C at the pad-1
#   end, ~1.4 proud of the module edge: STEP render 2026-11-09). angle 90 maps local (x, y)
#   to (y, -x): the module spans x U1_X..U1_X+23.5, y U1_Y-18..U1_Y, USB-C end at x U1_X.
#   U1_X 0: module end flush with the rear edge, so the receptacle overhangs and a plug seats.
#   U1_Y 33: module y 15-33, clear of MH1's head (4, 11; r 2.9) with J9 below it on the edge.
U1_X, U1_Y = 0.0, 33.0
place(
    "U1",
    "Waveshare_ESP32-S3-Zero",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount",
    U1_X,
    U1_Y,
    90,
)

#   U2: SparkFun TB6612FNG v2 Socket (courtyard ±13mm × ±13mm). angle 180: VM/AO/BO row
#   (pads 9-16) at x 53.62 beside J1/J2, PWMA..PWMB row (pads 1-8) at x 38.38 toward U1.
place("U2", "SparkFun_TB6612FNG_v2", "robot-projects:SparkFun_TB6612FNG_v2", 46, 28, 180)

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
place(
    "J6",
    "HC-SR04",
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    5,
    3,
    90,
)
place("J7", "E-Stop", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 22, 3)

# ── Left-edge connectors (angle=270 → pads along -Y, housing exits ←) ────────
#   At angle=270: pad1 at (x,y), pad2 at (x, y-2.5)
#   x=1.5: housing exits left (front at x=-1.35), pads at x=1.5 inside board
#   Courtyard right edge = 1.5+3.9=5.4 → clears left passives at x=6.5
#   J9 under U1 on the rear edge: pads y 36.5-44, courtyard 33.5-47 (U1 ends at 33).
place(
    "J9", "UART/Pi", "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical", 1.5, 36.5, 270
)
#   J8 (2026-11-09) on the bottom edge between J5 and the notch, housing front at the edge
#   (angle 180 mirrors J7): pads (24, 57) and (21.5, 57), courtyard ~18.5-27 x 53-59.9.
place("J8", "PWR In", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 24, 57, 180)

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
# 2026-11-09: a row under U1 (module ends y 33), right of J9 (courtyard x <= 4.4), above C3.
_ROW_Y = 37.0
place("R8", "100k", "Resistor_SMD:R_0402_1005Metric", 7.5, _ROW_Y, 90)  # bat top
place("R9", "47k", "Resistor_SMD:R_0402_1005Metric", 10.0, _ROW_Y, 90)  # bat bot
place("C2", "100n", "Capacitor_SMD:C_0402_1005Metric", 12.5, _ROW_Y, 90)  # bat filter
place("R5", "10k", "Resistor_SMD:R_0402_1005Metric", 15.0, _ROW_Y, 90)  # echo div top
place("R6", "20k", "Resistor_SMD:R_0402_1005Metric", 17.5, _ROW_Y, 90)  # echo div bot
place("R7", "100", "Resistor_SMD:R_0402_1005Metric", 20.0, _ROW_Y, 90)  # echo ESD

# ── Capacitors: VM bulk + rail decoupling ─────────────────────────────────────
#   C3 1000µF polarized THT: below U2 on VM/VBAT rail (back-EMF bulk)
#   10mm dia, 5mm lead pitch; placed at y=44 angle=0 (pads horizontal toward right)
#   Minor courtyard overlap with U2 (bottom at y=43.5) — OK, different stack heights.
#   2026-11-08 notch: body (origin = pad 1, body centre +2.5 x) was 43.5-53.5 x 45-55, into the
#   bottom notch. The notches cut the edge corridors, so left<->right traffic (+5V to J1/J2)
#   now runs through the bands between the notches and U2; C3 anywhere in the y 41-53 band
#   sealed it (0.75 mm each side). Now under U1, centred (21, 46.5): VM (+BATT, In2 plane)
#   and GND (In1) reach it through the planes; ~25 mm from U2's VM pins, fine for TT motors.
place("C3", "1000µF", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", 18.5, 46.5)
#   C4/C5 100nF: VBAT and 3V3 rail decoupling, in center-passive cluster
place("C4", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 38.5, 90)
place("C5", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 41.5, 90)

# ── NeoPixel + power-LED circuit — bottom-centre cluster (x 25-41, y 46-58) ─────
#   Shifted +5mm right vs initial placement to clear SDA Qwiic via at (19.16, 55.80)
#   that conflicted with J10 pin 1 at old (20, 57). New J10 at (25, 57) gives ~4mm
#   clearance from the SDA routing zone.
place("U3", "74AHCT1G125", "Package_TO_SOT_SMD:SOT-23-5", 29, 46)
place("R10", "330", "Resistor_SMD:R_0402_1005Metric", 25, 52, 90)
place("R11", "330", "Resistor_SMD:R_0402_1005Metric", 29, 50.5, 90)  # 52 -> 50.5: notch edge at y 53
place("C7", "100n", "Capacitor_SMD:C_0402_1005Metric", 33, 50.5, 90)  # 52 -> 50.5: notch edge at y 53
place("C6", "100µF", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm", 38, 50)
#   2026-11-08 notch: J10/J11 sat in the bottom notch (x 28.5-50, y > 53). J11 -> C3's old patch
#   under U2 (courtyard 42-53 x 45.9-52.7), low in the band so the +5V run to J1/J2 at y 45.05
#   (F.Cu, x 30.8-61.6) stays open. J10 -> the bottom-right corner on the edge beside MH4,
#   turned like J1/J2 (59.3-66 x 51.4-59.8). The bottom-left strip stays clear for the
#   SDA/SCL/+3V3 runs to J5 (J11 there crowded the SDA via at (19.16, 55.80), as in June).
place("J10", "LED", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 62.15, 56.8, 90)
place("J11", "NeoPixel", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", 45, 48.8)

# ── M3 mounting holes (3.2mm drill, mechanical — no net connections) ──────────
#   Positioned to avoid connector drills; minor courtyard touches are OK
#   TL: (4,11)  TR: (55,11)  BL: (4,56)  BR: (55,56)
place("MH1", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 4, 11)
place("MH2", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 55, 11)
place("MH3", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 4, 56)
place("MH4", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 55, 56)

# ── Board outline (Edge.Cuts) ─────────────────────────────────────────────────
_ol = BO.outline()
for (_x1, _y1), (_x2, _y2) in zip(_ol, _ol[1:] + _ol[:1]):
    b.graphicItems.append(
        GrLine(
            start=Position(X=OX + _x1, Y=OY + _y1),
            end=Position(X=OX + _x2, Y=OY + _y2),
            layer="Edge.Cuts",
            width=0.05,
            tstamp=str(uuid.uuid4()),
        )
    )

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
    return BO.contains(_pn.ToMM(x_nm) - _BOARD_OX, _pn.ToMM(y_nm) - _BOARD_OY)


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

# ── Prune dangling routing seeds ──────────────────────────────────────────────
# Seeds cut by the notch, or left on the old pads of moved parts (C3, J10, J11, R11, C7),
# end in nothing. Remove any track end that touches no pad, via or other track, until stable.
def _prune_dangling(board):
    removed = 0
    while True:
        tracks = [t for t in board.GetTracks() if t.Type() == _pn.PCB_TRACE_T]
        vias = [t for t in board.GetTracks() if t.Type() == _pn.PCB_VIA_T]
        pads = list(board.GetPads())
        def joined(t, p):
            # overlap, as KiCad's connectivity counts it (seed ends often miss by 0.01 mm)
            if any(o is not t and o.GetLayer() == t.GetLayer() and o.HitTest(p) for o in tracks):
                return True
            if any(v.HitTest(p) for v in vias):
                return True
            return any(pd.IsOnLayer(t.GetLayer()) and pd.HitTest(p) for pd in pads)

        dead = [t for t in tracks if not (joined(t, t.GetStart()) and joined(t, t.GetEnd()))]
        lone = [
            v for v in vias
            if not any(t.HitTest(v.GetPosition()) for t in tracks)
            and not any(pd.HitTest(v.GetPosition()) for pd in pads)
        ]
        if not dead and not lone:
            return removed
        for t in dead + lone:
            board.Remove(t)
        removed += len(dead) + len(lone)


# Seeds still lying on the pads of the parts moved for the notch (they routed past the old
# layout) would short or crowd them: clear any seed within 0.3 of those pads.
_MOVED = {"C3", "J10", "J11", "R11", "C7"}


def _clear_under(board, refs, margin_mm=0.3):
    # Pads only: seeds may run under a THT body (C3's held SDA/SCL/+3V3 to J5 in June).
    boxes = []
    for fp in board.GetFootprints():
        if fp.GetReference() in refs:
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                bb.Inflate(_pn.FromMM(margin_mm))
                boxes.append(bb)
    gone = 0
    for t in list(board.GetTracks()):
        if t.Type() == _pn.PCB_VIA_T:
            pts = [t.GetPosition()]
        else:
            a, e = t.GetStart(), t.GetEnd()
            pts = [_pn.VECTOR2I(int(a.x + (e.x - a.x) * k / 16), int(a.y + (e.y - a.y) * k / 16)) for k in range(17)]
        if any(bb.Contains(p) for bb in boxes for p in pts):
            board.Remove(t)
            gone += 1
    return gone


print(f"cleared {_clear_under(_b, _MOVED)} seed(s) under the moved parts")
# Old +3V3 patch copies (route_pcb.py step 7, laid at y 21.15 and again as seeds) crowd U1
# pad 19; let the router lay the R4-1 / U2-10 run fresh (it finds y 21.27-21.42).
_n3 = 0
for _t in list(_b.GetTracks()):
    if _t.Type() == _pn.PCB_TRACE_T and _t.GetNetname() == "+3V3" and _t.GetLayer() == _pn.F_Cu:
        _ends = [_t.GetStart(), _t.GetEnd()]
        if all(13.0 <= _pn.ToMM(e.x) <= 56.5 and 19.4 <= _pn.ToMM(e.y) <= 21.8 for e in _ends):
            _b.Remove(_t)
            _n3 += 1
print(f"dropped {_n3} old +3V3 patch seed(s)")
# ENC_LA ran along the top edge at y 7, now the notch edge: its leftover stub (via at
# (28.06, 9.93)) only boxes the router in. Lay the whole net fresh.
_RESEED = {"/ENC_LA"}
_nr = 0
for _t in list(_b.GetTracks()):
    if _t.GetNetname() in _RESEED:
        _b.Remove(_t)
        _nr += 1
print(f"dropped {_nr} seed(s) on {sorted(_RESEED)} to reroute them fresh")

# ...and give it the hard part as a seed: J1 pad 5 west along y 8.2, between the top notch
# (edge y 7, copper >= 7.5) and the MH2 hole (55, 11; r 1.6 + 0.25), to a via at its old spot.
# freerouting (which can't read the MH keepouts) then only joins the via to U1 pad 24.
def _seed_track(board, net, pts, layer=_pn.F_Cu, w=0.25):
    n = board.FindNet(net)
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = _pn.PCB_TRACK(board)
        t.SetLayer(layer)
        t.SetNet(n)
        t.SetWidth(_pn.FromMM(w))
        t.SetStart(_pn.VECTOR2I(_pn.FromMM(OX + x1), _pn.FromMM(OY + y1)))
        t.SetEnd(_pn.VECTOR2I(_pn.FromMM(OX + x2), _pn.FromMM(OY + y2)))
        board.Add(t)


_seed_track(_b, "/ENC_LA", [(62.15, 7.00), (58.50, 7.00), (57.30, 8.20), (29.79, 8.20), (28.06, 9.93)])
_v = _pn.PCB_VIA(_b)
_v.SetPosition(_pn.VECTOR2I(_pn.FromMM(OX + 28.06), _pn.FromMM(OY + 9.93)))
_v.SetWidth(_pn.FromMM(0.6))
_v.SetDrill(_pn.FromMM(0.3))
_v.SetNet(_b.FindNet("/ENC_LA"))
_b.Add(_v)
print("seeded /ENC_LA: J1-5 -> y 8.2 -> via (28.06, 9.93)")

print(f"pruned {_prune_dangling(_b)} dangling track/via seed(s)")

# ── THT pads keep their outer rings ───────────────────────────────────────────
# The stock KiCad footprints ship THT pads with remove_unused_layers (REMOVE_ALL): with no
# trace on B.Cu the ring is dropped there, the B.Cu GND pour floods to the hole, and the
# pad-sized mask opening exposes that GND. Soldering the pin (on B.Cu) then bridges it to GND:
# J8 pin 1 is +BATT. Found 2026-11-08 by KiCad 10's solder_mask_bridge check (33 pads in June).
_nk = 0
for _fp in _b.GetFootprints():
    for _pad in _fp.Pads():
        if _pad.GetAttribute() == _pn.PAD_ATTRIB_PTH:
            _pad.Padstack().SetUnconnectedLayerMode(_pn.UNCONNECTED_LAYER_MODE_REMOVE_EXCEPT_START_AND_END)
            _nk += 1
print(f"{_nk} THT pads keep their F.Cu/B.Cu rings")

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
    for cx, cy in BO.inset(BO.outline(), 0.3):  # notched outline, 0.3 in from the edge
        outline.Append(_pn.FromMM(OX + cx), _pn.FromMM(OY + cy))
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
        "clearance": 0.2,  # 0.25 -> 0.2 (2026-11-08): what route_pcb.py routes Power at; 8.4 V board
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
        "clearance": 0.2,  # 0.3 -> 0.2 (2026-11-08): route_pcb.py merges Motor into Power (0.2)
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
    "  C3 1000µF THT: pad1(+)=VBAT at (18.5,46.5), pad2(-)=GND at (23.5,46.5). Verify polarity."
)
print(
    "  MH1-MH4: M3 mounting holes (no nets) — minor courtyard overlaps near connectors are OK."
)
