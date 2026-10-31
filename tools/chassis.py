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
import drivetrain as dt  # noqa: E402  (08: the TPU track system's numbers and wheel geometry)
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
MOT_SHAFT_FLAT = (
    3.7  # double-D across the flats (Yahboom drawing; 08 / drivetrain TT_FLAT)
)
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
MOUNT_HOLE = (14.5, -28.0, 13.5)  # hole-pair midpoint on the motor-side face
# > Amendment (loop P2, 2026-10-30): z 11.5 -> 13.5 and pitch 18 -> 17.5 (the drawing).
# Ben's mount put the motor centre 11.5 up, so its 25 mm encoder and 22 mm gearbox hit
# the plate and foot (323 / 197 mm³); 13.5 clears both and gives the lower insert 2.4 mm
# of wall under it.
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
        *[
            f"prof|-3 3|M {MOT_SHAFT_X + sgn * MOT_SHAFT_FLAT / 2} {MOT_THICK} "
            f"L {MOT_SHAFT_X + sgn * (MOT_SHAFT_D / 2 + 0.5)} {MOT_THICK} "
            f"L {MOT_SHAFT_X + sgn * (MOT_SHAFT_D / 2 + 0.5)} {MOT_THICK + MOT_SHAFT_LEN + 0.1} "
            f"L {MOT_SHAFT_X + sgn * MOT_SHAFT_FLAT / 2} {MOT_THICK + MOT_SHAFT_LEN + 0.1}|cut"
            for sgn in (-1, 1)
        ],
        f"cyl|y|0 {MOT_HOLE_PITCH / 2}|all|{MOT_HOLE_D / 2}|cut",
        f"cyl|y|0 {-MOT_HOLE_PITCH / 2}|all|{MOT_HOLE_D / 2}|cut",
    ]
    v_gear = (MOT_GEAR_END - g0) * MOT_THICK * MOT_GEAR_W
    v_can = (g0 - e1) * (MOT_THICK - 3.4) * MOT_CAN_W
    v_enc = MOT_ENC_LEN * MOT_ENC_T * MOT_ENC_W
    # double-D flats, normal to the motor's X (the sprocket's D-bore flats face the same
    # way): a round envelope here read as a 15.4 mm3 clash with the bore (P11)
    r, f = MOT_SHAFT_D / 2, MOT_SHAFT_FLAT / 2
    seg = r * r * math.acos(f / r) - f * math.sqrt(r * r - f * f)
    v_shaft = math.pi * r * r * MOT_SHAFT_LEN - 2 * seg * MOT_SHAFT_LEN
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


# ------------------------------------------------------ plate features (06 §4)
# Inserts: Ruthex M3 x 5.7 placeholder geometry until the coupon (07 §4.2).
INS_HOLE, INS_DEPTH, INS_BOSS = 4.0, 7.2, 9.2
CLR_M3, CBORE_M3, CBORE_DEPTH = 3.4, 6.5, 2.0
UNDER_BOSS_Z = -8.0  # plate 4 + 4 mm under-boss for the motor-mount inserts (07 F2)
RIB_T, RIB_H = 1.2, 3.6  # 07 §1: rib <= 3 x thickness tall

# Track and followers (06 §7, 05). The track is 44.2 wide on a 31.6 drive gear, so it
# hangs ~6.3 inboard of the gear; the follower wheel (flange gap 45.2 + 2 mm flanges)
# reaches |y| ~47 and sweeps the plate edge at the rear. The rear corners are relieved.
TRACK_W, GEAR_W, GEAR_GAP = 44.2, 31.6, 1.0
REAR_RELIEF = (
    False  # P12: obsolete with the TPU track (belt inner edge |y| 56.5 > plate 55)
)
REAR_RELIEF_Y = 46.0  # plate half-width behind REAR_RELIEF_X
REAR_RELIEF_X = (
    -27.0
)  # front edge of the relief: wheel reach at full forward travel + margin
AXLE_X_MID, TRAVEL = (
    -60.0,
    10.0,
)  # follower axle station (mid travel); 05: 8-10 mm travel
GUIDE_Y, CLAMP_Y = (31.0, 41.0), 36.0  # carriage guide slots and clamp slot, |y|
GUIDE_W = 4.7  # 4.0 rail + 0.35/side slip (05)
RAIL_L = 20.0  # TBD with the carriage design
JACK_BLOCK_X, JACK_BLOCK_Y, JACK_BLOCK_Z = (-38.0, -28.0), (31.0, 42.0), (0.0, 10.0)
JACK_Y, JACK_Z = 36.5, 5.0  # F4b: M3 jack screw in an insert along X

# Bulkhead foot (06 §5, F1): only x >= 78.5 is clear of the motor-mount feet.
BULK_X = 81.5
BULK_HOLES_Y = (-22.0, 0.0, 22.0)
BULK_TAB_Y, BULK_TAB = 11.0, (4.6, 10.4)  # locating-tab slots (X x Y)

# Pi deck posts (F5): clear of the reflex board (x -40..25, |y| <= 30), the mount
# feet (x >= 27.4, |y| >= 13.4) and the follower carriages (|y| >= 28 aft of x -40).
DECK_Z = 24.0  # deck underside (06 §3 height table)
DECK_POSTS = [(30.0, -8.0), (30.0, 8.0), (-48.0, -20.0), (-48.0, 20.0)]
REFLEX_STANDOFF = 5.0
WIRE_SLOT = (
    35.0,
    55.0,
    0.0,
    3.0,
)  # forward wire slot x0 x1 y r (between the mount feet)

LONG_RIBS_Y, LONG_RIBS_X = (-25.0, 0.0, 25.0), (-80.0, 75.0)
CROSS_RIBS_X, CROSS_RIBS_Y = (-60.0, -20.0, 20.0, 60.0), (-44.0, 44.0)
# P3 (b): load-path ribs under the track-tension line (S1m: the plate bends in XZ between
# the mount feet and the jack stops). Top-side rails don't fit: the reflex board edge
# (|y| 30) and the encoder (|y| 30.7, z 1) leave 0.7 mm. Kept to the -8 underside of the
# insert bosses so ground clearance is unchanged. |y| 36.5 is the jack-screw line; it
# stops at x -42, short of the guide and clamp slots.
LOAD_RIBS = True
LOAD_RIB_T, LOAD_RIB_Z = 2.4, UNDER_BOSS_Z
LOAD_RIBS_YX = ((36.5, (-42.0, 72.0)), (47.0, (-78.0, 70.0)))


def mount_holes() -> list[tuple[float, float]]:
    """Motor-mount foot holes in chassis coordinates, both sides (06 §7)."""
    foot = [(-11.2, -38.9), (-25.2, -38.9), (3.5, -38.9), (-25.2, -23.0)]
    tx, ty = mount_tx(), mount_ty()
    right = [(-x + tx, -y - ty) for x, y in foot]  # TT_Motor_Mount_L, Rz180
    left = [(-x + tx, y + ty) for x, y in foot]  # mirror part, Ry180
    return right + left


def edge_room(x: float, y: float) -> float:
    """Distance from (x, y) to the nearest plate edge (front chamfer or sides)."""
    hx, hy = PLATE_L / 2, PLATE_W / 2
    chamfer = (hx + hy - FRONT_CHAMFER - (x + abs(y))) / math.sqrt(2)
    return min(chamfer, hy - abs(y), hx - abs(x))


# Shapes: ("outline",), ("rect", x0, x1, y0, y1), ("circle", cx, cy, r),
# ("slot", xa, ya, xb, yb, r) with the slot axis along X or Y.
def shape_prof(s: tuple) -> str:
    if s[0] == "outline":
        return plate_profile()
    if s[0] == "rect":
        _, x0, x1, y0, y1 = s
        return f"M {x0} {y0} L {x1} {y0} L {x1} {y1} L {x0} {y1}"
    if s[0] == "slot":
        _, xa, ya, xb, yb, r = s
        if ya == yb:  # along X
            return f"M {xb} {ya - r} A {xb} {ya} {xb} {ya + r} L {xa} {ya + r} A {xa} {ya} {xa} {ya - r}"
        return f"M {xa + r} {ya} L {xa + r} {yb} A {xa} {yb} {xa - r} {yb} L {xa - r} {ya} A {xa} {ya} {xa + r} {ya}"
    raise ValueError(s)


