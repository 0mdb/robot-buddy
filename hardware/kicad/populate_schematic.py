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
    and sym.entryName.startswith("Waveshare_ESP32-S3-Zero")
]
# Keep only the Waveshare lib_symbol entry
s.libSymbols = []  # U1's lib_symbol is re-added below as the _NoCluster variant
s.labels = []
s.noConnects = []
s.junctions = []
s.graphicalItems = []

# v2: U1 uses the perimeter-only symbol AND footprint. The clustered variant's rear
# pad geometry was fabricated (register F1) and every signal that used it has moved,
# so the symbol must not carry pins the footprint has no pads for.
for sym in s.schematicSymbols:
    sym.entryName = "Waveshare_ESP32-S3-Zero_NoCluster"
    sym.libId = "robot-projects:Waveshare_ESP32-S3-Zero_NoCluster"
    sym.libName = sym.libId
    for prop in sym.properties:
        if prop.key == "Footprint":
            prop.value = "robot-projects:Waveshare_ESP32-S3-Zero_FlatMount_NoCluster"

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
add_lib_sym(robot_lib, "Waveshare_ESP32-S3-Zero_NoCluster", "robot-projects")
add_lib_sym(device_lib, "R", "Device")
add_lib_sym(device_lib, "C", "Device")
add_lib_sym(device_lib, "C_Polarized", "Device")
for pname in ["+5V", "+3V3", "GND", "PWR_FLAG"]:
    add_lib_sym(power_lib, pname, "power")
for cname in ["Conn_01x02", "Conn_01x03", "Conn_01x04", "Conn_01x06"]:
    add_lib_sym(conn_lib, cname, "Connector_Generic")
expander_lib = SymbolLib.from_file(f"{SYMLIBS}Interface_Expansion.kicad_sym")
add_lib_sym(expander_lib, "TCA9554PW", "Interface_Expansion")

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
    "4": u1_pin(
        -15.24, 13.97
    ),  # GPIO1 / SPARE (ADC1_CH0) — was BAT_SENSE, dropped in A3
    "5": u1_pin(-15.24, 11.43),  # GPIO2 / ECHO_DIV
    "6": u1_pin(-15.24, 8.89),  # GPIO3 / unused
    "7": u1_pin(-15.24, 6.35),  # GPIO4 / PWMA
    "8": u1_pin(-15.24, 3.81),  # GPIO5 / PWMB
    "9": u1_pin(-15.24, 1.27),  # GPIO6 / SPARE — AIN1 moved to the expander
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
    "25": u1_pin(15.24, 3.81),  # GPIO8  / SCL  (STBY now hardware-tied to ESTOP)
    "26": u1_pin(15.24, 1.27),  # GPIO7  / SDA  (AIN2 moved to the expander)
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
    # Pad N maps to JP1 pin (17-N): the footprint is the Eagle layout rotated
    # 180 deg, so pads 9..16 run JP1 pin8 -> pin1. Authoritative JP1 order from
    # docs/ref/SparkFun_Motor_Driver-TB6612FNG_v11c.sch, pin1->8:
    #   GND, BO1, BO2, AO2, AO1, GND, VCC, VM   <- note TWO GNDs (pin1 and pin6)
    # Dropping the pin6 GND is what shifted pins 11-13 and left +BATT on pin 16
    # (a dead short across the pack). See docs/v2-defect-register.md E1.
    "VM": u2_pin(12.7, 8.89),  # pin 9  = JP1 pin8
    "VCC": u2_pin(12.7, 6.35),  # pin 10 = JP1 pin7
    "GND2": u2_pin(12.7, 3.81),  # pin 11 = JP1 pin6  (GND, not AO1)
    "AO1": u2_pin(12.7, 1.27),  # pin 12 = JP1 pin5
    "AO2": u2_pin(12.7, -1.27),  # pin 13 = JP1 pin4
    "BO2": u2_pin(12.7, -3.81),  # pin 14 = JP1 pin3
    "BO1": u2_pin(12.7, -6.35),  # pin 15 = JP1 pin2
    "GND3": u2_pin(12.7, -8.89),  # pin 16 = JP1 pin1  (GND, not a second VM)
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
        "MOTOR L",
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
        "MOTOR R",
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
        "QWIIC 3V3",
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
        "HC-SR04 5V",
        "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        "HC-SR04: 5V TRIG ECHO_IN GND",
    )
)

