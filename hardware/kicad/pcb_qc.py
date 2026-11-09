#!/usr/bin/env python3
"""Pre-order QC for robot-buddy-reflex. Run after make_fab.py; exits 1 on any FAIL.

    python3 hardware/kicad/make_fab.py && python3 hardware/kicad/pcb_qc.py

v2 (2026-11-09): expander board (A0), +5V only (A3), no NeoPixels/LED, NoCluster U1,
52.5 x 46 outline (board_outline.py). fab_export.py was cad-loop's v1 exporter; for v2
the fab package comes from make_fab.py (gates + gerbers + JLC BOM/CPL).

Written 2026-11-09 after the first order's footprint/pinout and silk/mask problems. Each
check names its reference; anything a script can't prove is listed under SIGN-OFF for a
person to tick before ordering (eyes before electrons).

  1 ERC / DRC / schematic parity        kicad-cli, zero errors and zero unconnected
  2 U2 TB6612 pinout                    vs SparkFun's own board file (docs/ref/*.brd)
  3 U1 ESP32-S3-Zero pads + GPIOs       vs Waveshare pinout + firmware pin_map.h
  4 Connector / IC pin tables           vs the device standards (Qwiic, HC-SR04, 74xG125)
  5 Mechanics                           outline, notches, M3 pattern, USB-C on the rear edge
  6 Fab package                         files present, PTH/NPTH split, fresh vs the board,
                                        copper/mask/drill inside the outline
  7 Renders                             top/bottom 3D + per-layer gerber sheet for review
"""

import json
import math
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import board_outline as BO  # noqa: E402

PROJ = HERE / "robot-buddy-reflex"
PCB = PROJ / "robot-buddy-reflex.kicad_pcb"
SCH = PROJ / "robot-buddy-reflex.kicad_sch"
GERB = PROJ / "gerbers"
ZIP = GERB / "robot-buddy-reflex-gerbers.zip"
QCDIR = PROJ / "qc"  # NOT under gerbers/: that directory is what goes to the fab
PIN_MAP = ROOT / "esp32-reflex/main/pin_map.h"
SPARKFUN_BRD = ROOT / "docs/ref/SparkFun_Motor_Driver-TB6612FNG_v11c.brd"
ESP_STEP = next((ROOT / "docs/ref").glob("ESP32-S3-Zero_v2-*.stp"), None)

results: list[tuple[str, str, str]] = []  # (status, section, message)
SIGNOFF: list[str] = []


def check(ok: bool, section: str, msg: str, warn: bool = False) -> bool:
    results.append(("PASS" if ok else ("WARN" if warn else "FAIL"), section, msg))
    return ok


def mm(v: int) -> float:
    return round(pcbnew.ToMM(v), 3)


def kicad(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["kicad-cli", *args], capture_output=True, text=True)


TMP = Path(tempfile.mkdtemp(prefix="pcb_qc_"))
board = pcbnew.LoadBoard(str(PCB))
FP = {f.GetReference(): f for f in board.GetFootprints()}


def pad_net(ref: str, num: str) -> str:
    p = FP[ref].FindPadByNumber(num)
    return p.GetNetname() if p else "<no pad>"


# ── 1 ERC / DRC / parity ─────────────────────────────────────────────────────
S = "1 ERC/DRC"
kicad(
    "sch",
    "erc",
    "--format",
    "json",
    "--severity-all",
    "-o",
    str(TMP / "erc.json"),
    str(SCH),
)
erc = json.load(open(TMP / "erc.json"))
erc_err = [
    v for s in erc["sheets"] for v in s["violations"] if v["severity"] == "error"
]
check(not erc_err, S, f"ERC errors: {len(erc_err)}")
for v in erc_err[:10]:
    results.append(("    ", S, v["description"]))

