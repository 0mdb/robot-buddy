#!/usr/bin/env python3
"""
PCB layout for robot-buddy-reflex.
Reads schematic netlist, places all footprints at sensible positions with nets
assigned.  Open the resulting .kicad_pcb in KiCad → route traces, run DRC.

Board outline: board_outline.py (63 × 46 mm since 2026-11-10)
"""

import subprocess
import uuid
import xml.etree.ElementTree as ET
from kiutils.board import Board
from kiutils.footprint import Footprint
from kiutils.items.common import Net, Position
from kiutils.items.gritems import GrLine

PCB = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb"
SCH = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_sch"
KICAD = "/usr/share/kicad/footprints"
LOCAL = "/home/ben/kicad-libs/footprints/robot-projects.pretty"
NETLIST = "/tmp/reflex-netlist.xml"

import os as _os0  # noqa: E402
import sys as _sys0  # noqa: E402

_sys0.path.insert(0, _os0.path.dirname(_os0.path.abspath(__file__)))
import board_outline as BO  # noqa: E402

OX, OY = 0.0, 0.0  # board origin in KiCad drawing (at top-left; move after routing)
W, H = BO.W, BO.H  # board dimensions mm (board_outline.py is the one source)

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
# --fresh: drop the old routing too. Use it after a RE-PLACEMENT: seeds from the previous
# placement run through where parts now sit, and route_pcb's unshort pass only removes
# seeds that short, not ones that merely detour. Default (no flag) keeps them as seeds.
if "--fresh" in _sys0.argv:
    print(f"  Seeds      : --fresh, dropped {len(b.traceItems)} old track/via items")
    b.traceItems.clear()

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
    # NOTE: this key used to appear TWICE. The first copy mapped the VH key to
    # JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical — a 2.50mm-pitch XH footprint under a
    # 3.96mm-pitch VH name, left over from when J9 was an XH part. The correct entry
    # below came later and won on dict ordering, so J9 was right by luck. Any reorder
    # or de-dup that kept the first would have silently shrunk J9's pitch by 1.46mm
    # on the power inlet. Removed; ruff F601 is what surfaced it.
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical": f"{KICAD}/Connector_PinHeader_2.54mm.pretty/PinHeader_1x04_P2.54mm_Vertical.kicad_mod",
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical.kicad_mod",
    "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical.kicad_mod",
    "Resistor_SMD:R_0402_1005Metric": f"{KICAD}/Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod",
    "Capacitor_SMD:C_0402_1005Metric": f"{KICAD}/Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount": f"{LOCAL}/Waveshare_ESP32-S3-Zero_FlatMount.kicad_mod",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount_NoCluster": f"{LOCAL}/Waveshare_ESP32-S3-Zero_FlatMount_NoCluster.kicad_mod",
    "Connector_JST:JST_VH_B4P-VH_1x04_P3.96mm_Vertical": f"{KICAD}/Connector_JST.pretty/JST_VH_B4P-VH_1x04_P3.96mm_Vertical.kicad_mod",
    "Package_SO:TSSOP-16_4.4x5mm_P0.65mm": f"{KICAD}/Package_SO.pretty/TSSOP-16_4.4x5mm_P0.65mm.kicad_mod",
    "robot-projects:SparkFun_TB6612FNG_v2": f"{LOCAL}/SparkFun_TB6612FNG_v2.kicad_mod",
    "MountingHole:MountingHole_3.2mm_M3_DIN965": f"{KICAD}/MountingHole.pretty/MountingHole_3.2mm_M3_DIN965.kicad_mod",
    # C3/C6 are radial THT electrolytics, hand-soldered — NOT in the JLC assembly.
    # They were briefly swapped to Capacitor_SMD:CP_Elec_* here; that contradicted
    # jlcpcb-assembly/README.md and the parts actually in hand. See register O2.
    "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm": f"{KICAD}/Capacitor_THT.pretty/CP_Radial_D10.0mm_P5.00mm.kicad_mod",
    "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm": f"{KICAD}/Capacitor_THT.pretty/CP_Radial_D5.0mm_P2.00mm.kicad_mod",
    "Package_TO_SOT_SMD:SOT-23-5": f"{KICAD}/Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod",
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
        # A pad's (at x y angle) in a .kicad_pcb is its ABSOLUTE orientation, footprint
        # rotation included; kiutils doesn't add it. Without this every rotated part kept
        # unrotated pad copper (0402 at 90: 0.54 x 0.64 instead of 0.64 x 0.54; J1/J2 XH
        # likewise). DRC can't see it. Register M5; same fix cad-loop made (600b271).
        if angle:
            pad.position.angle = ((pad.position.angle or 0) + angle) % 360
        net = make_net_obj(ref, str(pad.number))
        if net:
            pad.net = net
    b.footprints.append(fp)
    return fp


