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
# D5 (tick 45): the plate's motor-mount pockets sit in an 8 mm stack (plate 4 + boss 4), so
# 7.2 left a 0.8 mm floor a hot insert can push through; 6.7 = the 5.7 insert + 1.0 for the
# displaced melt, floor 1.3 (>= the 1.2 wall rule)
MOUNT_INS_DEPTH = 6.7
CLR_M3, CBORE_M3, CBORE_DEPTH = 3.4, 6.5, 2.0
UNDER_BOSS_Z = -8.0  # plate 4 + 4 mm under-boss for the motor-mount inserts (07 F2)
RIB_T, RIB_H = 1.2, 3.6  # 07 §1: rib <= 3 x thickness tall
# W3: the plate's grid ribs 1.2 x 3.6 -> 2.4 x 4.0: bottoms at -8 with the load ribs and
# insert bosses (no clearance lost), stiffer, and wide enough to round r 1.0 (a 1.2 rib
# couldn't be filleted, S1a2)
PLATE_RIB_T, PLATE_RIB_H = 2.4, 4.0

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
GUIDE_Y, CLAMP_Y = (30.5, 41.5), 36.0  # carriage guide slots and clamp slot, |y|
# D5c: guide slots 31 / 41 -> 30.5 / 41.5: the webs to the clamp slot were 0.95 mm (0.86
# after S1a3's fillets), now 1.45; the carriage rails follow GUIDE_Y
GUIDE_W = 4.7  # 4.0 rail + 0.35/side slip (05)
RAIL_L = 20.0  # TBD with the carriage design
JACK_BLOCK_X, JACK_BLOCK_Y, JACK_BLOCK_Z = (-38.0, -28.0), (31.0, 42.0), (0.0, 10.0)
JACK_Y, JACK_Z = 36.5, 5.0  # F4b: M3 jack screw in an insert along X

# P14 motor-bell relief: x span, |y| span, depth
BELL_POCKET = ((-11.0, 20.0), (31.0, 53.0), 2.0)

# Bulkhead foot (06 §5, F1): only x >= 78.5 is clear of the motor-mount feet.
BULK_X = 81.5
BULK_HOLES_Y = (-22.0, 0.0, 22.0)
BULK_TAB_Y, BULK_TAB = 11.0, (4.6, 10.4)  # locating-tab slots (X x Y)

# Pi deck posts (F5): clear of the reflex board (x -40..25, |y| <= 30), the mount
# feet (x >= 27.4, |y| >= 13.4) and the follower carriages (|y| >= 28 aft of x -40).
DECK_Z = 24.0  # deck underside (06 §3 height table)
DECK_POSTS = [(30.0, -8.0), (30.0, 8.0), (-70.0, -20.0), (-70.0, 20.0)]
# P4b (R1-F1): rear pair -48 -> -70. At -48 their deck screws sat under the Pi board
# (x -64.5 .. 22.5 with ports) and were trapped once the stack was on.
REFLEX_STANDOFF = 5.0
WIRE_SLOT = (
    35.0,
    53.0,
    0.0,
    3.0,
)  # forward wire slot x0 x1 y r (between the mount feet). D5b: x1 55 -> 53: at 55 its end
# (x 58) came within 0.12-0.24 mm of the knee counterbore (61, 2.4) r 3.25, the plate's
# min wall in meshcheck since tick 5