kicad(
    "pcb",
    "drc",
    "--format",
    "json",
    "--severity-all",
    "--schematic-parity",
    "--refill-zones",
    "-o",
    str(TMP / "drc.json"),
    str(PCB),
)
drc = json.load(open(TMP / "drc.json"))
errs = [v for v in drc["violations"] if v["severity"] == "error"]
check(not errs, S, f"DRC errors: {len(errs)}")
for v in errs[:15]:
    results.append(
        ("    ", S, f"{v['type']}: " + " ; ".join(i["description"] for i in v["items"]))
    )
check(
    not drc["unconnected_items"],
    S,
    f"unconnected items: {len(drc['unconnected_items'])}",
)

# Parity: only these known differences are allowed.
#   MH1-4 have no symbol; U1 symbol pins 27-29 (GPIO14-16) have no pad on the module;
#   J9's value carries ">"/"<" (L3) that parity compares escaped; empty Description fields.
ALLOWED = [
    ("extra_footprint", r"Footprint MH\d"),
    ("extra_footprint", r"Extra footprint"),  # MH1-4 (no symbol), as reported by 10.0.6
    ("net_conflict", r"No pad found for pin (27|28|29) in schematic"),
    ("footprint_symbol_mismatch", r"Value \(J9\)"),
    ("footprint_symbol_field_mismatch", r"."),
]
bad = []
for v in drc["schematic_parity"]:
    text = v["description"] + " " + " ".join(i["description"] for i in v["items"])
    if not any(v["type"] == t and re.search(rx, text) for t, rx in ALLOWED):
        bad.append(f"{v['type']}: {text}")
check(not bad, S, f"schematic parity: {len(bad)} unexpected issue(s)")
for b in bad[:10]:
    results.append(("    ", S, b))

warn_types: dict[str, int] = {}
for v in drc["violations"]:
    if v["severity"] == "warning":
        warn_types[v["type"]] = warn_types.get(v["type"], 0) + 1
check(
    warn_types.get("track_dangling", 0) == 0,
    S,
    f"dangling track stubs: {warn_types.get('track_dangling', 0)}",
    warn=True,
)
results.append(
    (
        "info",
        S,
        "DRC warnings: " + ", ".join(f"{k} {n}" for k, n in sorted(warn_types.items())),
    )
)

# ── 2 U2: SparkFun TB6612FNG breakout ────────────────────────────────────────
S = "2 U2 TB6612"
# SparkFun signal name -> our net. Footprint frame: chip up, top view, KiCad y down.
SF_NET = {
    "VM": "+5V",  # A3: no pack input, VM on the HAT's 5 V
    "VCC": "+3V3",
    "GND": "GND",
    "A01": "/AO1",
    "A02": "/AO2",
    "B01": "/BO1",
    "B02": "/BO2",
    "PWMA": "/PWMA",
    "AIN1": "/AIN1",
    "AIN2": "/AIN2",
    "STBY": "/ESTOP",  # A0: STBY tied to the hardware e-stop net
    "BIN1": "/BIN1",
    "BIN2": "/BIN2",
    "PWMB": "/PWMB",
}
t = ET.parse(SPARKFUN_BRD)
pkg = {p.get("name"): p for p in t.iter("package")}
sig = {
    (c.get("element"), c.get("pad")): s.get("name")
    for s in t.iter("signal")
    for c in s.iter("contactref")
}
sf = {}  # (x, y) in Eagle mm, y up -> signal
for e in t.iter("element"):
    if e.get("name") not in ("JP1", "JP2"):
        continue
    ex, ey, rot = (
        float(e.get("x")),
        float(e.get("y")),
        math.radians(int(e.get("rot", "R0")[1:])),
    )
    for pd in pkg[e.get("package")].iter("pad"):
        x, y = float(pd.get("x")), float(pd.get("y"))
        X = ex + x * math.cos(rot) - y * math.sin(rot)
        Y = ey + x * math.sin(rot) + y * math.cos(rot)
        sf[(round(X, 2), round(Y, 2))] = sig.get((e.get("name"), pd.get("name")))