# ════════════════════════════════════════════════════════════════════════
# PLACEMENT MAP  (all mm, PCB origin = top-left of board; x rear -> front)
#
#  0         10        20    24.5    31      47.8  51.2  58.4  63
#  +-MH1--[ J9 5V GND TX> RX< ]+ ~~~~ plug strip ~~~~ +[  ][MH2]+   y 0  (chassis left)
#  |                           |[  U2 TB6612, 180  ]   |J1|[J5] |
# USB=[ U1 ESP32-S3-Zero, 90 ] |[ ctrl col | motor ]   |  |     |
#  |  [ USB-C flush, x 0     ] |[  (PWM/AIN/BIN)   ]   [J7]|J2| |
#  |  C4 C7 C5 R5R6R7 R1 R2 C6 | R12-15 [U4] [ C3 1000u ] R4C1 |  | |
#  +-MH3--[ J6 SR04 ]----------+ ~~~~ plug strip ~~~~ +   [MH4]+   y 46 (chassis right)
#              63 x 46 mm (52.5 x 46 until 2026-11-10; was 65 x 60 + notches)
#
# 2026-11-09 shrink: board_outline.py has the why (46 mm clears the encoder sockets at
# |y| 23.9 with no notches). Order QC fixes from cad-loop carried over (register §M):
# U1 turned 90 so the USB-C (the Pi link) is flush on the rear edge (M6); U2 un-mirrored
# at the library and turned 180 so its control column faces U1 (M1); pads of rotated
# parts carry the footprint angle (M5, in place()).
# ════════════════════════════════════════════════════════════════════

# ── Main ICs ─────────────────────────────────────────────────────────────
#   U1: ESP32-S3-Zero flat-mount, 18 x 23.5, footprint origin top-left, USB-C at the pad-1
#   end and ~1.4 proud of the module (cad-loop STEP render). angle 90 maps local (x, y) to
#   (y, -x): the module spans x 0..23.5, y U1_Y-18..U1_Y, USB-C end flush on the rear edge so
#   the receptacle overhangs and a plug seats. Pads 1-9 (5V GND 3V3 GP1-6) run along the
#   bottom side rear->front, pads 18-26 (TX RX GP13-7) along the top side.
#   The plug's ~12.4 overmold spans y 16.5..29.5 at the rear edge: MH1/MH3 are clear.
U1_X, U1_Y = 0.0, 32.0
place(
    "U1",
    "Waveshare_ESP32-S3-Zero",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount_NoCluster",
    U1_X,
    U1_Y,
    90,
)

#   U2: SparkFun TB6612FNG module on 2x8 female headers. Footprint = SparkFun's .brd,
#   chip up (fixed 2026-11-09, register M1). At 180: control column (pads 1-8) at x 27.28,
#   top->bottom GND PWMB BIN2 BIN1 STBY AIN1 AIN2 PWMA, facing U1 and U4; motor column
#   (pads 9-16) at x 42.52, top->bottom GND BO1 BO2 AO2 AO1 GND VCC VM. VM (pad 9) at
#   (42.52, 26.29), bottom-right, so C3 sits right under it.
U2_X, U2_Y = 34.9, 17.4
place(
    "U2",
    "SparkFun_TB6612FNG_v2",
    "robot-projects:SparkFun_TB6612FNG_v2",
    U2_X,
    U2_Y,
    180,
)

# ── Motor connectors: two columns in the front strip (register M12, 2026-11-10) ──
#   The encoder plugs + wires own the long edges over x 31..47.8 (board_outline.
#   plug_keepouts), so J1/J2 moved forward of the sockets. At 90 the XH courtyard is
#   x pos-2.9..pos+3.94, y pos-15.49..pos+3. J1 (MOTOR L, chassis left = y 0 side) in the
#   inner column at y 3.5..22; J2 (MOTOR R) in the outer column at y 20.5..39, clear of
#   MH4 (y >= 39.4). The motor ends of the harness are bare wires crimped to XH (Ben).
place(
    "J1", "MOTOR L", "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical", 51.2, 19.0, 90
)
place(
    "J2", "MOTOR R", "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical", 58.4, 36.0, 90
)

