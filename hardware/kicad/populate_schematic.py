#!/usr/bin/env python3
"""
Populate robot-buddy-reflex schematic with all components:
U2 TB6612FNG, J1-J8 connectors, R1-R9, C1-C2, power symbols, net labels,
no-connects on unused ESP32 pins.
"""

import uuid
import copy
from kiutils.schematic import (
    Schematic,
    SchematicSymbol,
    Connection,
    NoConnect,
    Junction,
    LocalLabel,
    SymbolProjectInstance,
    SymbolProjectPath,
)
from kiutils.symbol import SymbolLib
from kiutils.items.common import Position, Property, Effects, Font

SCH = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_sch"
SYMLIBS = "/usr/share/kicad/symbols/"
SHEET_UUID = "be329060-5df2-4336-b672-5c4f1f6f3085"


def uid():
    return str(uuid.uuid4())


def pos(x, y, angle=0):
    return Position(X=round(x, 3), Y=round(y, 3), angle=angle)


def make_prop(key, value, x, y, angle=0):
    p = Property()
    p.key = key
    p.value = value
    p.position = pos(x, y, angle)
    eff = Effects()
    eff.font = Font()
    eff.font.size = [1.27, 1.27]
    p.effects = eff
    p.showName = False
    return p


def make_instance(ref, unit=1):
    spp = SymbolProjectPath()
    spp.sheetInstancePath = f"/{SHEET_UUID}"
    spp.reference = ref
    spp.unit = unit
    spi = SymbolProjectInstance()
    spi.name = "robot-buddy-reflex"
    spi.paths = [spp]
    return spi


_pwr_counter = [0]
_ref_counters = {}


def next_pwr():
    _pwr_counter[0] += 1
    return f"#PWR{_pwr_counter[0]:02d}"


def make_sym(
    lib_nick,
    entry,
    x,
    y,
    ref,
    value,
    footprint="",
    desc="",
    angle=0,
    in_bom=True,
    on_board=True,
):
    sym = SchematicSymbol()
    sym.libraryNickname = lib_nick
    sym.entryName = entry
    sym.libId = f"{lib_nick}:{entry}"
    sym.libName = f"{lib_nick}:{entry}"
    sym.position = pos(x, y, angle)
    sym.unit = 1
    sym.inBom = in_bom
    sym.onBoard = on_board
    sym.dnp = False
    sym.fieldsAutoplaced = True
    sym.uuid = uid()
    sym.mirror = None
    sym.pins = {}
    off = 5.0
    sym.properties = [
        make_prop("Reference", ref, x, y - off),
        make_prop("Value", value, x, y - off + 2.54),
        make_prop("Footprint", footprint, x, y),
        make_prop("Datasheet", "", x, y),
        make_prop("Description", desc, x, y),
    ]
    sym.instances = [make_instance(ref)]
    return sym


def make_pwr(name, x, y):
    sym = make_sym("power", name, x, y, next_pwr(), name, in_bom=False, on_board=False)
    return sym


def make_wire(x1, y1, x2, y2):
    c = Connection()
    c.type = "wire"
    c.points = [pos(x1, y1), pos(x2, y2)]
    c.uuid = uid()
    return c


def make_nc(x, y):
    nc = NoConnect()
    nc.position = pos(x, y)
    nc.uuid = uid()
    return nc


def make_label(text, x, y, angle=0):
    lbl = LocalLabel()
    lbl.text = text
    lbl.position = pos(x, y, angle)
    lbl.uuid = uid()
    eff = Effects()
    eff.font = Font()
    eff.font.size = [1.27, 1.27]
    lbl.effects = eff
    return lbl


def make_junction(x, y):
    j = Junction()
    j.position = pos(x, y)
    j.uuid = uid()
    return j


# ========================================================================
# Load existing schematic and reset to baseline (U1 only)
# This makes the script idempotent — safe to re-run.
# ========================================================================
s = Schematic.from_file(SCH)
# Keep only U1 (the Waveshare ESP32-S3-Zero placed by the user)
s.schematicSymbols = [
    sym
    for sym in s.schematicSymbols
    if sym.libraryNickname == "robot-projects"
    and sym.entryName == "Waveshare_ESP32-S3-Zero"
]
# Keep only the Waveshare lib_symbol entry
s.libSymbols = [ls for ls in s.libSymbols if ls.entryName == "Waveshare_ESP32-S3-Zero"]
s.labels = []
s.noConnects = []
s.junctions = []
s.graphicalItems = []

# Update U1 to verified socket footprint (15.5mm row spacing, measured 2026-06-22)
for sym in s.schematicSymbols:
    for prop in sym.properties:
        if prop.key == "Footprint":
            prop.value = "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount"

# ========================================================================
# Load standard library symbols for lib_symbols embedding
# ========================================================================
motor_lib = SymbolLib.from_file(f"{SYMLIBS}Driver_Motor.kicad_sym")
device_lib = SymbolLib.from_file(f"{SYMLIBS}Device.kicad_sym")
power_lib = SymbolLib.from_file(f"{SYMLIBS}power.kicad_sym")
conn_lib = SymbolLib.from_file(f"{SYMLIBS}Connector_Generic.kicad_sym")
logic_lib = SymbolLib.from_file(f"{SYMLIBS}74xGxx.kicad_sym")