cx = (min(k[0] for k in sf) + max(k[0] for k in sf)) / 2
cy = (min(k[1] for k in sf) + max(k[1] for k in sf)) / 2
u2 = FP["U2"]
mismatch = []
for p in u2.Pads():
    # pad position in the footprint's own frame (undo placement + rotation)
    d = p.GetPosition() - u2.GetPosition()
    a = math.radians(u2.GetOrientationDegrees())
    lx = pcbnew.ToMM(d.x) * math.cos(a) - pcbnew.ToMM(d.y) * math.sin(a)
    ly = pcbnew.ToMM(d.x) * math.sin(a) + pcbnew.ToMM(d.y) * math.cos(a)
    key = (round(cx + lx, 2), round(cy - ly, 2))  # footprint y down -> Eagle y up
    want = SF_NET.get(sf.get(key, "?"), f"<nothing at {key}>")
    if p.GetNetname() != want:
        mismatch.append(
            f"pad {p.GetNumber()}: board {p.GetNetname()}, SparkFun {sf.get(key)} -> {want}"
        )
check(
    len(sf) == 16 and not mismatch,
    S,
    f"16 pads vs SparkFun .brd (chip up): {len(mismatch)} mismatch(es)",
)
for m in mismatch:
    results.append(("    ", S, m))

# ── 3 U1: Waveshare ESP32-S3-Zero, flat mount ────────────────────────────────
S = "3 U1 ESP32"
# Waveshare pinout, top view, USB-C at the top (the pad-1 end): left column 5V GND 3V3 GP1-6,
# right column TX(43) RX(44) GP13 12 11 10 9 8 7. Footprint frame: corner origin, x right,
# y down. Edge pads x 1.38 / 16.62, y 1.59 + 2.54 n. Cluster pads (module underside) x 4.87 /
# 13.22, y 14.84 + 1.59 n (measured from the STEP's pad cylinders, 2026-06-26).
U1_REF = {
    "1": (1.38, 1.59, "5V"),
    "2": (1.38, 4.13, "GND"),
    "3": (1.38, 6.67, "3V3"),
    **{str(4 + i): (1.38, round(9.21 + 2.54 * i, 2), f"GPIO{1 + i}") for i in range(6)},
    "18": (16.62, 1.59, "GPIO43"),
    "19": (16.62, 4.13, "GPIO44"),
    **{
        str(20 + i): (16.62, round(6.67 + 2.54 * i, 2), f"GPIO{13 - i}")
        for i in range(7)
    },
}
kicad(
    "sch",
    "export",
    "netlist",
    "--format",
    "kicadxml",
    "-o",
    str(TMP / "net.xml"),
    str(SCH),
)
pinfn = {}
for n in ET.parse(TMP / "net.xml").iter("net"):
    for node in n.iter("node"):
        if node.get("ref") == "U1":
            pinfn[node.get("pin")] = (node.get("pinfunction") or "", n.get("name"))
u1 = FP["U1"]
bad_geo, bad_fn = [], []
for num, (x, y, fn) in U1_REF.items():
    p = u1.FindPadByNumber(num)
    if p is None:
        bad_geo.append(f"pad {num} missing")
        continue
    d = p.GetPosition() - u1.GetPosition()
    a = math.radians(u1.GetOrientationDegrees())
    lx = pcbnew.ToMM(d.x) * math.cos(a) - pcbnew.ToMM(d.y) * math.sin(a)
    ly = pcbnew.ToMM(d.x) * math.sin(a) + pcbnew.ToMM(d.y) * math.cos(a)
    if abs(lx - x) > 0.02 or abs(ly - y) > 0.02:
        bad_geo.append(f"pad {num} at ({lx:.2f}, {ly:.2f}), want ({x}, {y})")
    sym = re.sub(r"[~{}]", "", pinfn.get(num, ("", ""))[0])
    if fn not in sym.replace("TX", "").replace("RX", "") and fn != re.sub(
        r"_\d+$", "", sym
    ):
        bad_fn.append(f"pad {num}: symbol '{sym}', Waveshare {fn}")