def shape_mask(s: tuple, X, Y):
    import numpy as np

    if s[0] == "outline":
        hx, hy, c, r = PLATE_L / 2, PLATE_W / 2, FRONT_CHAMFER, REAR_RADIUS
        m = (np.abs(X) <= hx) & (np.abs(Y) <= hy) & (X + np.abs(Y) <= hx + hy - c)
        corner = (X < -(hx - r)) & (np.abs(Y) > hy - r)
        return m & ~(corner & ((X + hx - r) ** 2 + (np.abs(Y) - (hy - r)) ** 2 > r * r))
    if s[0] == "rect":
        _, x0, x1, y0, y1 = s
        return (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    if s[0] == "circle":
        _, cx, cy, r = s
        return (X - cx) ** 2 + (Y - cy) ** 2 <= r * r
    if s[0] == "slot":
        _, xa, ya, xb, yb, r = s
        px = np.clip(X, min(xa, xb), max(xa, xb))
        py = np.clip(Y, min(ya, yb), max(ya, yb))
        return (X - px) ** 2 + (Y - py) ** 2 <= r * r
    raise ValueError(s)


def plate_features() -> list[tuple[str, tuple, float, float]]:
    """(op, shape, z0, z1) in build order: all bosses, then all cuts.

    op: 'add' boss, 'cut' blind cut over z0..z1, 'all' through cut.
    """
    add: list[tuple[str, tuple, float, float]] = [("add", ("outline",), -PLATE_T, 0.0)]
    cut: list[tuple[str, tuple, float, float]] = []
    # motor-mount inserts: under-boss, sized down where the front chamfer is close
    for x, y in mount_holes():
        r = min(INS_BOSS / 2, round(edge_room(x, y) - 0.04, 2))
        add.append(("add", ("circle", x, y, r), UNDER_BOSS_Z, -PLATE_T))
        cut.append(("cut", ("circle", x, y, INS_HOLE / 2), -INS_DEPTH, 0.0))
    # bottom ribs
    for y in LONG_RIBS_Y:
        add.append(
            (
                "add",
                ("rect", *LONG_RIBS_X, y - RIB_T / 2, y + RIB_T / 2),
                -PLATE_T - RIB_H,
                -PLATE_T,
            )
        )
    if LOAD_RIBS:
        for y, (x0, x1) in LOAD_RIBS_YX:
            for sgn in (-1, 1):
                y0, y1 = sorted(
                    (sgn * (y - LOAD_RIB_T / 2), sgn * (y + LOAD_RIB_T / 2))
                )
                add.append(("add", ("rect", x0, x1, y0, y1), LOAD_RIB_Z, -PLATE_T))
    for x in CROSS_RIBS_X:
        add.append(
            (
                "add",
                ("rect", x - RIB_T / 2, x + RIB_T / 2, *CROSS_RIBS_Y),
                -PLATE_T - RIB_H,
                -PLATE_T,
            )
        )
    # Pi deck posts with inserts at the top
    for x, y in DECK_POSTS:
        add.append(("add", ("circle", x, y, INS_BOSS / 2), 0.0, DECK_Z))
        cut.append(("cut", ("circle", x, y, INS_HOLE / 2), DECK_Z - INS_DEPTH, DECK_Z))
    # reflex board standoffs (F7)
    rx, ry, _ = REFLEX_AT
    for dx, dy in corners(*REFLEX_HOLES):
        add.append(
            ("add", ("circle", rx + dx, ry + dy, INS_BOSS / 2), 0.0, REFLEX_STANDOFF)
        )
        cut.append(
            (
                "cut",
                ("circle", rx + dx, ry + dy, INS_HOLE / 2),
                REFLEX_STANDOFF - INS_DEPTH,
                REFLEX_STANDOFF,
            )
        )
    # follower: guide slots, clamp slot, jack-screw end stop (bore cut separately)
    a0, a1 = AXLE_X_MID - TRAVEL / 2, AXLE_X_MID + TRAVEL / 2
    for sgn in (-1, 1):
        for gy in GUIDE_Y:
            cut.append(
                (
                    "all",
                    (
                        "slot",
                        a0 - RAIL_L / 2,
                        sgn * gy,
                        a1 + RAIL_L / 2,
                        sgn * gy,
                        GUIDE_W / 2,
                    ),
                    0,
                    0,
                )
            )
        cut.append(
            ("all", ("slot", a0, sgn * CLAMP_Y, a1, sgn * CLAMP_Y, CLR_M3 / 2), 0, 0)
        )
        ys = sorted((sgn * JACK_BLOCK_Y[0], sgn * JACK_BLOCK_Y[1]))
        add.append(("add", ("rect", *JACK_BLOCK_X, *ys), *JACK_BLOCK_Z))
        # rear-corner relief: needed only for the kit track (it hung inboard of the gear);
        # the 08 TPU belt and idler sit outboard of |y| 56.5 (P12)
        if REAR_RELIEF:
            ry0, ry1 = sorted((sgn * REAR_RELIEF_Y, sgn * (PLATE_W / 2 + 1)))
            cut.append(
                ("all", ("rect", -PLATE_L / 2 - 1, REAR_RELIEF_X, ry0, ry1), 0, 0)
            )
    # bulkhead foot: screws up from below (counterbored), locating-tab slots
    for y in BULK_HOLES_Y:
        cut.append(("all", ("circle", BULK_X, y, CLR_M3 / 2), 0, 0))
        cut.append(
            (
                "cut",
                ("circle", BULK_X, y, CBORE_M3 / 2),
                -PLATE_T,
                -PLATE_T + CBORE_DEPTH,
            )
        )
    kx, ky = BH_KNEE_HOLE
    cut.append(("all", ("circle", kx, ky, CLR_M3 / 2), 0, 0))
    cut.append(
        (
            "cut",
            ("circle", kx, ky, CBORE_M3 / 2),
            -PLATE_T - RIB_H,
            -PLATE_T + CBORE_DEPTH,
        )
    )
    tw, th = BULK_TAB
    for sgn in (-1, 1):
        cy = sgn * BULK_TAB_Y
        cut.append(
            (
                "all",
                ("rect", BULK_X - tw / 2, BULK_X + tw / 2, cy - th / 2, cy + th / 2),
                0,
                0,
            )
        )
    x0, x1, wy, wr = WIRE_SLOT
    cut.append(("all", ("slot", x0, wy, x1, wy, wr), 0, 0))
    return add + cut


def plate_volume_numeric(step: float = 0.1) -> float:
    """Independent volume: integrate the feature list slab by slab on a 2D grid."""
    import numpy as np

    feats = plate_features()
    xs = np.arange(-PLATE_L / 2 - 1 + step / 2, PLATE_L / 2 + 1, step)
    ys = np.arange(-PLATE_W / 2 - 1 + step / 2, PLATE_W / 2 + 1, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    masks = [shape_mask(s, X, Y) for _, s, _, _ in feats]
    zs = sorted({z for op, _, z0, z1 in feats if op != "all" for z in (z0, z1)})
    vol = 0.0
    for za, zb in zip(zs, zs[1:]):
        zm = (za + zb) / 2
        solid = np.zeros_like(X, dtype=bool)
        hole = np.zeros_like(X, dtype=bool)
        for (op, _, z0, z1), m in zip(feats, masks):
            if op == "all" or (z0 <= zm <= z1):
                if op == "add":
                    solid |= m
                else:
                    hole |= m
        vol += float((solid & ~hole).sum()) * step * step * (zb - za)
    # the two jack-screw insert bores run along X through the end-stop blocks
    vol -= 2 * math.pi * (INS_HOLE / 2) ** 2 * (JACK_BLOCK_X[1] - JACK_BLOCK_X[0])
    return vol


PLATE_EDGE_R = 1.0  # S1a: accessible edges r >= 1.0 (BACKLOG kid-safety)


def plate_perimeter() -> float:
    """Outline length: straight front/rear/sides, two 45° front chamfers, two rear arcs."""
    c, r = FRONT_CHAMFER, REAR_RADIUS
    front = PLATE_W - 2 * c
    rear = PLATE_W - 2 * r
    sides = 2 * (PLATE_L - c - r)
    return front + rear + sides + 2 * c * math.sqrt(2) + 2 * (math.pi / 2) * r


def plate_lines(plate: str) -> list[str]:
    lines = [f"part|{plate}"]
    for op, s, z0, z1 in plate_features():
        if s[0] == "circle" and op != "all":
            kind = "boss" if op == "add" else "cut"
            lines.append(f"cyl|z|{s[1]} {s[2]}|{z0} {z1}|{s[3]}|{kind}")
        elif s[0] == "circle":
            lines.append(f"cyl|z|{s[1]} {s[2]}|all|{s[3]}|cut")
        elif op == "add":
            lines.append(f"prof|{z0} {z1}|{shape_prof(s)}")
        else:
            lines.append(f"prof|{z0} {z1}|{shape_prof(s)}|{op}")
    for sgn in (-1, 1):
        lines.append(f"cyl|x|{sgn * JACK_Y} {JACK_Z}|all|{INS_HOLE / 2}|cut")
    hx, hy = PLATE_L / 2, PLATE_W / 2
    vol = plate_volume_numeric()
    # S1a (kid safety): round the outline's top and bottom edges, the edges every hand
    # grabs. The outer loop of the top (z 0) and bottom (z -4) faces is the outline; a
    # convex 90° round removes (1 - pi/4) r² per mm of edge.
    dv = (1 - math.pi / 4) * PLATE_EDGE_R**2 * plate_perimeter()
    for nz, z in ((1, 0.0), (-1, -PLATE_T)):
        lines.append(
            f"filletface|{PLATE_EDGE_R}|{nz}|{z}|{-hx} {-hy} {hx} {hy}|max|{-dv:.2f} {0.1 * dv:.2f}"
        )
        vol -= dv
    lines += [
        f"expect|vol {vol:.1f} {vol * 0.004:.1f}|box {-hx} {hx} {-hy} {hy} {UNDER_BOSS_Z} {DECK_Z} 0.01",
        "save",
    ]
    return lines


# ------------------------------------------------------- Pi deck (06 §3, F5/F6, P4)
# Level 1: a 3 mm deck on the four plate posts (M3 down into their inserts), the Pi
# stack on it (M2.5 up from below into its brass standoffs). Part frame = chassis x, y
# with the deck top at z 0 and the body below, like the plate. Placed at DECK_Z + DECK_T.
# The wide part stays aft of the mount uprights (x >= 27.4, |y| >= 26.4) and inside the
# encoders (|y| 30.7); a tongue at |y| <= 14 reaches the front posts (30, +-8).
DECK_T = 3.0
DECK_X = (-66.0, 25.0)  # covers the Pi board (x -64.5 .. 22.5 after Rz180)
DECK_HW = 29.5
DECK_TONGUE = (36.0, 14.0)  # front end x, half-width
CLR_M25 = 2.9
DECK_VENTS = ((-45.0, 5.0), (-12.0, -6.0, 0.0, 6.0, 12.0), 2.0)  # x0 x1, ys, r
DECK_CABLE_REAR = (-62.0, -54.0, -10.0, 10.0)  # to level 0 (reflex board)
DECK_CABLE_FRONT = (
    26.0,
    32.0,
    0.0,
    3.0,
)  # forward, to the bulkhead; ends 1 mm short of
# the tongue's front edge (x 36): a slot end tangent to an edge makes the cut return null


def pi_holes_chassis() -> list[tuple[float, float]]:
    px, py, _ = PI_AT
    return [(px + dx, py + dy) for dx, dy in corners(*PI_HOLES)]


def deck_features() -> list[tuple[str, tuple, float, float]]:
    z0, z1 = (
        -DECK_T,
        0.0,
    )  # deck frame: top at z 0, like the plate (placed at DECK_Z + DECK_T)
    x0, x1 = DECK_X
    add = [
        ("add", ("rect", x0, x1, -DECK_HW, DECK_HW), z0, z1),
        (
            "add",
            ("rect", x1 - 1.0, DECK_TONGUE[0], -DECK_TONGUE[1], DECK_TONGUE[1]),
            z0,
            z1,
        ),
    ]
    cut: list[tuple[str, tuple, float, float]] = []
    for x, y in DECK_POSTS:
        cut.append(("all", ("circle", x, y, CLR_M3 / 2), 0, 0))
    for x, y in pi_holes_chassis():
        cut.append(("all", ("circle", x, y, CLR_M25 / 2), 0, 0))
    (vx0, vx1), vys, vr = DECK_VENTS
    for y in vys:
        cut.append(("all", ("slot", vx0, y, vx1, y, vr), 0, 0))
    cut.append(("all", ("rect", *DECK_CABLE_REAR), 0, 0))
    fx0, fx1, fy, fr = DECK_CABLE_FRONT
    cut.append(("all", ("slot", fx0, fy, fx1, fy, fr), 0, 0))
    return add + cut


def features_volume(feats: list, xr: tuple, yr: tuple, step: float = 0.1) -> float:
    """Slab-integrate an (op, shape, z0, z1) feature list on a 2D grid (as plate_volume_numeric)."""
    import numpy as np

    xs = np.arange(xr[0] + step / 2, xr[1], step)
    ys = np.arange(yr[0] + step / 2, yr[1], step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    masks = [shape_mask(s, X, Y) for _, s, _, _ in feats]
    zs = sorted({z for op, _, z0, z1 in feats if op != "all" for z in (z0, z1)})
    vol = 0.0
    for za, zb in zip(zs, zs[1:]):
        zm = (za + zb) / 2
        solid = np.zeros_like(X, dtype=bool)
        hole = np.zeros_like(X, dtype=bool)
        for (op, _, z0, z1), m in zip(feats, masks):
            if op == "all" or (z0 <= zm <= z1):
                if op == "add":
                    solid |= m
                else:
                    hole |= m
        vol += float((solid & ~hole).sum()) * step * step * (zb - za)
    return vol


def feature_lines(feats: list) -> list[str]:
    out = []
    for op, s, z0, z1 in feats:
        if s[0] == "circle":
            if op == "all":
                out.append(f"cyl|z|{s[1]} {s[2]}|all|{s[3]}|cut")
            else:
                out.append(
                    f"cyl|z|{s[1]} {s[2]}|{z0} {z1}|{s[3]}|{'boss' if op == 'add' else 'cut'}"
                )
        elif op == "add":
            out.append(f"prof|{z0} {z1}|{shape_prof(s)}")
        else:
            out.append(f"prof|{z0} {z1}|{shape_prof(s)}|{op}")
    return out


def deck_lines(path: str) -> list[str]:
    feats = deck_features()
    vol = features_volume(
        feats, (DECK_X[0] - 1, DECK_TONGUE[0] + 1), (-DECK_HW - 1, DECK_HW + 1)
    )
    return [
        f"part|{path}",
        *feature_lines(feats),
        f"expect|vol {vol:.1f} {vol * 0.004:.1f}|box {DECK_X[0]} {DECK_TONGUE[0]} {-DECK_HW} {DECK_HW} {-DECK_T} 0 0.01",
        "save",
    ]


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
REFLEX_PAD_R = 4.7  # > the Ø9.2 standoff; overhangs the board edge (holes sit 4.0 in)


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


def reflex_pad_area() -> float:
    """Pad area inside the board: each pad loses a circular segment past any edge
    closer than its radius (no hole is near two edges' corner within r)."""
    r = REFLEX_PAD_R
    seg = 0.0
    for x, y in corners(*REFLEX_HOLES):
        for d in (x - REFLEX_X[0], REFLEX_X[1] - x, y - REFLEX_Y[0], REFLEX_Y[1] - y):
            if d < r:
                seg += r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)
    return 4 * math.pi * r * r - seg


def reflex_ops() -> tuple[list[str], float]:
    ops = [
        f"box|{REFLEX_X[0]} {REFLEX_X[1]}|{REFLEX_Y[0]} {REFLEX_Y[1]}|{REFLEX_Z[0]} {REFLEX_Z[1]}"
    ]
    # standoff landing pads: clear the underside-component zone around each hole
    ops += [
        f"cyl|z|{x} {y}|{REFLEX_Z[0]} 0|{REFLEX_PAD_R}|cut"
        for x, y in corners(*REFLEX_HOLES)
    ]
    ops += [f"cyl|z|{x} {y}|all|1.6|cut" for x, y in corners(*REFLEX_HOLES)]
    h = REFLEX_Z[1] - REFLEX_Z[0]
    vol = (
        (REFLEX_X[1] - REFLEX_X[0]) * (REFLEX_Y[1] - REFLEX_Y[0]) * h
        - reflex_pad_area() * -REFLEX_Z[0]
        - 4 * math.pi * 1.6**2 * REFLEX_Z[1]
    )
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
    -10.5,
    -3.5,
    5.0,
)  # between the motors, x -40..25; 0.7 clear of the encoders
# board X (short side) -> chassis Z, board Y (MIC end) -> chassis -Y, board Z (screen) -> chassis X
FACE_BASE = [0, 0, 1, 0, -1, 0, 1, 0, 0]


def rebuild_manifest(win: str) -> list[str]:
    cad = win + r"\CAD"
    plate = cad + r"\parts\RB-PRT-001_base_plate.SLDPRT"
    motor = cad + r"\library\TT_Motor_envelope_v2.SLDPRT"
    pi = cad + r"\library\Pi5_stack_envelope.SLDPRT"
    face = cad + r"\library\FNK0104_face_envelope.SLDPRT"
    reflex = cad + r"\library\reflex_board_envelope.SLDPRT"
    bulkhead = cad + r"\parts\RB-PRT-002_bulkhead.SLDPRT"
    deck = cad + r"\parts\RB-PRT-003_pi_deck.SLDPRT"  # P4
    sprocket = cad + r"\parts\RB-PRT-020_sprocket.SLDPRT"  # 08, outrigger variant (P2o)
    idler = cad + r"\parts\RB-PRT-021_idler.SLDPRT"  # 08, 2 x 624
    belt_l = cad + r"\library\belt_envelope_L.SLDPRT"
    belt_r = cad + r"\library\belt_envelope_R.SLDPRT"
    mount_r = cad + r"\parts\RB-PRT-010_motor_mount_R.SLDPRT"  # generated v2 (P2)
    mount_l = cad + r"\parts\RB-PRT-011_motor_mount_L.SLDPRT"  # its X-mirror
    asm = cad + r"\assemblies\RB-ASM-101_chassis.SLDASM"
    shots = win + r"\shots\rebuild"

    m_ops, m_vol = motor_ops()
    # the drivetrain's shaft station must be ours (it keeps its own copy of 52.7 / 13.5)
    shaft_x = mount_tx() - (MOUNT_HOLE[0] - MOT_SHAFT_X)
    assert abs(shaft_x - dt.X_DRIVE) < 0.05 and abs(MOUNT_HOLE[2] - dt.Z_AXLE) < 1e-9, (
        shaft_x,
        dt.X_DRIVE,
    )
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
        *plate_lines(plate),
        f"part|{motor}",
        *m_ops,
        f"expect|vol {m_vol:.1f} 5.0|box {MOT_CAN_END} {MOT_GEAR_END} {(MOT_THICK - MOT_ENC_T) / 2} "
        f"{MOT_THICK + MOT_SHAFT_LEN} {-MOT_ENC_W / 2} {MOT_ENC_W / 2} 0.05",
        "save",
        *envelope_lines(pi, face, reflex),
        *bulkhead_lines(bulkhead),
        *deck_lines(deck),
        *mount_v2_lines(mount_r, mirror=False),
        *mount_v2_lines(mount_l, mirror=True),
        *wheel_lines(sprocket, dt.sprocket_layers(True)),
        *wheel_lines(idler, dt.idler_layers(2)),
        *belt_envelope_lines(belt_l, +1),
        *belt_envelope_lines(belt_r, -1),
        f"asm|{asm}",
        f"comp|plate|{plate}|{row(ROT_I, (0, 0, 0))}|fix",
        f"comp|mount_R|{mount_r}|{row(ROT_Z180, (tx, -ty, 0))}",
        f"comp|mount_L|{mount_l}|{row(ROT_I, (tx, ty, 0))}",
        f"comp|motor_R|{motor}|{row(ROT_X180, mot_r_t)}",
        f"comp|motor_L|{motor}|{row(ROT_I, mot_l_t)}",
        f"comp|pi_stack|{pi}|{row(ROT_Z180, PI_AT)}",
        f"comp|reflex|{reflex}|{row(ROT_I, REFLEX_AT)}",
        f"comp|bulkhead|{bulkhead}|{row(ROT_I, (0, 0, 0))}",
        f"comp|pi_deck|{deck}|{row(ROT_I, (0, 0, DECK_Z + DECK_T))}",
        f"comp|sprocket_L|{sprocket}|{row(*wheel_at(dt.X_DRIVE, +1))}",
        f"comp|sprocket_R|{sprocket}|{row(*wheel_at(dt.X_DRIVE, -1))}",
        f"comp|idler_L|{idler}|{row(*wheel_at(dt.belt_fit()['x_fit'], +1))}",
        f"comp|idler_R|{idler}|{row(*wheel_at(dt.belt_fit()['x_fit'], -1))}",
        f"comp|belt_L|{belt_l}|{row(ROT_I, (0, 0, 0))}",
        f"comp|belt_R|{belt_r}|{row(ROT_I, (0, 0, 0))}",
        f"comp|face|{face}|{row(*face_on_bulkhead())}",
        "interfere",
        "asmsave",
        # T10: analysis-only part, plate + both mounts as one body (not printed)
        *fea_plate_mounts_lines(cad + r"\\fea\\FEA-plate_mounts.SLDPRT"),
        f"shot|{asm}|{shots}",
        f"close|{asm}",
        f"shot|{plate}|{win}\\shots\\plate",
        f"close|{plate}",
        f"shot|{bulkhead}|{win}\\shots\\bulkhead",
        f"close|{bulkhead}",
        # printed parts -> STL in chassis coordinates (T1); meshcheck reads these
        *[
            f"stl|{p}|{cad}\\exports\\gen\\{n}.stl"
            for p, n in (
                (plate, "RB-PRT-001_base_plate"),
                (bulkhead, "RB-PRT-002_bulkhead"),
                (deck, "RB-PRT-003_pi_deck"),
                (mount_r, "RB-PRT-010_motor_mount_R"),
                (mount_l, "RB-PRT-011_motor_mount_L"),
                (sprocket, "RB-PRT-020_sprocket"),
                (idler, "RB-PRT-021_idler"),
            )
        ],
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


# ------------------------------------------------------- front bulkhead (06 §5, P1)
# Built VERTICAL in chassis coordinates (wall front face at x = BH_XF, thickness BH_T,
# so the wall spans x BH_XF - BH_T .. BH_XF), then tilted BH_TILT back about its
# back-bottom edge (BH_PIVOT); the foot and tabs go on afterwards, in the chassis frame.
# Layout on the wall (y across, z up, pre-tilt): sonar + speaker side by side in the
# lower band, face board behind a window, camera lens above (Q6 default). The face
# board sits BEHIND the wall: its LCD stack bears on the wall's back face, the window
# shows the active area, M3 x 5 screws go through the PCB into inserts in 4.3 standoffs.
BH_XF, BH_T, BH_W, BH_H, BH_TILT = 85.0, 3.0, 94.0, 126.0, 15.0
BH_PIVOT = (BH_XF - BH_T, 0.0, 0.0)
BH_FACE_Z = 77.0  # face-board centre height (pre-tilt)
FACE_AA = (43.2, 57.6)  # active area (board X, board Y)
FACE_AA_CY = (FACE_H / 2 - 11.12) - FACE_AA[
    1
] / 2  # AA centre along board Y (MIC end +)
BH_FACE_Y = FACE_AA_CY  # board centre y so the window (and the AA) is centred: board Y -> chassis -y
BH_STANDOFF_R, BH_STANDOFF_L = (
    3.5,
    FACE_FRONT,
)  # LCD stack thickness: LCD bears on the wall
BH_FACE_POCKET = (
    6.0  # M3 x 5 screw: PCB 1.6 + 3.4 engaged < 5.7 insert, no bottom relief needed
)
BH_SONAR_Y, BH_SONAR_Z, BH_SONAR_PITCH, BH_SONAR_R = (
    -22.0,
    26.0,
    26.0,
    8.3,
)  # HC-SR04 Ø16
BH_SLEEVE_R, BH_SLEEVE_L = 9.8, 6.0
BH_SPK = (
    24.0,
    26.0,
    17.0,
)  # speaker centre y, z and grille radius (CE40P-8, cone ~Ø34)
BH_SLOT_W, BH_SLOT_DZ = (
    2.0,
    (-10.0, -6.0, -2.0, 2.0, 6.0, 10.0),
)  # grille slots <= 2 mm (audio §4.3)
BH_CAM = (
    0.0,
    113.0,
    4.5,
)  # lens hole y, z, r (Pi Camera Module 3, Q6 default) 🟡 no bosses yet
BH_LUG_Y, BH_LUG_Z = 38.0, (112.0, BH_H)  # canopy screw lugs (F9) behind the wall top
BH_FLANGE = (
    FACE_FRONT,
    1.8,
)  # side flanges: depth = standoff length, so the face PCB edge clears them
BH_RIB_Z = 50.0  # horizontal rib between the lower band and the face
BH_FOOT = (
    (78.5, BH_XF),
    (-29.5, 29.5),
    (0.0, 9.0),
)  # chassis box; x >= 78.5 clears the mount feet
BH_TAB = (4.0, 9.8, 3.6)  # into the 4.6 x 10.4 plate slots (0.3/side)
# Knee gusset (P1b): the only clear slot behind the lower band is between the sonar
# sleeves (y <= 0.8) and the speaker (y >= 4); it stays below the face board (z <= 44).
# Its tail pad is bolted down through the plate (M3 up into an insert, like F1).
BH_KNEE_Y = (1.2, 3.6)  # 2.4 thick
BH_KNEE_TOP = 44.0  # top of the gusset, chassis z
BH_KNEE_TAIL = 56.0  # rear end on the plate (the wire slot ends at x 55)
BH_KNEE_PAD = ((56.0, 66.0), (-2.2, 7.0), (0.0, 9.0))
BH_KNEE_HOLE = (61.0, 2.4)


def _rotate_y(p, deg: float, pivot):
    """Rotate points p (N x 3) about the axis through `pivot` parallel to Y."""
    import numpy as np

    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    q = np.asarray(p, float) - pivot
    x, z = q[..., 0], q[..., 2]
    out = np.stack([c * x + s_ * z, q[..., 1], -s_ * x + c * z], axis=-1)
    return out + pivot


def bulkhead_features() -> tuple[list[tuple], list[tuple]]:
    """(pre, post): pre-tilt features (wall frame = chassis, vertical wall) and
    post-tilt features (chassis frame). Each: (op, shape) with op 'add' | 'cut'.
    Shapes: ('box', x0, x1, y0, y1, z0, z1), ('cylx', y, z, x0, x1, r), ('cylz', x, y, z0, z1, r)."""
    x0, x1 = BH_XF - BH_T, BH_XF
    hw = BH_W / 2
    pre: list[tuple] = [("add", ("box", x0, x1, -hw, hw, 0.0, BH_H))]
    fd, ft = BH_FLANGE
    for sgn in (-1, 1):  # side flanges
        ys = sorted((sgn * hw, sgn * (hw - ft)))
        pre.append(("add", ("box", x0 - fd, x0, *ys, 0.0, BH_H)))
    pre.append(
        (
            "add",
            (
                "box",
                x0 - 4.0,
                x0,
                -(hw - ft),
                hw - ft,
                BH_RIB_Z - RIB_T / 2,
                BH_RIB_Z + RIB_T / 2,
            ),
        )
    )
    # face standoffs on the back face, at the board's holes (board X -> z, board Y -> -y)
    face_holes = [(BH_FACE_Y - by, BH_FACE_Z + bx) for bx, by in corners(*FACE_HOLES)]
    for y, z in face_holes:
        pre.append(("add", ("cylx", y, z, x0 - BH_STANDOFF_L, x0 + 0.5, BH_STANDOFF_R)))
    # sonar sleeves
    sonar = [(BH_SONAR_Y + d * BH_SONAR_PITCH / 2, BH_SONAR_Z) for d in (-1, 1)]
    for y, z in sonar:
        pre.append(("add", ("cylx", y, z, x0 - BH_SLEEVE_L, x0 + 0.5, BH_SLEEVE_R)))
    # canopy lugs (vertical before the tilt)
    lug_x = x0 - INS_BOSS / 2 + 1.0
    for sgn in (-1, 1):
        pre.append(("add", ("cylz", lug_x, sgn * BH_LUG_Y, *BH_LUG_Z, INS_BOSS / 2)))
    # cuts
    aw, ah = FACE_AA[1] + 2.0, FACE_AA[0] + 2.0  # window: AA + 1 mm all round
    pre.append(
        (
            "cut",
            (
                "box",
                x0 - 0.1,
                x1 + 0.1,
                -aw / 2,
                aw / 2,
                BH_FACE_Z - ah / 2,
                BH_FACE_Z + ah / 2,
            ),
        )
    )
    for y, z in face_holes:
        pre.append(
            (
                "cut",
                (
                    "cylx",
                    y,
                    z,
                    x0 - BH_STANDOFF_L,
                    x0 - BH_STANDOFF_L + BH_FACE_POCKET,
                    INS_HOLE / 2,
                ),
            )
        )
    for y, z in sonar:
        pre.append(
            ("cut", ("cylx", y, z, x0 - BH_SLEEVE_L - 0.1, x1 + 0.1, BH_SONAR_R))
        )
    sy, sz, sr = BH_SPK
    for dz in BH_SLOT_DZ:
        far = abs(dz) + BH_SLOT_W / 2
        half = math.sqrt(sr * sr - far * far)
        pre.append(
            (
                "cut",
                (
                    "box",
                    x0 - 0.1,
                    x1 + 0.1,
                    sy - half,
                    sy + half,
                    sz + dz - BH_SLOT_W / 2,
                    sz + dz + BH_SLOT_W / 2,
                ),
            )
        )
    cy, cz, cr = BH_CAM
    pre.append(("cut", ("cylx", cy, cz, x0 - 0.1, x1 + 0.1, cr)))
    for sgn in (-1, 1):
        pre.append(
            (
                "cut",
                (
                    "cylz",
                    lug_x,
                    sgn * BH_LUG_Y,
                    BH_LUG_Z[1] - INS_DEPTH,
                    BH_LUG_Z[1] + 0.1,
                    INS_HOLE / 2,
                ),
            )
        )
    # post-tilt, chassis frame: foot, tabs, foot insert pockets (F1)
    (fx0, fx1), (fy0, fy1), (fz0, fz1) = BH_FOOT
    post: list[tuple] = [("add", ("box", fx0, fx1, fy0, fy1, fz0, fz1))]
    tw, th, td = BH_TAB
    for sgn in (-1, 1):
        cyy = sgn * BULK_TAB_Y
        post.append(
            (
                "add",
                (
                    "box",
                    BULK_X - tw / 2,
                    BULK_X + tw / 2,
                    cyy - th / 2,
                    cyy + th / 2,
                    -td,
                    0.0,
                ),
            )
        )
    # knee gusset: a triangle in XZ from the tail to the wall's back face (0.6 overlap)
    lean = math.tan(math.radians(BH_TILT))
    back0 = BH_PIVOT[0] + 0.6  # back face at z = 0, plus overlap into the wall
    knee = [
        (BH_KNEE_TAIL, 0.0),
        (back0, 0.0),
        (back0 - BH_KNEE_TOP * lean, BH_KNEE_TOP),
    ]
    post.append(("add", ("prismy", knee, *BH_KNEE_Y)))
    (px0, px1), (py0, py1), (pz0, pz1) = BH_KNEE_PAD
    post.append(("add", ("box", px0, px1, py0, py1, pz0, pz1)))
    for y in BULK_HOLES_Y:
        post.append(("cut", ("cylz", BULK_X, y, -0.1, INS_DEPTH, INS_HOLE / 2)))
    post.append(("cut", ("cylz", *BH_KNEE_HOLE, -0.1, INS_DEPTH, INS_HOLE / 2)))
    return pre, post


def _shape_mask3(s: tuple, P):
    import numpy as np

    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    if s[0] == "box":
        _, x0, x1, y0, y1, z0, z1 = s
        return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)
    if s[0] == "cylx":
        _, cy, cz, x0, x1, r = s
        return (x >= x0) & (x <= x1) & ((y - cy) ** 2 + (z - cz) ** 2 <= r * r)
    if s[0] == "cylz":
        _, cx, cy, z0, z1, r = s
        return (z >= z0) & (z <= z1) & ((x - cx) ** 2 + (y - cy) ** 2 <= r * r)
    if s[0] in ("prismz", "prismx"):  # polygon in (x, y) over z / in (y, z) over x
        _, poly, a0, a1 = s
        u, v, w = (x, y, z) if s[0] == "prismz" else (y, z, x)
        inside = np.zeros(x.shape, dtype=bool)
        for (ua, va), (ub, vb) in zip(poly, poly[1:] + poly[:1]):
            crosses = (va > v) != (vb > v)
            with np.errstate(divide="ignore", invalid="ignore"):
                ui = ua + (v - va) * (ub - ua) / (vb - va)
            inside ^= crosses & (u < ui)
        return inside & (w >= a0) & (w <= a1)
    if s[0] == "cyly":
        _, cx, cz, y0, y1, r = s
        return (y >= y0) & (y <= y1) & ((x - cx) ** 2 + (z - cz) ** 2 <= r * r)
    if s[0] == "prismy":  # polygon in (x, z), extruded over y0..y1; even-odd rule
        _, poly, y0, y1 = s
        inside = np.zeros(x.shape, dtype=bool)
        for (xa, za), (xb, zb) in zip(poly, poly[1:] + poly[:1]):
            crosses = (za > z) != (zb > z)
            with np.errstate(divide="ignore", invalid="ignore"):
                xi = xa + (z - za) * (xb - xa) / (zb - za)
            inside ^= crosses & (x < xi)
        return inside & (y >= y0) & (y <= y1)
    raise ValueError(s)