def add_lib_sym(lib, entry_name, nick):
    sym = copy.deepcopy(next(x for x in lib.symbols if x.entryName == entry_name))
    sym.libraryNickname = nick
    s.libSymbols.append(sym)


robot_lib = SymbolLib.from_file("/home/ben/kicad-libs/symbols/robot-projects.kicad_sym")
add_lib_sym(robot_lib, "SparkFun_TB6612FNG_v2", "robot-projects")
add_lib_sym(device_lib, "R", "Device")
add_lib_sym(device_lib, "C", "Device")
add_lib_sym(device_lib, "C_Polarized", "Device")
for pname in ["+5V", "+3V3", "GND", "+BATT", "PWR_FLAG"]:
    add_lib_sym(power_lib, pname, "power")
for cname in ["Conn_01x02", "Conn_01x03", "Conn_01x04", "Conn_01x06"]:
    add_lib_sym(conn_lib, cname, "Connector_Generic")
add_lib_sym(logic_lib, "74LVC1G125", "74xGxx")

# ========================================================================
# ESP32-S3-Zero U1 pin coordinates
# Symbol center: (153.67, 97.79)
# abs pin = (cx + sx, cy - sy)   [KiCad Y-flip]
# ========================================================================
U1X, U1Y = 153.67, 97.79


def u1_pin(sx, sy):
    return (round(U1X + sx, 3), round(U1Y - sy, 3))


# Left pins (sx=-15.24, angle=0 → wire extends left)
U1L = {
    "1": u1_pin(-15.24, 21.59),  # 5V
    "2": u1_pin(-15.24, 19.05),  # GND
    "3": u1_pin(-15.24, 16.51),  # 3V3
    "4": u1_pin(-15.24, 13.97),  # GPIO1 / BAT_SENSE
    "5": u1_pin(-15.24, 11.43),  # GPIO2 / ECHO_DIV
    "6": u1_pin(-15.24, 8.89),  # GPIO3 / unused
    "7": u1_pin(-15.24, 6.35),  # GPIO4 / PWMA
    "8": u1_pin(-15.24, 3.81),  # GPIO5 / PWMB
    "9": u1_pin(-15.24, 1.27),  # GPIO6 / AIN1
    "10": u1_pin(-15.24, -2.54),  # GPIO45 unused
    "11": u1_pin(-15.24, -5.08),  # GPIO42 unused
    "12": u1_pin(-15.24, -7.62),  # GPIO41 unused
    "13": u1_pin(-15.24, -10.16),  # GPIO40 unused
    "14": u1_pin(-15.24, -12.70),  # GPIO39 unused
    "15": u1_pin(-15.24, -15.24),  # GPIO38 unused
    "16": u1_pin(-15.24, -17.78),  # GPIO18 / SCL
    "17": u1_pin(-15.24, -20.32),  # GPIO17 / SDA
}
# Right pins (sx=+15.24, angle=180 → wire extends right)
U1R = {
    "18": u1_pin(15.24, 21.59),  # TX
    "19": u1_pin(15.24, 19.05),  # RX
    "20": u1_pin(15.24, 16.51),  # GPIO13 / ESTOP
    "21": u1_pin(15.24, 13.97),  # GPIO12 / ENC_RB
    "22": u1_pin(15.24, 11.43),  # GPIO11 / ENC_RA
    "23": u1_pin(15.24, 8.89),  # GPIO10 / ENC_LB
    "24": u1_pin(15.24, 6.35),  # GPIO9  / ENC_LA
    "25": u1_pin(15.24, 3.81),  # GPIO8  / STBY
    "26": u1_pin(15.24, 1.27),  # GPIO7  / AIN2
    "27": u1_pin(15.24, -6.35),  # GPIO16 / BIN2
    "28": u1_pin(15.24, -8.89),  # GPIO15 / BIN1
    "29": u1_pin(15.24, -11.43),  # GPIO14 unused
}

# ========================================================================
# SparkFun TB6612FNG v2 U2 pin coordinates
# Symbol center: (215, 97.79)
# Symbol pin layout (sx=-12.7 left, sx=+12.7 right, y=+8.89 top step -2.54):
#   Left  pin 1 PWMA → 8 GND  (sx=-12.7, y from +8.89 down)
#   Right pin 9 VM   → 16 VM2 (sx=+12.7, y from +8.89 down)
# ========================================================================
U2X, U2Y = 215.0, 97.79


def u2_pin(sx, sy):
    return (round(U2X + sx, 3), round(U2Y - sy, 3))


# Pin positions using SparkFun breakout symbol geometry
# Left pins (angle=0, wire extends left): sx=-12.7, but stub len=2.54 → connection at sx-2.54=-15.24
# Wait: in KiCad pin position IS the connection point (wire end), body end = position + length in angle dir
# For angle=0 (pointing right into body): connection at x=-12.7, body side at x=-10.16
# So wire connects at sx - length = -12.7 (for angle=0, pin length 2.54, body at -10.16)
# Actually: pin position in symbol = WHERE THE WIRE CONNECTS
# For angle=0 with sx=-12.7: connection is at abs (U2X + (-12.7), U2Y - sy) = (202.3, ...)
# Pin stub len 2.54 → body edge at (-10.16, ...)
# But in symbol, sx IS the connection point so U2_abs_x = U2X + sx

