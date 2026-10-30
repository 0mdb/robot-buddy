#!/usr/bin/env python3
"""Chassis geometry for robot-buddy, driven into SOLIDWORKS by tools/swbuild.cs.

Python owns the numbers (from docs/cad/06_frame_design_spec.md and
07_materials_fasteners_fea.md); swbuild.cs owns SOLIDWORKS. Every part gets an
`expect` line computed here, independently of SOLIDWORKS, and the build fails
if the solid doesn't match.

    python3 tools/chassis.py rebuild      # plate + motor envelope + chassis assembly
    python3 tools/chassis.py rebuild -n   # write the manifest only

Chassis frame (CLAUDE.md): origin at the base-plate top-face centre, +X forward,
+Y left, +Z up. All lengths in mm. Values marked TBD come from parts not yet
measured (06 §9) and are flagged in the specs.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sw  # noqa: E402  (staging/winpath/sync helpers)

# ---------------------------------------------------------------- plate (06 §1, §4)
PLATE_L, PLATE_W, PLATE_T = 170.0, 110.0, 4.0
FRONT_CHAMFER = 20.0  # 45° corner chamfers at +X, kept from Ben's bottom_plate
REAR_RADIUS = 20.0  # corner radii at -X, kept from Ben's bottom_plate

# --------------------------------------------- TT motor (Yahboom product drawing)
# Motor frame: origin at the midpoint of the two Ø3.2 mounting holes on the
# gearbox face that bears on the bracket. +X toward the gearbox (shaft) end,
# +Y along the shaft (away from the bracket), +Z across the 17.5 hole pair.
MOT_HOLE_PITCH = 17.5
MOT_HOLE_D = 3.2
MOT_SHAFT_X = 19.8  # hole line -> output shaft, along the body
MOT_SHAFT_D = 5.4
MOT_SHAFT_LEN = 10.0  # TBD: protrusion past the gearbox face
MOT_GEAR_END = 32.1  # hole line -> gearbox end (75 overall)
MOT_CAN_END = -42.9  # hole line -> encoder end
MOT_GEAR_START = 29.0 - 42.9  # drawing "29": encoder end -> gearbox start
MOT_THICK = 22.6  # TBD: gearbox thickness along the shaft
MOT_GEAR_W = 22.0  # TBD: gearbox width across the holes
MOT_CAN_W = 19.2  # can width (drawing)
MOT_ENC_LEN = 13.3  # encoder housing along the body (drawing)
MOT_ENC_T = 26.0  # encoder housing along the shaft axis (drawing "26")
MOT_ENC_W = (
    25.0  # encoder housing across (drawing "25"); TBD which way the 8.7 lug points
)

# --------------------------------------------------------- motor mount (measured)
# TT_Motor_Mount_L.SLDPRT in its own frame (read 2026-10-30): foot Z 0..3, upright
# wall Y -31..-28, motor holes along Y at X 14.5, Z 2.5 and 20.5 (18 apart).
MOUNT_HOLE = (14.5, -28.0, 11.5)  # hole-pair midpoint on the motor-side face
MOUNT_FOOT_Y = (-47.0, -8.9)  # foot extent across the upright

# Placement. The motor sits on the upright's +Y side with the shaft pointing +Y
# (outboard) and the gearbox end toward the part's -X (stopped by the gusset at
# X -20..-17), so the can runs aft. Shaft at part X = 14.5 - 19.8 = -5.3.
# TT_Motor_Mount_L therefore fits the RIGHT side (rotated 180° about Z), and its
# mirror fits the LEFT. The shaft's fore-aft station is held back until the
# whole foot clears the front chamfer (TBD: review with Ben, 06 §7).
MOTOR_FACE_Y = PLATE_W / 2  # gearbox outer face (shaft side) flush with the plate edge


# Foot outline corners that face forward/outboard, part frame (the foot has its
# own corner chamfer from (-30.4, -18.7) to (-19.9, -8.9)).
FOOT_FRONT_CORNERS = [(-30.4, -47.0), (-30.4, -18.7), (-19.9, -8.9)]
CHAMFER_MARGIN = 0.5


def mount_ty() -> float:
    # Right side: chassis y = -(part y) - ty. The motor's outer (shaft) face is at
    # part y = -28 + MOT_THICK; put it on the plate edge, y = -PLATE_W/2.
    return MOTOR_FACE_Y - (MOUNT_HOLE[1] + MOT_THICK)


def mount_tx() -> float:
    # Right side: chassis x = -(part x) + tx. Every foot corner must stay inside
    # the front chamfer line x + |y| <= PLATE_L/2 + PLATE_W/2 - FRONT_CHAMFER.
    ty = mount_ty()
    lim = PLATE_L / 2 + PLATE_W / 2 - FRONT_CHAMFER - CHAMFER_MARGIN
    return min(lim - abs(-py - ty) + px for px, py in FOOT_FRONT_CORNERS)


# ------------------------------------------------------------------- helpers
def plate_profile() -> str:
    hx, hy, c, r = PLATE_L / 2, PLATE_W / 2, FRONT_CHAMFER, REAR_RADIUS
    return " ".join(
        [
            f"M {hx} {-(hy - c)}",
            f"L {hx} {hy - c}",
            f"L {hx - c} {hy}",
            f"L {-(hx - r)} {hy}",
            f"A {-(hx - r)} {hy - r} {-hx} {hy - r}",
            f"L {-hx} {-(hy - r)}",
            f"A {-(hx - r)} {-(hy - r)} {-(hx - r)} {-hy}",
            f"L {hx - c} {-hy}",
        ]
    )


def plate_volume() -> float:
    a = (
        PLATE_L * PLATE_W
        - 2 * (FRONT_CHAMFER**2 / 2)
        - 2 * (REAR_RADIUS**2 * (1 - math.pi / 4))
    )
    return a * PLATE_T


def motor_ops() -> tuple[list[str], float]:
    """Motor envelope as Z-extruded boxes plus the shaft and hole cuts.

    The engine extrudes boxes along Z only, so the motor is modelled with its
    own Z axis as the extrude axis: box|x0 x1|y0 y1|z0 z1.
    """
    gw, cw, ew = MOT_GEAR_W / 2, MOT_CAN_W / 2, MOT_ENC_W / 2
    g0, e1 = MOT_GEAR_START, MOT_CAN_END + MOT_ENC_LEN
    ey0 = (MOT_THICK - MOT_ENC_T) / 2
    ops = [
        f"box|{g0} {MOT_GEAR_END}|0 {MOT_THICK}|{-gw} {gw}",  # gearbox
        f"box|{e1} {g0}|1.7 {MOT_THICK - 1.7}|{-cw} {cw}",  # can
        f"box|{MOT_CAN_END} {e1}|{ey0} {ey0 + MOT_ENC_T}|{-ew} {ew}",  # encoder
        f"cyl|y|{MOT_SHAFT_X} 0|{MOT_THICK} {MOT_THICK + MOT_SHAFT_LEN}|{MOT_SHAFT_D / 2}|boss",
        f"cyl|y|0 {MOT_HOLE_PITCH / 2}|all|{MOT_HOLE_D / 2}|cut",
        f"cyl|y|0 {-MOT_HOLE_PITCH / 2}|all|{MOT_HOLE_D / 2}|cut",
    ]
    v_gear = (MOT_GEAR_END - g0) * MOT_THICK * MOT_GEAR_W
    v_can = (g0 - e1) * (MOT_THICK - 3.4) * MOT_CAN_W
    v_enc = MOT_ENC_LEN * MOT_ENC_T * MOT_ENC_W
    v_shaft = math.pi * (MOT_SHAFT_D / 2) ** 2 * MOT_SHAFT_LEN
    v_holes = (
        2 * math.pi * (MOT_HOLE_D / 2) ** 2 * MOT_THICK
    )  # both holes lie in the gearbox
    return ops, v_gear + v_can + v_enc + v_shaft - v_holes


def row(r: list[float], t: tuple[float, float, float]) -> str:
    return " ".join(f"{v:g}" for v in [*r, *t])


ROT_I = [1, 0, 0, 0, 1, 0, 0, 0, 1]
ROT_Z180 = [-1, 0, 0, 0, -1, 0, 0, 0, 1]
ROT_Y180 = [-1, 0, 0, 0, 1, 0, 0, 0, -1]
ROT_X180 = [1, 0, 0, 0, -1, 0, 0, 0, -1]


# ------------------------------------------------- envelopes (06 §9, 07 §4.5)
# Pi stack, measured by Ben 2026-10-30: 6 mm brass standoffs -> Freenove M.2 NVMe
# adapter -> Pi 5 -> UPS HAT (B). 53 mm adapter bottom -> HAT top. Frame: origin at
# the centre of the Pi's 58 x 49 hole pattern, Z = 0 at the standoff feet, +X toward
# the USB/Ethernet end. The Pi's holes sit 3.5 in from the board's left edge, so the
# 85 x 56 board spans X -32.5 .. 52.5; ports stand 2 proud. TBD: HAT/adapter overhang.
PI_HOLES = (29.0, 24.5)
PI_STANDOFF_H, PI_STANDOFF_D = 6.0, 5.0
PI_STACK_H = 53.0
PI_BOX_X = (-32.5, 54.5)
PI_BOX_Y = (-28.0, 28.0)

# Face board FNK0104 = QDtech ES3C28P drawing (V1.0, 2025-06-11), PCB 50 x 86 confirmed.
# Frame: origin at the PCB centre on its BACK component plane, +Y toward the MIC end,
# +Z toward the viewer. Back parts 4.7 max, PCB 1.6, LCD/touch stack 4.3 (10.6 total).
FACE_W, FACE_H, FACE_R = 50.0, 86.0, 3.5
FACE_HOLES = (21.0, 39.0)
FACE_HOLE_D, FACE_PAD_D = 3.2, 5.6
FACE_BACK, FACE_PCB, FACE_FRONT = 4.7, 1.6, 4.3
FACE_LCD_H, FACE_LCD_TOP = (
    69.2,
    8.22,
)  # backlight/touch outline, offset from the MIC end

# Reflex board (KiCad hardware/kicad/robot-buddy-reflex): 65 x 60, M3 holes at
# (4,11) (55,11) (4,56) (55,56). Frame: origin at the hole-pattern centre on the
# PCB's bottom face, KiCad Y flipped. TBD: component heights (12 top, 2 bottom).
REFLEX_X = (-29.5, 35.5)
REFLEX_Y = (-26.5, 33.5)
REFLEX_HOLES = (25.5, 22.5)
REFLEX_Z = (-2.0, 13.6)


def rounded_rect(w: float, h: float, r: float) -> str:
    x, y = w / 2, h / 2
    return " ".join(
        [
            f"M {x} {-(y - r)}",
            f"L {x} {y - r}",
            f"A {x - r} {y - r} {x - r} {y}",
            f"L {-(x - r)} {y}",
            f"A {-(x - r)} {y - r} {-x} {y - r}",
            f"L {-x} {-(y - r)}",
            f"A {-(x - r)} {-(y - r)} {-(x - r)} {-y}",
            f"L {x - r} {-y}",
            f"A {x - r} {-(y - r)} {x} {-(y - r)}",
        ]
    )


def corners(hx: float, hy: float) -> list[tuple[float, float]]:
    return [(sx * hx, sy * hy) for sx in (-1, 1) for sy in (-1, 1)]


def pi_ops() -> tuple[list[str], float]:
    ops = [
        f"cyl|z|{x} {y}|0 {PI_STANDOFF_H}|{PI_STANDOFF_D / 2}|boss"
        for x, y in corners(*PI_HOLES)
    ]
    ops.append(
        f"box|{PI_BOX_X[0]} {PI_BOX_X[1]}|{PI_BOX_Y[0]} {PI_BOX_Y[1]}|"
        f"{PI_STANDOFF_H} {PI_STANDOFF_H + PI_STACK_H}"
    )
    vol = 4 * math.pi * (PI_STANDOFF_D / 2) ** 2 * PI_STANDOFF_H + (
        (PI_BOX_X[1] - PI_BOX_X[0]) * (PI_BOX_Y[1] - PI_BOX_Y[0]) * PI_STACK_H
    )
    return ops, vol


def face_ops() -> tuple[list[str], float]:
    z_pcb = FACE_BACK + FACE_PCB
    lcd_top = FACE_H / 2 - FACE_LCD_TOP
    ops = [f"prof|0 {z_pcb}|{rounded_rect(FACE_W, FACE_H, FACE_R)}"]
    # standoff landing pads: clear the back-component zone around each hole
    ops += [
        f"cyl|z|{x} {y}|0 {FACE_BACK}|{FACE_PAD_D / 2}|cut"
        for x, y in corners(*FACE_HOLES)
    ]
    ops += [f"cyl|z|{x} {y}|all|{FACE_HOLE_D / 2}|cut" for x, y in corners(*FACE_HOLES)]
    ops.append(
        f"box|{-FACE_W / 2} {FACE_W / 2}|{lcd_top - FACE_LCD_H} {lcd_top}|"
        f"{z_pcb} {z_pcb + FACE_FRONT}"
    )
    area = FACE_W * FACE_H - (4 - math.pi) * FACE_R**2
    vol = (
        area * z_pcb
        - 4 * math.pi * (FACE_PAD_D / 2) ** 2 * FACE_BACK
        - 4 * math.pi * (FACE_HOLE_D / 2) ** 2 * FACE_PCB
        + FACE_W * FACE_LCD_H * FACE_FRONT
    )
    return ops, vol


def reflex_ops() -> tuple[list[str], float]:
    ops = [
        f"box|{REFLEX_X[0]} {REFLEX_X[1]}|{REFLEX_Y[0]} {REFLEX_Y[1]}|{REFLEX_Z[0]} {REFLEX_Z[1]}"
    ]
    ops += [f"cyl|z|{x} {y}|all|1.6|cut" for x, y in corners(*REFLEX_HOLES)]
    h = REFLEX_Z[1] - REFLEX_Z[0]
    vol = (REFLEX_X[1] - REFLEX_X[0]) * (
        REFLEX_Y[1] - REFLEX_Y[0]
    ) * h - 4 * math.pi * 1.6**2 * h
    return ops, vol


def matmul(a: list[float], b: list[float]) -> list[float]:
    return [
        sum(a[i * 3 + k] * b[k * 3 + j] for k in range(3))
        for i in range(3)
        for j in range(3)
    ]


def rot_y(deg: float) -> list[float]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [c, 0, s, 0, 1, 0, -s, 0, c]


# Provisional placements (06 §3 height table; TBD until the plate layout is set):
PI_AT = (
    -10.0,
    0.0,
    27.0,
)  # pattern centre over the plate, standoff feet on the deck top
REFLEX_AT = (
    -44.5,
    -3.5,
    5.0,
)  # aft of the motor cans, 0.7 clear of the encoders' |y| 30.7
FACE_AT = (72.0, 0.0, 68.0)  # on the bulkhead, screen facing +X, tilted 15° back
FACE_TILT = 15.0
# board X (short side) -> chassis Z, board Y (MIC end) -> chassis -Y, board Z (screen) -> chassis X
FACE_BASE = [0, 0, 1, 0, -1, 0, 1, 0, 0]


def rebuild_manifest(win: str) -> list[str]:
    cad = win + r"\CAD"
    plate = cad + r"\parts\RB-PRT-001_base_plate.SLDPRT"
    motor = cad + r"\library\TT_Motor_envelope_v2.SLDPRT"
    pi = cad + r"\library\Pi5_stack_envelope.SLDPRT"
    face = cad + r"\library\FNK0104_face_envelope.SLDPRT"
    reflex = cad + r"\library\reflex_board_envelope.SLDPRT"
    mount_r = cad + r"\parts\TT_Motor_Mount_L.SLDPRT"  # fits the right side
    mount_l = cad + r"\parts\MirrorTT_Motor_Mount_L.SLDPRT"  # fits the left side
    asm = cad + r"\assemblies\RB-ASM-101_chassis.SLDASM"
    shots = win + r"\shots\rebuild"

    hx, hy = PLATE_L / 2, PLATE_W / 2
    m_ops, m_vol = motor_ops()
    tx, ty = mount_tx(), mount_ty()
    hxm, hym, hzm = MOUNT_HOLE

    # Motor frame -> mount part frame: (hxm - X, hym + Y, hzm - Z), i.e. the
    # gearbox toward the part's -X, shaft along the part's +Y.
    # Right: mount Rz180 + (tx, -ty, 0) -> chassis (X + tx - hxm, -Y - hym - ty, hzm - Z)
    #        = Rx180 + (tx - hxm, -hym - ty, hzm).
    mot_r_t = (tx - hxm, -hym - ty, hzm)
    # Left: mirror part with Ry180 + (tx, ty, 0) is an X-mirror of the L frame ->
    #       chassis (X + tx - hxm, Y + hym + ty, hzm - Z). That is a reflection; the
    #       motor envelope is symmetric in its Z, so place it at identity instead.
    mot_l_t = (tx - hxm, hym + ty, hzm)

    lines = [
        "# generated by tools/chassis.py rebuild -- do not edit",
        f"part|{plate}",
        f"prof|{-PLATE_T} 0|{plate_profile()}",
        f"expect|vol {plate_volume():.1f} 1.0|box {-hx} {hx} {-hy} {hy} {-PLATE_T} 0 0.01",
        "save",
        f"part|{motor}",
        *m_ops,
        f"expect|vol {m_vol:.1f} 5.0|box {MOT_CAN_END} {MOT_GEAR_END} {(MOT_THICK - MOT_ENC_T) / 2} "
        f"{MOT_THICK + MOT_SHAFT_LEN} {-MOT_ENC_W / 2} {MOT_ENC_W / 2} 0.05",
        "save",
        *envelope_lines(pi, face, reflex),
        f"asm|{asm}",
        f"comp|plate|{plate}|{row(ROT_I, (0, 0, 0))}|fix",
        f"comp|mount_R|{mount_r}|{row(ROT_Z180, (tx, -ty, 0))}",
        f"comp|mount_L|{mount_l}|{row(ROT_Y180, (tx, ty, 0))}",
        f"comp|motor_R|{motor}|{row(ROT_X180, mot_r_t)}",
        f"comp|motor_L|{motor}|{row(ROT_I, mot_l_t)}",
        f"comp|pi_stack|{pi}|{row(ROT_Z180, PI_AT)}",
        f"comp|reflex|{reflex}|{row(ROT_I, REFLEX_AT)}",
        f"comp|face|{face}|{row(matmul(rot_y(-FACE_TILT), FACE_BASE), FACE_AT)}",
        "interfere",
        "asmsave",
        f"shot|{asm}|{shots}",
        f"close|{asm}",
    ]
    return lines


def envelope_lines(pi: str, face: str, reflex: str) -> list[str]:
    p_ops, p_vol = pi_ops()
    f_ops, f_vol = face_ops()
    r_ops, r_vol = reflex_ops()
    top = PI_STANDOFF_H + PI_STACK_H
    fz = FACE_BACK + FACE_PCB + FACE_FRONT
    return [
        f"part|{pi}",
        *p_ops,
        f"expect|vol {p_vol:.1f} 2.0|box {PI_BOX_X[0]} {PI_BOX_X[1]} {PI_BOX_Y[0]} {PI_BOX_Y[1]} 0 {top} 0.01",
        "save",
        f"part|{face}",
        *f_ops,
        f"expect|vol {f_vol:.1f} 2.0|box {-FACE_W / 2} {FACE_W / 2} {-FACE_H / 2} {FACE_H / 2} 0 {fz} 0.01",
        "save",
        f"part|{reflex}",
        *r_ops,
        f"expect|vol {r_vol:.1f} 2.0|box {REFLEX_X[0]} {REFLEX_X[1]} {REFLEX_Y[0]} {REFLEX_Y[1]} "
        f"{REFLEX_Z[0]} {REFLEX_Z[1]} 0.01",
        "save",
    ]


# ------------------------------------------------------------------- runner
def compile_engine(tool: str) -> str:
    shutil.copyfile(
        os.path.join(sw.REPO, "tools", "swbuild.cs"), os.path.join(tool, "swbuild.cs")
    )
    for dll in sw.DLLS:
        if not os.path.exists(os.path.join(tool, dll)):
            shutil.copyfile(os.path.join(sw.SWAPI, dll), os.path.join(tool, dll))
    w = sw.winpath(tool)
    refs = " ".join(f'/reference:"{w}\\{d}"' for d in sw.DLLS)
    bat = os.path.join(tool, "build_swbuild.bat")
    with open(bat, "w", newline="") as fh:
        fh.write(
            f'@echo off\r\n"{sw.CSC}" /nologo /target:exe /platform:x64 '
            f'/out:"{w}\\swbuild.exe" {refs} "{w}\\swbuild.cs"\r\n'
        )
    r = subprocess.run(
        ["cmd.exe", "/c", sw.winpath(bat)], capture_output=True, text=True, cwd="/mnt/c"
    )
    if r.returncode or "error CS" in r.stdout:
        sys.exit(r.stdout.replace("\r", "") + "csc failed")
    return w + "\\swbuild.exe"


def run(lines: list[str], dry: bool) -> None:
    stage = sw.staging()
    tool = os.path.join(stage, "tools")
    os.makedirs(tool, exist_ok=True)
    os.makedirs(os.path.join(stage, "shots"), exist_ok=True)
    man = os.path.join(tool, "chassis_manifest.txt")
    with open(man, "w", newline="") as fh:
        fh.write("\r\n".join(lines) + "\r\n")
    print(f"manifest: {man} ({len(lines)} lines)")
    if dry:
        print("\n".join(lines))
        return
    exe = compile_engine(tool)
    r = subprocess.run(
        ["cmd.exe", "/c", exe, sw.winpath(man)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd="/mnt/c",
    )
    out = r.stdout.replace("\r", "")
    print(out, end="")
    # cmd.exe swallows .NET exit codes through WSL interop -- trust the last line
    if "BUILD OK" not in out:
        sys.exit("swbuild did not report BUILD OK")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("what", choices=["rebuild"])
    ap.add_argument("-n", "--dry-run", action="store_true")
    a = ap.parse_args()
    win = sw.winpath(sw.staging())
    if a.what == "rebuild":
        run(rebuild_manifest(win), a.dry_run)


if __name__ == "__main__":
    main()