# ── Pi link: J9 top-rear, beside U1's TX/RX pads ─────────────────────────────
# Value reads pin 1->4 in order, with direction marks resolving L3: ">" means the pin
# is DRIVEN BY THIS BOARD, "<" means it is driven by the far end. J9.3 /UART_TX lands on
# U1.18 (TX, GPIO43, output), J9.4 /UART_RX on U1.19 (RX, GPIO44, input): wire pin 3 to
# the Pi's RX. At 180 the pins run front->rear: 5V (21.9), GND, TX, RX (10.02), so TX/RX
# are nearest U1's pads 18/19 (x 1.59/4.13).
place(
    "J9",
    "5V GND TX> RX<",
    "Connector_JST:JST_VH_B4P-VH_1x04_P3.96mm_Vertical",
    21.9,
    6,
    180,
)

# ── HC-SR04 header on the bottom-rear edge, under U1's ECHO/TRIG pads ────────
place(
    "J6",
    "HC-SR04 5V",
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    8.6,
    43.5,
    90,
)

# ── Front strip, around J1/J2: Qwiic (outer column, under MH2) + E-stop (inner column,
#    under J1) ─────────────────────────────────────────────────────────────────
place(
    "J5",
    "QWIIC 3V3",
    "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical",
    59.2,
    11.5,
    90,
)
# J7 3-pin (E3): pin1=+3V3, pin2=ESTOP (through the NC contact), pin3=cable-detect loop.
place(
    "J7",
    "E-STOP NC",
    "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
    51.2,
    31,
    90,
)
#   ESTOP: R4 (pad2=ESTOP, pad1=GND) holds it low when the loop is open, C1 debounce;
#   R18: e-stop cable-detect loop pull-down (E3). All three beside J7.
place("R4", "10k", "Resistor_SMD:R_0402_1005Metric", 50.0, 35.6, 0)
place("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", 50.0, 36.9, 0)
place("R18", "10k", "Resistor_SMD:R_0402_1005Metric", 50.0, 38.2, 0)