U2P = {
    # Left column (sx=-12.7, angle=0 → wires extend further left)
    "PWMA": u2_pin(-12.7, 8.89),  # pin 1
    "AIN2": u2_pin(-12.7, 6.35),  # pin 2
    "AIN1": u2_pin(-12.7, 3.81),  # pin 3
    "STBY": u2_pin(-12.7, 1.27),  # pin 4
    "BIN1": u2_pin(-12.7, -1.27),  # pin 5
    "BIN2": u2_pin(-12.7, -3.81),  # pin 6
    "PWMB": u2_pin(-12.7, -6.35),  # pin 7
    "GND": u2_pin(-12.7, -8.89),  # pin 8
    # Right column (sx=+12.7, angle=180 → wires extend further right)
    "VM": u2_pin(12.7, 8.89),  # pin 9
    "VCC": u2_pin(12.7, 6.35),  # pin 10
    "AO1": u2_pin(12.7, 3.81),  # pin 11
    "AO2": u2_pin(12.7, 1.27),  # pin 12
    "GND2": u2_pin(12.7, -1.27),  # pin 13  (motor GND on breakout)
    "BO2": u2_pin(12.7, -3.81),  # pin 14
    "BO1": u2_pin(12.7, -6.35),  # pin 15
    "VM2": u2_pin(12.7, -8.89),  # pin 16  (second VM on breakout)
}


# ========================================================================
# Conn_01x02 pin helper (pins point LEFT by default)
#   pin1 at (cx-5.08, cy),      pin2 at (cx-5.08, cy+2.54)
# Conn_01x04 pin helper
#   pin1 at (cx-5.08, cy-2.54), pin2 at (cx-5.08, cy),
#   pin3 at (cx-5.08, cy+2.54), pin4 at (cx-5.08, cy+5.08)
# ========================================================================
def conn2_pins(cx, cy):
    return [(cx - 5.08, cy), (cx - 5.08, cy + 2.54)]


def conn3_pins(cx, cy):
    return [(cx - 5.08, cy - 2.54), (cx - 5.08, cy), (cx - 5.08, cy + 2.54)]


def conn4_pins(cx, cy):
    return [
        (cx - 5.08, cy - 2.54),
        (cx - 5.08, cy),
        (cx - 5.08, cy + 2.54),
        (cx - 5.08, cy + 5.08),
    ]


def conn6_pins(cx, cy):
    return [
        (cx - 5.08, cy - 5.08),
        (cx - 5.08, cy - 2.54),
        (cx - 5.08, cy),
        (cx - 5.08, cy + 2.54),
        (cx - 5.08, cy + 5.08),
        (cx - 5.08, cy + 7.62),
    ]


FP_XH2 = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
FP_XH3 = "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
FP_SOT235 = "Package_TO_SOT_SMD:SOT-23-5"


def u3_pins(cx, cy):
    """74LVC1G125 SOT-23-5 pin endpoints in schematic space (KiCad Y-flip applied).
    Pin 1 ~OE  angle=270 (wire up),  pin 2 A   angle=0   (wire left),
    pin 3 GND  angle=90  (wire down), pin 4 Y   angle=180 (wire right),
    pin 5 VCC  angle=270 (wire up).
    """
    return {
        "OE_bar": (cx, cy - 10.16),  # pin 1 — tie GND (always enabled)
        "A": (cx - 15.24, cy),  # pin 2 — data input
        "GND": (cx - 5.08, cy + 10.16),  # pin 3
        "Y": (cx + 12.70, cy),  # pin 4 — buffered output
        "VCC": (cx - 5.08, cy - 10.16),  # pin 5
    }


# ========================================================================
# PLACE COMPONENTS
# ========================================================================

# U2: SparkFun TB6612FNG v2 breakout board (w/ pre-soldered headers)
s.schematicSymbols.append(
    make_sym(
        "robot-projects",
        "SparkFun_TB6612FNG_v2",
        U2X,
        U2Y,
        "U2",
        "SparkFun_TB6612FNG_v2",
        "robot-projects:SparkFun_TB6612FNG_v2",
        "SparkFun Dual TB6612FNG motor driver breakout v2",
    )
)

# ── Motor connectors (6-pin, one per motor: power + encoder) ─────────────
# J1: Motor A (Left)  pin1=AO1 pin2=AO2 pin3=+5V pin4=GND pin5=ENC_LA pin6=ENC_LB
J1X, J1Y = 248.0, 78.0
j1_p = conn6_pins(J1X, J1Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x06",
        J1X,
        J1Y,
        "J1",
        "Motor A",
        "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
        "Motor A (Left): AO1 AO2 5V GND ENC_LA ENC_LB",
    )
)

# J2: Motor B (Right)  pin1=BO1 pin2=BO2 pin3=+5V pin4=GND pin5=ENC_RA pin6=ENC_RB
J2X, J2Y = 248.0, 100.0
j2_p = conn6_pins(J2X, J2Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x06",
        J2X,
        J2Y,
        "J2",
        "Motor B",
        "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
        "Motor B (Right): BO1 BO2 5V GND ENC_RA ENC_RB",
    )
)