check(
    not bad_geo,
    S,
    f"18 perimeter pads at the Waveshare/STEP positions (NoCluster): {len(bad_geo)} off",
)
for m in bad_geo:
    results.append(("    ", S, m))
check(
    not bad_fn,
    S,
    f"symbol pin function = Waveshare pad function: {len(bad_fn)} mismatch(es)",
)
for m in bad_fn:
    results.append(("    ", S, m))

# v2: AIN1/AIN2/BIN1/BIN2 live on U4 (TCA9554A P0-P3) and STBY is the /ESTOP net, so
# none of them is a GPIO any more; a PIN_AIN*/PIN_BIN*/PIN_STBY in pin_map.h is a v1
# leftover and fails below (TODO: "Direction-change sequencing - required by the v2 board").
FW_NET = {
    "PIN_PWMA": "/PWMA",
    "PIN_PWMB": "/PWMB",
    "PIN_ENC_L_A": "/ENC_LA",
    "PIN_ENC_L_B": "/ENC_LB",
    "PIN_ENC_R_A": "/ENC_RA",
    "PIN_ENC_R_B": "/ENC_RB",
    "PIN_I2C_SDA": "/SDA",  # shared bus: IMU (via J5) + U4 expander
    "PIN_I2C_SCL": "/SCL",
    "PIN_RANGE_TRIG": "/TRIG",
    "PIN_RANGE_ECHO": "/ECHO_DIV",
    "PIN_ESTOP_N": "/ESTOP",
    "PIN_ESTOP_LOOP": "/ESTOP_LOOP",  # E3 cable detect
}
fw = dict(re.findall(r"(PIN_\w+)\s*=\s*GPIO_NUM_(\d+)", PIN_MAP.read_text()))
gpio_net = {}
for num, (fn, net) in pinfn.items():
    m = re.search(r"GPIO(\d+)", fn)
    if m:
        gpio_net[m.group(1)] = (net, num)
bad = []
for name, net in FW_NET.items():
    g = fw.get(name)
    got = gpio_net.get(g, ("<no pad>", "?"))
    if got[0] != net:
        bad.append(f"{name} = GPIO{g}: board net {got[0]} (pad {got[1]}), want {net}")
for name in ("PIN_AIN1", "PIN_AIN2", "PIN_BIN1", "PIN_BIN2", "PIN_STBY"):
    if name in fw:
        bad.append(
            f"{name} = GPIO{fw[name]}: v2 has no such GPIO (U4 expander / e-stop net)"
        )
# U4 direction bits: pin_map.h EXP_BIT_* vs the netlist (TCA9554A P0..P3 = pins 4..7)
_pm = PIN_MAP.read_text()
_exp = dict(re.findall(r"(EXP_BIT_\w+)\s*=\s*1u\s*<<\s*(\d)", _pm))
for name, net in (
    ("EXP_BIT_AIN1", "/AIN1"),
    ("EXP_BIT_AIN2", "/AIN2"),
    ("EXP_BIT_BIN1", "/BIN1"),
    ("EXP_BIT_BIN2", "/BIN2"),
):
    bit = _exp.get(name)
    got = pad_net("U4", str(4 + int(bit))) if bit is not None else "<missing>"
    if got != net:
        bad.append(f"{name} = P{bit}: U4 pin carries {got}, want {net}")
if not re.search(r"EXP_I2C_ADDR\s*=\s*0x38\b", _pm):
    bad.append("EXP_I2C_ADDR is not 0x38 (TCA9554A, A2..A0 = GND on the board)")
check(
    not bad and len(fw) >= len(FW_NET),
    S,
    f"firmware pin_map.h vs board (GPIOs + U4 bits/address): {len(bad)} mismatch(es)",
)
for m in bad:
    results.append(("    ", S, m))

