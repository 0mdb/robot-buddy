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
        net = make_net_obj(ref, str(pad.number))
        if net:
            pad.net = net
    b.footprints.append(fp)
    return fp


# ════════════════════════════════════════════════════════════════════════
# PLACEMENT MAP  (all mm, PCB origin = top-left of board)
#
#  0        10       20       30       40       50       60   65
#  +--J6(SR04)---J7(Estop)------------MH2------C3(1000u)-------+
#  | MH1                                       |          J1(MtrL)
#  |         [R5R6R7]  [U1 ESP32]  [R4,C1 ]  [ U2 TB6612 ]     |
# J9(5V+UART)[  C6   ] [        ]  [R1R2   ]  [           ] J2(MtrR)
#  |                              [C4C5    ]                   |
#  |         [expander U4 + pulldowns R12-R17, LED J10]         |
#  +-MH3--J5(Qwiic)-------------------------------------MH4----+
#                              65 x 60 mm
#
# C3 sits ABOVE U2, not below: its 10mm can on the same X as pad 9 (VM) would
# otherwise cover pads 9-13. MH2 vacated (55,11) to make that approach possible.
# ════════════════════════════════════════════════════════════════════

# ── Main ICs ─────────────────────────────────────────────────────────────
#   U1: ESP32-S3-Zero flat-mount (18×23.5mm, top-left-origin footprint)
#   (9,16) keeps module center at ~(18,28) — same physical position as the old Socket
place(
    "U1",
    "Waveshare_ESP32-S3-Zero",
    "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount_NoCluster",
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
    "MOTOR L",
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
    62.15,
    17,
    90,
)
place(
    "J2",
    "MOTOR R",
    # y 42 -> 46.5 to open an 11mm slot between J1 and J2 for MH5 (see below).
    # Courtyard offset is -15.5..+3.0, so this puts it at y 31.0..49.5 — clear of
    # MH5's keepout (ends 27.59) and of MH4's (starts 52.90).
    "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
    62.15,
    46.5,
    90,
)