# ── Qwiic / I2C ─────────────────────────────────────────────────────────
# J5: Qwiic  pin1=GND  pin2=+3V3  pin3=SDA  pin4=SCL
J5X, J5Y = 108.0, 118.0
j5_p = conn4_pins(J5X, J5Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x04",
        J5X,
        J5Y,
        "J5",
        "Qwiic",
        "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical",
        "Qwiic I2C: GND 3V3 SDA SCL",
    )
)

# ── HC-SR04 ─────────────────────────────────────────────────────────────
# J6: HC-SR04  pin1=+5V  pin2=TRIG  pin3=ECHO_IN  pin4=GND
J6X, J6Y = 108.0, 73.0
j6_p = conn4_pins(J6X, J6Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x04",
        J6X,
        J6Y,
        "J6",
        "HC-SR04",
        "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        "HC-SR04: 5V TRIG ECHO_IN GND",
    )
)

# ── E-stop ───────────────────────────────────────────────────────────────
# J7: E-stop  pin1=ESTOP  pin2=GND
J7X, J7Y = 192.0, 78.0
j7_p = conn2_pins(J7X, J7Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x02",
        J7X,
        J7Y,
        "J7",
        "E-Stop",
        "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
        "E-stop: pin1=ESTOP(NC=HIGH=safe) pin2=GND",
    )
)

# ── Power input ──────────────────────────────────────────────────────────
# J8: VBAT / GND  pin1=VBAT  pin2=GND
J8X, J8Y = 90.0, 93.0
j8_p = conn2_pins(J8X, J8Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x02",
        J8X,
        J8Y,
        "J8",
        "PWR In",
        "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
        "Power in: pin1=VBAT(2S LiPo) pin2=GND",
    )
)

# ── UART / Pi connector ──────────────────────────────────────────────────
# J9: 4-pin JST-XH  pin1=+5V  pin2=GND  pin3=UART_TX  pin4=UART_RX
# Placed above J7 (E-stop), right of U1 UART labels
J9X, J9Y = 190.5, 66.04  # x=150×1.27, y=52×1.27
j9_p = conn4_pins(J9X, J9Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x04",
        J9X,
        J9Y,
        "J9",
        "UART/Pi",
        "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
        "Pi UART: pin1=+5V pin2=GND pin3=TX pin4=RX",
    )
)


# ── Power LED (hardware, hardwired to +5V) ───────────────────────────────
# J10: XH 2-pin  pin1=LED_A  pin2=GND — always on when 5V present, no GPIO
J10X, J10Y = 248.0, 58.0
j10_p = conn2_pins(J10X, J10Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x02",
        J10X,
        J10Y,
        "J10",
        "Power LED",
        FP_XH2,
        "Power LED (panel mount). Hardwired to +5V rail — always on when powered.",
    )
)

# ── NeoPixel WS2812B 8×8 matrix connector ────────────────────────────────
# J11: XH 3-pin  pin1=NEO_DIN  pin2=+5V  pin3=GND
J11X, J11Y = 248.0, 45.0
j11_p = conn3_pins(J11X, J11Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x03",
        J11X,
        J11Y,
        "J11",
        "NeoPixel",
        FP_XH3,
        "WS2812B 8x8 NeoPixel: pin1=DATA_IN pin2=+5V pin3=GND. GPIO42 via U3 level shift.",
    )
)


# ── Resistors ────────────────────────────────────────────────────────────
# Vertical R: pin1 at (x, y-3.81), pin2 at (x, y+3.81)
def r_pins(rx, ry):
    return (rx, ry - 3.81), (rx, ry + 3.81)


# R1 100k: PWMA pulldown  (between GPIO4 net and GND)
R1X, R1Y = 121.92, 91.44  # x=96×1.27, y=72×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R1X,
        R1Y,
        "R1",
        "100k",
        "Resistor_SMD:R_0402_1005Metric",
        "GPIO4/PWMA boot-safety pulldown",
    )
)

# R2 100k: PWMB pulldown
R2X, R2Y = 121.92, 96.52  # x=96×1.27, y=76×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R2X,
        R2Y,
        "R2",
        "100k",
        "Resistor_SMD:R_0402_1005Metric",
        "GPIO5/PWMB boot-safety pulldown",
    )
)

# R3 100k: STBY pulldown  (GPIO8, right side, between components)
R3X, R3Y = 185.42, 93.98  # x=146×1.27, y=74×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R3X,
        R3Y,
        "R3",
        "100k",
        "Resistor_SMD:R_0402_1005Metric",
        "GPIO8/STBY boot-safety pulldown",
    )
)

# R4 10k: E-stop pullup (GPIO13 → 3V3)
R4X, R4Y = 182.88, 78.74  # x=144×1.27, y=62×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R4X,
        R4Y,
        "R4",
        "10k",
        "Resistor_SMD:R_0402_1005Metric",
        "E-stop pullup to 3V3",
    )
)