# ── Under U1 (bottom-rear strip): rail decoupling, echo divider, PWM pull-downs ─
place("C4", "100n", "Capacitor_SMD:C_0402_1005Metric", 2, 35.5, 90)  # +5V at U1 pad 1
place("C7", "100n", "Capacitor_SMD:C_0402_1005Metric", 3.5, 35.5, 90)  # +5V
place(
    "C5", "100n", "Capacitor_SMD:C_0402_1005Metric", 6.7, 35.5, 90
)  # +3V3 at U1 pad 3
#   HC-SR04 echo divider: R5 (top, ECHO_IN->MID), R6 (bot, MID->GND), R7 (series ESD,
#   MID->ECHO_DIV) between U1's ECHO pad (x 11.75) and J6.
place("R5", "10k", "Resistor_SMD:R_0402_1005Metric", 11, 35, 90)
place("R6", "15k", "Resistor_SMD:R_0402_1005Metric", 12.5, 35, 90)
place("R7", "100", "Resistor_SMD:R_0402_1005Metric", 14, 35, 90)
#   PWMA/PWMB pull-downs under U1's PWM pads (x 16.83, 19.37): pad1 = signal, pad2 = GND
place("R1", "100k", "Resistor_SMD:R_0402_1005Metric", 16.8, 34.5, 90)
place("R2", "100k", "Resistor_SMD:R_0402_1005Metric", 19.4, 34.5, 90)
#   C6 100uF: +5V bulk. On the solid In2.Cu +5V plane, so position is not critical.
place("C6", "100µF", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm", 19.6, 38.5)

# ── VM bulk: C3 right under U2's VM pad ──────────────────────────────────────
#   C3 1000uF radial THT, hand-soldered (not in the JLC assembly). VM has 0.5 V of margin
#   (A3), so C3 must be the low-impedance path at 20 kHz (E2). At 180 the footprint (origin
#   = pad 1) runs pad 2 to the left: pad1 (+) at (42.52, 33.2), 6.9 mm straight below VM pad 9
#   (42.52, 26.29). Its THT barrels also land on the In2 +5V / In1 GND planes.
#   NOTE: the can is ~12.5 tall: check against the 12 mm parts budget under the Pi deck.
place("C3", "1000µF", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", 42.52, 33.2, 180)

# ── U4 TCA9554A expander + support, under U2's control column ────────────────
place("U4", "TCA9554APWR", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", 30.5, 34.0)
place("R12", "100k", "Resistor_SMD:R_0402_1005Metric", 25.6, 30.0, 90)  # AIN1 pd
place("R13", "100k", "Resistor_SMD:R_0402_1005Metric", 25.6, 32.0, 90)  # AIN2 pd
place("R14", "100k", "Resistor_SMD:R_0402_1005Metric", 25.6, 34.0, 90)  # BIN1 pd
place("R15", "100k", "Resistor_SMD:R_0402_1005Metric", 25.6, 36.0, 90)  # BIN2 pd
place("R16", "4.7k", "Resistor_SMD:R_0402_1005Metric", 28.2, 29.0)  # SDA pu
place("R17", "4.7k", "Resistor_SMD:R_0402_1005Metric", 30.3, 29.0)  # SCL pu
place("C8", "100n", "Capacitor_SMD:C_0402_1005Metric", 32.4, 29.0)  # U4 decoupling
place("C9", "10u", "Capacitor_SMD:C_0402_1005Metric", 30.5, 38.0)  # +3V3 bulk

# ── M3 mounting holes: 4 in a rectangle (board_outline.HOLES; base plate standoffs) ─
for _i, (_hx, _hy) in enumerate(BO.HOLES, start=1):
    place(
        f"MH{_i}", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", _hx, _hy
    )

# ── Board outline (Edge.Cuts) ─────────────────────────────────────────────────
# Drawn from board_outline.outline() so the edge, the router boundary, pcb_qc.py and the
# chassis envelope all come from one polygon.
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
    return _pn.FromMM(_BOARD_OX) <= x_nm <= _pn.FromMM(
        _BOARD_OX + _BOARD_W
    ) and _pn.FromMM(_BOARD_OY) <= y_nm <= _pn.FromMM(_BOARD_OY + _BOARD_H)


# Reviewed anchors for labels that matter (finish_pcb keeps a field that starts clear and
# only moves ones that collide). J9's pin order (L3) lands under U2's module wherever the
# placer's candidate ring puts it; the band under J9 (y 10.3-12.9) is clear and is next to
# the pins it describes. (x, y, angle) of the Value field.
_LABEL_AT = {"J9": (16.0, 11.35, 0)}  # 11.0 grazed J9's own housing outline

for fp in _b.GetFootprints():
    pos = fp.GetPosition()
    px, py = pos.x, pos.y

    # REF → F.SilkS, positioned just above footprint center, clamped on-board
    ref = fp.Reference()
    if fp.GetReference().startswith("MH"):
        # Mounting-hole refs say nothing a hole doesn't, and on the 52.5 x 46 board
        # (2026-11-09) MH2/MH4's landed on MOTOR L and R18. Hidden, not deleted.
        ref.SetVisible(False)
        val = fp.Value()
        val.SetLayer(_pn.F_Fab)
        continue
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
    if fp.GetReference() in _LABEL_AT:
        _lx, _ly, _la = _LABEL_AT[fp.GetReference()]
        val.SetPosition(_pn.VECTOR2I(_pn.FromMM(OX + _lx), _pn.FromMM(OY + _ly)))
        val.SetTextAngle(_pn.EDA_ANGLE(_la, _pn.DEGREES_T))
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


# clearance_mm defaults to the Default netclass value, NOT a hardcoded 0.1.
# A plane carves around foreign-net copper at ITS local clearance while DRC checks
# against the netclass rule, so any value below the design clearance makes every
# foreign track crossing the plane a clearance error. See the B.Cu note in
# route_pcb.py — that zone had exactly this bug and it stayed hidden until signals
# were actually routed on the plane layer.
_ZONE_CLR_MM = 0.2  # keep in step with the Default netclass clearance below


def _add_zone(board, net_name, layer, clearance_mm=_ZONE_CLR_MM):
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
_add_zone(_b, "+5V", _pn.In2_Cu)  # solid +5V plane (was +BATT; eliminated in A3)


# ── Plane fan-out: every SMD pad on a plane net gets its own stub + via ──────────
# GND (In1 + B.Cu) and +5V (In2) reach SMD pads only through a via. On the 52.5 x 46 board
# (2026-11-09) freerouting left a different GND pad unconnected in the strip under U1 on
# successive runs (C5.2, R2.2, U1.2): the strip is packed and the router gives up on
# plane drops once the signal stubs box a pad in. Laying the drops here, before routing,
# makes them part of the placement instead of a routing gamble. The vias go in only on a
# --fresh run (seeded runs already carry them in their tracks) and DRC checks them after.
_PLANE_NETS = {
    "GND": (0.6, 0.3, 0.25),
    "+5V": (0.8, 0.4, 0.4),
}  # via dia, drill, stub w


def _pad_boxes(board):
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            # key by (ref, pad number): pad.GetParent() comes back as a bare
            # BOARD_ITEM_CONTAINER proxy in this pcbnew build (no GetReference)
            out.append(
                (
                    (fp.GetReference(), p.GetNumber()),
                    bb.GetLeft(),
                    bb.GetTop(),
                    bb.GetRight(),
                    bb.GetBottom(),
                )
            )
    return out


def _fanout(board):
    pads = _pad_boxes(board)
    vias = []  # (x, y, r) placed so far
    clr = _pn.FromMM(0.2)
    edge = _pn.FromMM(0.5)
    n = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith(("MH", "U2")):
            continue
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in _PLANE_NETS or p.GetAttribute() != _pn.PAD_ATTRIB_SMD:
                continue
            dia, drill, sw = _PLANE_NETS[net]
            r = _pn.FromMM(dia / 2)
            pc = p.GetPosition()
            fc = fp.GetPosition()
            # candidate directions: straight away from the footprint centre first, then the
            # other three axes; distances step out from just clear of the pad
            dx, dy = pc.x - fc.x, pc.y - fc.y
            prim = (
                (1 if dx > 0 else -1, 0)
                if abs(dx) >= abs(dy)
                else (0, 1 if dy > 0 else -1)
            )
            dirs = [
                prim,
                (prim[1], prim[0]),
                (-prim[1], -prim[0]),
                (-prim[0], -prim[1]),
            ]
            half = (
                max(p.GetBoundingBox().GetWidth(), p.GetBoundingBox().GetHeight()) // 2
            )
            done = False
            for step in (0.0, 0.25, 0.5, 0.8, 1.2):
                for ux, uy in dirs:
                    d = half + r + clr + _pn.FromMM(step)
                    vx, vy = pc.x + ux * d, pc.y + uy * d
                    if not (
                        _pn.FromMM(OX) + edge + r <= vx <= _pn.FromMM(OX + W) - edge - r
                        and _pn.FromMM(OY) + edge + r
                        <= vy
                        <= _pn.FromMM(OY + H) - edge - r
                    ):
                        continue
                    ok = True
                    for q, lft, t, rr, bt in pads:
                        if q == (ref, p.GetNumber()):
                            continue
                        if (
                            lft - clr - r < vx < rr + clr + r
                            and t - clr - r < vy < bt + clr + r
                        ):
                            ok = False
                            break
                    if ok:
                        for ox, oy, orr in vias:
                            if (vx - ox) ** 2 + (vy - oy) ** 2 < (r + orr + clr) ** 2:
                                ok = False
                                break
                    if not ok:
                        continue
                    v = _pn.PCB_VIA(board)
                    v.SetPosition(_pn.VECTOR2I(int(vx), int(vy)))
                    v.SetWidth(_pn.FromMM(dia))
                    v.SetDrill(_pn.FromMM(drill))
                    v.SetNet(p.GetNet())
                    board.Add(v)
                    t = _pn.PCB_TRACK(board)
                    t.SetStart(pc)
                    t.SetEnd(_pn.VECTOR2I(int(vx), int(vy)))
                    t.SetWidth(_pn.FromMM(sw))
                    t.SetLayer(_pn.F_Cu)
                    t.SetNet(p.GetNet())
                    board.Add(t)
                    vias.append((vx, vy, r))
                    n += 1
                    done = True
                    break
                if done:
                    break
            if not done:
                print(
                    f"  Fan-out    : NO legal via spot for {ref}.{p.GetNumber()} ({net})"
                )
    return n


if "--fresh" in _sys0.argv:
    print(f"  Fan-out    : {_fanout(_b)} plane-net SMD pads given a stub + via")

try:
    _filler = _pn.ZONE_FILLER(_b)
    _filler.Fill(_b.Zones())
except Exception:
    pass  # zones will fill when user opens in KiCad

# ── Drop orphaned (netless) tracks ────────────────────────────────────────────
# traceItems are deliberately preserved above as freerouting seeds, but when a
# net is renumbered or a pad's net changes (e.g. the E1 TB6612 JP1 fix), the old
# tracks survive with NO net at all.  That copper is worse than useless: it is
# dead as a seed, invisible to the netlist, and still physically on the board —
# which is exactly how a corrected schematic can still fabricate a short.
# Caught 2026-08-06 by tools/check_pcb_routing.py.  See docs/v2-defect-register.md.
_orphans = [t for t in _b.GetTracks() if not t.GetNetname()]
for _t in _orphans:
    _b.RemoveNative(_t)
if _orphans:
    print(f"  Orphans    : removed {len(_orphans)} netless track/via segments")

_b.Save(PCB)

# ── Declare the stackup, so copper weight is a decision and not an assumption ──
# A0e: the board carried NO stackup at all, so every ampacity number in the register
# rested on a parameter nobody had chosen — and check_pcb_ampacity.py was defaulting
# to 2oz while JLC's 4-layer default is 1oz. Sized properly in
# docs/electrical-design-calcs.md §1a; 1oz outer / 0.5oz inner wins on both counts:
#
#   - Electrically it is not close. The worst outer conductor is a motor output at
#     0.75A peak against a 1.99A rating — 2.6x margin, 3.3C rise. The 1.5A motor-flip
#     current never touches outer copper at all: J9.1 -> In2.Cu plane -> U2.9, all
#     through-hole with ZONE_CONNECTION_FULL. Even a pessimistic 10mm strip of that
#     plane carries 6.2A at 0.5oz, and each 1.0mm barrel 7.0A.
#   - 2oz would COST margin where the board is actually tight. JLC's minimum
#     trace/space at 2oz outer is 0.2mm; this board routes at 0.2mm clearance, so 2oz
#     puts it exactly on the limit. At 1oz the limit is 0.0889mm — 2.25x margin.
#
# Scout used 2oz because 15A on 1oz reached 138C there. Buddy's currents are an order
# of magnitude lower; copying that choice would buy nothing and spend clearance margin.
_STACKUP = """	(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0175))
			(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0175))
			(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
"""
with open(PCB) as _sf2:
    _s2 = _sf2.read()
if "(stackup" not in _s2:
    _s2 = _s2.replace("\t(setup\n", "\t(setup\n\t" + _STACKUP.lstrip("\t"), 1)
    with open(PCB, "w") as _sf2:
        _sf2.write(_s2)
    print("  Stackup    : declared 1oz outer / 0.5oz inner, ENIG (A0e)")
else:
    print("  Stackup    : already present")


# ── DFM pass: mask-opening-without-copper ─────────────────────────────────────
# JLCPCB holds any order where a solder-mask opening has no copper under it.
# Both causes below were found on all four boards 2026-07-20, fixed by hand, and
# then silently REINTRODUCED by the next layout regeneration (caught 2026-08-06)
# because the fixes lived outside this pipeline.  They are applied here so a
# regeneration can never ship the defect again.  See docs/v2-defect-register.md.
#
#  (1) THT pads with (keep_end_layers no) under (remove_unused_layers yes):
#      KiCad strips the OUTER-layer annular ring on pads routed only on inner
#      layers, leaving an orphan mask opening.  "yes" keeps top+bottom copper
#      while still trimming unused inner layers.
#  (2) np_thru_hole (NPTH) pads carrying "*.Mask": mounting holes and fuse
#      holders get a full-diameter mask opening with no copper at all.  Scope
#      strictly to np_thru_hole — plated connectors use thru_hole and must keep
#      their mask layers.
with open(PCB) as _df:
    _dfm = _df.read()

_n_keep = _dfm.count("(keep_end_layers no)")
_dfm = _dfm.replace("(keep_end_layers no)", "(keep_end_layers yes)")

#  (3) subtractmaskfromsilk: knock the soldermask openings out of the silkscreen
#      at plot time, so no ink is generated over a solderable surface. This is the
#      standard handling for silk that must sit near pads — notably the polarity
#      bars on C3 and C6, which are drawn across their own pads deliberately and
#      must not be trimmed away: a 1000uF electrolytic on the 5V rail fitted
#      backwards vents. With this on, the mark stays in the design and prints right
#      up to the pad edge, and the gerbers carry no ink on the pad itself.
#      DRC still reports silk_over_copper — it inspects the design, not the plot —
#      so those warnings are expected and are dispositioned in the defect register.
_n_silk_sub = _dfm.count("(subtractmaskfromsilk no)")
_dfm = _dfm.replace("(subtractmaskfromsilk no)", "(subtractmaskfromsilk yes)")


def _strip_npth_mask(m):
    """Remove *.Mask from the (layers ...) list of an np_thru_hole pad only."""
    body = m.group(0)
    if "np_thru_hole" not in body.split("(layers", 1)[0]:
        return body
    return _re.sub(r'(\(layers[^)]*?)\s*"\*\.Mask"', r"\1", body, count=1)


_n_mask_before = len(
    [
        p
        for p in _re.split(r"\(pad ", _dfm)[1:]
        if "np_thru_hole" in p[:80] and _re.search(r"\(layers[^)]*\*\.Mask", p)
    ]
)
_dfm = _re.sub(
    r"\(pad [^\n]*\n(?:[^\n]*\n)*?[^\n]*\(layers[^)]*\)", _strip_npth_mask, _dfm
)

with open(PCB, "w") as _df:
    _df.write(_dfm)

print(
    f"  DFM pass   : keep_end_layers no→yes ×{_n_keep}, "
    f"np_thru_hole *.Mask stripped ×{_n_mask_before}, "
    f"subtractmaskfromsilk no→yes ×{_n_silk_sub}"
)

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
        # Rail = +5V. 1.5mm -> 0.8mm (shorts/mask bridges) -> 0.4mm (clearance).
        #
        # The surface +5V trace carries almost nothing: In2.Cu is a solid, filled +5V
        # plane, and EVERY high-current +5V node is a through-hole pad that reaches it
        # directly through its own barrel — J9 pad 1 (board power in), U2 pad 9 (VM),
        # J1/J2 pad 3 (motor 5V), J6 pad 1. The only SMD +5V loads are C3/C4/C6/C7
        # decoupling, U1, and R10, each a short stub to a via. So surface width is not
        # what sets ampacity here; the plane and the pad barrels are.
        #
        # 0.8mm was costing 14 of the 16 unique clearance violations — freerouting was
        # threading 0.8mm rail between 0402 pads that have nothing like that much room.
        # At 0.4mm each side gains 0.2mm, which covers every shortfall seen (0.05-0.19mm).
        "name": "Rail",
        "priority": 90,
        "clearance": 0.2,
        "track_width": 0.4,
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
        "name": "Power",
        "priority": 100,
        "clearance": 0.2,
        "track_width": 0.4,
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
        "clearance": 0.2,
        "track_width": 0.4,
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
# Clearance is 0.2mm on every class. It was 0.25 (Power) / 0.3 (Motor), sized
# when +BATT carried pack voltage; A3 removed that rail, so nothing on this
# board exceeds 5V. IPC-2221 creepage below 15V is negligible and JLC 4-layer
# capability is well under 0.2mm, so 0.2 is a comfortable manufacturing margin
# rather than a relaxation. Demanding 0.3 on a board this dense simply produced
# violations the router could not satisfy (86 vs 72 at 0.25).
# NOTE: these widths/clearances are the SINGLE SOURCE OF TRUTH. route_pcb.py
# reads them back out of the .kicad_pro to build its freerouting DSN classes and
# its post-import width fixup. Previously they were hardcoded in both places and
# drifted: freerouting routed motor nets at 200um clearance while KiCad DRC
# demanded 300um, which is where 72 clearance violations came from.
_pro["net_settings"]["netclass_patterns"] = [
    {"netclass": "Rail", "pattern": "+5V"},
    {"netclass": "Power", "pattern": "+3V3"},
    {"netclass": "Power", "pattern": "GND"},
    {"netclass": "Motor", "pattern": "/AO1"},
    {"netclass": "Motor", "pattern": "/AO2"},
    {"netclass": "Motor", "pattern": "/BO1"},
    {"netclass": "Motor", "pattern": "/BO2"},
]

# ── DRC rule severities ───────────────────────────────────────────────────────
# `lib_footprint_mismatch` is expected on this board BY DESIGN and is the only rule
# deliberately silenced. The DFM pass below edits pad properties after placement
# (keep_end_layers on 33 pads, *.Mask stripped from 4 NPTH), so every touched
# footprint legitimately differs from its library copy. Leaving it at "error"
# buries 30 known-good diffs in the DRC report, which is how the real defects got
# missed the first time round.
#
# It is silenced, NOT excluded per-instance: an exclusion list would go stale the
# moment a footprint moved, and would quietly start hiding a genuinely swapped
# footprint. The gate that actually catches a wrong footprint is the pre-fab
# review pass (check_board_review.py), not this rule.
_pro.setdefault("board", {}).setdefault("design_settings", {}).setdefault(
    "rule_severities", {}
)["lib_footprint_mismatch"] = "ignore"

with open(PRO, "w") as _pf:
    _json.dump(_pro, _pf, indent=2)


# ── Silk text legibility ──────────────────────────────────────────────────────
# Footprint text inherits its size from the source libraries, and several are below
# KiCad's 0.8mm minimum — every one is a text_height violation and prints marginally.
#
# This used to match the literal "(size 0.7 0.7)" only. That silently missed the
# 0.6mm pin labels inside the U1 and U2 footprints — 20 violations that looked like
# they had been handled. Match ANY size below the minimum instead, so a library
# whose text is 0.5 or 0.65 can never reintroduce this class.
# Bump to exactly the minimum, not above it. This used to promote to 1.0mm, which
# made U1's 18 pin labels 25% wider than they had to be and pushed them into the
# passives packed around the module — 17 of the silk violations were caused by the
# fix for text_height, not by the layout. 0.8mm is legible and is what the rule asks.
_MIN_SILK_MM = 0.8
_NEW_SILK_MM = 0.8
with open(PCB) as _tf3:
    _t3 = _tf3.read()


def _bump_font(m):
    global _nfix
    if float(m.group(2)) < _MIN_SILK_MM or float(m.group(3)) < _MIN_SILK_MM:
        _nfix += 1
        return f"{m.group(1)}{_NEW_SILK_MM} {_NEW_SILK_MM})"
    return m.group(0)


# MUST stay anchored on "(font" — pads carry "(size x y)" too, and an unanchored
# match would silently shrink-wrap every 0402 pad (0.6x0.5mm) up to 1.0x1.0mm.
_nfix = 0
_t3 = _re.sub(r"(\(font\s*\n?\s*\(size )([0-9.]+) ([0-9.]+)\)", _bump_font, _t3)
_t3 = _t3.replace("(thickness 0.1)", "(thickness 0.15)")
_t3 = _t3.replace("(thickness 0.12)", "(thickness 0.15)")
with open(PCB, "w") as _tf3:
    _tf3.write(_t3)
print(f"  Silk text  : {_nfix} text items below {_MIN_SILK_MM}mm -> {_NEW_SILK_MM}mm")

# ── Connector Value fields → F.SilkS (register L1) ────────────────────────────
with open(PCB) as _sf:
    _s = _sf.read()
_blocks = _s.split("\n\t(footprint ")
_moved = 0
for _i in range(1, len(_blocks)):
    _ref = _re.search(r'\(property "Reference" "([^"]+)"', _blocks[_i])
    if not _ref or not _re.match(r"J\d+$", _ref.group(1)):
        continue
    _new, _n = _re.subn(
        r'(\(property "Value" "[^"]*"\s*\n\s*\(at [^)]*\)\s*\n\s*\(layer ")F\.Fab(")',
        r"\1F.SilkS\2",
        _blocks[_i],
        count=1,
    )
    _blocks[_i] = _new
    _moved += _n
with open(PCB, "w") as _sf:
    _sf.write("\n\t(footprint ".join(_blocks))
print(f"  Silk       : {_moved} connector Value fields moved F.Fab -> F.SilkS")

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
print(f"  Board: {W:g}×{H:g}mm (4-layer; origin in drawing at ({OX:g},{OY:g}))")
print("  In1.Cu = GND plane, In2.Cu = +5V plane")
print("  U1 NoCluster (perimeter pads only); direction pins via the U4 expander (A0).")
print("  GPIO14/15/16 (pads 27-29) are NOT accessible on this module — schematic NCs.")
print(
    "  C3 1000µF THT at 180 under U2: pad1(+)=+5V at (42.52,33.2), 6.9mm below U2 pad 9 (VM)."
    " pad2(-)=GND at (37.52,33.2). Verify polarity."
)
print(
    "  MH1-MH4: M3 mounting holes (no nets) — minor courtyard overlaps near connectors are OK."
)