def bulkhead_volume_numeric(step: float = 0.2) -> tuple[float, list[float]]:
    """Independent volume and bounding box: voxel integration of the feature list,
    with pre-tilt features tested at inverse-rotated points."""
    import numpy as np

    pre, post = bulkhead_features()
    xs = np.arange(40.0 + step / 2, 90.0, step)
    ys = np.arange(-BH_W / 2 - 1 + step / 2, BH_W / 2 + 1, step)
    zs = np.arange(-5.0 + step / 2, BH_H + 2, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    vol, lo, hi = 0.0, [1e9] * 3, [-1e9] * 3
    for z in zs:
        P = np.stack([X, Y, np.full_like(X, z)], axis=-1)
        Q = _rotate_y(P, BH_TILT, BH_PIVOT)  # inverse of the -TILT rotation
        solid = np.zeros_like(X, dtype=bool)
        for op, sh in pre:
            m = _shape_mask3(sh, Q)
            solid = solid | m if op == "add" else solid & ~m
        for op, sh in post:
            m = _shape_mask3(sh, P)
            solid = solid | m if op == "add" else solid & ~m
        n = int(solid.sum())
        if n:
            vol += n * step**3
            ix, iy = np.nonzero(solid)
            lo = [min(lo[0], xs[ix].min()), min(lo[1], ys[iy].min()), min(lo[2], z)]
            hi = [max(hi[0], xs[ix].max()), max(hi[1], ys[iy].max()), max(hi[2], z)]
    return vol, [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]


def _right_rect(y0: float, y1: float, z0: float, z1: float) -> str:
    """Rectangle in Right-plane sketch coordinates (sketch x = -z, sketch y = y)."""
    return f"M {-z0} {y0} L {-z0} {y1} L {-z1} {y1} L {-z1} {y0}"


def bulkhead_lines(path: str) -> list[str]:
    pre, post = bulkhead_features()

    def emit(op: str, sh: tuple) -> str:
        kind = "boss" if op == "add" else "cut"
        if sh[0] == "box":
            _, x0, x1, y0, y1, z0, z1 = sh
            return f"prof|{x0} {x1}|{_right_rect(y0, y1, z0, z1)}|{kind}|right"
        if sh[0] == "cylx":
            _, cy, cz, x0, x1, r = sh
            return f"cyl|x|{cy} {cz}|{x0} {x1}|{r}|{kind}"
        if sh[0] == "prismy":  # Top plane: sketch (x, -z), extrude +Y
            _, poly, y0, y1 = sh
            pts = [f"{x:.4f} {-z:.4f}" for x, z in poly]
            segs = "M " + pts[0] + "".join(" L " + p for p in pts[1:])
            return f"prof|{y0} {y1}|{segs}|{kind}|top"
        _, cx, cy, z0, z1, r = sh
        return f"cyl|z|{cx} {cy}|{z0} {z1}|{r}|{kind}"

    lines = [f"part|{path}"]
    lines += [emit(op, sh) for op, sh in pre if op == "add"]
    lines += [emit(op, sh) for op, sh in pre if op == "cut"]
    lines.append(f"rotbody|{BH_PIVOT[0]} {BH_PIVOT[1]} {BH_PIVOT[2]}|y|{-BH_TILT}")
    for op, sh in post:
        if sh[0] == "box" and op == "add":
            _, x0, x1, y0, y1, z0, z1 = sh
            lines.append(f"box|{x0} {x1}|{y0} {y1}|{z0} {z1}")
        else:
            lines.append(emit(op, sh))
    vol, bb = bulkhead_volume_numeric()
    lines += [
        f"expect|vol {vol:.1f} {vol * 0.01:.1f}|box {' '.join(f'{v:.2f}' for v in bb)} 0.35",
        "save",
    ]
    return lines


def face_on_bulkhead() -> tuple[list[float], tuple[float, float, float]]:
    """Face-board envelope placement from the bulkhead: its PCB front face bears on the
    standoff tips, so the board-frame origin (back plane) sits FACE_BACK + FACE_PCB
    behind them; then the same tilt as the wall."""
    x0 = BH_XF - BH_T - BH_STANDOFF_L - (FACE_BACK + FACE_PCB)
    p = _rotate_y([x0, BH_FACE_Y, BH_FACE_Z], -BH_TILT, BH_PIVOT)
    return matmul(rot_y(-BH_TILT), FACE_BASE), (float(p[0]), float(p[1]), float(p[2]))


# ------------------------------------------------------- motor mount v2 (P2, fixes S2)
# Generated replacement for Ben's imported L-bracket, in the SAME part frame (foot on
# Z = 0, motor-side face at y = -28, motor holes along Y), so the plate holes and the
# placements carry over. Right part = this frame (placed Rz180); left part = its X-mirror
# (placed at identity), which is the mapping Ben's mirror part had.
MM_T = 6.0  # upright 3 -> 6: 6.6 left the S2 peak unchanged (12.0 MPa), so it is local, not bending
MM_FACE = MOUNT_HOLE[1]
MM_X = (
    MOUNT_HOLE[0] - MOT_GEAR_END,
    20.0,
)  # gearbox end (drawing) .. Ben's upright end
MM_TOP = MOUNT_HOLE[2] + MOT_GEAR_W / 2 + 2.0  # 2 mm above the gearbox
MM_FOOT_T = 3.0
MM_STOP_T = 3.0  # end stop at the gearbox end (Ben's gusset)
MM_GUSSETS = (
    -18.2,
    -3.9,
    10.0,
)  # inboard, between the foot screws (x -25.2, -11.2, 3.5); D8: 12.0 -> 10.0 so the
# lower motor-insert pocket (x 12.5-16.5, through the upright) misses gusset 3's root
MM_GUSSET_T, MM_GUSSET_Y, MM_GUSSET_Z = 2.4, -45.5, 20.0
MM_CHAMFER = 3.6  # root chamfer on the inboard side (stands in for a fillet until T7)
MM_INS_DEPTH = MM_T  # M3 inserts through the upright, pressed from the motor face (F3)
MM_INS_BOSS_H = 1.8  # D10: local boss on the inboard face around the lower insert
MM_INS_BLIND = MM_T + MM_INS_BOSS_H - 1.2  # 6.6: lower pocket stops 1.2 inside the boss


def mount_v2_features(mirror: bool) -> list[tuple]:
    xa, xb = MM_X
    yi = MM_FACE - MM_T  # inboard face of the upright
    foot = [
        (-30.4, -47.0),
        (xb, -47.0),
        (xb, yi),
        (xa, yi),
        (xa, -8.9),
        (-19.9, -8.9),
        (-30.4, -18.7),
    ]
    ops: list[tuple] = [
        ("add", ("prismz", foot, 0.0, MM_FOOT_T)),
        ("add", ("box", xa, xb, yi, MM_FACE, 0.0, MM_TOP)),
        ("add", ("box", xa - MM_STOP_T, xa, yi, -8.9, 0.0, MM_TOP - 4.0)),
    ]
    tri = [(yi + 0.6, MM_FOOT_T), (yi + 0.6, MM_GUSSET_Z), (MM_GUSSET_Y, MM_FOOT_T)]
    for gx in MM_GUSSETS:
        ops.append(("add", ("prismx", tri, gx - MM_GUSSET_T / 2, gx + MM_GUSSET_T / 2)))
    ch = [
        (yi + 0.6, MM_FOOT_T),
        (yi - MM_CHAMFER, MM_FOOT_T),
        (yi + 0.6, MM_FOOT_T + MM_CHAMFER + 0.6),
    ]
    # D10: the lower motor-insert pocket used to run through the upright and open across
    # the root corner, so the root chamfer had to stop short of it (D7) and the bare corner
    # past it was S2's singular peak (D8; a stub chamfer made it worse, D9). Now that
    # pocket is blind, ending 1.2 mm inside a local boss on the inboard face, and the
    # chamfer runs the full length with nothing crossing it.
    ops.append(("add", ("prismx", ch, xa, xb)))
    hx, _, hz = MOUNT_HOLE
    bz = hz - MOT_HOLE_PITCH / 2
    ops.append(("add", ("cyly", hx, bz, yi - MM_INS_BOSS_H, yi + 0.5, INS_BOSS / 2)))
    for dz in (-MOT_HOLE_PITCH / 2, MOT_HOLE_PITCH / 2):
        y0 = MM_FACE - MM_INS_BLIND if dz < 0 else MM_FACE - MM_INS_DEPTH - 0.1
        ops.append(("cut", ("cyly", hx, hz + dz, y0, MM_FACE + 0.1, INS_HOLE / 2)))
    for x, y in [(-11.2, -38.9), (-25.2, -38.9), (3.5, -38.9), (-25.2, -23.0)]:
        ops.append(("cut", ("cylz", x, y, -0.1, MM_FOOT_T + 0.1, CLR_M3 / 2)))
    if not mirror:
        return ops

    def mx(sh: tuple) -> tuple:
        k = sh[0]
        if k == "box":
            return ("box", -sh[2], -sh[1], *sh[3:])
        if k == "prismz":
            return ("prismz", [(-u, v) for u, v in sh[1]][::-1], sh[2], sh[3])
        if k == "prismx":
            return ("prismx", sh[1], -sh[3], -sh[2])
        if k == "cyly":
            return ("cyly", -sh[1], *sh[2:])
        if k == "cylz":
            return ("cylz", -sh[1], *sh[2:])
        raise ValueError(k)

    return [(op, mx(sh)) for op, sh in ops]


def solid_volume_numeric(
    ops: list[tuple], bounds, step: float = 0.2
) -> tuple[float, list[float]]:
    """Voxel volume + bbox of an add/cut feature list (no rotation), for any part."""
    import numpy as np

    (x0, x1), (y0, y1), (z0, z1) = bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    vol, lo, hi = 0.0, [1e9] * 3, [-1e9] * 3
    for z in np.arange(z0 + step / 2, z1, step):
        P = np.stack([X, Y, np.full_like(X, z)], axis=-1)
        solid = np.zeros_like(X, dtype=bool)
        for op, sh in ops:
            m = _shape_mask3(sh, P)
            solid = solid | m if op == "add" else solid & ~m
        n = int(solid.sum())
        if n:
            vol += n * step**3
            ix, iy = np.nonzero(solid)
            lo = [min(lo[0], xs[ix].min()), min(lo[1], ys[iy].min()), min(lo[2], z)]
            hi = [max(hi[0], xs[ix].max()), max(hi[1], ys[iy].max()), max(hi[2], z)]
    return vol, [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]


def emit_ops(ops: list[tuple]) -> list[str]:
    """Manifest lines for a no-rotation add/cut feature list (adds first, then cuts)."""
    out = []
    for want in ("add", "cut"):
        for op, sh in ops:
            if op != want:
                continue
            kind = "boss" if op == "add" else "cut"
            k = sh[0]
            if k == "box":
                _, x0, x1, y0, y1, z0, z1 = sh
                out.append(
                    f"box|{x0} {x1}|{y0} {y1}|{z0} {z1}"
                    if op == "add"
                    else f"prof|{z0} {z1}|M {x0} {y0} L {x1} {y0} L {x1} {y1} L {x0} {y1}|cut"
                )
            elif k == "prismz":
                pts = [f"{u:.4f} {v:.4f}" for u, v in sh[1]]
                out.append(
                    f"prof|{sh[2]} {sh[3]}|M "
                    + pts[0]
                    + "".join(" L " + q for q in pts[1:])
                    + f"|{kind}|front"
                )
            elif k == "prismx":  # Right plane: sketch (-z, y)
                pts = [f"{-v:.4f} {u:.4f}" for u, v in sh[1]]
                out.append(
                    f"prof|{sh[2]} {sh[3]}|M "
                    + pts[0]
                    + "".join(" L " + q for q in pts[1:])
                    + f"|{kind}|right"
                )
            elif k == "cyly":
                _, cx, cz, y0, y1, r = sh
                out.append(f"cyl|y|{cx} {cz}|{y0} {y1}|{r}|{kind}")
            elif k == "cylz":
                _, cx, cy, z0, z1, r = sh
                out.append(f"cyl|z|{cx} {cy}|{z0} {z1}|{r}|{kind}")
            else:
                raise ValueError(k)
    return out


def mount_v2_lines(path: str, mirror: bool) -> list[str]:
    ops = mount_v2_features(mirror)
    vol, bb = solid_volume_numeric(
        ops, ((-36.0, 36.0), (-50.0, -5.0), (-1.0, MM_TOP + 1.0))
    )
    return [
        f"part|{path}",
        *emit_ops(ops),
        f"expect|vol {vol:.1f} {vol * 0.01:.1f}|box {' '.join(f'{v:.2f}' for v in bb)} 0.35",
        "save",
    ]


# ------------------------------------------------- FEA part: plate + both mounts (T10)
# Plate and mounts are all PET-CF, so merging them into ONE body is exactly Simulation's
# bonded contact: the feet bear on the plate over their whole footprint instead of the
# axle load entering through the plate's insert pockets (S1a's coupling artefact).


def mount_ops_chassis(side: int) -> list[tuple]:
    """mount_v2_features (right part frame) mapped to chassis: x' = tx - x and
    y' = side * (y + ty) (right = Rz180 of the part, left = its X-mirror at identity)."""
    tx, ty = mount_tx(), mount_ty()

    def X(x: float) -> float:
        return tx - x

    def Y(y: float) -> float:
        return side * (y + ty)

    def span(a: float, b: float, f) -> tuple[float, float]:
        u, v = f(a), f(b)
        return (min(u, v), max(u, v))

    out = []
    for op, sh in mount_v2_features(False):
        k = sh[0]
        if k == "box":
            _, x0, x1, y0, y1, z0, z1 = sh
            out.append((op, ("box", *span(x0, x1, X), *span(y0, y1, Y), z0, z1)))
        elif k == "prismz":
            out.append((op, ("prismz", [(X(x), Y(y)) for x, y in sh[1]], sh[2], sh[3])))
        elif k == "prismx":
            out.append(
                (op, ("prismx", [(Y(y), z) for y, z in sh[1]], *span(sh[2], sh[3], X)))
            )
        elif k == "cyly":
            _, cx, cz, y0, y1, r = sh
            out.append((op, ("cyly", X(cx), cz, *span(y0, y1, Y), r)))
        elif k == "cylz":
            _, cx, cy, z0, z1, r = sh
            out.append((op, ("cylz", X(cx), Y(cy), z0, z1, r)))
        else:
            raise ValueError(k)
    return out


def fea_plate_mounts_lines(path: str) -> list[str]:
    plate = plate_lines(path)
    assert plate[-2].startswith("expect|vol ") and plate[-1] == "save"
    v_plate = float(plate[-2].split("|")[1].split()[1])
    v_mount, _ = solid_volume_numeric(
        mount_v2_features(False), ((-36.0, 36.0), (-50.0, -5.0), (-1.0, MM_TOP + 1.0))
    )
    vol = v_plate + 2 * v_mount
    hx, hy = PLATE_L / 2, PLATE_W / 2
    return [
        *plate[:-2],
        *emit_ops(mount_ops_chassis(+1)),
        *emit_ops(mount_ops_chassis(-1)),
        f"expect|vol {vol:.1f} {vol * 0.006:.1f}|box {-hx} {hx} {-hy} {hy} {UNDER_BOSS_Z} {max(DECK_Z, MM_TOP)} 0.01",
        "save",
    ]


# ------------------------------------------------- printed TPU track system (08, P11)
# drivetrain.py owns the drivetrain numbers and the wheel geometry (its layer stacks);
# this only turns them into native SolidWorks parts and places them. Part frames
# (drivetrain.py): Z = wheel axis, Z = 0 on the outboard (bed) face.


def _loop(c) -> str:
    import numpy as np

    c = np.asarray(c, float)
    if float(np.ptp(c)) < 1e-9:
        return f"c {c[0]:.6f}"
    return "p " + " ".join(f"{v:.5f}" for v in c)


def ring_lines(layers: list) -> list[str]:
    """Annuli from a drivetrain.py layer stack; consecutive layers with the same two
    curves merge into one extrusion."""
    rows: list[list] = []
    for z0, z1, ann in layers:
        for ri, ro in ann:
            key = (ri.tobytes(), ro.tobytes())
            prev = next(
                (r for r in rows if r[4] == key and abs(r[1] - z0) < 1e-9), None
            )
            if prev is not None:
                prev[1] = z1
            else:
                rows.append([z0, z1, ri, ro, key])
    return [
        f"ring|{z0:.4f} {z1:.4f}|{_loop(ro)}|{_loop(ri)}|boss"
        for z0, z1, ri, ro, _ in rows
    ]


def wheel_lines(path: str, layers: list) -> list[str]:
    vol = dt.check(dt.mesh(layers))[1]
    r = max(float(ro.max()) for _, _, ann in layers for _, ro in ann)
    return [
        f"part|{path}",
        *ring_lines(layers),
        f"expect|vol {vol:.1f} {vol * 0.003:.1f}|box {-r:.3f} {r:.3f} {-r:.3f} {r:.3f} 0 {dt.BELT_W} 0.05",
        "save",
    ]


def track_y() -> tuple[float, float]:
    """Belt inner / outer face, |y| (08 §3: inner edge SIDE_GAP off the plate edge)."""
    y0 = PLATE_W / 2 + dt.SIDE_GAP
    return y0, y0 + dt.BELT_W


def belt_envelope_lines(path: str, side: int) -> list[str]:
    """The belt as a stadium annulus (lugs left out) for interference only."""
    ri, ro = dt.R_RUN, dt.outer_r()
    xd, xi, z = dt.X_DRIVE, dt.belt_fit()["x_fit"], dt.Z_AXLE
    y0, y1 = track_y()
    ya, yb = (y0, y1) if side > 0 else (-y1, -y0)

    def stadium(
        r: float,
    ) -> str:  # Top plane: sketch (x, -z), arcs CCW in sketch coords
        return (
            f"M {xd} {-z - r} A {xd} {-z} {xd} {-z + r} L {xi} {-z + r} "
            f"A {xi} {-z} {xi} {-z - r}"
        )

    c = xd - xi
    vol = (math.pi * (ro * ro - ri * ri) + 2 * c * (ro - ri)) * dt.BELT_W
    return [
        f"part|{path}",
        f"prof|{ya} {yb}|{stadium(ro)}|boss|top",
        f"prof|{ya - 0.1} {yb + 0.1}|{stadium(ri)}|cut|top",
        f"expect|vol {vol:.1f} {vol * 0.002:.1f}|box {xi - ro:.3f} {xd + ro:.3f} {ya} {yb} {z - ro:.3f} {z + ro:.3f} 0.05",
        "save",
    ]


# wheel part frame -> chassis: part X -> X, part Z (outboard -> inboard) -> -Y on the
# left, +Y on the right; part Y completes a right-handed frame
ROT_WHEEL_L = [1, 0, 0, 0, 0, -1, 0, 1, 0]
ROT_WHEEL_R = [1, 0, 0, 0, 0, 1, 0, -1, 0]


def wheel_at(x: float, side: int) -> tuple[list[float], tuple[float, float, float]]:
    y_out = track_y()[1]
    return (ROT_WHEEL_L if side > 0 else ROT_WHEEL_R), (x, side * y_out, dt.Z_AXLE)


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


# T3: printed parts and their material (07 / Bambu TDS, g/cm³). Envelopes (motor, Pi
# stack, boards, belt stand-ins) and analysis-only parts are left out.
RHO = {"PET-CF": 1.29, "TPU": 1.22}
PART_MATERIAL = {
    "RB-PRT-001": "PET-CF",
    "RB-PRT-002": "PET-CF",
    "RB-PRT-003": "PET-CF",
    "RB-PRT-010": "PET-CF",
    "RB-PRT-011": "PET-CF",
    "RB-PRT-020": "PET-CF",
    "RB-PRT-021": "PET-CF",
}


def mass_report(lines: list[str], out: str) -> list[tuple]:
    """Per-part mass + centroid from the engine's MASS lines, and the printed-part
    total + CoG in the chassis frame using each component's transform (v' = R v + t)."""
    parts: dict[str, tuple[float, list[float]]] = {}
    for ln in out.splitlines():
        if ln.startswith("MASS|"):
            _, name, vol, com = ln.split("|")
            parts[name.upper()] = (float(vol), [float(v) for v in com.split()])
    rows = []
    for name, (vol, com) in parts.items():
        mat = PART_MATERIAL.get(name[:10])
        if mat:
            rows.append((name, mat, vol, vol / 1000 * RHO[mat], com))
    print("\nMASS (printed parts, part frame)")
    for name, mat, vol, g, com in rows:
        print(
            f"  {name:40s} {mat:6s} {vol:10.1f} mm3 {g:7.1f} g  com ({com[0]:.1f}, {com[1]:.1f}, {com[2]:.1f})"
        )
    tot, mom = 0.0, [0.0, 0.0, 0.0]
    for ln in lines:
        if not ln.startswith("comp|"):
            continue
        _, cname, path, nums, *_ = ln.split("|")
        key = path.split("\\")[-1].upper()
        hit = next((r for r in rows if r[0] == key), None)
        if hit is None:
            continue
        n = [float(v) for v in nums.split()]
        c = hit[4]
        p = [sum(n[i * 3 + j] * c[j] for j in range(3)) + n[9 + i] for i in range(3)]
        tot += hit[3]
        mom = [m + hit[3] * v for m, v in zip(mom, p)]
    if tot:
        cog = [m / tot for m in mom]
        print(
            f"  printed parts in the assembly: {tot:.1f} g, CoG ({cog[0]:.1f}, {cog[1]:.1f}, {cog[2]:.1f}) mm"
        )
    return rows


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
    mass_report(lines, out)
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