# W3: long ribs through the insert-boss centres (|y| 21.5; at 25 their edge ran 0.1 mm
# past the bosses' and no fillet would take the sliver); the y 0 rib stops before the wire
# slot and the knee counterbore; the front cross rib 60 -> 66 clears that counterbore
LONG_RIBS = ((-21.5, (-80.0, 75.0)), (0.0, (-80.0, 30.0)), (21.5, (-80.0, 75.0)))
CROSS_RIBS_X, CROSS_RIBS_Y = (-60.0, -20.0, 20.0, 66.0), (-44.0, 44.0)
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
        cut.append(("cut", ("circle", x, y, INS_HOLE / 2), -MOUNT_INS_DEPTH, 0.0))
    # bottom ribs
    for y, (lx0, lx1) in LONG_RIBS:
        add.append(
            (
                "add",
                ("rect", lx0, lx1, y - PLATE_RIB_T / 2, y + PLATE_RIB_T / 2),
                -PLATE_T - PLATE_RIB_H,
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
        # W3: the x -60 rib ran through the follower guide/clamp slots (x -75..-45), which
        # cut it into 0.6-1 mm slivers (no use, and no fillet would take them): stop it inside
        ys = CROSS_RIBS_Y if x > -40 else (-26.0, 26.0)
        add.append(
            (
                "add",
                ("rect", x - PLATE_RIB_T / 2, x + PLATE_RIB_T / 2, *ys),
                -PLATE_T - PLATE_RIB_H,
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
    # P14 (Ben, 2026-10-31): the motors don't sit exactly flat, and the can/encoder end
    # would bear on the plate and lever the bracket: a 2 mm deep relief under each
    # (not through), clear of the reflex standoff boss (|y| 30.6) and 2 mm in from the edge
    for sgn in (-1, 1):
        ys = sorted((sgn * BELL_POCKET[1][0], sgn * BELL_POCKET[1][1]))
        cut.append(("cut", ("rect", *BELL_POCKET[0], *ys), -BELL_POCKET[2], 0.0))
    # bulkhead foot: screws up from below, locating-tab slots. D5b: no counterbores here:
    # at x 81.5 an r 3.25 counterbore reached x 84.75, a 0.25 mm wall at the plate front
    # (and the foot is too narrow to move the screw line back, D4). Low-head M3 (DIN 7984,
    # 2 mm head) sits on the belly instead.
    for y in BULK_HOLES_Y:
        cut.append(("all", ("circle", BULK_X, y, CLR_M3 / 2), 0, 0))
    kx, ky = BH_KNEE_HOLE
    cut.append(("all", ("circle", kx, ky, CLR_M3 / 2), 0, 0))
    cut.append(
        (
            "cut",
            ("circle", kx, ky, CBORE_M3 / 2),
            -PLATE_T - PLATE_RIB_H,
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
    # Q19: slots for the canopy's side tongues (bearing in x; 0.1 clearance all round)
    (_, _), (tx0, tx1), _, cl = CAN_TAB
    for sgn in (-1, 1):
        y0, y1 = sorted((sgn * (CAN_HW - CAN_T - cl), sgn * (CAN_HW + cl)))
        cut.append(("all", ("rect", tx0 - cl, tx1 + cl, y0, y1), 0, 0))
    # P6b: the canopy's rear screws, M3 x 10 button up from the belly into the inserts in
    # its apron bosses (07 F9 amendment); square edge for the head, clear of the ribs
    for sgn in (-1, 1):
        cut.append(
            ("all", ("circle", CAN_BOSS[0], sgn * CAN_BOSS[1], CLR_M3 / 2), 0, 0)
        )
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


def belly_edge_length(step: float = 0.05) -> float:
    """Edge length of the plate's z -8 footprint (features whose bottom is at -8), from a
    raster: boundary pixel edges, with the staircase on the boss circles taken out."""
    import numpy as np

    xs = np.arange(-PLATE_L / 2 + step / 2, PLATE_L / 2, step)
    ys = np.arange(-PLATE_W / 2 + step / 2, PLATE_W / 2, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    feats = plate_features()
    m = np.zeros_like(X, dtype=bool)
    for op, sh, z0, _ in feats:
        if op == "add" and abs(z0 - UNDER_BOSS_Z) < 1e-6:
            m |= shape_mask(sh, X, Y)
    for op, sh, z0, z1 in feats:
        if op == "all" or (op == "cut" and z0 <= UNDER_BOSS_Z + 1e-6):
            m &= ~shape_mask(sh, X, Y)
    n = np.count_nonzero(m[1:, :] != m[:-1, :]) + np.count_nonzero(
        m[:, 1:] != m[:, :-1]
    )
    raw = n * step
    # circles read 4/pi long on a raster; take that out for the boss rims (and the holes)
    circ = sum(
        2 * math.pi * s[3]
        for op, s, z0, _ in feats
        if s[0] == "circle"
        and (abs(z0 - UNDER_BOSS_Z) < 1e-6 or op != "add")
        and (op == "add" or z0 <= UNDER_BOSS_Z + 1e-6)
    )
    return raw - circ * (4 / math.pi - 1)


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
    # P14: r 1.0 round each relief's floor edge (concave: adds (1 - pi/4) r² per mm)
    (bx0, bx1), (by0, by1), bd = BELL_POCKET
    dvp = (1 - math.pi / 4) * PLATE_EDGE_R**2 * 2 * ((bx1 - bx0) + (by1 - by0))
    for sgn in (1, -1):
        ya, yb = sorted((sgn * by0, sgn * by1))
        lines.append(
            f"filletface|{PLATE_EDGE_R}|1|{-bd}|{bx0 - 1} {ya - 1} {bx1 + 1} {yb + 1}|1|{dvp:.2f} {0.15 * dvp:.2f}"
        )
        vol += dvp
    # S1a2 + W3: every bottom face at z -8 (grid ribs, load ribs, insert bosses, now one
    # level) rounded r 1.0, inner loops included (the grid's cells). Edge length from a
    # raster of that footprint (belly_edge_length).
    dvb = (1 - math.pi / 4) * PLATE_EDGE_R**2 * belly_edge_length()
    lines.append(
        f"filletface|{PLATE_EDGE_R}|-1|{UNDER_BOSS_Z}|{-hx} {-hy} {hx} {hy}|any|{-dvb:.2f} {0.15 * dvb:.2f}|all"
    )
    vol -= dvb
    # S1a3: r 1.0 on the slot and hole edges in the belly (z -4), loop by loop (not the
    # rib roots, which are concave and one sits 1.05 mm from a counterbore). Edge lengths
    # by hand: guide slots 2 x (2 x 40 + 2 pi 2.35) + clamp slot (2 x 10 + 2 pi 1.7) per
    # side; wire slot (2 x 20 + 2 pi 3) + knee counterbore pi 6.5; tab slots 2 x 30 +
    # three counterbores 3 x pi 6.5
    a0, a1 = AXLE_X_MID - TRAVEL / 2, AXLE_X_MID + TRAVEL / 2
    g_len = 2 * (a1 + RAIL_L / 2 - (a0 - RAIL_L / 2)) + 2 * math.pi * GUIDE_W / 2
    c_len = 2 * (a1 - a0) + 2 * math.pi * CLR_M3 / 2
    w_len = 2 * (WIRE_SLOT[1] - WIRE_SLOT[0]) + 2 * math.pi * WIRE_SLOT[3]
    cb = math.pi * CBORE_M3
    t_len = 2 * 2 * (BULK_TAB[0] + BULK_TAB[1])
    groups = [
        (f"{a0 - RAIL_L / 2 - 3} 26 {a1 + RAIL_L / 2 + 3} 46", 2 * g_len + c_len),
        (f"{a0 - RAIL_L / 2 - 3} -46 {a1 + RAIL_L / 2 + 3} -26", 2 * g_len + c_len),
        (f"{WIRE_SLOT[0] - 5} -5 {BH_KNEE_HOLE[0] + 5} 8", w_len + cb),
        # tab slots only: the bulkhead screw holes (no counterbores since D5b) keep a square
        # edge for the screw heads to seat on
        (f"{BULK_X - 5} 4 {hx} 18", t_len / 2),
        (f"{BULK_X - 5} -18 {hx} -4", t_len / 2),
    ]
    for box, length in groups:
        dvl = (1 - math.pi / 4) * PLATE_EDGE_R**2 * length
        lines.append(
            f"filletface|{PLATE_EDGE_R}|-1|{-PLATE_T}|{-hx} {-hy} {hx} {hy}|any|{-dvl:.2f} {0.15 * dvl:.2f}|loops:{box}"
        )
        vol -= dvl
    # D1b (tick 82, REJECTED): an r 2 round of each jack block's root (one 4-edge feature)
    # made S1m 9.97 -> 13.3, S1a 11.6 -> 14.8, S1b 3.7 -> 4.3 (half mesh 5.0 -> 7.9) at the
    # vertex where the fillet's corner blend meets the plate (-40 / -26, +-29, 0). Removed.
    lines += [
        PART_LABELS["plate"],
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
DECK_X = (
    -75.0,
    25.0,
)  # covers the Pi board (x -64.5 .. 22.5 after Rz180) + the rear posts (P4b)
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
        PART_LABELS["deck"],
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


# E4 hero renders (tick 76): eye direction (target -> eye), up vector, perspective. "face": a
# 5-year-old's eye ~40 cm off the floor, ~1 m in front (looking down ~17°).
HERO_VIEWS = (
    ("three_quarter", "1 0.65 0.45", "0 0 1"),
    ("face", "1 0 0.3", "0 0 1"),
    ("rear_quarter", "-1 -0.7 0.5", "0 0 1"),
    ("top", "0 0 1", "1 0 0"),
)


# R3 (tick 78): part number + revision, 4 mm bold, cut 0.6 into a hidden face. Volumes are
# not predicted (~20 mm3, inside every part's expect tolerance); the FEA copies drop them.
#   plate: belly cell (x -11.5..11.5, y -8.5..-1, clear of ribs/slots: STL ray scan), read
#   from below; canopy: the left skirt's inner face (y 51.2), z 40..44, read from inside
#   (seen from inside, Top-plane text is the whole line turned 180°; SW's escapement turns
#   each glyph in place and "mirror" flips the whole line, so: mirror + 180° + the string
#   reversed. Checked by ray-casting exported test walls, tick 78. No hyphen: the reversed
#   string with "-" cut nothing, twice)
PART_LABELS = {
    "plate": "text|front|11.5 -6.75|-4.5 -3.4|4|RB-001 r1|mirror",
    "canopy": f"text|top|-10 -40|50.9 51.8|4|{'RB 004 r1'[::-1]}|mirror|180",
    # deck underside (faces the plate), clear cell x -15.5..15.5, y -21..-13.5 (STL scan)
    "deck": "text|front|11.5 -19.35|-3.5 -2.4|4|RB-003 r1|mirror",
}


def trackframe_label(side: int) -> str:
    """R3: on the frame plate's inner face (|y| 93.5, behind the belt), centred x 0, z 12..16
    (clear: STL scan). Read from inside: the +y frame is seen from its back (mirror + 180° +
    reversed, as the canopy), the -y frame from the front (plain + 180° + reversed); 180° is
    per glyph, so the order needs reversing in both."""
    y0 = trackframe_geom()["y"][0]
    if side > 0:
        return f"text|top|9 -12|{y0 - 0.3:.2f} {y0 + 0.6:.2f}|4|{'RB 040 r1'[::-1]}|mirror|180"
    return f"text|top|-8.5 -12|{-y0 - 0.6:.2f} {-y0 + 0.3:.2f}|4|{'RB 041 r1'[::-1]}|plain|180"


def rebuild_manifest(win: str) -> list[str]:
    cad = win + r"\CAD"
    plate = cad + r"\parts\RB-PRT-001_base_plate.SLDPRT"
    motor = cad + r"\library\TT_Motor_envelope_v2.SLDPRT"
    pi = cad + r"\library\Pi5_stack_envelope.SLDPRT"
    face = cad + r"\library\FNK0104_face_envelope.SLDPRT"
    reflex = cad + r"\library\reflex_board_envelope.SLDPRT"
    bulkhead = cad + r"\parts\RB-PRT-002_bulkhead.SLDPRT"
    deck = cad + r"\parts\RB-PRT-003_pi_deck.SLDPRT"  # P4
    canopy = cad + r"\parts\RB-PRT-004_canopy.SLDPRT"  # P6
    tf_l = cad + r"\parts\RB-PRT-040_trackframe_L.SLDPRT"  # P2o
    tf_r = cad + r"\parts\RB-PRT-041_trackframe_R.SLDPRT"
    canopy_fea = cad + r"\fea\FEA-canopy_S8.SLDPRT"  # P6c heel study S8, analysis only
    car_l = cad + r"\parts\RB-PRT-030_carriage_L.SLDPRT"  # P5
    car_r = cad + r"\parts\RB-PRT-031_carriage_R.SLDPRT"
    sprocket = cad + r"\parts\RB-PRT-020_sprocket.SLDPRT"  # 08, outrigger variant (P2o)
    idler = cad + r"\parts\RB-PRT-021_idler.SLDPRT"  # 08, 2 x 624
    road = cad + r"\parts\RB-PRT-022_road_disc.SLDPRT"  # 08 rev 1, 684, x 8 (P13b)
    road_axle = cad + r"\library\road_axle_envelope.SLDPRT"
    # T11: the installed belt, native, replaces the stadium envelopes for fit checks
    belt_l = cad + r"\parts\RB-PRT-050_belt_L.SLDPRT"
    belt_r = cad + r"\parts\RB-PRT-051_belt_R.SLDPRT"
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
        *canopy_lines(canopy),
        *trackframe_lines(tf_l, +1),
        *trackframe_lines(tf_r, -1),
        *carriage_lines(car_l, mirror=False),
        *carriage_lines(car_r, mirror=True),
        *mount_v2_lines(mount_r, mirror=False),
        *mount_v2_lines(mount_l, mirror=True),
        *wheel_lines(sprocket, dt.sprocket_layers(True)),
        *wheel_lines(idler, dt.idler_layers(2)),
        *wheel_lines(road, dt.road_wheel_layers()),
        *road_axle_lines(road_axle),
        *belt_native_lines(belt_l, +1),
        *belt_native_lines(belt_r, -1),
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
        f"comp|canopy|{canopy}|{row(ROT_I, (0, 0, 0))}",
        f"comp|trackframe_L|{tf_l}|{row(ROT_I, (0, 0, 0))}",
        f"comp|trackframe_R|{tf_r}|{row(ROT_I, (0, 0, 0))}",
        f"comp|carriage_L|{car_l}|{row(ROT_I, (dt.belt_fit()['x_fit'], 0, 0))}",
        f"comp|carriage_R|{car_r}|{row(ROT_I, (dt.belt_fit()['x_fit'], 0, 0))}",
        *[
            f"comp|{n}_{sd}|{p}|{row(*wheel_at(x, s, z, wheel_phase(x, z)))}"
            for n, p, x, z in (
                ("sprocket", sprocket, dt.X_DRIVE, dt.Z_AXLE),
                ("idler", idler, dt.belt_fit()["x_fit"], idler_z()),
            )
            for sd, s in (("L", +1), ("R", -1))
        ],
        *[
            f"comp|road{i + 1}{'i' if ib else 'o'}_{sd}|{road}|{row(*road_disc_at(x, z, s, ib))}"
            for i, (x, z) in enumerate(road_axles())
            for sd, s in (("L", +1), ("R", -1))
            for ib in (True, False)
        ],
        *[
            f"comp|raxle{i + 1}_{sd}|{road_axle}|{row(ROT_I, (x, s * track_y()[0] if s > 0 else -track_y()[1], z))}"
            for i, (x, z) in enumerate(road_axles())
            for sd, s in (("L", +1), ("R", -1))
        ],
        f"comp|belt_L|{belt_l}|{row(ROT_I, (0, 0, 0))}",
        f"comp|belt_R|{belt_r}|{row(ROT_I, (0, 0, 0))}",
        f"comp|face|{face}|{row(*face_on_bulkhead())}",
        "interfere",
        "asmsave",
        # T10: analysis-only part, plate + both mounts as one body (not printed)
        *fea_plate_mounts_lines(cad + r"\\fea\\FEA-plate_mounts.SLDPRT"),
        *canopy_fea_lines(canopy_fea),
        f"shot|{asm}|{shots}",
        *[f"view|{asm}|{win}\\shots\\hero_{tag}.bmp|{eye}|{up}|persp" for tag, eye, up in HERO_VIEWS],
        f"close|{asm}",
        f"shot|{plate}|{win}\\shots\\plate",
        f"close|{plate}",
        f"shot|{bulkhead}|{win}\\shots\\bulkhead",
        f"close|{bulkhead}",
        f"shot|{canopy}|{win}\\shots\\canopy",
        f"close|{canopy}",
        # printed parts -> STL in chassis coordinates (T1); meshcheck reads these
        *[
            f"stl|{p}|{cad}\\exports\\gen\\{n}.stl"
            for p, n in (
                (plate, "RB-PRT-001_base_plate"),
                (bulkhead, "RB-PRT-002_bulkhead"),
                (deck, "RB-PRT-003_pi_deck"),
                (canopy, "RB-PRT-004_canopy"),
                (tf_l, "RB-PRT-040_trackframe_L"),
                (tf_r, "RB-PRT-041_trackframe_R"),
                (car_l, "RB-PRT-030_carriage_L"),
                (car_r, "RB-PRT-031_carriage_R"),
                (mount_r, "RB-PRT-010_motor_mount_R"),
                (mount_l, "RB-PRT-011_motor_mount_L"),
                (sprocket, "RB-PRT-020_sprocket"),
                (idler, "RB-PRT-021_idler"),
                (road, "RB-PRT-022_road_disc"),
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
    # S2a side cheeks (pre-tilt: the wall's thickness, beyond its sides)
    cw, ch = BH_CHEEK
    for sgn in (-1, 1):
        ys_ = sorted((sgn * hw, sgn * (hw + cw)))
        pre.append(("add", ("box", x0, x1, *ys_, 0.0, ch)))
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
    # D2 (tick 77): full-radius ends (box + two Ø2 end cylinders), same overall length;
    # they were square-ended boxes on the face side
    sr_end = BH_SLOT_W / 2
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
                    sy - half + sr_end,
                    sy + half - sr_end,
                    sz + dz - BH_SLOT_W / 2,
                    sz + dz + BH_SLOT_W / 2,
                ),
            )
        )
        for ye in (sy - half + sr_end, sy + half - sr_end):
            pre.append(("cut", ("cylx", ye, sz + dz, x0 - 0.1, x1 + 0.1, sr_end)))
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
    yh = BH_W / 2 + BH_CHEEK[0] + 1  # S2a: the cheeks reach |y| BH_W / 2 + 5
    ys = np.arange(-yh + step / 2, yh, step)
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


BH_SIDE_EDGE = 266.6  # S1b: edge length round one outer side face (STL, tick 32)
# S2a (Q22 F1, tick 65): side cheeks close the 9.5 mm finger slot between the wall's sides
# (|y| 47) and the belts (56.5) at the front corners: the wall (its 3 mm, not the flange,
# which would reach the motor mounts at x 77.8) continued sideways to |y| 52 from the bottom
# to z 30 (pre-tilt height 31.1). Leaves 4.5 to the belt.
BH_CHEEK = (5.0, 31.1)


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
    # S1b2 (tick 59): r 1.0 on the front face's openings, done BEFORE the tilt while the
    # face is the plane x = BH_XF: the window rim, the two sonar holes and the camera hole
    # (inner loops whose centre is at y <= 10; the speaker-grille slots at y 24 are 2 mm
    # wide and would round right through)
    aw, ah = FACE_AA[1] + 2.0, FACE_AA[0] + 2.0
    face_len = 2 * (aw + ah) + 2 * math.pi * 2 * BH_SONAR_R + 2 * math.pi * BH_CAM[2]
    dvf = (1 - math.pi / 4) * PLATE_EDGE_R**2 * face_len
    lines.append(
        f"filletface|{PLATE_EDGE_R}|x:1|{BH_XF}|-50 -5 50 130|1|{-dvf:.2f} {0.15 * dvf:.2f}|loops:-45 10 10 125"
    )
    # S1b3 (tick 63): r 1.0 on the wall's top front edge (x BH_XF, z BH_H, along y), the
    # top of the "head", also pre-tilt. Between the side flanges' ends (|y| BH_W / 2)
    dvt = (1 - math.pi / 4) * PLATE_EDGE_R**2 * BH_W
    lines.append(
        f"fillet|{PLATE_EDGE_R}|y|{BH_XF - 0.2} {-BH_W / 2 - 0.1} {BH_H - 0.2} {BH_XF + 0.2} {BH_W / 2 + 0.1} {BH_H + 0.2}|1|{-dvt:.2f} {0.2 * dvt:.2f}"
    )
    lines.append(f"rotbody|{BH_PIVOT[0]} {BH_PIVOT[1]} {BH_PIVOT[2]}|y|{-BH_TILT}")
    for op, sh in post:
        if sh[0] == "box" and op == "add":
            _, x0, x1, y0, y1, z0, z1 = sh
            lines.append(f"box|{x0} {x1}|{y0} {y1}|{z0} {z1}")
        else:
            lines.append(emit(op, sh))
    vol, bb = bulkhead_volume_numeric()
    vol -= (
        (1 - math.pi / 4)
        * PLATE_EDGE_R**2
        * (
            2 * (FACE_AA[1] + FACE_AA[0] + 4.0)
            + 2 * math.pi * 2 * BH_SONAR_R
            + 2 * math.pi * BH_CAM[2]
        )
    )  # S1b2 front-face opening rounds
    vol -= (1 - math.pi / 4) * PLATE_EDGE_R**2 * BH_W  # S1b3 top front edge
    # S1b (kid safety): r 1.0 round the two outer side faces (|y| 47, normals +-y): their
    # outer loops are the wall's side edges, front, back, top and foot. Edge length per
    # side, all convex, measured from the generated STL (tick 32): 266.6 mm
    ys = BH_W / 2
    # S2a: the cheek covers the side face's front + bottom edge over its height (convex,
    # out) and adds two concave edges where it meets the side (in): net 266.6 - 2 x 34.1
    cw, ch = BH_CHEEK
    q = (1 - math.pi / 4) * PLATE_EDGE_R**2
    cov = ch + BH_T
    dvs = q * (BH_SIDE_EDGE - 2 * cov)
    dvc = q * 2 * (ch + BH_T)  # cheek outer face: its whole outline, convex
    for sgn in (1, -1):
        lines.append(
            f"filletface|{PLATE_EDGE_R}|y:{sgn}|{sgn * ys:.2f}|30 -10 100 130|1|{-dvs:.2f} {0.2 * dvs:.2f}"
        )
        vol -= dvs
        lines.append(
            f"filletface|{PLATE_EDGE_R}|y:{sgn}|{sgn * (ys + cw):.2f}|30 -10 100 130|1|{-dvc:.2f} {0.2 * dvc:.2f}"
        )
        vol -= dvc
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
MM_ROOT_R = 2.2  # 07 fil_in at load roots (D1); not 2.0: an r 2.0 y-cylinder is what S2 selects as a motor insert
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
    # D1 (tick 36): r 2.0 (07 fil_in at load roots) in the concave step where the end
    # stop's top (z MM_TOP - 4) meets the upright's end face (x MM_X[0]), y yi..MM_FACE:
    # S2's half-mesh peak after D10. Not the vertical corner at y MM_FACE: the gearbox's
    # end corner bears there. A concave 90° round adds (1 - pi/4) r² per mm.
    xa = MM_X[0] * (-1 if mirror else 1)
    zs = MM_TOP - 4.0
    yi = MM_FACE - MM_T
    dvs = (1 - math.pi / 4) * MM_ROOT_R**2 * (MM_FACE - yi)
    vol += dvs
    return [
        f"part|{path}",
        *emit_ops(ops),
        f"fillet|{MM_ROOT_R}|y|{xa - 0.1} {yi - 0.1} {zs - 0.1} {xa + 0.1} {MM_FACE + 0.1} {zs + 0.1}|1|{dvs:.2f} {0.15 * dvs:.2f}",
        # R3 (tick 80): on the foot's underside (on the plate), 3 mm text read from below,
        # centred (5.25 / -5.15, -32.4): the middle of a valid 26 x 8 clear window (STL scan
        # per part; the first try at y -37.5 cut through the foot's screw holes)
        f"text|front|{13.9 if mirror else 3.5} -33.9|-0.5 0.6|3|RB-{'011' if mirror else '010'} r1|mirror",
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
    plate = [ln for ln in plate_lines(path) if not ln.startswith("text|")]  # R3 labels: not in FEA
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


# ------------------------------------------- follower carriage (05, 06 §7, 08; P5)
# Part frame: chassis y and z, x measured from the idler axle (placed at the taut station
# dt.belt_fit()["x_fit"]); left part, the right one is its Y-mirror. First cut: rails in
# the plate's guide slots, clamp over the clamp slot, a pad for the jack screw, and a
# pedestal at the plate edge carrying the Ø12 journal boss into the idler's open inboard
# side (up to 0.5 mm short of its hub tube, 05 "support the overhang").
CAR_L = RAIL_L  # 20, the rail length the plate slots were sized for
CAR_FOOT_T = 4.0  # 05: clamp foot ~4
CAR_FOOT_Y = (
    28.0,
    53.0,
)  # inboard of the plate edge (55) with margin at the rear corner
CAR_RAIL_W, CAR_RAIL_D = (
    4.0,
    3.6,
)  # 4.0 in the 4.7 slots (0.35/side); stops 0.4 above the belly
CAR_PED = (
    10.0,
    40.0,
)  # pedestal half-length in x, inboard y (outboard = foot edge); the
# first cut (6.0, 44.0) twisted at its root under the 26 mm-outboard axle load (S6 16.5 MPa)
CAR_BOSS_R = (
    7.5  # S6: Ø12 bent at its root (12.9 MPa); the idler's inboard opening is ~r 20
)
CAR_BORE = 4.1  # 05: slip for the Ø4 shoulder
CAR_CLAMP_BOSS_Z = (
    6.0  # top of the open clamp-insert boss (insert 0 .. 5.7 from below, tick 68)
)
CAR_PAD = (
    6.0,
    (32.0, 41.0),
    9.0,
)  # jack pad: x from, y span, top z (screw at z 5, |y| 36.5)


def idler_tube_inboard() -> float:
    """|y| of the idler hub tube's inboard end (the boss stops 0.5 short of it)."""
    tube_end = dt.BELT_W / 2 + dt.BRG_W
    return track_y()[1] - tube_end


def carriage_features(mirror: bool) -> list[tuple]:
    hx = CAR_L / 2
    y0, y1 = CAR_FOOT_Y
    za = idler_z()  # 08 rev 1: 10.5
    boss_y1 = idler_tube_inboard() - 0.5
    px, (pa, pb), pz = CAR_PAD
    ops: list[tuple] = [
        ("add", ("box", -hx, hx, y0, y1, 0.0, CAR_FOOT_T)),
        *[
            (
                "add",
                (
                    "box",
                    -hx,
                    hx,
                    gy - CAR_RAIL_W / 2,
                    gy + CAR_RAIL_W / 2,
                    -CAR_RAIL_D,
                    0.0,
                ),
            )
            for gy in GUIDE_Y
        ],
        # pedestal up to the boss top, so the boss leaves a clean vertical face at y1
        (
            "add",
            (
                "box",
                -CAR_PED[0],
                CAR_PED[0],
                CAR_PED[1],
                y1,
                CAR_FOOT_T,
                za + CAR_BOSS_R,
            ),
        ),
        ("add", ("cyly", 0.0, za, CAR_PED[1], boss_y1, CAR_BOSS_R)),
        ("add", ("box", px, hx, pa, pb, CAR_FOOT_T, pz)),
        ("cut", ("cyly", 0.0, za, CAR_PED[1] - 0.1, boss_y1 + 0.1, CAR_BORE / 2)),
        # R2a: the clamp screw comes up from under the plate (through the clamp slot) into
        # an M3 insert, so a track swap needs one key and no blind nyloc under the plate
        # (05 option). Tick 68 (idler axle 13.5 -> 10.5): the insert is pressed UP from the
        # foot's underside into a short open boss (top CAR_CLAMP_BOSS_Z 6.0), so the axle
        # bolt's head on the pedestal face (Ø8, z 6.5-14.5) clears it, and the clamp pulls
        # the insert's brass face onto the plate instead of the plastic over it
        ("add", ("cylz", 0.0, CLAMP_Y, CAR_FOOT_T, CAR_CLAMP_BOSS_Z, INS_BOSS / 2)),
        (
            "cut",
            ("cylz", 0.0, CLAMP_Y, -0.1, CAR_CLAMP_BOSS_Z + 0.1, INS_HOLE / 2),
        ),
    ]
    if not mirror:
        return ops

    def my(sh: tuple) -> tuple:
        if sh[0] == "box":
            _, a, b, c, d, e, f = sh
            return ("box", a, b, -d, -c, e, f)
        if sh[0] == "cyly":
            _, cx, cz, c, d, r = sh
            return ("cyly", cx, cz, -d, -c, r)
        if sh[0] == "cylz":
            _, cx, cy, e, f, r = sh
            return ("cylz", cx, -cy, e, f, r)
        raise ValueError(sh[0])

    return [(op, my(sh)) for op, sh in ops]


def carriage_lines(path: str, mirror: bool) -> list[str]:
    ops = carriage_features(mirror)
    yb = (-80.0, -20.0) if mirror else (20.0, 80.0)
    vol, bb = solid_volume_numeric(ops, ((-12.0, 12.0), yb, (-5.0, 23.0)))
    return [
        f"part|{path}",
        *emit_ops(ops),
        f"expect|vol {vol:.1f} {vol * 0.01:.1f}|box {' '.join(f'{v:.2f}' for v in bb)} 0.35",
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
    # S1c (kid safety): r 1.0 on the outboard rim, the running disc's outer edge on the bed
    # face (part z 0), the wheel edge a hand meets from the side: (1 - pi/4) r² x 2 pi R
    r0 = float(layers[0][2][0][1].max())  # bed-face layer's outer radius
    dvr = (1 - math.pi / 4) * PLATE_EDGE_R**2 * 2 * math.pi * r0
    vol -= dvr
    return [
        f"part|{path}",
        *ring_lines(layers),
        f"filletface|{PLATE_EDGE_R}|-1|0.0|{-r - 1} {-r - 1} {r + 1} {r + 1}|1|{-dvr:.2f} {0.1 * dvr:.2f}",
        f"expect|vol {vol:.1f} {vol * 0.003:.1f}|box {-r:.3f} {r:.3f} {-r:.3f} {r:.3f} 0 {layers[-1][1]:g} 0.05",
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


def wheel_at(
    x: float, side: int, z: float = dt.Z_AXLE, phase: float = 0.0
) -> tuple[list[float], tuple[float, float, float]]:
    """Wheel part -> chassis at (x, z), turned `phase` degrees about its axle (x -> z)."""
    y_out = track_y()[1]
    r = ROT_WHEEL_L if side > 0 else ROT_WHEEL_R
    if phase:
        r = matmul(rot_y(-phase), r)
    return r, (x, side * y_out, z)


# road wheels (08 rev 1 §4b, P13b): two discs per axle straddle the lug row, each with its
# 684 pocket (bed face) flush with a belt edge; axles at drivetrain.wheels() road1/road2.
def road_axles() -> list[tuple[float, float]]:
    return [(w[1], w[2]) for w in dt.wheels() if w[0].startswith("road")]


def road_disc_at(
    x: float, z: float, side: int, inboard: bool
) -> tuple[list[float], tuple[float, float, float]]:
    """Disc part -> chassis: bed face on the belt's outer (or inner) edge, facing out."""
    y_in, y_out = track_y()
    if inboard:  # bed face on the inner belt edge, the disc grows outboard
        return (ROT_WHEEL_R if side > 0 else ROT_WHEEL_L), (x, side * y_in, z)
    return (ROT_WHEEL_L if side > 0 else ROT_WHEEL_R), (x, side * y_out, z)


RW_SPACER_R = 3.5  # Ø7 spacer between the 684 inner races, under the lugs (tips 5 off)


def road_axle_lines(path: str) -> list[str]:
    """Envelope (interference only): Ø4 shoulder over the belt width + the Ø7 spacer
    from inner race to inner race (through the discs' r 3.7 shoulder holes). Part
    frame: axis Y, y 0 = the belt's inner edge. Hanger-side axle ends come with P13c."""
    bw, bd = dt.BELT_W, dt.RW_BRG_W
    v = math.pi * (4.0 * bw + (RW_SPACER_R**2 - 4.0) * (bw - 2 * bd - 0.1))
    r = RW_SPACER_R
    return [
        f"part|{path}",
        f"cyl|y|0 0|0 {bw}|2.0|boss",
        f"cyl|y|0 0|{bd + 0.05} {bw - bd - 0.05}|{r}|boss",
        f"expect|vol {v:.1f} {v * 0.005:.1f}|box {-r} {r} 0 {bw} {-r} {r} 0.05",
        "save",
    ]


# ------------------------------------------------------------- canopy (06 §6, P6)
# First cut to E1 / Q18 (a) "pebble": one PC shell, CAN_T wall, open at the bottom.
# Side profile (XZ) extruded |y| <= CAN_HW: the body over the Pi stack (top CAN_TOP) and
# a "hood" behind the bulkhead's head that rises to the wall top, so its ceiling bears on
# the two canopy lugs (S5c: the canopy holds them). The hood's front follows the wall's
# back face; there the canopy is open (the bulkhead closes it), leaving side lips at
# |y| > BH_W / 2. The skirt stops at CAN_Z0, above the motor mounts (top 26.5) and the
# carriages; the tracks cover the sides below it (belt inner edge |y| 56.5, 3.5 mm off).
# At the rear an apron reaches the plate between the carriages with 2 insert bosses:
# M3 buttons go up through the plate from the belly (hidden, E1 §3; F9 amended).
CAN_T = (
    1.8  # 06 §6 / 07: PC White 60100 (M4 closed tick 49: S8 heel PC SF 2.4, ASA 1.45)
)
CAN_HW = 53.0  # 3.5 inboard of the belt's inner edge (< 5 mm: no finger gap)
CAN_Z0 = 30.0  # skirt bottom: 3.5 over the mount tops
CAN_TOP = 95.0  # Ben (tick 49): 93 -> 97 for a 4 mm rib grid; then 97 -> 95 with S8 relaxed to 150 N: rib bottoms 3.2 over the stack top (86)
# S7 (tick 49): a bare 1.8 top sagged 19.5 mm / 78.5 MPa (PC) under the 300 N heel, the
# 1.8 skin bending between the side walls. A rib grid under the flat top, inside the
# inner rounds (x >= -77, |y| <= 45) up to the hood's back wall (x 36.2).
CAN_RIB = (1.6, 4.0)  # thickness (4 x 0.4 nozzle), depth below the inner ceiling
CAN_RIBS_Y = (-15.0, 0.0, 15.0)  # ribs along x (the keels replace the +-30 pair)
CAN_RIBS_X = (-62.0, -42.0, -22.0, -2.0, 18.0)  # ribs along y
# S7 rev 2 (tick 49): ribs alone 19.5 -> 7.0 mm, still the top spanning 106 between the
# side walls. Two lengthwise inner walls ("keels") just outside the Pi stack (|y| <= 28)
# halve that span; down to z 75 (clear of the stack's sides by 2.7, of everything below).
# Q19 (Ben, tick 51): S5k showed the canopy can't hold the bulkhead's lugs (its rear apron
# hinges; the side walls stop at z 30). Each side wall now drops a web to the plate in the
# free strip between the carriages (front <= x -45) and the motors (can end x -10), ending
# in a tongue that sits in a plate slot: the side walls become shear panels. No screws.
# Rev 2 (tick 52): webs 16 -> 30 long (S5k 0.91 mm with 16: they bent in their own plane)
CAN_TAB = (
    (-44.0, -14.0),
    (-43.0, -15.0),
    3.0,
    0.1,
)  # web x, tongue x, tongue depth, slot clearance
CAN_EDGE_R = 1.0  # P6e: outer skirt rim (kid-safety minimum, E1 1 mm family)
CAN_ROOT_R = (
    1.0  # P6g (Ben): rib/keel roots, 07 fil_in (not 1.95/2.0: S8 fixes those cylinders)
)
CAN_KEEL = (
    31.5,
    CAN_T,
    73.0,
)  # |y| centre, thickness, bottom z (75 -> 73 with the top at 95: S8 1.82 mm, keep the 20.2 depth)
CAN_X0 = -PLATE_L / 2  # rear face flush with the plate's rear edge
CAN_HOOD_D = (
    15.0  # hood depth behind the wall's back face (face board 10.6 + lugs 8.2 + room)
)
CAN_R = (
    20.0,
    8.0,
    8.0,
)  # rear plan corners (= plate R20), hood edges, top edges (E1 8)
CAN_WIN_HW = BH_W / 2 + 0.3  # front opening: the bulkhead's width + 0.3 per side
CAN_APRON_HW = 26.0  # rear apron, inside the carriages (|y| >= 28)
CAN_BOSS = (
    -80.4,
    12.0,
    12.0,
)  # rear insert bosses: x, |y|, height (clear of the deck at x -75)
CAN_LUG_HOLE = 3.9  # vertical hole through the 15° hood ceiling: 3.4 + 1.8 tan 15
CAN_LUG_GAP = 0.1  # ceiling over the lug tops (touching on the 15° tilt read as 2 x 0.1 mm3 interference, tick 47); the screws close it
# P6f (tick 74): crown along x over the body top (E1 §2: no flat panel > 60 x 60; white
# shows layer lines on flats). An arc through the top's rear and hood ends (both at
# CAN_TOP) rising CAN_CROWN in the middle; the shell keeps it on the ceiling (radius - t),
# the ribs and keels follow it (tops CAN_RIB_SINK into the skin, bottoms flat as before).
CAN_CROWN = 2.5
CAN_RIB_SINK = 0.5


def _pre2ch(xp: float, zp: float) -> tuple[float, float]:
    """Bulkhead pre-tilt (x, z) -> chassis (x, z): the same 15° back tilt as the wall."""
    c, s = math.cos(math.radians(BH_TILT)), math.sin(math.radians(BH_TILT))
    dx = xp - BH_PIVOT[0]
    return (BH_PIVOT[0] + c * dx - s * zp, s * dx + c * zp)


def canopy_crown() -> tuple[float, float, float]:
    """(x centre, z centre, outer radius) of the crowned top's arc in XZ."""
    x0, x1 = CAN_X0, canopy_profile()[2][0]
    c, sg = x1 - x0, CAN_CROWN
    r = (c * c / 4 + sg * sg) / (2 * sg)
    return (x0 + x1) / 2, CAN_TOP + sg - r, r


def can_top_z(x: float, inset: float = 0.0) -> float:
    """Height of the crowned top at x: outer skin (inset 0), ceiling (inset CAN_T)."""
    xc, zc, r = canopy_crown()
    return zc + math.sqrt((r - inset) ** 2 - (x - xc) ** 2)


def _crown_area(x0: float, x1: float, inset: float, zref: float, n: int = 400) -> float:
    """Area between the arc (at inset) and the line z = zref over x0..x1 (midpoint rule)."""
    h = (x1 - x0) / n
    return sum(can_top_z(x0 + (i + 0.5) * h, inset) - zref for i in range(n)) * h


def canopy_profile() -> list[tuple[float, float]]:
    """Outer side profile A..F (clockwise in XZ): rear bottom, rear top, hood back foot,
    hood back top, hood front top (on the wall's back-face plane), front bottom."""
    top_pre = (
        BH_H + CAN_LUG_GAP + CAN_T
    )  # hood ceiling just over the wall top / lug tops (z_pre BH_H)
    xd, zd = _pre2ch(BH_PIVOT[0] - CAN_HOOD_D, top_pre)
    xe, ze = _pre2ch(BH_PIVOT[0], top_pre)
    xf = BH_PIVOT[0] - CAN_Z0 * math.tan(math.radians(BH_TILT))
    return [
        (CAN_X0, CAN_Z0),
        (CAN_X0, CAN_TOP),
        (xd, CAN_TOP),
        (xd, zd),
        (xe, ze),
        (xf, CAN_Z0),
    ]


def _poly_area(p: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
            for i in range(len(p))
        )
        / 2
    )


def _inset_profile(p: list[tuple[float, float]], t: float) -> list[tuple[float, float]]:
    """Every edge but the open bottom (F -> A) moved inward by t (clockwise: inward is
    the right-hand normal); the shell's cavity in side view."""
    n = len(p)
    lines = []  # (point, direction) per edge i: p[i] -> p[i+1], bottom left as is
    for i in range(n):
        (x0, z0), (x1, z1) = p[i], p[(i + 1) % n]
        dx, dz = x1 - x0, z1 - z0
        ln = math.hypot(dx, dz)
        off = 0.0 if i == n - 1 else t
        nx, nz = dz / ln, -dx / ln
        lines.append(((x0 + off * nx, z0 + off * nz), (dx, dz)))

    def meet(a, b):
        (px, pz), (dx, dz) = a
        (qx, qz), (ex, ez) = b
        den = dx * ez - dz * ex
        u = ((qx - px) * ez - (qz - pz) * ex) / den
        return (px + u * dx, pz + u * dz)

    return [meet(lines[i - 1], lines[i]) for i in range(n)]


def _round_area(alpha_deg: float, r: float) -> float:
    """Cross-section a convex round of radius r removes from an edge of interior angle alpha."""
    a = math.radians(alpha_deg)
    return r * r * (1 / math.tan(a / 2) - (math.pi - a) / 2)


def canopy_outer_volume(p, hw: float, rr: float, rh: float, rt: float) -> dict:
    """Solid (unshelled) canopy volume and each round's share, analytic (Pappus on the
    plan-corner arcs; vertex blends ignored, ~r³ each)."""
    a, b, c, d, e, _ = p
    q90 = _round_area(90.0, 1.0)
    # hood back-top edge D: the back face runs down from D, the ceiling up-forward at
    # BH_TILT, so the solid's interior angle there is 90 + 15 = 105° (tick 47: not 75)
    alpha_d = 90.0 + math.degrees(math.atan2(e[1] - d[1], e[0] - d[0]))
    dv = {
        "rear": -2 * q90 * rr * rr * (b[1] - a[1]),
        "hood": -(
            2 * q90 * rh * rh * (d[1] - c[1])
            + _round_area(alpha_d, rh) * 2 * hw
            + 2 * q90 * rh * rh * math.dist(d, e)
        ),
    }
    cbar = rt * (10 - 3 * math.pi) / (3 * (4 - math.pi))  # centroid of the round's cut
    straight = (2 * hw - 2 * rr) + 2 * ((c[0] + rh) - (a[0] + rr))
    dv["top"] = -(q90 * rt * rt * straight + q90 * rt * rt * math.pi * (rr - cbar))
    return {"base": _poly_area(p) * 2 * hw, **dv, "alpha_d": alpha_d}


def canopy_ribs() -> list[tuple[float, ...]]:
    """Rib grid boxes (x0, x1, y0, y1, z0, z1) under the body's inner ceiling, inside its
    inner rounds (r 6.2 at x -77 / |y| 45) and up to the hood's back wall."""
    t, dep = CAN_RIB
    zc = CAN_TOP - CAN_T
    xa = canopy_rear_seam()  # -77.45 (flat: -77)
    xb = canopy_profile()[2][0] + CAN_T  # hood back wall, inner face
    ya = CAN_HW - CAN_T - (CAN_R[2] - CAN_T)  # 45
    # z1 = the flat ceiling's height; with the crown the tops follow the arc instead
    # (canopy_rib_profile / can_top_z) and the bottoms too, CAN_RIB[1] under the ceiling
    out = [(xa, xb, y - t / 2, y + t / 2, zc - dep, zc) for y in CAN_RIBS_Y]
    out += [(x - t / 2, x + t / 2, -ya, ya, zc - dep, zc) for x in CAN_RIBS_X]
    return out


def canopy_rear_seam() -> float:
    """x of the tangent seam between the crowned ceiling (inset CAN_T) and the rear inner
    round. Flat: -77. Crowned the r 8 round's centre sits on the arc's R - 8 circle, so the
    seam moves back to -77.45 (tick 74c: ribs ending at -77 left a 0.45 sliver of ceiling
    behind their ends, and S8 peaked there: 38 / 83 MPa)."""
    xc, _, R = canopy_crown()
    xf = CAN_X0 + CAN_R[2]  # the round's centre x
    return xc + (xf - xc) * (R - CAN_T) / (R - CAN_R[2])


def _crown_top(x0: float, x1: float) -> list:
    """Profile pieces from (x0, top) to (x1, top) along the ceiling arc sunk CAN_RIB_SINK
    into the skin: a start point and one arc entry ("arc", xc, zc, x1, z1)."""
    xc, zc, _ = canopy_crown()
    ins = CAN_T - CAN_RIB_SINK
    return [(x0, can_top_z(x0, ins)), ("arc", xc, zc, x1, can_top_z(x1, ins))]


def canopy_cross_rib_profile(x0: float, x1: float) -> list:
    """Side profile (XZ) of a cross rib x0..x1: top and bottom on the same arcs as the
    lengthwise ribs (tick 74d: flat-bottomed boxes left a micron step at every crossing
    and S8 peaked on it, 83.8 MPa at (-22.8, 15.8, 91.69))."""
    xc, zc, _ = canopy_crown()
    ib = CAN_T + CAN_RIB[1]
    return [*_crown_top(x0, x1), (x1, can_top_z(x1, ib)), ("arc", xc, zc, x0, can_top_z(x0, ib))]


def canopy_rib_profile() -> list:
    """Side profile (XZ) of the lengthwise ribs: constant depth under the crowned ceiling
    (tick 74b: flat bottoms made the middle 6.5 deep and moved S8's peak to the rear
    ceiling panel, 38 MPa). Top sunk CAN_RIB_SINK into the skin, bottom the concentric arc."""
    xa, xb = canopy_ribs()[0][:2]
    xc, zc, _ = canopy_crown()
    ib = CAN_T + CAN_RIB[1]
    return [*_crown_top(xa, xb), (xb, can_top_z(xb, ib)), ("arc", xc, zc, xa, can_top_z(xa, ib))]


def _profile_poly(prof: list, n: int = 60) -> list[tuple[float, float]]:
    """Profile with its arcs sampled (for areas)."""
    out: list[tuple[float, float]] = []
    for q in prof:
        if q[0] == "arc":
            _, xc, zc, x1, z1 = q
            x0, z0 = out[-1]
            a0, a1 = math.atan2(z0 - zc, x0 - xc), math.atan2(z1 - zc, x1 - xc)
            r = math.hypot(x0 - xc, z0 - zc)
            out += [
                (xc + r * math.cos(a0 + (a1 - a0) * k / n), zc + r * math.sin(a0 + (a1 - a0) * k / n))
                for k in range(1, n + 1)
            ]
        else:
            out.append(q)
    return out


def canopy_keel_profile() -> list[tuple[float, float]]:
    """Keel side profile (XZ). Rev 3 (tick 49): rev 2's keels (boxes x -77..36.2) ended
    free at both ends and peaked there (83.7 MPa at x -77). Now tied into the rear wall
    (x -83.2, chamfered inside the r 6.2 inner round, so no overlap) and tapered up into
    the ceiling over the last 20 mm before the hood. Built as a Top-plane profile: the
    same keel as a `box` came out 2.4 thick, not 1.8, inside the canopy (cause unknown)."""
    _, _, kz = CAN_KEEL
    zc = CAN_TOP - CAN_T
    xr = CAN_X0 + CAN_T  # rear wall inner face
    ri = CAN_R[2] - CAN_T  # inner top round
    xb = canopy_profile()[2][0] + CAN_T  # hood back wall, inner face
    return [
        (xr, kz),
        (xr, zc - ri),
        *_crown_top(canopy_rear_seam(), xb),  # flat: xr + ri = -77
        (xb, zc - CAN_RIB[1]),
        (xb - 20.0, kz),
    ]


def canopy_hood_edge() -> tuple[float, str]:
    """P6e (tick 62): r 1.0 on the hood's front top edge (E, along y), right behind the head.
    E1 wants r 3 here but the ceiling is 1.8 thick over the window: r 1 is what fits.
    Returns (volume removed, the fillet's pick box around the line)."""
    e = canopy_profile()[4]
    L = 2 * (CAN_HW - CAN_R[1])  # between the hood's r 8 side rounds
    vol = _round_area(90.0, CAN_EDGE_R) * L
    box = f"{e[0] - 0.3:.3f} {-CAN_HW:.3f} {e[1] - 0.3:.3f} {e[0] + 0.3:.3f} {CAN_HW:.3f} {e[1] + 0.3:.3f}"
    return vol, box


def canopy_front_corners() -> tuple[float, list[str]]:
    """P6e (tick 75): r 1.0 on the canopy's outer front corners (front face meets the side
    face at |y| 53), from the rim round up to the hood's r 8 side round."""
    e, f = canopy_profile()[4], canopy_profile()[5]
    tan15 = (f[0] - e[0]) / (e[1] - f[1])
    z1 = e[1] - CAN_R[1]
    L = (z1 - CAN_Z0) / math.cos(math.atan(tan15)) - CAN_EDGE_R
    zm = (CAN_Z0 + z1) / 2
    xm = f[0] - (zm - CAN_Z0) * tan15
    boxes = [
        f"{xm - 0.7:.3f} {s * CAN_HW - 0.3:.3f} {zm - 2:.3f} {xm + 0.7:.3f} {s * CAN_HW + 0.3:.3f} {zm + 2:.3f}"
        for s in (-1, 1)
    ]
    return 2 * _round_area(90.0, CAN_EDGE_R) * L, boxes


def canopy_rim_round() -> tuple[float, list[str]]:
    """P6e (tick 61): r 1.0 on the OUTER edge of the skirt's bottom rim (z CAN_Z0), the edge a
    hand meets; the inner edge stays square (rounding both would eat the 1.8 wall). Returns
    (volume removed, skip boxes): inner edges, inner corner arcs and the concave junctions
    with the tab webs and the rear apron are left out by their midpoints."""
    r = CAN_EDGE_R
    q90 = _round_area(90.0, r)
    z = CAN_Z0
    hw, t = CAN_HW, CAN_T
    rr = CAN_R[0]
    (wx0, wx1), _, _, _ = CAN_TAB
    xf = canopy_profile()[5][0]  # front bottom on the wall's back-face line
    rear = 2 * ((hw - rr) - CAN_APRON_HW)
    sides = 2 * ((wx0 - (CAN_X0 + rr)) + (xf - wx1))
    cbar = r * (10 - 3 * math.pi) / (3 * (4 - math.pi))
    arcs = 2 * q90 * (rr - cbar) * math.pi / 2
    lips = 2 * (hw - CAN_WIN_HW)  # front-wall bottom edge beside the window (75° wedge)
    vol = q90 * (rear + sides) + _round_area(75.0, r) * lips + arcs
    zz = f"{z - 0.5} {z + 0.5}"

    def box(x0, x1, y0, y1):
        a, b = zz.split()
        return f"{x0:.2f} {y0:.2f} {a} {x1:.2f} {y1:.2f} {b}"

    yi = hw - t
    ai = (CAN_X0 + rr + (CAN_X0 + t)) / 2  # inner arc chord midpoint, roughly
    skips = [
        box(-200, 200, yi - 0.4, yi + 0.4),
        box(-200, 200, -yi - 0.4, -yi + 0.4),
        box(CAN_X0 + t - 0.4, CAN_X0 + t + 0.4, -60, 60),
    ]
    # inner corner arcs: chord midpoint of the r (rr - t) arc centred (x0 + rr, +-(hw - rr))
    cx, cy, ri = CAN_X0 + rr, hw - rr, rr - t
    mx, my = cx - ri / 2, cy + ri / 2
    skips += [
        box(mx - 0.4, mx + 0.4, my - 0.4, my + 0.4),
        box(mx - 0.4, mx + 0.4, -my - 0.4, -my + 0.4),
    ]
    for xw in (wx0, wx1):  # web junctions (concave)
        skips += [box(xw - 0.4, xw + 0.4, -60, 60)]
    skips += [box(CAN_X0 - 1, CAN_X0 + t + 1, CAN_APRON_HW - 0.4, CAN_APRON_HW + 0.4)]
    skips += [box(CAN_X0 - 1, CAN_X0 + t + 1, -CAN_APRON_HW - 0.4, -CAN_APRON_HW + 0.4)]
    # front-wall inner edge (back-face line minus t along the normal), beside the window
    xfi = xf - t / math.cos(math.radians(BH_TILT))
    skips += [box(xfi - 0.6, xfi + 0.6, -60, 60)]
    del ai
    return vol, skips


def canopy_features() -> dict:
    p = canopy_profile()
    rr, rh, rt = CAN_R
    out = canopy_outer_volume(p, CAN_HW, rr, rh, rt)
    pin = _inset_profile(p, CAN_T)
    inn = canopy_outer_volume(pin, CAN_HW - CAN_T, rr - CAN_T, rh - CAN_T, rt - CAN_T)
    v_out = out["base"] + out["rear"] + out["hood"] + out["top"]
    v_in = inn["base"] + inn["rear"] + inn["hood"] + inn["top"]
    # P6f crown: the segment over the chord, outside and (concentric, r - t) inside
    crown_out = _crown_area(p[1][0], p[2][0], 0.0, CAN_TOP) * 2 * CAN_HW
    crown_in = (
        _crown_area(pin[1][0], pin[2][0], CAN_T, CAN_TOP - CAN_T) * 2 * (CAN_HW - CAN_T)
    )
    v_out += crown_out
    v_in += crown_in
    # front opening: the 1.8 front wall at |y| <= CAN_WIN_HW, from the skirt (z_pre at
    # mid-wall) up to the hood ceiling's underside (z_pre BH_H)
    xm = BH_PIVOT[0] - CAN_T / 2
    s, c_ = math.sin(math.radians(BH_TILT)), math.cos(math.radians(BH_TILT))
    zp0 = (CAN_Z0 - s * (xm - BH_PIVOT[0])) / c_
    win = CAN_T * 2 * CAN_WIN_HW * (BH_H + CAN_LUG_GAP - zp0)
    # lug holes: lug axis on the wall's (tilted) z, at mid-ceiling
    lug_x = BH_XF - BH_T - INS_BOSS / 2 + 1.0  # = bulkhead_features()' lug_x
    hx, hz = _pre2ch(lug_x, BH_H + CAN_LUG_GAP + CAN_T / 2)
    holes = 2 * math.pi * (CAN_LUG_HOLE / 2) ** 2 * CAN_T / c_
    # rear apron + bosses (the boss's slice inside the apron counted once)
    apron = CAN_T * 2 * CAN_APRON_HW * CAN_Z0
    bx, by, bh = CAN_BOSS
    r = INS_BOSS / 2
    dd = bx - (CAN_X0 + CAN_T)
    seg = r * r * math.acos(dd / r) - dd * math.sqrt(r * r - dd * dd)
    boss = 2 * (math.pi * r * r - seg) * bh
    pockets = 2 * math.pi * (INS_HOLE / 2) ** 2 * INS_DEPTH
    ribs = canopy_ribs()
    rt_, rd_ = CAN_RIB
    ky, kt, kz = CAN_KEEL
    # below the (crowned) ceiling only: the CAN_RIB_SINK into the skin adds nothing
    zb = ribs[0][4]
    xa_, xb_, ya_ = ribs[0][0], ribs[0][1], ribs[-1][3]
    dep = {x: rd_ for x in CAN_RIBS_X}  # cross-rib depth (constant since tick 74b)
    nY = len(CAN_RIBS_Y)
    rib_vol = (
        nY * rt_ * (_crown_area(xa_, xb_, CAN_T, zb - 9) - _crown_area(xa_, xb_, CAN_T + rd_, zb - 9))
        + sum(rt_ * 2 * ya_ * d for d in dep.values())  # cross ribs
        - sum(nY * rt_ * rt_ * d for d in dep.values())  # rib crossings
        + 2
        * kt
        * (
            _poly_area(_profile_poly(canopy_keel_profile()))
            - CAN_RIB_SINK * (xb_ - xa_)
        )
        - sum(2 * rt_ * kt * d for d in dep.values())  # cross ribs through the keels
    )
    # P6g root rounds (concave: + (1 - pi/4) r² per mm), both sides of every rib/keel
    # root on the ceiling between the crossings, x -77 .. 36.2, |y| <= 45
    xa, xb = ribs[0][0], ribs[0][1]
    ya = ribs[-1][3]
    nxr, nyr = len(CAN_RIBS_Y), len(CAN_RIBS_X)
    l_x = nxr * 2 * ((xb - xa) - nyr * rt_)  # x-ribs
    l_y = nyr * 2 * (2 * ya - nxr * rt_ - 2 * kt)  # y-ribs
    l_k = 2 * 2 * ((xb - xa) - nyr * rt_)  # keels
    roots = (1 - math.pi / 4) * CAN_ROOT_R**2 * (l_x + l_y + l_k)
    (wx0, wx1), (tx0, tx1), td, _ = CAN_TAB
    tabs = 2 * CAN_T * ((wx1 - wx0) * CAN_Z0 + (tx1 - tx0) * td)
    return {
        "p": p,
        "pin": pin,
        "out": out,
        "inn": inn,
        "v_out": v_out,
        "v_in": v_in,
        "crown": (crown_out, crown_in),
        "win": win,
        "win_zp0": zp0,
        "lug_hole": (hx, hz),
        "holes": holes,
        "apron": apron,
        "boss": boss,
        "pockets": pockets,
        "ribs": rib_vol,
        "roots": roots,
        "tabs": tabs,
        "rim": canopy_rim_round()[0],
        "hood_edge": canopy_hood_edge()[0],
        "fcorner": canopy_front_corners()[0],
        "vol": -canopy_rim_round()[0]
        - canopy_hood_edge()[0]
        - canopy_front_corners()[0]
        + v_out
        - v_in
        - win
        - holes
        + apron
        + boss
        - pockets
        + rib_vol
        + roots
        + tabs
        - canopy_vents()[1],
    }


# P6d (tick 71): vents on the REAR wall (flat for |y| <= 33, z <= 87). Not the sides: the
# belt runs 3.5 mm outside them and throws grit; not the top: the Pi's heat would cross the
# cells (S4 #6) and the mic disc sits there. A low field at the Pi's port end (intake under
# the HAT) and a high one over the HAT PCB (exhaust, faces the buzzer): E1 slot motif,
# 2 mm wide (06 §5 <= 2 mm) on a 4 mm pitch, vertical so the tops bridge only 2 mm.
CAN_VENT_W, CAN_VENT_PITCH, CAN_VENT_HY = (
    2.0,
    4.0,
    24.0,
)  # |y| of the outer slot centres
CAN_VENT_Z = ((36.0, 48.0), (70.0, 84.0))  # slot extents (ends r 1)


def canopy_vents() -> tuple[list[str], float]:
    """One Right-plane sketch of closed stadiums (sketch u = -z, v = y, both arcs
    clockwise), cut through the rear wall; and the volume removed."""
    r = CAN_VENT_W / 2
    n = int(round(2 * CAN_VENT_HY / CAN_VENT_PITCH)) + 1
    ys = [-CAN_VENT_HY + i * CAN_VENT_PITCH for i in range(n)]
    loops = []
    for z0, z1 in CAN_VENT_Z:
        ulo, uhi = -(z0 + r), -(z1 - r)
        for yc in ys:
            loops.append(
                f"M {ulo:g} {yc - r:g} L {uhi:g} {yc - r:g} a {uhi:g} {yc:g} {uhi:g} {yc + r:g} "
                f"L {ulo:g} {yc + r:g} a {ulo:g} {yc:g} {ulo:g} {yc - r:g}"
            )
    area = sum((z1 - z0 - 2 * r) * 2 * r + math.pi * r * r for z0, z1 in CAN_VENT_Z) * n
    line = f"prof|{CAN_X0 - 0.2} {CAN_X0 + CAN_T + 0.2}|{' '.join(loops)}|cut|right"
    return [line], area * CAN_T


def canopy_lines(path: str) -> list[str]:
    f = canopy_features()
    p = f["p"]
    a, b, c, d, e, fp = p
    rr, rh, rt = CAN_R
    hw = CAN_HW
    o = f["out"]
    zc_in = CAN_TOP - CAN_T  # ceiling underside at its ends (crowned: up to + CAN_CROWN)
    xcr, zcr, rcr = canopy_crown()
    zc_hi = zc_in + CAN_CROWN
    xr_in = canopy_rear_seam()  # -77.45: tangent seam into the rear inner round
    xb_in = canopy_profile()[2][0] + CAN_T  # 36.2: ceiling ends at the hood
    yr_in = (
        CAN_HW - CAN_T - (CAN_R[2] - CAN_T)
    )  # 45: tangent seams into the side rounds

    def prismy(poly, y0, y1, kind):  # Top plane: sketch (x, -z), extrude +Y
        # entries (x, z) or ("arc", xc, zc, x1, z1): a minor arc from the previous point;
        # its sense is taken in sketch coordinates (z -> -z mirrors it)
        x0, z0 = poly[0]
        toks = [f"M {x0:.6f} {-z0:.6f}"]
        px, pz = x0, z0
        for q in poly[1:]:
            if q[0] == "arc":
                _, xc, zc, x1, z1 = q
                cr = (px - xc) * (-z1 + zc) - (-pz + zc) * (x1 - xc)
                # 6 decimals: a centre rounded to 1e-4 is off-equidistant from the ends by
                # more than SolidWorks' tolerance at r ~700 and the extrude comes back null
                toks.append(f"{'A' if cr > 0 else 'a'} {xc:.6f} {-zc:.6f} {x1:.6f} {-z1:.6f}")
                px, pz = x1, z1
            else:
                toks.append(f"L {q[0]:.6f} {-q[1]:.6f}")
                px, pz = q
        return f"prof|{y0} {y1}|{' '.join(toks)}|{kind}|top"

    def tol(v, k=0.2):
        return f"{v:.1f} {abs(v) * k + 5:.1f}"

    # front opening: a slab round the front wall in the wall's own frame
    x0p, x1p = BH_PIVOT[0] - CAN_T - 0.5, BH_PIVOT[0] + 0.5
    zw = BH_H + CAN_LUG_GAP
    win = [_pre2ch(x0p, 20.0), _pre2ch(x0p, zw), _pre2ch(x1p, zw), _pre2ch(x1p, 20.0)]
    hx, _ = f["lug_hole"]
    bx, by, bh = CAN_BOSS
    zlo, zhi = e[1] - 12.0, e[1] + 6.0
    lines = [
        f"part|{path}",
        prismy([a, b, ("arc", xcr, zcr, *c), d, e, fp], -hw, hw, "boss"),
        # plan corners at the rear (vertical edges)
        f"fillet|{rr}|z|{a[0] - 0.1} {-hw - 0.1} {a[1]} {a[0] + 0.1} {hw + 0.1} {b[1]}|2|{tol(o['rear'], 0.05)}",
        # hood: back corners (vertical), back-top edge, ceiling side edges
        f"fillet|{rh}|any|{c[0] - 0.1} {-hw - 0.1} {c[1] + 0.1} {c[0] + 0.6 * (e[0] - c[0]):.3f} {hw + 0.1} {e[1] + 0.1}|5|{tol(o['hood'])}",
        # body top: rear edge, plan arcs and side edges; not the concave edge at the hood
        f"filletface|{rt}|cyl|{rcr:.4f}|{a[0]} {-hw} {c[0]} {hw}|1|{tol(o['top'])}|skip:{c[0] - 0.5} {-hw - 1} {b[1] - 0.5} {c[0] + rh + 0.5} {hw + 1} {b[1] + 0.5}",
        f"shell|{CAN_T}|z:-1|{CAN_Z0}|{a[0] - 1} {-hw - 1} {fp[0] + 1} {hw + 1}|1|{-f['v_in']:.1f} {0.04 * (f['v_out'] - f['v_in']):.1f}",
        prismy(win, -CAN_WIN_HW, CAN_WIN_HW, "cut"),
        *[
            f"cyl|z|{hx:.4f} {sg * BH_LUG_Y}|{zlo:.3f} {zhi:.3f}|{CAN_LUG_HOLE / 2}|cut"
            for sg in (-1, 1)
        ],
        *[
            prismy(canopy_rib_profile(), y0, y1, "boss")
            for _, _, y0, y1, _, _ in canopy_ribs()[: len(CAN_RIBS_Y)]
        ],
        *[
            prismy(canopy_cross_rib_profile(x0, x1), y0, y1, "boss")
            for x0, x1, y0, y1, _, _ in canopy_ribs()[len(CAN_RIBS_Y) :]
        ],
        *[
            prismy(
                canopy_keel_profile(),
                s * CAN_KEEL[0] - CAN_KEEL[1] / 2,
                s * CAN_KEEL[0] + CAN_KEEL[1] / 2,
                "boss",
            )
            for s in (-1, 1)
        ],
        # P6g (Ben): r 1.0 at the rib and keel roots on the ceiling's underside (every cell
        # face of the grid, outer loops). Not the tangent seams into the inner rounds
        # (x -77, |y| 45) nor the ceiling's front end at the hood (x 36.2)
        f"filletface|{CAN_ROOT_R}|cyl|{rcr - CAN_T:.4f}|{CAN_X0} {-CAN_HW} {xb_in + 1:.3f} {CAN_HW}|any"
        f"|{f['roots']:.1f} {0.15 * f['roots']:.1f}"
        f"|skip:{CAN_X0 - 1} {-CAN_HW - 1} {zc_in - 0.5:.3f} {xr_in + 0.4:.3f} {CAN_HW + 1} {zc_hi + 0.5:.3f}"
        f";{xb_in - 0.4:.3f} {-CAN_HW - 1} {zc_in - 0.5:.3f} {xb_in + 1:.3f} {CAN_HW + 1} {zc_hi + 0.5:.3f}"
        f";{CAN_X0 - 1} {yr_in - 0.4:.3f} {zc_in - 0.5:.3f} {xb_in + 1:.3f} {CAN_HW + 1} {zc_hi + 0.5:.3f}"
        f";{CAN_X0 - 1} {-CAN_HW - 1} {zc_in - 0.5:.3f} {xb_in + 1:.3f} {-yr_in + 0.4:.3f} {zc_hi + 0.5:.3f}",
        *[
            ln
            for sg in (-1, 1)
            for ln in (
                f"box|{CAN_TAB[0][0]} {CAN_TAB[0][1]}|{min(sg * (CAN_HW - CAN_T), sg * CAN_HW)} {max(sg * (CAN_HW - CAN_T), sg * CAN_HW)}|0 {CAN_Z0}",
                f"box|{CAN_TAB[1][0]} {CAN_TAB[1][1]}|{min(sg * (CAN_HW - CAN_T), sg * CAN_HW)} {max(sg * (CAN_HW - CAN_T), sg * CAN_HW)}|{-CAN_TAB[2]} 0",
            )
        ],
        f"box|{CAN_X0} {CAN_X0 + CAN_T}|{-CAN_APRON_HW} {CAN_APRON_HW}|0 {CAN_Z0}",
        *[f"cyl|z|{bx} {sg * by}|0 {bh}|{INS_BOSS / 2}|boss" for sg in (-1, 1)],
        *[
            f"cyl|z|{bx} {sg * by}|-0.1 {INS_DEPTH}|{INS_HOLE / 2}|cut"
            for sg in (-1, 1)
        ],
        f"fillet|{CAN_EDGE_R}|y|{canopy_hood_edge()[1]}|1|{-f['hood_edge']:.2f} {0.25 * f['hood_edge']:.2f}",
        f"filletface|{CAN_EDGE_R}|z:-1|{CAN_Z0}|{CAN_X0 - 1} {-hw - 1} {fp[0] + 1} {hw + 1}|any"
        f"|{-f['rim']:.2f} {0.25 * f['rim']:.2f}|skip:"
        + ";".join(canopy_rim_round()[1]),
        # (tick 75: no round on the window lips' edges at y +-47.3: they sit in a 0.3 x 3 slot
        # beside the bulkhead, which stands 3 proud of the lip face; rounding them raised
        # S5k 9.5 -> 11.1 MPa at the window's top corner, which won't take a fillet)
        *[
            f"fillet|{CAN_EDGE_R}|any|{b}|1|{-f['fcorner'] / 2:.2f} {0.15 * f['fcorner'] / 2:.2f}"
            for b in canopy_front_corners()[1]
        ],
        *canopy_vents()[0],
        PART_LABELS["canopy"],
        f"expect|vol {f['vol']:.1f} {f['vol'] * 0.03:.1f}|box {CAN_X0} {fp[0]:.2f} {-hw} {hw} {-CAN_TAB[2]} {e[1]:.2f} 0.5",
        "save",
    ]
    return lines


# S8 (P6c, heel; was "S7" in BACKLOG): analysis-only copy of the canopy with a Ø30 x 0.5 heel pad on the flat top at
# the middle of its unsupported span, so the study can load exactly that patch (split
# lines don't work through the API, tick 12). Not printed.
CAN_HEEL = (
    -32.0,
    7.5,
    15.0,
    0.5,
)  # x, y, r, pad height: centred on a rib cell (-42..-22, 0..15)


def canopy_heel() -> tuple[float, float, float]:
    """S8 pad on the crowned top: (bottom z, flat top z, volume added above the skin).
    Bottom 0.1 under the lowest skin point it covers; top hh over the highest."""
    hx, _, hr, hh = CAN_HEEL
    zs = [can_top_z(hx + hr * k / 20) for k in range(-20, 21)]
    z0, z1 = min(zs) - 0.1, max(zs) + hh
    n, add = 60, 0.0
    for i in range(n):
        for j in range(n):
            u, v = -hr + (i + 0.5) * 2 * hr / n, -hr + (j + 0.5) * 2 * hr / n
            if u * u + v * v <= hr * hr:
                add += (z1 - can_top_z(hx + u)) * (2 * hr / n) ** 2
    return z0, z1, add


def canopy_fea_lines(path: str) -> list[str]:
    body = [ln for ln in canopy_lines(path) if not ln.startswith("text|")]  # R3 labels: not in FEA
    assert body[-1] == "save" and body[-2].startswith("expect|vol ")
    hx, hy, hr, hh = CAN_HEEL
    z0, z1, pad = canopy_heel()
    vol = canopy_features()["vol"] + pad
    head, rest = body[-2].split("|box ")
    return [
        *body[:-2],
        f"cyl|z|{hx} {hy}|{z0:.3f} {z1:.3f}|{hr}|boss",
        f"expect|vol {vol:.1f} {vol * 0.03:.1f}|box {rest}",
        "save",
    ]


# ------------------------------------------------ installed belt, native (T11)
# The 08 belt wrapped on its wheels (the as-printed ring is drivetrain.belt()): pitch line
# = drivetrain.belt_path() round the 4 wheels of 08 rev 1 (idler, two road wheels,
# sprocket) at the fit station, inner face R_RUN, base T_BASE, tread bars GROUSER_H
# outboard (an envelope over the 1.0 pads), trapezoid lugs LUG_H inward in the centre
# LUG_W band (2 mm end chamfers left out). Lug centres at pitch-line s = 5 + 10 k from the
# sprocket's top tangent point; the sprocket and idler are turned (wheel_phase) so their
# pockets sit on the lugs. Replaces the stadium envelope for fit checks.
def idler_z() -> float:
    """Idler axle z (08 rev 1: RAISE below the TT shaft)."""
    return next(w[2] for w in dt.wheels() if w[0] == "idler")


def _belt_geom() -> list[tuple]:
    """Path pieces from s = 0 (sprocket top tangent, going aft over the top run):
    ("line", (x0, z0), (x1, z1), len) and ("arc", (cx, cz), r_pitch, phi0, wrap)."""
    ws = dt.wheels(dt.belt_fit()["x_fit"])
    bp = dt.belt_path(ws)
    n = len(ws)
    c = [(w[1], w[2], w[3] + dt.T_BASE / 2) for w in ws]
    out = []
    i = n - 1  # sprocket: leave it over the top run
    for _ in range(n):
        (p0, p1), j = bp["segs"][i], (i + 1) % n
        out.append(("line", p0, p1, math.dist(p0, p1)))
        out.append(("arc", (c[j][0], c[j][1]), c[j][2], bp["phi_in"][j], bp["wrap"][j]))
        i = j
    return out


def _belt_path(s_: float, off: float) -> tuple[float, float]:
    """Chassis (x, z) at pitch-line arclength s_ (0 = sprocket top tangent, going aft
    over the top run), offset `off` outward from the pitch line."""
    g = _belt_geom_cache()
    s_ %= sum(p[3] if p[0] == "line" else p[2] * p[4] for p in g)
    for p in g:
        if p[0] == "line":
            (x0, z0), (x1, z1), ln = p[1], p[2], p[3]
            if s_ <= ln:
                t = s_ / ln
                nx, nz = (z1 - z0) / ln, -(x1 - x0) / ln  # right of travel = outward
                return (x0 + t * (x1 - x0) + off * nx, z0 + t * (z1 - z0) + off * nz)
            s_ -= ln
        else:
            (cx, cz), r, ph, wr = p[1], p[2], p[3], p[4]
            if s_ <= r * wr:
                th = ph + s_ / r
                return (cx + (r + off) * math.cos(th), cz + (r + off) * math.sin(th))
            s_ -= r * wr
    raise AssertionError(s_)


_BG: list = []


def _belt_geom_cache() -> list[tuple]:
    if not _BG:
        _BG.extend(_belt_geom())
    return _BG


def _lug_clearance(x: float, z: float, deg: float) -> float:
    """Worst radial gap (mm) from every lug near the wheel at (x, z) to its tooth band
    (drivetrain.wheel_band, pockets at 0 mod 360/N in the chassis frame as wheel_at
    places it), with the wheel turned `deg`. Radial, so a lower bound on the true gap."""
    import numpy as np

    key = (round(x, 6), round(z, 6))
    if key not in _LUGS:
        lug = np.array(_belt_loop("lugs"))
        r = np.hypot(lug[:, 0] - x, lug[:, 1] - z)
        sel = r < dt.R_RUN + 0.5
        _LUGS[key] = (np.arctan2(lug[sel, 1] - z, lug[sel, 0] - x), r[sel])
    a, r = _LUGS[key]
    m = dt.N_TEETH * 48
    band = np.asarray(dt.wheel_band(m)).ravel()
    th = np.arange(m) * 2 * np.pi / m
    br = np.interp((a - math.radians(deg)) % (2 * np.pi), th, band, period=2 * np.pi)
    return float((r - br).min())


_LUGS: dict = {}


def wheel_phase(x: float, z: float) -> float:
    """Degrees to turn a toothed wheel at (x, z) about its axle (chassis x -> z sense)
    so its pockets sit on the lugs: start from the lugs on the wrap (the parts' pockets
    read 0 mod 360/N in the chassis frame as wheel_at places them; tick 55), then take
    the turn within +-1 deg that maximises the worst gap over every lug near the wheel,
    including the ones still on a straight as they enter or leave (tick 68: the 6 deg
    climb into the sprocket from road wheel 2 grazed the entering lug)."""
    pitch_deg = 360.0 / dt.N_TEETH
    links = dt.belt_fit()["links"]
    rp = dt.pitch_radius()
    for k in range(links):
        px, pz = _belt_path(5.0 + 10.0 * k, 0.0)
        if abs(math.hypot(px - x, pz - z) - rp) < 1e-6:
            th0 = math.degrees(math.atan2(pz - z, px - x)) % pitch_deg
            cands = [th0 + 0.02 * i for i in range(-50, 51)]
            return max(cands, key=lambda d: _lug_clearance(x, z, d))
    raise AssertionError((x, z))


def _belt_loop(kind: str) -> list[tuple[float, float]]:
    """'outer' (base + bars), 'inner' (plain), 'lugs' (inner with lugs) as XZ polylines."""
    links = dt.belt_fit()["links"]
    hb = dt.T_BASE / 2
    # the inner face sits ON the wheel rims (R_RUN): its 0.5 mm chords dip ~0.001 inside
    # them and read as 816 x 0.0 mm3 interferences (tick 55); model it 0.02 off instead
    gap = 0.02
    pts = []
    for k in range(links):
        s0 = 10.0 * k
        ss = sorted(
            set(
                [s0 + 0.5 * i for i in range(20)]
                + [s0 + 5 + d for d in (-2.5, -1.5, 1.5, 2.5, -2.0, -1.0, 1.0, 2.0)]
            )
        )
        for s_ in ss:
            u = abs(s_ - (s0 + 5))
            if kind == "outer":  # bars: flat top |u| <= 1, ramp to 2
                h = dt.GROUSER_H * min(1.0, max(0.0, (2.0 - u) / 1.0))
                pts.append(_belt_path(s_, hb + h))
            elif kind == "lugs":  # lug: tip |u| <= 1.5, root 2.5
                h = dt.LUG_H * min(1.0, max(0.0, (2.5 - u) / 1.0))
                pts.append(_belt_path(s_, -hb + gap - h))
            else:
                pts.append(_belt_path(s_, -hb + gap))
    return pts


def belt_native_lines(path: str, side: int) -> list[str]:
    y0, y1 = track_y()
    l0, l1 = y0 + (dt.BELT_W - dt.LUG_W) / 2, y0 + (dt.BELT_W + dt.LUG_W) / 2

    def ys(a, b):
        return (a, b) if side > 0 else (-b, -a)

    def prof(poly, a, b, kind):
        pts = [f"{x:.3f} {-z:.3f}" for x, z in poly]
        return (
            f"prof|{a:.3f} {b:.3f}|M "
            + pts[0]
            + "".join(" L " + q for q in pts[1:])
            + f"|{kind}|top"
        )

    out, inn, lug = _belt_loop("outer"), _belt_loop("inner"), _belt_loop("lugs")
    a_out, a_in, a_lug = _poly_area(out), _poly_area(inn), _poly_area(lug)
    vol = a_out * dt.BELT_W - a_in * (dt.BELT_W - dt.LUG_W) - a_lug * dt.LUG_W
    ya, yb = ys(y0, y1)
    b1 = ys(y0 - 0.1, l0)
    b2 = ys(l0, l1)
    b3 = ys(l1, y1 + 0.1)
    zs = [z for _, z in out]
    xs = [x for x, _ in out]
    return [
        f"part|{path}",
        prof(out, ya, yb, "boss"),
        prof(inn, *b1, "cut"),
        prof(lug, *b2, "cut"),
        prof(inn, *b3, "cut"),
        f"expect|vol {vol:.1f} {vol * 0.005:.1f}|box {min(xs):.2f} {max(xs):.2f} {ya} {yb} {min(zs):.2f} {max(zs):.2f} 0.1",
        "save",
    ]


# --------------------------------------------- outboard track frame (P2o, Q17 b)
# One bar per side, outboard of the wheels: a tie between the sprocket's outboard 624
# (steel Ø4 dowel pressed through the bar + boss, 5 mm into the bearing) and the idler's
# Ø4 shoulder axle (its M3 end through an x-slot, nyloc clamps the bar after the jack
# screw sets the tension). Belt tension then closes through the bar instead of bending
# the plate (S1m). Pinned on two parallel axles it needs no legs: the plate belly has no
# room for them (the |y| 47 load rib, the canopy tongue slots, the motor), tick 54.
TF_GAP, TF_T, TF_H = (
    1.0,
    2.4,
    14.0,
)  # off the wheel faces, thickness, height (bar stadium)
# S2b (Q22 F2, tick 66): the bar grows into a SIDE PLATE over the belt loop's window, so a
# finger can't reach the lug <-> pocket nips: rounded rectangle round both axles, z
# TF_PLATE_Z (8 over the ground line, ~3-4 mm diagonally to the runs' lug tips), corners
# r 8 (E1). 3.6 -> 2.4 thick (a 48-tall plate is far stiffer in tension than the bar).
TF_PLATE_Z, TF_PLATE_R = (-10.0, 38.0), 8.0
TF_SLOT = (dt.TRAVEL, 3.4)  # +- travel round the taut station, M3 clearance
TF_BOSS = (5.0, 3.0)  # dowel boss r, height outboard
TF_DOWEL = 3.95  # Ø4 h8 dowel press hole (07 press fits: tune on the coupon)


def trackframe_geom() -> dict:
    yw = track_y()[1]  # wheels' outboard faces
    y0, y1 = yw + TF_GAP, yw + TF_GAP + TF_T
    xs, xi, z = dt.X_DRIVE, dt.belt_fit()["x_fit"], dt.Z_AXLE
    zi = idler_z()  # 08 rev 1: the idler axle (slot) sits RAISE below the sprocket's
    tr, sw = TF_SLOT
    xa = xi - tr  # rear centre of the stadium = rear end of the slot
    r = TF_H / 2
    br, bh = TF_BOSS
    pz0, pz1 = TF_PLATE_Z
    pr = TF_PLATE_R
    area = (xs - xa + 2 * r) * (pz1 - pz0) - (4 - math.pi) * pr * pr
    slot = (2 * tr) * sw + math.pi * (sw / 2) ** 2
    vol = (
        area * TF_T
        + math.pi * br * br * bh
        - math.pi * (TF_DOWEL / 2) ** 2 * (TF_T + bh)
        - slot * TF_T
    )
    return {
        "y": (y0, y1),
        "xs": xs,
        "xi": xi,
        "xa": xa,
        "z": z,
        "zi": zi,
        "r": r,
        "vol": vol,
    }


def trackframe_lines(path: str, side: int) -> list[str]:
    g = trackframe_geom()
    y0, y1 = g["y"]
    br, bh = TF_BOSS
    xs, xi, xa, z, r = g["xs"], g["xi"], g["xa"], g["z"], g["r"]
    tr, sw = TF_SLOT
    s = 1 if side > 0 else -1

    def ys(a, b):  # mirror for the right side
        return (a, b) if s > 0 else (-b, -a)

    zi = g["zi"]

    def stadium(xb, xf, rr):  # Top plane: sketch (x, -z), arcs CCW in sketch coords
        return f"M {xf} {-zi - rr} A {xf} {-zi} {xf} {-zi + rr} L {xb} {-zi + rr} A {xb} {-zi} {xb} {-zi - rr}"

    def plate():  # rounded rectangle x xa - r .. xs + r, z TF_PLATE_Z, corners TF_PLATE_R
        x0_, x1_ = xa - r, xs + r
        (zb, zt), q = TF_PLATE_Z, TF_PLATE_R
        v0, v1 = -zt, -zb  # sketch v = -z: top is v0
        return (
            f"M {x0_ + q} {v0} L {x1_ - q} {v0} A {x1_ - q} {v0 + q} {x1_} {v0 + q} "
            f"L {x1_} {v1 - q} A {x1_ - q} {v1 - q} {x1_ - q} {v1} L {x0_ + q} {v1} "
            f"A {x0_ + q} {v1 - q} {x0_} {v1 - q} L {x0_} {v0 + q} A {x0_ + q} {v0 + q} {x0_ + q} {v0}"
        )

    ya, yb = ys(y0, y1)
    ba, bb = ys(y1, y1 + bh)
    da, db = ys(y0 - 0.1, y1 + bh + 0.1)
    vol = g["vol"]
    # S2c (tick 67): r 1.0 round the plate's outline on its OUTER face (the edge a hand
    # meets); straight runs + the four r 8 corners (torus segments)
    q = (1 - math.pi / 4) * 1.0**2
    (zb, zt), pr = TF_PLATE_Z, TF_PLATE_R
    w, h = (xs + r) - (xa - r), zt - zb
    straight = 2 * (w - 2 * pr) + 2 * (h - 2 * pr)
    corners = 4 * q * (pr - 0.2234) * math.pi / 2
    dvo = q * straight + corners
    return [
        f"part|{path}",
        f"prof|{ya} {yb}|{plate()}|boss|top",
        f"cyl|y|{xs} {z}|{ba} {bb}|{br}|boss",
        f"cyl|y|{xs} {z}|{da} {db}|{TF_DOWEL / 2}|cut",
        f"prof|{ya - 0.1} {yb + 0.1}|{stadium(xi - tr, xi + tr, sw / 2)}|cut|top",
        f"filletface|1.0|y:{s}|{s * y1:.2f}|{xa - r - 1} {zb - 1} {xs + r + 1} {zt + 1}|1|{-dvo:.2f} {0.15 * dvo:.2f}",
        trackframe_label(side),
        f"expect|vol {vol - dvo:.1f} {vol * 0.01:.1f}|box {xa - r:.2f} {xs + r:.2f} "
        f"{min(ya, ba):.2f} {max(yb, bb):.2f} {TF_PLATE_Z[0]:.2f} {TF_PLATE_Z[1]:.2f} 0.05",
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


# T3: printed parts and their material (07 / Bambu TDS, g/cm³). Envelopes (motor, Pi
# stack, boards, belt stand-ins) and analysis-only parts are left out.
RHO = {"PET-CF": 1.29, "TPU": 1.22, "PC": 1.20}  # PC 🟡 until checked on the TDS
PART_MATERIAL = {
    "RB-PRT-001": "PET-CF",
    "RB-PRT-002": "PET-CF",
    "RB-PRT-003": "PET-CF",
    "RB-PRT-004": "PC",  # canopy (06 §6, P6): PC white (M4, tick 49)
    "RB-PRT-030": "PET-CF",
    "RB-PRT-040": "PET-CF",  # track frames (P2o)
    "RB-PRT-050": "TPU",  # installed belts (T11; the print is drivetrain.belt())
    "RB-PRT-051": "TPU",
    "RB-PRT-041": "PET-CF",
    "RB-PRT-031": "PET-CF",
    "RB-PRT-010": "PET-CF",
    "RB-PRT-011": "PET-CF",
    "RB-PRT-020": "PET-CF",
    "RB-PRT-021": "PET-CF",
    "RB-PRT-022": "PET-CF",  # road-wheel disc x 8 (P13b; PA6-CF candidate, M6)
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