# ── 4 Connector and IC pin tables ────────────────────────────────────────────
S = "4 pinouts"
PINS = {  # ref: [net per pad 1..n], reference
    "J5": (["GND", "+3V3", "/SDA", "/SCL"], "Qwiic standard: GND 3V3 SDA SCL"),
    "J6": (["+5V", "/TRIG", "/ECHO_IN", "GND"], "HC-SR04 header: VCC Trig Echo GND"),
    "J1": (
        ["/AO1", "/AO2", "+3V3", "GND", "/ENC_LA", "/ENC_LB"],
        "harness: M+ M- 3V3 GND A B",
    ),
    "J2": (
        ["/BO1", "/BO2", "+3V3", "GND", "/ENC_RA", "/ENC_RB"],
        "harness: M+ M- 3V3 GND A B",
    ),
    "J7": (
        ["+3V3", "/ESTOP", "/ESTOP_LOOP"],
        "E-stop: 3V3, NC contact, cable-detect loop (E3)",
    ),
    "J9": (
        ["+5V", "GND", "/UART_TX", "/UART_RX"],
        "Pi: 5V GND TX RX (cross TX/RX in the harness)",
    ),
    "C3": (["+5V", "GND"], "polarized: pad 1 = +"),
    "C6": (["+5V", "GND"], "polarized: pad 1 = +"),
}
for ref, (nets, note) in PINS.items():
    got = [pad_net(ref, str(i + 1)) for i in range(len(nets))]
    check(
        got == nets, S, f"{ref:4s} {' '.join(n.lstrip('/') for n in got):40s} ({note})"
    )
SIGNOFF.append(
    "J1/J2 motor harness: encoder-motor socket pin order -> XH 6-pin M+ M- 3V3 GND A B"
)

# ── 5 Mechanics ──────────────────────────────────────────────────────────────
S = "5 mechanics"
edges = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
pts = {(mm(d.GetStart().x), mm(d.GetStart().y)) for d in edges}
want = {(float(x), float(y)) for x, y in BO.outline()}
check(
    pts == want and len(edges) == len(want),
    S,
    f"Edge.Cuts = board_outline.py ({BO.W:g} x {BO.H:g})",
)
# Encoder sockets stand to chassis |y| 23.9 (board_outline.py); the board is centred on the
# chassis centreline, so it clears them if it is no wider than 2 x 23 (0.9 mm margin).
check(
    BO.H <= 46.0,
    S,
    f"board {BO.H:g} wide: |y| <= {BO.H / 2:g}, encoder sockets at |y| 23.9",
)
# Encoder plugs: the sockets face inboard, so plug + cable sit over the long edges in
# board x 31..47.8 (board_outline.plug_keepouts, PLUG_DEPTH provisional until measured).
_in_zone = []
for _ref, _f in FP.items():
    _c = _f.GetCourtyard(pcbnew.F_CrtYd)
    if not _c.OutlineCount():
        continue
    _bb = _c.BBox()
    _l, _t, _r, _b = (
        mm(v) for v in (_bb.GetLeft(), _bb.GetTop(), _bb.GetRight(), _bb.GetBottom())
    )
    for _x0, _y0, _x1, _y1 in BO.plug_keepouts():
        if _r > _x0 and _l < _x1 and _b > _y0 and _t < _y1:
            _in_zone.append(_ref)
            break
check(
    not _in_zone,
    S,
    f"encoder plug keep-out (x {BO.SOCKET_X[0]:g}-{BO.SOCKET_X[1]:g}, {BO.PLUG_DEPTH:g} mm inboard of the socket face, "
    f"PLUG_DEPTH provisional) clear: {sorted(_in_zone) or 'yes'}",
)
SIGNOFF.append(
    "Encoder plug + cable depth inboard of the socket face measured and set as board_outline.PLUG_DEPTH"
)
MH = {f"MH{i}": xy for i, xy in enumerate(BO.HOLES, start=1)}
bad = []
for ref, (x, y) in MH.items():
    f = FP.get(ref)
    p = f.Pads()[0] if f else None
    if (
        not p
        or (mm(p.GetPosition().x), mm(p.GetPosition().y)) != (x, y)
        or mm(p.GetDrillSize().x) != 3.2
        or p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH
    ):
        bad.append(ref)