# ── E-stop — FAIL-SAFE, with cable detection (register E3) ────────────────
# J7: pin1=+3V3  pin2=ESTOP  pin3=ESTOP_LOOP
#
# Was a 2-pin, normally-OPEN switch shorting ESTOP to GND against a pull-up.
# That stops the motors when pressed, but an unplugged or broken cable reads
# EXACTLY like "not pressed" — the robot runs with no protection and nothing
# indicates it. The MCU could not tell the difference; both are the same voltage.
#
# Now de-energise-to-stop, the standard e-stop topology:
#   +3V3 --> [NC contact] --> ESTOP, with R4 pulling ESTOP DOWN
# so pressed, unplugged, broken wire and failed crimp all pull ESTOP low, and low
# drives U2 STBY low — the driver is disabled in hardware with no firmware in the
# path (A0 decision 2 is preserved, only its polarity changes).
#
# Pin 3 is the cable-detect loop, tied to pin 1 at the SWITCH end of the harness,
# with R18 pulling it down on the board. That makes the three states distinct:
#   loop high + estop high -> connected, not pressed
#   loop high + estop low  -> connected, PRESSED
#   loop low               -> CABLE MISSING
# Both failure modes still stop the motors; the loop only lets firmware say which.
J7X, J7Y = 192.0, 78.0
j7_p = conn3_pins(J7X, J7Y)
s.schematicSymbols.append(
    make_sym(
        "Connector_Generic",
        "Conn_01x03",
        J7X,
        J7Y,
        "J7",
        "E-STOP NC",
        "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical",
        "E-stop, fail-safe: pin1=+3V3 pin2=ESTOP(NC contact) pin3=ESTOP_LOOP. "
        "Harness ties pin3 to pin1 at the switch. LOW = stopped.",
    )
)

# ── Power input ──────────────────────────────────────────────────────────
# J8: VBAT / GND  pin1=VBAT  pin2=GND

# ── UART / Pi connector ──────────────────────────────────────────────────
# J9: 4-pin JST-VH  pin1=+5V  pin2=GND  pin3=UART_TX  pin4=UART_RX
# JST-VH (10A) not XH (3A): this is the ONLY power input now that the pack
# tap is gone, and it carries the motors too. VH > the 1.5mm trace (5.26A) >
# the HAT's ~5A limit, so the chain is coordinated with no series fuse — a
# PTC would have burned ~47% of the TB6612's 0.5V VM margin (A0d).
# VH is also physically distinct from every XH on the board, which is what
# retires the C1/C2 mateability hazard by construction.
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
        "5V+UART Pi",
        "Connector_JST:JST_VH_B4P-VH_1x04_P3.96mm_Vertical",
        "Pi UART: pin1=+5V pin2=GND pin3=TX pin4=RX",
    )
)


# ── Power LED: J10 + R10 DELETED 2026-11-09 (Ben: no LEDs on the reflex board; the
#    face screen shows the robot is alive). Board shrink, docs/v2-defect-register.md §M.

# ── NeoPixel WS2812B 8×8 matrix connector ────────────────────────────────
# J11: XH 3-pin  pin1=NEO_DIN  pin2=+5V  pin3=GND


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

# R4 10k: E-stop pull-DOWN (ESTOP → GND). Was a pull-up to +3V3; inverted for
# fail-safe, see J7 above. Low is the de-energised, safe state.
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
        "E-stop pull-down to GND (fail-safe: no cable = low = stopped)",
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

# R6 15k: Echo divider bottom (mid node → GND).  20k→15k 2026-08-06 (X5):
# 10k/20k gave 3.50V at a 5.25V HC-SR04 supply vs a 3.6V absolute max — only
# 100mV. 10k/15k gives 3.15V worst case, and V_IH is only 2.475V so the logic
# margin is untouched.
R6X, R6Y = 111.76, 93.98  # x=88×1.27, y=74×1.27
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R6X,
        R6Y,
        "R6",
        "15k",
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