# R5 10k: Echo divider top (ECHO_IN → mid node)
R5X, R5Y = 111.76, 82.55  # x=88×1.27, y=65×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R5X,
        R5Y,
        "R5",
        "10k",
        "Resistor_SMD:R_0402_1005Metric",
        "HC-SR04 echo voltage divider top",
    )
)

# R6 20k: Echo divider bottom (mid node → GND)
R6X, R6Y = 111.76, 93.98  # x=88×1.27, y=74×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R6X,
        R6Y,
        "R6",
        "20k",
        "Resistor_SMD:R_0402_1005Metric",
        "HC-SR04 echo voltage divider bottom",
    )
)

# R7 100Ω: Echo ESD series (mid node → GPIO2)
R7X, R7Y = 121.92, 86.36  # x=96×1.27, y=68×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R7X,
        R7Y,
        "R7",
        "100",
        "Resistor_SMD:R_0402_1005Metric",
        "HC-SR04 echo ESD series resistor",
    )
)

# R8 100k: Battery sense divider top (VBAT → BAT_SENSE)
R8X, R8Y = 127.0, 80.01  # x=100×1.27, y=63×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R8X,
        R8Y,
        "R8",
        "100k",
        "Resistor_SMD:R_0402_1005Metric",
        "Battery sense divider top",
    )
)

# R9 47k: Battery sense divider bottom (BAT_SENSE → GND)
R9X, R9Y = 127.0, 91.44  # x=100×1.27, y=72×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R9X,
        R9Y,
        "R9",
        "47k",
        "Resistor_SMD:R_0402_1005Metric",
        "Battery sense divider bottom",
    )
)

# ── Capacitors ───────────────────────────────────────────────────────────
# Vertical C: same as R — pin1 top, pin2 bottom

# C1 100n: E-stop debounce (ESTOP → GND)
C1X, C1Y = 192.01, 83.82  # x=151.2×1.27→151×1.27=191.77 ≈ 192, y=66×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C",
        C1X,
        C1Y,
        "C1",
        "100n",
        "Capacitor_SMD:C_0402_1005Metric",
        "E-stop debounce cap",
    )
)

# C2 100n: Battery ADC noise filter (BAT_SENSE → GND)
C2X, C2Y = 133.35, 86.36  # x=105×1.27, y=68×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C",
        C2X,
        C2Y,
        "C2",
        "100n",
        "Capacitor_SMD:C_0402_1005Metric",
        "Battery ADC noise filter",
    )
)

# C3 1000µF: VM bulk cap (VBAT → GND) — near motor driver, critical for TB6612 back-EMF
C3X, C3Y = 90.0, 108.0  # below J8 in schematic
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C_Polarized",
        C3X,
        C3Y,
        "C3",
        "1000µF",
        "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
        "VM bulk decoupling (TB6612 back-EMF protection)",
    )
)

# C4 100n: VBAT rail decoupling
C4X, C4Y = 152.4, 128.0
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C",
        C4X,
        C4Y,
        "C4",
        "100n",
        "Capacitor_SMD:C_0402_1005Metric",
        "VBAT rail decoupling",
    )
)

# C5 100n: +3V3 rail decoupling
C5X, C5Y = 162.0, 128.0
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C",
        C5X,
        C5Y,
        "C5",
        "100n",
        "Capacitor_SMD:C_0402_1005Metric",
        "+3V3 rail decoupling",
    )
)

# ── R10: Power LED series resistor (hardwired +5V → 330Ω → LED_A) ────────
R10X, R10Y = 231.0, 58.0
r10_t, r10_b = r_pins(R10X, R10Y)
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R10X,
        R10Y,
        "R10",
        "330",
        "Resistor_SMD:R_0402_1005Metric",
        "Power LED series resistor (5V→330Ω→LED_A, ~9mA, no GPIO)",
    )
)

# ── R11: NeoPixel data line series resistor (ringing suppression) ─────────
R11X, R11Y = 232.0, 45.0
r11_t, r11_b = r_pins(R11X, R11Y)
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R11X,
        R11Y,
        "R11",
        "330",
        "Resistor_SMD:R_0402_1005Metric",
        "NeoPixel data line series resistor (suppress ringing at 800kHz)",
    )
)

# ── U3: 74LVC1G125 level shifter (3.3V GPIO42 → 5V NeoPixel data) ─────────
U3X, U3Y = 215.0, 45.0
u3_p = u3_pins(U3X, U3Y)
s.schematicSymbols.append(
    make_sym(
        "74xGxx",
        "74LVC1G125",
        U3X,
        U3Y,
        "U3",
        "74LVC1G125",
        FP_SOT235,
        "Single buffer/driver, 3-state. 3.3V→5V level shift for NeoPixel data.",
    )
)

# ── C6: 100µF NeoPixel 5V bulk decoupling ────────────────────────────────
C6X, C6Y = 262.0, 45.0
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C_Polarized",
        C6X,
        C6Y,
        "C6",
        "100µF",
        "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
        "NeoPixel +5V bulk decoupling (64-LED inrush at power-on)",
    )
)

# ── C7: 100nF NeoPixel 5V HF decoupling ─────────────────────────────────
C7X, C7Y = 272.0, 45.0
s.schematicSymbols.append(
    make_sym(
        "Device",
        "C",
        C7X,
        C7Y,
        "C7",
        "100n",
        "Capacitor_SMD:C_0402_1005Metric",
        "NeoPixel +5V HF decoupling",
    )
)