check(
    not bad,
    S,
    f"M3 holes: 3.2 NPTH on the {2 * BO.HOLE_HALF[0]:g} x {2 * BO.HOLE_HALF[1]:g} pattern (board_outline.HOLES = chassis.py REFLEX_HOLES) {bad or ''}",
)
# USB-C: footprint pad-1 end; at angle 90 it faces -x (the rear edge, chassis x -40).
ang = u1.GetOrientationDegrees() % 360
ux = mm(u1.GetPosition().x)
check(
    abs(ang - 90) < 0.1 and abs(ux) <= 0.3,
    S,
    f"U1 USB-C on the rear edge (R2c): angle {ang:g}, module end x {ux:g}",
)
uy0, uy1 = mm(u1.GetPosition().y) - 18, mm(u1.GetPosition().y)
usb_y = ((uy0 + uy1) / 2 - 6.5, (uy0 + uy1) / 2 + 6.5)  # plug overmold ~12.4 wide
block = []
for ref, f in FP.items():
    if ref == "U1":
        continue
    c = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if (
        mm(c.GetLeft()) < 3
        and mm(c.GetBottom()) > usb_y[0]
        and mm(c.GetTop()) < usb_y[1]
    ):
        block.append(ref)
check(
    not block,
    S,
    f"nothing in the plug's path at the rear edge (y {usb_y[0]:.1f}-{usb_y[1]:.1f}) {block or ''}",
)
SIGNOFF.append(
    "Heights under the Pi deck (12 mm parts budget, chassis.py REFLEX_Z): C3 1000 uF "
    "must be 10 x 12.5 or shorter; U2 on female headers ~11 mm"
)
SIGNOFF.append(
    "USB-C plug for the Pi link fits the rear bay (7 mm to the carriages): right-angle plug or adapter"
)

# ── 6 Fab package ────────────────────────────────────────────────────────────
S = "6 fab package"
if not ZIP.exists():
    check(False, S, f"{ZIP.name} missing: run make_fab.py")