# ── R11: NeoPixel data line series resistor (ringing suppression) ─────────

# ── U3: 74LVC1G125 level shifter (3.3V GPIO42 → 5V NeoPixel data) ─────────

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
s.schematicSymbols.append(make_pwr("+5V", *U2P["VM"]))  # pin 9 (only VM pin)
s.schematicSymbols.append(make_pwr("GND", *U2P["GND"]))  # pin 8
s.schematicSymbols.append(make_pwr("GND", *U2P["GND2"]))  # pin 11
s.schematicSymbols.append(make_pwr("GND", *U2P["GND3"]))  # pin 16

# Resistor / capacitor power pins (GND at bottom = y+3.81, power at top = y-3.81)
s.schematicSymbols.append(make_pwr("GND", R1X, R1Y + 3.81))  # R1 bottom
s.schematicSymbols.append(make_pwr("GND", R2X, R2Y + 3.81))  # R2 bottom
s.schematicSymbols.append(make_pwr("GND", R4X, R4Y - 3.81))  # R4 top (pull-down)
s.schematicSymbols.append(make_pwr("GND", R6X, R6Y + 3.81))  # R6 bottom
s.schematicSymbols.append(make_pwr("GND", C1X, C1Y + 3.81))  # C1 bottom
# KiCad Y-flip: symbol pin1 at sym_y=+3.81 maps to absolute y = Cy-3.81 (TOP on screen)
#               symbol pin2 at sym_y=-3.81 maps to absolute y = Cy+3.81 (BOTTOM on screen)
# C3 polarized: pin1(+) at top=C3Y-3.81 → +5V, pin2(-) at bottom=C3Y+3.81 → GND
# A3: +BATT eliminated; C3 is now the +5V bulk that holds TB6612 VM above its
# 4.5V floor. VM has only 0.5V of margin, so C3 MUST be placed at U2 pad 9.
s.schematicSymbols.append(make_pwr("+5V", C3X, C3Y - 3.81))  # C3 pin1 (+) top
s.schematicSymbols.append(make_pwr("GND", C3X, C3Y + 3.81))  # C3 pin2 (-) bottom
s.schematicSymbols.append(make_pwr("+5V", C4X, C4Y - 3.81))  # C4 pin1 top (+5V)
s.schematicSymbols.append(make_pwr("GND", C4X, C4Y + 3.81))  # C4 pin2 bottom (GND)
s.schematicSymbols.append(make_pwr("+3V3", C5X, C5Y - 3.81))  # C5 pin1 top (+3V3)
s.schematicSymbols.append(make_pwr("GND", C5X, C5Y + 3.81))  # C5 pin2 bottom (GND)

# J8 connector: pin2=GND

# J5 Qwiic: pin1=GND, pin2=+3V3
s.schematicSymbols.append(make_pwr("GND", *j5_p[0]))
s.schematicSymbols.append(make_pwr("+3V3", *j5_p[1]))

# J6 HC-SR04: pin1=+5V, pin4=GND
s.schematicSymbols.append(make_pwr("+5V", *j6_p[0]))
s.schematicSymbols.append(make_pwr("GND", *j6_p[3]))

# J1 Motor A: pin3=+3V3 (encoder power), pin4=GND. 2026-11-09 (register M7): was +5V, but
# the encoder's A/B outputs go straight to non-5V-tolerant GPIO9-12, so power it at 3.3 V
# (Yahboom encoder TT: 3.3-5 V). Same fix cad-loop made on v1 (600b271).
s.schematicSymbols.append(make_pwr("+3V3", *j1_p[2]))
s.schematicSymbols.append(make_pwr("GND", *j1_p[3]))

# J2 Motor B: pin3=+3V3 (encoder power), pin4=GND
s.schematicSymbols.append(make_pwr("+3V3", *j2_p[2]))
s.schematicSymbols.append(make_pwr("GND", *j2_p[3]))

# J7 E-stop: pin1=+3V3 (through the NC contact to pin2). No GND on this connector
# any more — the switch loop is powered, so losing it de-energises ESTOP.
s.schematicSymbols.append(make_pwr("+3V3", *j7_p[0]))