# ========================================================================
# POWER SYMBOLS
# Place at exact pin-endpoint coordinates so they connect without wires
# ========================================================================

# ESP32 power pins
s.schematicSymbols.append(make_pwr("+5V", *U1L["1"]))
s.schematicSymbols.append(make_pwr("GND", *U1L["2"]))
s.schematicSymbols.append(make_pwr("+3V3", *U1L["3"]))

# SparkFun TB6612FNG v2 power pins
s.schematicSymbols.append(make_pwr("+3V3", *U2P["VCC"]))  # pin 10
s.schematicSymbols.append(make_pwr("+BATT", *U2P["VM"]))  # pin 9
s.schematicSymbols.append(make_pwr("+BATT", *U2P["VM2"]))  # pin 16
s.schematicSymbols.append(make_pwr("GND", *U2P["GND"]))  # pin 8
s.schematicSymbols.append(make_pwr("GND", *U2P["GND2"]))  # pin 13 (motor GND)

# Resistor / capacitor power pins (GND at bottom = y+3.81, power at top = y-3.81)
s.schematicSymbols.append(make_pwr("GND", R1X, R1Y + 3.81))  # R1 bottom
s.schematicSymbols.append(make_pwr("GND", R2X, R2Y + 3.81))  # R2 bottom
s.schematicSymbols.append(make_pwr("GND", R3X, R3Y + 3.81))  # R3 bottom
s.schematicSymbols.append(make_pwr("+3V3", R4X, R4Y - 3.81))  # R4 top
s.schematicSymbols.append(make_pwr("GND", R6X, R6Y + 3.81))  # R6 bottom
s.schematicSymbols.append(make_pwr("+BATT", R8X, R8Y - 3.81))  # R8 top
s.schematicSymbols.append(make_pwr("GND", R9X, R9Y + 3.81))  # R9 bottom
s.schematicSymbols.append(make_pwr("GND", C1X, C1Y + 3.81))  # C1 bottom
s.schematicSymbols.append(make_pwr("GND", C2X, C2Y + 3.81))  # C2 bottom
# KiCad Y-flip: symbol pin1 at sym_y=+3.81 maps to absolute y = Cy-3.81 (TOP on screen)
#               symbol pin2 at sym_y=-3.81 maps to absolute y = Cy+3.81 (BOTTOM on screen)
# C3 polarized: pin1(+) at top=C3Y-3.81 → +BATT, pin2(-) at bottom=C3Y+3.81 → GND
s.schematicSymbols.append(make_pwr("+BATT", C3X, C3Y - 3.81))  # C3 pin1 (+) top
s.schematicSymbols.append(make_pwr("GND", C3X, C3Y + 3.81))  # C3 pin2 (-) bottom
s.schematicSymbols.append(make_pwr("+BATT", C4X, C4Y - 3.81))  # C4 pin1 top (+BATT)
s.schematicSymbols.append(make_pwr("GND", C4X, C4Y + 3.81))  # C4 pin2 bottom (GND)
s.schematicSymbols.append(make_pwr("+3V3", C5X, C5Y - 3.81))  # C5 pin1 top (+3V3)
s.schematicSymbols.append(make_pwr("GND", C5X, C5Y + 3.81))  # C5 pin2 bottom (GND)

# J8 connector: pin2=GND
s.schematicSymbols.append(make_pwr("GND", *j8_p[1]))

# J5 Qwiic: pin1=GND, pin2=+3V3
s.schematicSymbols.append(make_pwr("GND", *j5_p[0]))
s.schematicSymbols.append(make_pwr("+3V3", *j5_p[1]))

# J6 HC-SR04: pin1=+5V, pin4=GND
s.schematicSymbols.append(make_pwr("+5V", *j6_p[0]))
s.schematicSymbols.append(make_pwr("GND", *j6_p[3]))

# J1 Motor A: pin3=+5V (encoder power), pin4=GND
s.schematicSymbols.append(make_pwr("+5V", *j1_p[2]))
s.schematicSymbols.append(make_pwr("GND", *j1_p[3]))

# J2 Motor B: pin3=+5V (encoder power), pin4=GND
s.schematicSymbols.append(make_pwr("+5V", *j2_p[2]))
s.schematicSymbols.append(make_pwr("GND", *j2_p[3]))

# J7 E-stop: pin2=GND
s.schematicSymbols.append(make_pwr("GND", *j7_p[1]))

# J9 UART: pin1=+5V  pin2=GND
s.schematicSymbols.append(make_pwr("+5V", *j9_p[0]))
s.schematicSymbols.append(make_pwr("GND", *j9_p[1]))

# J10 Power LED: pin2=GND
s.schematicSymbols.append(make_pwr("GND", *j10_p[1]))

# J11 NeoPixel: pin2=+5V, pin3=GND
s.schematicSymbols.append(make_pwr("+5V", *j11_p[1]))
s.schematicSymbols.append(make_pwr("GND", *j11_p[2]))

# R10 power LED: top=+5V (bottom=LED_A via label)
s.schematicSymbols.append(make_pwr("+5V", *r10_t))