else:
    names = set(zipfile.ZipFile(ZIP).namelist())
    need = [  # make_fab.py plots plain .gbr (no Protel extensions)
        "F_Cu.gbr",
        "In1_Cu.gbr",
        "In2_Cu.gbr",
        "B_Cu.gbr",
        "F_Mask.gbr",
        "B_Mask.gbr",
        "F_Silkscreen.gbr",
        "B_Silkscreen.gbr",
        "Edge_Cuts.gbr",
        "-PTH.drl",
        "-NPTH.drl",
        "-job.gbrjob",
    ]
    miss = [n for n in need if not any(x.endswith(n) for x in names)]
    check(
        not miss,
        S,
        f"zip has 4 copper, 2 mask, 2 silk, outline, PTH + NPTH drill, job file {miss or ''}",
    )
    check(
        ZIP.stat().st_mtime >= PCB.stat().st_mtime,
        S,
        "zip is newer than the .kicad_pcb",
    )
    z = zipfile.ZipFile(ZIP)
    job = json.loads(z.read(next(n for n in names if n.endswith(".gbrjob"))))
    gs = job["GeneralSpecs"]
    check(
        gs["LayerNumber"] == 4 and abs(gs["BoardThickness"] - 1.6) < 1e-6,
        S,
        f"job: {gs['LayerNumber']} layers, {gs['BoardThickness']} mm, {gs['Size']['X']} x {gs['Size']['Y']}",
    )

    # NPTH file holds exactly the four 3.2 M3 holes; PTH holds none of them
    def tools(name: str) -> dict[str, float]:
        txt = z.read(next(n for n in names if n.endswith(name))).decode()
        return {
            m.group(1): float(m.group(2))
            for m in re.finditer(r"^T(\d+)C([\d.]+)", txt, re.M)
        }, txt

    nt, ntxt = tools("-NPTH.drl")
    pt, _ = tools("-PTH.drl")
    n_holes = len(re.findall(r"^X[-\d.]+Y[-\d.]+", ntxt, re.M))
    check(
        list(nt.values()) == [3.2] and n_holes == 4 and 3.2 not in pt.values(),
        S,
        f"NPTH: {n_holes} x {list(nt.values())} mm; PTH tools {sorted(set(pt.values()))}",
    )
    check(
        min(pt.values()) >= 0.3,
        S,
        f"smallest plated drill {min(pt.values())} mm (fab min 0.2-0.3)",
    )
    # staleness: copper/mask/outline in the zip == a fresh export of the board
    fresh = TMP / "fresh"
    fresh.mkdir()
    kicad(
        "pcb",
        "export",
        "gerbers",
        "--no-protel-ext",  # same names as make_fab.py
        "--layers",
        "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,Edge.Cuts",
        "-o",
        f"{fresh}/",
        str(PCB),
    )
    strip = re.compile(r"^(G04|%TF\.CreationDate|%TF\.GenerationSoftware).*$", re.M)
    stale = []
    for f in fresh.iterdir():
        if (
            f.suffix == ".gbrjob"
        ):  # JSON with a creation date; layer files carry the content
            continue
        zn = next((n for n in names if n.endswith(f.name)), None)
        if zn and strip.sub("", z.read(zn).decode()) != strip.sub("", f.read_text()):
            stale.append(f.name)
    check(not stale, S, f"gerbers match the current board {stale or ''}")
    # extents vs outline, independent reader (gerbonara via uv)
    gchk = subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "-q",
            "--with",
            "gerbonara==1.5.0",
            "python",
            "-I",
            str(HERE / "gerber_check.py"),
            str(ZIP),
            str(QCDIR),
            str(BO.W),
            str(BO.H),
        ],
        capture_output=True,
        text=True,
    )
    out = gchk.stdout.strip().splitlines()
    for line in out:
        st, _, msg = line.partition(" ")
        results.append((st if st in ("PASS", "FAIL", "WARN") else "info", S, msg))
    if gchk.returncode not in (0, 1) or not out or "Traceback" in gchk.stderr:
        check(False, S, f"gerber_check.py crashed: {gchk.stderr.strip()[-300:]}")

# ── 7 Renders for review ─────────────────────────────────────────────────────
S = "7 renders"
QCDIR.mkdir(parents=True, exist_ok=True)
for side in ("top", "bottom"):
    r = kicad(
        "pcb",
        "render",
        "--side",
        side,
        "--width",
        "1600",
        "--height",
        "1500",
        "--quality",
        "high",
        "-o",
        str(QCDIR / f"render_{side}.png"),
        str(PCB),
    )
    check(r.returncode == 0, S, f"render_{side}.png", warn=True)
SIGNOFF.append(f"Ben has looked at {QCDIR.relative_to(ROOT)}/ (renders + layer sheet)")

# ── Report ───────────────────────────────────────────────────────────────────
print(f"robot-buddy-reflex pre-order QC  ({PCB.relative_to(ROOT)})\n")
section = None
for st, sec, msg in results:
    if sec != section:
        print(f"\n[{sec}]")
        section = sec
    print(f"  {st:4s}  {msg}")
fails = sum(1 for r in results if r[0] == "FAIL")
warns = sum(1 for r in results if r[0] == "WARN")
print("\nSIGN-OFF (a person, before ordering):")
for s in SIGNOFF:
    print(f"  [ ] {s}")
print(f"\n{'FAIL' if fails else 'PASS'}: {fails} fail, {warns} warn")
sys.exit(1 if fails else 0)