# J9 UART: pin1=+5V  pin2=GND
s.schematicSymbols.append(make_pwr("+5V", *j9_p[0]))
s.schematicSymbols.append(make_pwr("GND", *j9_p[1]))


# J11 NeoPixel: pin2=+5V, pin3=GND


# U3 74LVC1G125: VCC=+5V, GND, OE_bar tied to GND (always enabled)

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
# (U2 VM PWR_FLAG removed 2026-11-09: it dates from VM = +BATT, a separate rail. Since A3
#  VM is +5V, so it was a second PWR_FLAG on +5V: ERC pin_to_pin "power output to power output".)

# ========================================================================
# NET LABELS (angle=180 = connection on right → text extends LEFT,
#             angle=0   = connection on left  → text extends RIGHT)
# Convention: left-side ESP32 pins → angle=180 (label faces away from body)
#             right-side ESP32 pins → angle=0   (label faces away from body)
# ========================================================================
lbl = s.labels

# ── ESP32 left-side signal pins ──────────────────────────────────────────
# angle=180: connection at right end of label, text extends left (away from ESP32)
lbl.append(make_label("ECHO_DIV", *U1L["5"], 180))
lbl.append(make_label("TRIG", *U1L["6"], 180))
lbl.append(make_label("PWMA", *U1L["7"], 180))
lbl.append(make_label("PWMB", *U1L["8"], 180))
# SDA/SCL move off the deleted rear cluster onto perimeter pads 26/25
# (GPIO7/GPIO8), freed by AIN2 and STBY leaving. See A0c pin map.
lbl.append(make_label("SCL", *U1R["25"], 0))
lbl.append(make_label("SDA", *U1R["26"], 0))

# ── ESP32 right-side signal pins ─────────────────────────────────────────
# angle=0: connection at left end, text extends right
lbl.append(make_label("UART_TX", *U1R["18"], 0))
lbl.append(make_label("UART_RX", *U1R["19"], 0))
lbl.append(make_label("ESTOP", *U1R["20"], 0))
lbl.append(make_label("ENC_RB", *U1R["21"], 0))
lbl.append(make_label("ENC_RA", *U1R["22"], 0))
lbl.append(make_label("ENC_LB", *U1R["23"], 0))
lbl.append(make_label("ENC_LA", *U1R["24"], 0))

# ── SparkFun TB6612FNG v2 left-side inputs (angle=180: text extends left) ──
lbl.append(make_label("PWMA", *U2P["PWMA"], 180))
lbl.append(make_label("AIN2", *U2P["AIN2"], 180))
lbl.append(make_label("AIN1", *U2P["AIN1"], 180))
# STBY tied to the ESTOP net: e-stop disables the driver in hardware, no
# firmware in the path. Frees GPIO8 for SCL. See v2-defect-register A0.
lbl.append(make_label("ESTOP", *U2P["STBY"], 180))
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
lbl.append(make_label("ESTOP", *j7_p[1], 180))
lbl.append(make_label("ESTOP_LOOP", *j7_p[2], 180))

# ── Power in J8 ──────────────────────────────────────────────────────────
# Use +BATT power symbol on pin1 so J8 feeds the same +BATT net as TB6612 VM

# ── Resistors / Caps: vertical component, label at top pin (y-3.81) ──────
# angle=90 → connection at bottom, text extends upward (away from component)

# R1: top=PWMA, bottom=GND (already powered)
lbl.append(make_label("PWMA", R1X, R1Y - 3.81, 90))

# R2: top=PWMB, bottom=GND
lbl.append(make_label("PWMB", R2X, R2Y - 3.81, 90))

# R3: top=STBY, bottom=GND

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


# C1: top=ESTOP, bottom=GND (powered)
lbl.append(make_label("ESTOP", C1X, C1Y - 3.81, 90))


# ── NeoPixel circuit: GPIO42 → U3(74LVC1G125) → R11 → J11 ───────────────
# GPIO42 inner cluster pad 11: NEO_DATA source
# U3 input (A, pin 2): NEO_DATA
# U3 output (Y, pin 4): NEO_BUF
# R11: top=NEO_BUF, bottom=NEO_DIN
# J11: pin1=NEO_DIN