# U3 74LVC1G125: VCC=+5V, GND, OE_bar tied to GND (always enabled)
s.schematicSymbols.append(make_pwr("+5V", *u3_p["VCC"]))
s.schematicSymbols.append(make_pwr("GND", *u3_p["GND"]))
s.schematicSymbols.append(make_pwr("GND", *u3_p["OE_bar"]))

# C6 100µF NeoPixel bulk: pin1(+)=+5V, pin2(-)=GND
s.schematicSymbols.append(make_pwr("+5V", C6X, C6Y - 3.81))
s.schematicSymbols.append(make_pwr("GND", C6X, C6Y + 3.81))

# C7 100nF NeoPixel HF: pin1=+5V, pin2=GND
s.schematicSymbols.append(make_pwr("+5V", C7X, C7Y - 3.81))
s.schematicSymbols.append(make_pwr("GND", C7X, C7Y + 3.81))

# PWR_FLAG: place at SAME position as the power symbols they annotate
# so the pins overlap and KiCad sees them on the same net
s.schematicSymbols.append(make_pwr("PWR_FLAG", *U1L["1"]))  # on +5V net
s.schematicSymbols.append(make_pwr("PWR_FLAG", *U1L["2"]))  # on GND net
s.schematicSymbols.append(make_pwr("PWR_FLAG", *U2P["VM"]))  # on +BATT net

# ========================================================================
# NET LABELS (angle=180 = connection on right → text extends LEFT,
#             angle=0   = connection on left  → text extends RIGHT)
# Convention: left-side ESP32 pins → angle=180 (label faces away from body)
#             right-side ESP32 pins → angle=0   (label faces away from body)
# ========================================================================
lbl = s.labels

# ── ESP32 left-side signal pins ──────────────────────────────────────────
# angle=180: connection at right end of label, text extends left (away from ESP32)
lbl.append(make_label("BAT_SENSE", *U1L["4"], 180))
lbl.append(make_label("ECHO_DIV", *U1L["5"], 180))
lbl.append(make_label("TRIG", *U1L["6"], 180))
lbl.append(make_label("PWMA", *U1L["7"], 180))
lbl.append(make_label("PWMB", *U1L["8"], 180))
lbl.append(make_label("AIN1", *U1L["9"], 180))
lbl.append(make_label("SCL", *U1L["16"], 180))
lbl.append(make_label("SDA", *U1L["17"], 180))

# ── ESP32 right-side signal pins ─────────────────────────────────────────
# angle=0: connection at left end, text extends right
lbl.append(make_label("UART_TX", *U1R["18"], 0))
lbl.append(make_label("UART_RX", *U1R["19"], 0))
lbl.append(make_label("ESTOP", *U1R["20"], 0))
lbl.append(make_label("ENC_RB", *U1R["21"], 0))
lbl.append(make_label("ENC_RA", *U1R["22"], 0))
lbl.append(make_label("ENC_LB", *U1R["23"], 0))
lbl.append(make_label("ENC_LA", *U1R["24"], 0))
lbl.append(make_label("STBY", *U1R["25"], 0))
lbl.append(make_label("AIN2", *U1R["26"], 0))
lbl.append(make_label("BIN1", *U1L["15"], 180))  # GPIO38, cluster pad 15
lbl.append(make_label("BIN2", *U1L["14"], 180))  # GPIO39, cluster pad 14

# ── SparkFun TB6612FNG v2 left-side inputs (angle=180: text extends left) ──
lbl.append(make_label("PWMA", *U2P["PWMA"], 180))
lbl.append(make_label("AIN2", *U2P["AIN2"], 180))
lbl.append(make_label("AIN1", *U2P["AIN1"], 180))
lbl.append(make_label("STBY", *U2P["STBY"], 180))
lbl.append(make_label("BIN1", *U2P["BIN1"], 180))
lbl.append(make_label("BIN2", *U2P["BIN2"], 180))
lbl.append(make_label("PWMB", *U2P["PWMB"], 180))

# ── SparkFun TB6612FNG v2 right-side outputs (angle=0: text extends right) ─
lbl.append(make_label("AO1", *U2P["AO1"], 0))
lbl.append(make_label("AO2", *U2P["AO2"], 0))
lbl.append(make_label("BO2", *U2P["BO2"], 0))
lbl.append(make_label("BO1", *U2P["BO1"], 0))

# ── Motor connectors J1/J2 (6-pin, pins face LEFT, angle=180) ────────────
# pins 3-4 (+5V, GND) use power symbols; pins 1,2,5,6 use net labels
lbl.append(make_label("AO1", *j1_p[0], 180))
lbl.append(make_label("AO2", *j1_p[1], 180))
lbl.append(make_label("ENC_LA", *j1_p[4], 180))
lbl.append(make_label("ENC_LB", *j1_p[5], 180))
lbl.append(make_label("BO1", *j2_p[0], 180))
lbl.append(make_label("BO2", *j2_p[1], 180))
lbl.append(make_label("ENC_RA", *j2_p[4], 180))
lbl.append(make_label("ENC_RB", *j2_p[5], 180))