# ── Top-edge connectors (angle=0 → pads along +X, housing front at y≈0) ─────
#   Footprint origin = pad1 at (x,y); housing extends from y-2.85 (≈top edge) to y+3.9
place(
    "J6",
    "HC-SR04 5V",
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    5,
    3,
    90,
)
# J7 is 3-pin as of E3: pin1=+3V3, pin2=ESTOP (through the NC contact), pin3=the
# cable-detect loop. It grew one pin, so it now spans 5.0mm of pads instead of 2.5mm
# — still comfortably inside the top-edge gap between J6 (ends x=14.44) and the
# clear band before U2's courtyard.
place("J7", "E-STOP NC", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", 22, 3)

# ── Left-edge connectors (angle=270 → pads along -Y, housing exits ←) ────────
#   At angle=270: pad1 at (x,y), pad2 at (x, y-2.5)
#   x=2.0: housing exits left, pads at x=2.0 inside board
#   Was x=1.5, but the JST-VH pads are 2.7mm square → pad left edge at 0.15mm, against
#   a 0.5mm board-edge rule (4x copper_edge_clearance). 2.0 puts it at 0.65mm.
#   Courtyard right edge = 2.0+3.9=5.9 → left passives moved 6.5 → 7.7 to keep clear.
# Value reads pin 1->4 in order, with direction marks resolving L3: ">" means the pin
# is DRIVEN BY THIS BOARD, "<" means it is driven by the far end. Verified from the
# netlist rather than the net name: J9.3 /UART_TX lands on U1.18 (TX, GPIO43,
# pintype=output) and J9.4 /UART_RX on U1.19 (RX, GPIO44, pintype=input). So the board
# transmits on pin 3 — wire pin 3 to the Pi's RX.
# "5V+UART Pi" said nothing about direction, which is the whole of defect L3: both ends
# of a UART call their own pin TX, so the label has to say whose view it is.
place(
    "J9",
    "5V GND TX> RX<",
    "Connector_JST:JST_VH_B4P-VH_1x04_P3.96mm_Vertical",
    2.0,
    34,
    270,
)

# ── Bottom-edge Qwiic (angle=0, adjust orientation in KiCad if needed) ───────
place(
    "J5",
    "QWIIC 3V3",
    "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical",
    13,
    56,
)

# ── Passives in gap between U1 and U2 (x: ~29–38, y: ~20–38) ────────────────
#   angle=90 → pad1 at top (lower Y), pad2 at bottom (higher Y)
#   PWMA/PWMB/STBY pulldowns: pad1 = signal, pad2 = GND
place("R1", "100k", "Resistor_SMD:R_0402_1005Metric", 30, 33.0, 90)  # PWMA pd
place("R2", "100k", "Resistor_SMD:R_0402_1005Metric", 30, 35.5, 90)  # PWMB pd
#   ESTOP: R4 pullup (pad1=+3V3, pad2=ESTOP), C1 debounce (pad1=ESTOP, pad2=GND)
place("R4", "10k", "Resistor_SMD:R_0402_1005Metric", 30, 21.0, 90)  # ESTOP pu
place("C1", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 23.5, 90)  # ESTOP debnc

# ── Passives left of U1 (x: ~5–9) ────────────────────────────────────────────
#   Battery sense divider: R8 (top, +BATT→BAT_SENSE), R9 (bot, BAT_SENSE→GND)
#   HC-SR04 echo divider: R5 (top, ECHO_IN→MID), R6 (bot, MID→GND),
#                         R7 (series ESD, MID→ECHO_DIV)
# Echo divider moved out of the left strip to the clear block under J6 (x 15-40,
# y 7-15). They were at x=6.5, then 7.7 when J9 shifted right for edge clearance,
# and at 7.7 they sat directly on top of U1's left-hand silk pin labels.
#
# This is the better home anyway: R7 is the series ESD resistor on the incoming
# HC-SR04 echo line, and it now sits ~5mm below J6 instead of 34mm away, so the
# clamp is near the connector where incoming energy arrives. The divider is a
# slow ultrasonic pulse, so the extra run to U1 costs nothing.
#   crtyd x 15.48..16.52 → clears MH1 (7.09) and J7 (19.00) comfortably
#   y 8.02..14.98        → clears J7 crtyd bottom (6.95) and U1 crtyd top (15.71)
place("R5", "10k", "Resistor_SMD:R_0402_1005Metric", 16, 9.0, 90)  # echo div top
place("R6", "15k", "Resistor_SMD:R_0402_1005Metric", 16, 11.5, 90)  # echo div bot
place("R7", "100", "Resistor_SMD:R_0402_1005Metric", 16, 14.0, 90)  # echo ESD

# ── Capacitors: VM bulk + rail decoupling ─────────────────────────────────────
#   C3 1000µF polarized radial THT: VM rail bulk (TB6612 back-EMF).
#   10mm dia, 5mm lead pitch, hand-soldered — NOT part of the JLC assembly.
#   jlcpcb-assembly/README.md lists it under "What YOU hand-solder (THT / modules)".
# C3 MUST sit at U2 pad 9 (VM). VM has only 0.5V of margin post-A3, and the ripple
# analysis only holds if C3 is the low-impedance path at 20kHz — trace inductance
# between C3 and pad 9 would hand the ripple back to the breakout's small caps.
# U2 is at (46,28); pad 9 is local (+7.62,-8.89) -> (53.62, 19.11).
#
# It was previously at (53.62, 25.0) — the same X as pad 9, but 5.9mm BELOW it, which
# put the 10mm can squarely on top of U2's right pad column and covered pads 9-13.
# Unbuildable, and DRC only said "courtyards overlap" + 5x "PTH inside courtyard".
# Correct answer is the same X but ABOVE the module, rotated 90 so the pads stack
# vertically: pad1(+) lands at (53.62, 15.09), 4.02mm straight down to pad 9.
# Fits only because F4 was resolved — the real body is 20.32mm, not the 23mm the
# footprint used to claim, so U2's courtyard top moved 14.96 -> 17.59.
# rot 90: footprint-local (x,0) maps to global (0,-x), so local pad1 (-4.2,0) -> +4.2 in Y.
# y=10.75, not the 10.89 the arithmetic suggests: courtyard bounding boxes include the
# 0.05mm stroke width, so ±10.41 on U2 actually reaches 17.55 and the two courtyards
# grazed by 0.04mm. 10.75 leaves 0.10mm and costs 0.14mm of trace.
# Resulting gaps: MH2 0.49mm left, J1 0.10mm right, U2 0.10mm below.
# Radial THT restored (was silently swapped to Capacitor_SMD:CP_Elec_10x10.5 in an
# uncommitted edit). The THT pads are the better answer here anyway: their barrels
# pass through In2.Cu, so C3's +5V terminal lands ON the +5V plane and its GND
# terminal on the In1/B.Cu GND planes — the plane IS the connection, and the short
# surface run to U2 pad 9 is only a secondary path.
# NOTE the origin of this footprint is PAD 1, not the body centre — courtyard runs
# y-7.79 .. y+2.79, x 48.33..58.91. y=14.6 leaves 0.16mm to U2's courtyard top
# (17.55), clears MH2 (ends 47.60) and J1 (starts 59.26), and puts
# pad 1 (+) at (53.62, 14.60) — 4.51mm from U2 pad 9 (53.62, 19.11).
place("C3", "1000µF", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", 53.62, 14.6, 90)
#   C4/C5 100nF: VBAT and 3V3 rail decoupling, in center-passive cluster
place("C4", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 38.5, 90)
place("C5", "100n", "Capacitor_SMD:C_0402_1005Metric", 30, 41.5, 90)

# ── NeoPixel + power-LED circuit — bottom-centre cluster (x 25-41, y 46-58) ─────
#   Shifted +5mm right vs initial placement to clear SDA Qwiic via at (19.16, 55.80)
#   that conflicted with J10 pin 1 at old (20, 57). New J10 at (25, 57) gives ~4mm
#   clearance from the SDA routing zone.
place("R10", "330", "Resistor_SMD:R_0402_1005Metric", 25, 52, 90)
place("C7", "100n", "Capacitor_SMD:C_0402_1005Metric", 33, 52, 90)
# C6 = +5V bulk. It used to sit at (4.5, 25) in the left strip, rotated 90 to fit
# the 9mm between the board edge and U1's left pad column. It fitted, but it was
# occupying the ONLY clear channel for U1's left-hand silk pin labels, and its own
# outline crossed its own pads — 12 of the residual silk violations traced back to
# this one part. The strip is 9mm wide and had to hold J9 (6.25mm of courtyard),
# C6 (7.19mm) and U1's labels (~1.8mm). It never fitted; it just wasn't DRC-visible.
#
# Moved to the empty block below U1 (x 8-24, y 40-53), which nothing else uses.
# Electrically fine: unlike C3, C6 is bulk on a rail fed by the solid In2.Cu +5V
# plane, so the plane carries it — this is not the VM node with 0.5V of margin.
place("C6", "100µF", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm", 12.5, 45.5, 90)
place("J10", "LED 5V", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", 25, 57)

# ── M3 mounting holes (3.2mm drill, mechanical — no net connections) ──────────
#   Positioned to avoid connector drills; minor courtyard touches are OK
#   TL: (4,11)  TR: (55,11)  BL: (4,56)  BR: (55,56)
# ── U4 TCA9554A expander + support, in the space the NeoPixel cluster vacated ──
place("U4", "TCA9554APWR", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", 33, 46)
place("R12", "100k", "Resistor_SMD:R_0402_1005Metric", 26, 44, 90)  # AIN1 pd
place("R13", "100k", "Resistor_SMD:R_0402_1005Metric", 26, 46.5, 90)  # AIN2 pd
place("R14", "100k", "Resistor_SMD:R_0402_1005Metric", 26, 49, 90)  # BIN1 pd
place("R15", "100k", "Resistor_SMD:R_0402_1005Metric", 26, 51.5, 90)  # BIN2 pd
place("R16", "4.7k", "Resistor_SMD:R_0402_1005Metric", 40, 44, 90)  # SDA pu
# R18: e-stop cable-detect loop pull-down (E3). Sits with the other pull-downs in
# the expander cluster rather than near J7 — it only has to hold the net low when
# the harness is absent, so trace length is irrelevant.
place("R18", "10k", "Resistor_SMD:R_0402_1005Metric", 40, 41.5, 90)
place("R17", "4.7k", "Resistor_SMD:R_0402_1005Metric", 40, 46.5, 90)  # SCL pu
place("C8", "100n", "Capacitor_SMD:C_0402_1005Metric", 40, 49, 90)  # U4 decoupling
place("C9", "10u", "Capacitor_SMD:C_0402_1005Metric", 40, 51.5, 90)  # +3V3 bulk

place("MH1", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 4, 11)
# MH2 moved (55,11) -> (44.5,4) so C3 can sit directly above U2 pad 9 (VM). At (55,11)
# it owned x 51.9-58.1 / y 7.9-14.1, which is the ONLY approach to pad 9 from above —
# with it there the best C3 could manage was an 8.8mm dogleg on a rail with 0.5V of
# margin. Now 4.02mm, straight down. Keepout x 41.41-47.60 clears C3's courtyard left
# (48.07) by 0.47mm; an M3 head (Ø6) clears C3's 10mm can by 1.1mm and is reachable.
# MECHANICAL CONSEQUENCE: the top-right corner (x>48, y<20) has no screw — C3 and J1
# live there and J1 takes motor-cable pull. The chassis needs a support boss under
# that corner. A screw is not possible: C3 and J1 fill the region edge to edge.
place("MH2", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 44.5, 4)
place("MH3", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 4, 56)
place("MH4", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 55, 56)
# MH5: fifth hole on the right edge, between J1 and J2.
#
# The right edge is where the mechanical load actually is — J1 and J2 are the motor
# connectors and both take cable pull, and with four corner holes the nearest support
# to J1 was ~25mm away. This braces both of them directly.
#
# J2 moved y 42 -> 46.5 to open the slot. Before that the J1/J2 courtyard gap was
# 6.5mm, which fits the 6.19mm keepout but NOT a driver: an M3 head is ~6mm across
# and would have sat in a 6.5mm slot between two ~11mm-tall connector housings.
# At y=46.5 the gap is 11mm, leaving 1.4mm to J1 and 3.4mm to J2 around the head.
#   keepout x 57.41..63.59 → clears U2 courtyard right (56.45) by 0.96mm
place("MH5", "MountingHole", "MountingHole:MountingHole_3.2mm_M3_DIN965", 60.5, 24.5)

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
print(
    f"  Board: {int(W)}×{int(H)}mm (4-layer; origin in drawing at ({int(OX)},{int(OY)}))"
)
print("  In1.Cu = GND plane, In2.Cu = +5V plane")
print(
    "  U1 flat-mount: BIN1=GPIO38(pad15), BIN2=GPIO39(pad14), SDA=GPIO17(pad17), SCL=GPIO18(pad16)"
)
print(
    "  Cluster pads (10-17) are THT Φ1.43mm — reflow solder from above or hand-inject."
)
print("  GPIO14/15/16 (pads 27-29) are NOT accessible on this module — schematic NCs.")
print(
    "  C3 1000µF SMD, rot 90 ABOVE U2: pad1(+)=+5V at (53.62,14.95) — 4.16mm straight "
    "down to U2 pad 9 (VM). pad2(-)=GND at (53.62,6.55). Verify polarity."
)
print(
    "  MH1-MH4: M3 mounting holes (no nets) — minor courtyard overlaps near connectors are OK."
)