# ── VBAT label on J8 (already added) already connects J8 pin1 to +BATT rail ──
# Add VBAT label also on R8 (top) is already powered by +BATT symbol


# ========================================================================
# U4 — TCA9554A I²C GPIO expander  (v2, register A0 decision 3)
# ========================================================================
# The four TB6612 direction pins live here so the ESP32's 18 perimeter pads can
# carry everything else once the rear cluster was deleted (F1).  Full PER-CHANNEL
# control is preserved, including COAST (IN1=IN2=L) — which a dual-inverter
# scheme cannot reach, because IN1==IN2 is unreachable by construction and STBY
# is chip-wide.  PWM stays on hardware GPIO so PWM=0 → short brake works even if
# the bus wedges, and /ESTOP → STBY gives hardware high-Z independently of I²C.
#
# TCA9554A addresses 0x38-0x3F; A0/A1/A2 = GND → 0x38.  No clash with the BMI270
# at 0x68/0x69.  Powers up with all I/O as INPUTS, so R12-R15 hold the driver in
# a defined state until firmware configures it.
U4X, U4Y = 120.0, 145.0


def u4_pin(sx, sy):
    return (round(U4X + sx, 3), round(U4Y - sy, 3))


U4P = {
    "A0": u4_pin(-10.16, -5.08),  # 1
    "A1": u4_pin(-10.16, -7.62),  # 2
    "A2": u4_pin(-10.16, -10.16),  # 3
    "P0": u4_pin(10.16, 7.62),  # 4  -> AIN1
    "P1": u4_pin(10.16, 5.08),  # 5  -> AIN2
    "P2": u4_pin(10.16, 2.54),  # 6  -> BIN1
    "P3": u4_pin(10.16, 0.0),  # 7  -> BIN2
    "GND": u4_pin(0.0, -15.24),  # 8
    "P4": u4_pin(10.16, -2.54),  # 9
    "P5": u4_pin(10.16, -5.08),  # 10
    "P6": u4_pin(10.16, -7.62),  # 11
    "P7": u4_pin(10.16, -10.16),  # 12
    "INT": u4_pin(-10.16, 2.54),  # 13
    "SCL": u4_pin(-10.16, 7.62),  # 14
    "SDA": u4_pin(-10.16, 5.08),  # 15
    "VDD": u4_pin(0.0, 12.7),  # 16
}

s.schematicSymbols.append(
    make_sym(
        "Interface_Expansion",
        "TCA9554PW",
        U4X,
        U4Y,
        "U4",
        "TCA9554APWR",
        "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        "I2C GPIO expander for TB6612 direction pins. LCSC C2863976, addr 0x38.",
    )
)
s.schematicSymbols.append(make_pwr("+3V3", *U4P["VDD"]))
s.schematicSymbols.append(make_pwr("GND", *U4P["GND"]))
for _a in ("A0", "A1", "A2"):
    s.schematicSymbols.append(make_pwr("GND", *U4P[_a]))

lbl.append(make_label("SCL", *U4P["SCL"], 180))
lbl.append(make_label("SDA", *U4P["SDA"], 180))
lbl.append(make_label("AIN1", *U4P["P0"], 0))
lbl.append(make_label("AIN2", *U4P["P1"], 0))
lbl.append(make_label("BIN1", *U4P["P2"], 0))
lbl.append(make_label("BIN2", *U4P["P3"], 0))
for _p in ("P4", "P5", "P6", "P7", "INT"):
    s.noConnects.append(make_nc(*U4P[_p]))

# ── R12-R15: 100k pulldowns on the direction lines ───────────────────────
# TCA9554A powers up with P0-P3 as high-impedance inputs, so without these the
# TB6612 direction inputs float from power-on until firmware configures U4.
for _i, (_ref, _net) in enumerate(
    [("R12", "AIN1"), ("R13", "AIN2"), ("R14", "BIN1"), ("R15", "BIN2")]
):
    _x, _y = 145.0 + _i * 10.0, 145.0
    s.schematicSymbols.append(
        make_sym(
            "Device",
            "R",
            _x,
            _y,
            _ref,
            "100k",
            "Resistor_SMD:R_0402_1005Metric",
            f"{_net} boot-safety pulldown (U4 powers up as inputs)",
        )
    )
    s.schematicSymbols.append(make_pwr("GND", _x, _y + 3.81))
    lbl.append(make_label(_net, _x, _y - 3.81, 90))