# ── Qwiic J5 (pins face left, angle=180) ─────────────────────────────────
lbl.append(make_label("SDA", *j5_p[2], 180))
lbl.append(make_label("SCL", *j5_p[3], 180))

# ── HC-SR04 J6 ───────────────────────────────────────────────────────────
lbl.append(make_label("TRIG", *j6_p[1], 180))
lbl.append(make_label("ECHO_IN", *j6_p[2], 180))

# ── UART J9 ──────────────────────────────────────────────────────────────
lbl.append(make_label("UART_TX", *j9_p[2], 180))
lbl.append(make_label("UART_RX", *j9_p[3], 180))

# ── E-stop J7 ────────────────────────────────────────────────────────────
lbl.append(make_label("ESTOP", *j7_p[0], 180))

# ── Power in J8 ──────────────────────────────────────────────────────────
# Use +BATT power symbol on pin1 so J8 feeds the same +BATT net as TB6612 VM
s.schematicSymbols.append(make_pwr("+BATT", *j8_p[0]))

# ── Resistors / Caps: vertical component, label at top pin (y-3.81) ──────
# angle=90 → connection at bottom, text extends upward (away from component)

# R1: top=PWMA, bottom=GND (already powered)
lbl.append(make_label("PWMA", R1X, R1Y - 3.81, 90))

# R2: top=PWMB, bottom=GND
lbl.append(make_label("PWMB", R2X, R2Y - 3.81, 90))

# R3: top=STBY, bottom=GND
lbl.append(make_label("STBY", R3X, R3Y - 3.81, 90))

# R4: top=+3V3 (powered), bottom=ESTOP
lbl.append(make_label("ESTOP", R4X, R4Y + 3.81, 270))

# R5: top=ECHO_IN, bottom=ECHO_MID
lbl.append(make_label("ECHO_IN", R5X, R5Y - 3.81, 90))
lbl.append(make_label("ECHO_MID", R5X, R5Y + 3.81, 270))

# R6: top=ECHO_MID, bottom=GND (already powered)
lbl.append(make_label("ECHO_MID", R6X, R6Y - 3.81, 90))

# R7: top=ECHO_MID, bottom=ECHO_DIV  (series from mid → GPIO2)
lbl.append(make_label("ECHO_MID", R7X, R7Y - 3.81, 90))
lbl.append(make_label("ECHO_DIV", R7X, R7Y + 3.81, 270))

# R8: top=+BATT (powered), bottom=BAT_SENSE
lbl.append(make_label("BAT_SENSE", R8X, R8Y + 3.81, 270))

# R9: top=BAT_SENSE, bottom=GND (powered)
lbl.append(make_label("BAT_SENSE", R9X, R9Y - 3.81, 90))

# C1: top=ESTOP, bottom=GND (powered)
lbl.append(make_label("ESTOP", C1X, C1Y - 3.81, 90))

# C2: top=BAT_SENSE, bottom=GND (powered)
lbl.append(make_label("BAT_SENSE", C2X, C2Y - 3.81, 90))

# ── Power LED J10 + R10 ───────────────────────────────────────────────────
# R10: top=+5V (power symbol), bottom=LED_A
lbl.append(make_label("LED_A", *r10_b, 270))
# J10: pin1=LED_A, pin2=GND (power symbol)
lbl.append(make_label("LED_A", *j10_p[0], 180))

# ── NeoPixel circuit: GPIO42 → U3(74LVC1G125) → R11 → J11 ───────────────
# GPIO42 inner cluster pad 11: NEO_DATA source
lbl.append(make_label("NEO_DATA", *U1L["11"], 180))
# U3 input (A, pin 2): NEO_DATA
lbl.append(make_label("NEO_DATA", *u3_p["A"], 180))
# U3 output (Y, pin 4): NEO_BUF
lbl.append(make_label("NEO_BUF", *u3_p["Y"], 0))
# R11: top=NEO_BUF, bottom=NEO_DIN
lbl.append(make_label("NEO_BUF", *r11_t, 90))
lbl.append(make_label("NEO_DIN", *r11_b, 270))
# J11: pin1=NEO_DIN
lbl.append(make_label("NEO_DIN", *j11_p[0], 180))

# ── VBAT label on J8 (already added) already connects J8 pin1 to +BATT rail ──
# Add VBAT label also on R8 (top) is already powered by +BATT symbol

# ========================================================================
# NO-CONNECTS on unused ESP32 pins
# ========================================================================
# Left inner cluster: GPIO45(10), GPIO41(12), GPIO40(13) unused
# GPIO42(11)=NEO_DATA → labelled below; GPIO39(14)=BIN2, GPIO38(15)=BIN1 → labelled above
for p in ["10", "12", "13"]:
    s.noConnects.append(make_nc(*U1L[p]))

# Right side: GPIO16(27), GPIO15(28), GPIO14(29) are NOT accessible on flat-mount module
for p in ["27", "28", "29"]:
    s.noConnects.append(make_nc(*U1R[p]))

# ========================================================================
# WRITE SCHEMATIC
# ========================================================================
s.to_file(SCH)
print(f"Schematic written: {SCH}")
print(f"Components: {len(s.schematicSymbols)} symbols")
print(f"Labels: {len(s.labels)}")
print(f"No-connects: {len(s.noConnects)}")