# ── R16/R17: I²C pull-ups (register X1) ──────────────────────────────────
# BLOCKER without these: U4 is an ON-BOARD I²C device, so the bus must work with
# J5 empty. v1 had no pull-ups at all and relied entirely on the external Qwiic
# breakout's. 4.7k gives ~219ns rise at 55pF; in parallel with a 2.2k Qwiic
# device that is 1.5k → 70ns and 2.2mA sink, inside the 3mA I²C limit.
for _ref, _net, _x in [("R16", "SDA", 95.0), ("R17", "SCL", 105.0)]:
    s.schematicSymbols.append(
        make_sym(
            "Device",
            "R",
            _x,
            145.0,
            _ref,
            "4.7k",
            "Resistor_SMD:R_0402_1005Metric",
            f"I2C {_net} pull-up to +3V3",
        )
    )
    s.schematicSymbols.append(make_pwr("+3V3", _x, 145.0 - 3.81))
    lbl.append(make_label(_net, _x, 145.0 + 3.81, 270))

# R18 10k: pull-DOWN on the e-stop cable-detect loop (register E3).
# The loop is tied to J7 pin 1 (+3V3) at the SWITCH end of the harness, so with the
# cable present it reads high; with the cable gone R18 takes it low. That is what
# separates "pressed" from "cable missing" — both stop the motors, only this tells
# firmware which. Must be a pull-DOWN: absence has to be the low, de-energised state.
R18X, R18Y = 115.0, 145.0
s.schematicSymbols.append(
    make_sym(
        "Device",
        "R",
        R18X,
        R18Y,
        "R18",
        "10k",
        "Resistor_SMD:R_0402_1005Metric",
        "E-stop cable-detect loop pull-down (no cable = low)",
    )
)
s.schematicSymbols.append(make_pwr("GND", R18X, R18Y - 3.81))
lbl.append(make_label("ESTOP_LOOP", R18X, R18Y + 3.81, 270))

# ── C8/C9: U4 decoupling and the +3V3 bulk that v1 lacked (X3) ───────────
for _ref, _val, _x, _desc in [
    ("C8", "100n", 95.0, "U4 TCA9554A supply decoupling"),
    ("C9", "10u", 105.0, "+3V3 bulk — rail is module-LDO derived and leaves over J5"),
]:
    s.schematicSymbols.append(
        make_sym(
            "Device",
            "C",
            _x,
            165.0,
            _ref,
            _val,
            "Capacitor_SMD:C_0402_1005Metric",
            _desc,
        )
    )
    s.schematicSymbols.append(make_pwr("+3V3", _x, 165.0 - 3.81))
    s.schematicSymbols.append(make_pwr("GND", _x, 165.0 + 3.81))

# ========================================================================
# NO-CONNECTS on unused ESP32 pins
# ========================================================================
# The rear cluster is GONE in v2 (F1: its geometry was fabricated, and A0 removed
# every signal that used it). Symbol pins 10-17 have no pad on the _NoCluster
# footprint, so they are all no-connect.
#
# Pad 9 (GPIO6) was one of the two A0c spares; E3 spends it on ESTOP_LOOP, the
# e-stop cable-detect input. Pad 4 (GPIO1, ADC1_CH0) remains the only spare — and
# it is the ADC-capable one, which is the better of the two to keep.
lbl.append(make_label("ESTOP_LOOP", *U1L["9"], 0))
s.noConnects.append(make_nc(*U1L["4"]))

# Right side: GPIO16(27), GPIO15(28), GPIO14(29) are NOT accessible on flat-mount module

# ========================================================================
# WRITE SCHEMATIC
# ========================================================================
s.to_file(SCH)
print(f"Schematic written: {SCH}")
print(f"Components: {len(s.schematicSymbols)} symbols")
print(f"Labels: {len(s.labels)}")
print(f"No-connects: {len(s.noConnects)}")
