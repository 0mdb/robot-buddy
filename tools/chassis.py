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
import json
import math
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hardware as hw  # noqa: E402  (bought-hardware envelopes)
import drivetrain as dt  # noqa: E402  (08: the TPU track system's numbers and wheel geometry)
import sw  # noqa: E402  (staging/winpath/sync helpers)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hardware", "kicad"))
import board_outline as pcb_outline  # noqa: E402  (the reflex PCB outline + holes, one source)

# ---------------------------------------------------------------- plate (06 §1, §4)
PLATE_L, PLATE_W, PLATE_T = 170.0, 110.0, 6.0
# Rev 2 (Ben 2026-11-08, 06 §4.1 amendment): flat 6 mm plate, nothing below its belly (it
# prints belly down with no support), stiffness from the thickness plus TOP_POCKETS cut
# from the top where nothing rests. Rev 1 was 4 mm with 2.4 x 4 ribs and insert under-bosses
# below (to z -8): printed ribs down, every cell between the ribs drew support.
BOTTOM_RIBS = False
POCKET_D = 3.0  # top pockets' depth (floor 3 mm)
POCKET_R = 3.0  # their plan corner radius
# From an offline keep-out map (2026-11-08): the contact footprints at z 0..1 of the mount
# feet, the carriages over their travel, the bulkhead and the canopy, plus the plate's own
# posts / standoffs / jack blocks / openings, each grown by a 2.4 web, and a 3 mm edge band.
# Cells between the old rib lines (x -60/-40/-20/0/20/45/66, y 0/+-21.5/+-36.5/+-47), 1.2
# off each line, shrunk until clear. (x0, x1, y0, y1)
TOP_POCKETS = (
    (-73.3, -61.2, -12.8, -1.2),
    (-73.3, -61.2, 1.2, 12.8),
    (-58.8, -41.2, -20.3, -1.2),
    (-58.8, -43.2, 1.2, 20.3),
    (-38.8, -21.2, -18.8, -1.2),
    (-38.8, -21.2, 1.2, 11.8),
    (-18.8, -1.2, -20.3, -1.2),
    (-18.8, -1.2, 1.2, 20.3),
    (1.2, 18.8, -18.8, -1.2),
    (1.2, 18.8, 1.2, 11.8),
    (22.7, 43.8, -45.8, -37.7),
    (22.7, 43.8, 37.7, 45.8),
    (46.2, 62.3, -45.8, -37.7),
    (46.2, 62.3, 37.7, 45.8),
)
# Ben (2026-11-06): the 45° front chamfers are gone. The bulkhead and its cheeks span
# |y| 52 at x 82-85 and hung over the cut corner (an unfinished-looking gap under the
# face). Square front corners with a small plan radius (kid-safety r >= 1; E1 family 3).
FRONT_R = 3.0  # front plan corner radii at +X
MOUNT_CHAMFER_REF = 20.0  # the old chamfer line still fixes the motor station (mount_tx 47.4)
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
MOT_SHAFT_LEN = dt.TT_SHAFT_LEN  # protrusion past the gearbox face (8.5, Ben 2026-11-09)
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
# Encoder socket (Ben 2026-11-08): a block on the encoder board facing the chassis centre,
# 16.8 along the body from ~1 mm in from the encoder end, 13.35 tall, standing 8.5 past the
# mount face (motor frame y 0 -> -8.5). Centred on the motor axis (Ben: "located in the
# middle", so both sides sit alike): chassis z 6.8-20.2, its bottom 4 over the mount foot's top.
MOT_CONN_L, MOT_CONN_OUT, MOT_CONN_IN = 16.8, 8.5, 1.0  # length, protrusion, inset from the end
MOT_CONN_Z = 13.35 / 2  # half-height about the motor axis

# --------------------------------------------------------- motor mount (measured)
# TT_Motor_Mount_L.SLDPRT in its own frame (read 2026-10-30): foot Z 0..3, upright
# wall Y -31..-28, motor holes along Y at X 14.5, Z 2.5 and 20.5 (18 apart).
MOUNT_HOLE = (14.5, -28.0, 13.5)  # hole-pair midpoint on the motor-side face
# > Amendment (loop P2, 2026-10-30): z 11.5 -> 13.5 and pitch 18 -> 17.5 (the drawing).
# Ben's mount put the motor centre 11.5 up, so its 25 mm encoder and 22 mm gearbox hit
# the plate and foot (323 / 197 mm³); 13.5 clears both and gives the lower insert 2.4 mm
# of wall under it.
MOUNT_FOOT_Y = (-47.0, -8.9)  # foot extent across the upright
# Foot screw holes (mount part frame), one source for the mount's clearance holes and the
# plate's insert holes. Ben 2026-11-08: the three at y -38.9 sat under the upright's 3.6 root
# chamfer (toe y -37.6): an M3 head (r 2.75) or washer (r 3.5) at -38.9 landed on the slope at
# x -11.2 and 3.5. Moved out to y -41.5: head edge -38.75, washer -38.0, clear of the toe;
# 3.8 mm from the hole edge to the foot's outer edge (y -47). The chamfer stays (S2's root).
MOUNT_FOOT_HOLES = ((-11.2, -41.5), (-25.2, -41.5), (3.5, -41.5), (-25.2, -23.0))

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
    # the (former) front chamfer line x + |y| <= PLATE_L/2 + PLATE_W/2 - MOUNT_CHAMFER_REF.
    # Kept as a reference so squaring the plate's corners leaves the drivetrain where it is.
    ty = mount_ty()
    lim = PLATE_L / 2 + PLATE_W / 2 - MOUNT_CHAMFER_REF - CHAMFER_MARGIN
    return min(lim - abs(-py - ty) + px for px, py in FOOT_FRONT_CORNERS)


# ------------------------------------------------------------------- helpers
def plate_profile() -> str:
    hx, hy, c, r = PLATE_L / 2, PLATE_W / 2, FRONT_R, REAR_RADIUS
    return " ".join(
        [
            f"M {hx} {-(hy - c)}",
            f"L {hx} {hy - c}",
            f"A {hx - c} {hy - c} {hx - c} {hy}",
            f"L {-(hx - r)} {hy}",
            f"A {-(hx - r)} {hy - r} {-hx} {hy - r}",
            f"L {-hx} {-(hy - r)}",
            f"A {-(hx - r)} {-(hy - r)} {-(hx - r)} {-hy}",
            f"L {hx - c} {-hy}",
            f"A {hx - c} {-(hy - c)} {hx} {-(hy - c)}",
        ]
    )


def plate_volume() -> float:
    a = (
        PLATE_L * PLATE_W
        - 2 * (FRONT_R**2 * (1 - math.pi / 4))
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
        f"box|{MOT_CAN_END + MOT_CONN_IN} {MOT_CAN_END + MOT_CONN_IN + MOT_CONN_L}|"
        f"{-MOT_CONN_OUT} 0|{-MOT_CONN_Z} {MOT_CONN_Z}",  # encoder socket
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
    c0, c1 = MOT_CAN_END + MOT_CONN_IN, MOT_CAN_END + MOT_CONN_IN + MOT_CONN_L
    v_conn = (c1 - c0) * MOT_CONN_OUT * 2 * MOT_CONN_Z
    v_conn -= max(0.0, min(c1, e1) - c0) * max(0.0, -ey0) * 2 * min(MOT_CONN_Z, ew)  # in the encoder
    # double-D flats, normal to the motor's X (the sprocket's D-bore flats face the same
    # way): a round envelope here read as a 15.4 mm3 clash with the bore (P11)
    r, f = MOT_SHAFT_D / 2, MOT_SHAFT_FLAT / 2
    seg = r * r * math.acos(f / r) - f * math.sqrt(r * r - f * f)
    v_shaft = math.pi * r * r * MOT_SHAFT_LEN - 2 * seg * MOT_SHAFT_LEN
    v_holes = (
        2 * math.pi * (MOT_HOLE_D / 2) ** 2 * MOT_THICK
    )  # both holes lie in the gearbox
    return ops, v_gear + v_can + v_enc + v_conn + v_shaft - v_holes


def row(r: list[float], t: tuple[float, float, float]) -> str:
    return " ".join(f"{v:g}" for v in [*r, *t])


ROT_I = [1, 0, 0, 0, 1, 0, 0, 0, 1]
ROT_Z180 = [-1, 0, 0, 0, -1, 0, 0, 0, 1]
ROT_Y180 = [-1, 0, 0, 0, 1, 0, 0, 0, -1]
ROT_X180 = [1, 0, 0, 0, -1, 0, 0, 0, -1]


# ------------------------------------------------------ plate features (06 §4)
# Inserts: M3 x 5.7 x 4.6 (07 §4.2). Hole from the PET-CF ladder coupon (Ben 2026-11-08):
# 4.1 seats square, no spin at 0.30 N·m. PC parts (canopy) stay on the 4.0 placeholder until
# the PC ladder is pressed.
INS_HOLE, INS_DEPTH, INS_BOSS = 4.1, 7.2, 9.2
INS_HOLE_PC = 4.0  # TBD: RB-CPN-003@PC
# D5 (tick 45): the plate's motor-mount pockets sit in an 8 mm stack (plate 4 + boss 4), so
# 7.2 left a 0.8 mm floor a hot insert can push through; 6.7 = the 5.7 insert + 1.0 for the
# displaced melt, floor 1.3 (>= the 1.2 wall rule)
MOUNT_INS_DEPTH = 6.7
CLR_M3, CBORE_M3, CBORE_DEPTH = 3.4, 6.5, 2.0
UNDER_BOSS_Z = -8.0  # rev 1: plate 4 + 4 mm under-boss for the motor-mount inserts (07 F2)
PLATE_BOTTOM = UNDER_BOSS_Z if BOTTOM_RIBS else -PLATE_T  # lowest point of the plate
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
GUIDE_W = 4.5  # 4.0 rail + 0.25/side; slide coupon RB-CPN-001 (Ben 2026-11-08, 05 amendment)
RAIL_L = 20.0  # TBD with the carriage design
JACK_BLOCK_X, JACK_BLOCK_Y, JACK_BLOCK_Z = (-38.0, -28.0), (31.0, 42.0), (0.0, 10.0)
JACK_Y, JACK_Z = 36.5, 5.0  # F4b: M3 jack screw in an insert along X

# P14 motor-bell relief: x span, |y| span, depth
BELL_POCKET = ((-11.0, 20.0), (31.0, 53.0), 2.0)

# Bulkhead foot (06 §5, F1): only x >= 78.5 is clear of the motor-mount feet.
BULK_X = 81.5
BULK_HOLES_Y = (-22.0, 0.0, 22.0)
BULK_TAB_Y, BULK_TAB = 11.0, (4.6, 10.4)  # locating-tab slots (X x Y)

# Pi deck posts (F5): clear of the reflex board (x -40..12.5, |y| <= 23 since 2026-11-09), the mount
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
    foot = MOUNT_FOOT_HOLES
    tx, ty = mount_tx(), mount_ty()
    right = [(-x + tx, -y - ty) for x, y in foot]  # TT_Motor_Mount_L, Rz180
    left = [(-x + tx, y + ty) for x, y in foot]  # mirror part, Ry180
    return right + left


def edge_room(x: float, y: float) -> float:
    """Distance from (x, y) to the nearest plate edge (front, sides, front corner arcs)."""
    hx, hy, c = PLATE_L / 2, PLATE_W / 2, FRONT_R
    d = min(hy - abs(y), hx - abs(x))
    if x > hx - c and abs(y) > hy - c:
        d = min(d, c - math.hypot(x - (hx - c), abs(y) - (hy - c)))
    return d


# Shapes: ("outline",), ("rect", x0, x1, y0, y1), ("circle", cx, cy, r),
# ("slot", xa, ya, xb, yb, r) with the slot axis along X or Y.
def shape_prof(s: tuple) -> str:
    if s[0] == "outline":
        return plate_profile()
    if s[0] == "rect":
        _, x0, x1, y0, y1 = s
        return f"M {x0} {y0} L {x1} {y0} L {x1} {y1} L {x0} {y1}"
    if s[0] == "rrect":  # rounded rectangle, corner radius r; arcs CCW (centre, end)
        _, x0, x1, y0, y1, r = s
        return (
            f"M {x0 + r} {y0} L {x1 - r} {y0} A {x1 - r} {y0 + r} {x1} {y0 + r} "
            f"L {x1} {y1 - r} A {x1 - r} {y1 - r} {x1 - r} {y1} L {x0 + r} {y1} "
            f"A {x0 + r} {y1 - r} {x0} {y1 - r} L {x0} {y0 + r} A {x0 + r} {y0 + r} {x0 + r} {y0}"
        )
    if s[0] == "slot":
        _, xa, ya, xb, yb, r = s
        if ya == yb:  # along X
            return f"M {xb} {ya - r} A {xb} {ya} {xb} {ya + r} L {xa} {ya + r} A {xa} {ya} {xa} {ya - r}"
        return f"M {xa + r} {ya} L {xa + r} {yb} A {xa} {yb} {xa - r} {yb} L {xa - r} {ya} A {xa} {ya} {xa + r} {ya}"
    raise ValueError(s)


def shape_mask(s: tuple, X, Y):
    import numpy as np

    if s[0] == "outline":
        hx, hy, c, r = PLATE_L / 2, PLATE_W / 2, FRONT_R, REAR_RADIUS
        m = (np.abs(X) <= hx) & (np.abs(Y) <= hy)
        corner = (X < -(hx - r)) & (np.abs(Y) > hy - r)
        m &= ~(corner & ((X + hx - r) ** 2 + (np.abs(Y) - (hy - r)) ** 2 > r * r))
        fc = (X > hx - c) & (np.abs(Y) > hy - c)
        return m & ~(fc & ((X - (hx - c)) ** 2 + (np.abs(Y) - (hy - c)) ** 2 > c * c))
    if s[0] == "rect":
        _, x0, x1, y0, y1 = s
        return (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    if s[0] == "rrect":
        _, x0, x1, y0, y1, r = s
        cx, cy = np.clip(X, x0 + r, x1 - r), np.clip(Y, y0 + r, y1 - r)
        return (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1) & ((X - cx) ** 2 + (Y - cy) ** 2 <= r * r)
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
    # motor-mount inserts: under-boss, sized down where a plate edge is close
    for x, y in mount_holes():
        if BOTTOM_RIBS:
            r = min(INS_BOSS / 2, round(edge_room(x, y) - 0.04, 2))
            add.append(("add", ("circle", x, y, r), UNDER_BOSS_Z, -PLATE_T))
            cut.append(("cut", ("circle", x, y, INS_HOLE / 2), -MOUNT_INS_DEPTH, 0.0))
        else:  # rev 2: the 5.7 insert in a 6 mm plate: hole through, insert flush with the top
            cut.append(("all", ("circle", x, y, INS_HOLE / 2), 0, 0))
    # rev 2: pockets in the top where nothing rests (TOP_POCKETS)
    if not BOTTOM_RIBS:
        for x0, x1, y0, y1 in TOP_POCKETS:
            cut.append(("cut", ("rrect", x0, x1, y0, y1, POCKET_R), -POCKET_D, 0.1))
    # bottom ribs (rev 1)
    for y, (lx0, lx1) in LONG_RIBS if BOTTOM_RIBS else ():
        add.append(
            (
                "add",
                ("rect", lx0, lx1, y - PLATE_RIB_T / 2, y + PLATE_RIB_T / 2),
                -PLATE_T - PLATE_RIB_H,
                -PLATE_T,
            )
        )
    if LOAD_RIBS and BOTTOM_RIBS:
        for y, (x0, x1) in LOAD_RIBS_YX:
            for sgn in (-1, 1):
                y0, y1 = sorted(
                    (sgn * (y - LOAD_RIB_T / 2), sgn * (y + LOAD_RIB_T / 2))
                )
                add.append(("add", ("rect", x0, x1, y0, y1), LOAD_RIB_Z, -PLATE_T))
    for x in CROSS_RIBS_X if BOTTOM_RIBS else ():
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
            -PLATE_T - 0.1,
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
PLATE_SLOT_EDGE_R = 0.5  # tick 88: 2 mm wide slots (r 1 would round through)


def plate_perimeter() -> float:
    """Outline length: straight front/rear/sides, two front and two rear corner arcs."""
    c, r = FRONT_R, REAR_RADIUS
    front = PLATE_W - 2 * c
    rear = PLATE_W - 2 * r
    sides = 2 * (PLATE_L - c - r)
    return front + rear + sides + 2 * (math.pi / 2) * (c + r)


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
    if BOTTOM_RIBS:
        dvb = (1 - math.pi / 4) * PLATE_EDGE_R**2 * belly_edge_length()
        lines.append(
            f"filletface|{PLATE_EDGE_R}|-1|{UNDER_BOSS_Z}|{-hx} {-hy} {hx} {hy}|any|{-dvb:.2f} {0.15 * dvb:.2f}|all"
        )
        vol -= dvb
    else:
        # rev 2: r 1.0 round every top pocket's floor edge (concave, 07 fil_in; PET-CF is
        # notch-sensitive): adds (1 - pi/4) r^2 per mm of floor edge
        per = sum(2 * ((x1 - x0) + (y1 - y0)) - (8 - 2 * math.pi) * POCKET_R for x0, x1, y0, y1 in TOP_POCKETS)
        dvf = (1 - math.pi / 4) * PLATE_EDGE_R**2 * per
        lines.append(
            f"filletface|{PLATE_EDGE_R}|1|{-POCKET_D}|{-hx} {-hy} {hx} {hy}|any|{dvf:.2f} {0.15 * dvf:.2f}|all"
        )
        vol += dvf
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
    # P-kid (tick 88): r 0.5 on the canopy-tongue slots' belly edges (28.2 x 2.0: r 1 would
    # round through), the plate's biggest accessible sharp clusters after the R3 label
    (_, _), (tx0, tx1), _, cl = CAN_TAB
    ts_len = 2 * ((tx1 - tx0 + 2 * cl) + (CAN_T + 2 * cl))
    dvts = (1 - math.pi / 4) * PLATE_SLOT_EDGE_R**2 * ts_len
    for sgn in (-1, 1):
        ya, yb = sorted((sgn * (CAN_HW - CAN_T - cl - 3), sgn * (CAN_HW + cl + 3)))
        lines.append(
            f"filletface|{PLATE_SLOT_EDGE_R}|-1|{-PLATE_T}|{-hx} {-hy} {hx} {hy}|any|{-dvts:.2f} {0.25 * dvts:.2f}"
            f"|loops:{tx0 - 3} {ya} {tx1 + 3} {yb}"
        )
        vol -= dvts
    # D1b (tick 82, REJECTED): an r 2 round of each jack block's root (one 4-edge feature)
    # made S1m 9.97 -> 13.3, S1a 11.6 -> 14.8, S1b 3.7 -> 4.3 (half mesh 5.0 -> 7.9) at the
    # vertex where the fillet's corner blend meets the plate (-40 / -26, +-29, 0). Removed.
    # Retry (tick 90, REJECTED): r 3 vertical corners first, then r 2 on the tangent root
    # loop: S1m 9.2 -> 8.4, S1b 3.45 -> 2.93 at the 2 mm mesh, but half mesh 23 MPa on the
    # toroidal blend's tangent seam (-35, -30.9, 1.3): not converged. Roots stay square;
    # their S1 peaks are singular and SF is judged on converged measures (07 §3).
    lines += [
        PART_LABELS["plate"],
        f"expect|vol {vol:.1f} {vol * 0.004:.1f}|box {-hx} {hx} {-hy} {hy} {PLATE_BOTTOM} {DECK_Z} 0.01",
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

# P9 (tick 99): XVF3800 core board (Seeed DXF/STEP, audio-hardware §3: 70.5 x 52.2 x 1.5,
# 4 x Ø3.3 on 62.5 x 44.2, parts 9.0 up / leads 1.6 down; USB-C, 3.5 jack, PH-4 on one long
# edge). The voxel map of the canopy interior (tick 99) finds it only fits on edge: the free
# bay outboard of the Pi on the -y side (x -74..42, z 27..92, |y| 36..48; +y is the Pi/HAT
# port side, aft is the Pi's USB plug space). Board in the x-z plane, parts outboard (2.0
# off the canopy wall), connector edge DOWN with the USB-C over the free pocket between the
# right carriage and motor (x -50..-10, z 3..24) for a right-angle plug; USB-C end forward.
# It hangs on a wall standing on the deck (the canopy lifts off, so nothing on it): the deck
# widens to the wall aft of the motor (x <= -12); forward of that the wall overhangs the
# motor from z 27.5. Its upper holes sit level with the keel (z >= 73, |y| 30.6..32.4), so
# the standoff + wall is 5.0: M2.5 x 4 inserts (Ben 2026-11-05) pressed through Ø8 bosses,
# M2.5 x 6 SHCS (M3 inserts need a 6.7 pocket).
CORE_PCB = (70.5, 52.2, 1.5)
CORE_HOLES = (62.5, 44.2)  # 4.0 in from each edge
CORE_COMP_H, CORE_LEAD_H = 9.0, 1.6
CORE_X1 = 4.0  # board's forward end (USB-C end); u runs aft from here
CORE_ZB = 27.5  # connector edge (bottom): 1.5 over the right motor's top (26)
CORE_GAP = 2.0  # parts to the canopy's side wall (|y| 51.2)
CORE_BOSS_D, CORE_INS_D = 8.0, 3.6  # Ø8 boss, M2.5 x 4 insert pocket, through
CORE_WALL_T = 2.0
CORE_WALL_X = (-68.0, 6.0)
CORE_WALL_TOP = 80.0
CORE_DECK_X1 = -12.0  # deck widening ends aft of the motor / encoder (x -10)
CORE_USB = (29.5, 38.4, 1.3, 4.9)  # u span, proud of the edge, top above the PCB
CORE_JACK = (54.8, 62.1, 2.0, 7.1)


def core_overhang_poly() -> list[tuple[float, float]]:
    """P9: the wall forward of the deck (x CORE_DECK_X1 .. CORE_WALL_X[1]), deck frame (x, z).
    The deck prints top up, so its underside rises at 45° from the deck's bottom + 1 (support-
    free; 1.0 over the motor's top at x -10). The forward-lower standoff goes with it: the
    board hangs on 3 of its 4 holes."""
    zc = DECK_Z + DECK_T
    x0, x1 = CORE_DECK_X1, CORE_WALL_X[1]
    zb = -DECK_T + 1.0
    return [(x0, zb), (x1, zb + (x1 - x0)), (x1, CORE_WALL_TOP - zc), (x0, CORE_WALL_TOP - zc)]


# P9b (S1e, 20 g drop): the bare 2 mm wall let the bores move 1.95 mm toward the canopy wall
# (2.0 gap), so no lightening window. Stiffeners on its inboard face, inside the 5.7 gap to
# the Pi box (|y| 28) and under the keels (chassis z 73): vertical ribs and a 45° top chord.
CORE_RIB_D, CORE_RIB_T = 4.0, 2.0  # depth inboard of the wall, thickness
CORE_RIB_X = (-66.0, -42.0, -18.0)  # rib centres; the last 5 aft of the deck step at x -12 (a rib flush with it took S1d 9.0 -> 15.3)
CORE_RIB_TOP = 72.7  # chassis z: the keel bottoms are at 73


def core_stiffeners() -> tuple[list, list[str], float]:
    """Deck-frame features: ribs (deck_features adds), the chord (a Right-plane prism), volume
    of the chord minus its overlap with the ribs."""
    zc = DECK_Z + DECK_T
    wi = core_geom()["y_wall"][1]  # wall's inboard face
    zt = CORE_RIB_TOP - zc
    ribs = [("add", ("rect", x - CORE_RIB_T / 2, x + CORE_RIB_T / 2, wi, wi + CORE_RIB_D), -DECK_T, zt)
            for x in CORE_RIB_X]
    d = CORE_RIB_D  # chord: triangle in (y, z), 45° underside off the wall; Right plane (-z, y)
    tri = [(wi, zt), (wi + d, zt), (wi, zt - d)]
    chord = ("prof|{:.3f} {:.3f}|M {:.3f} {:.3f} ".format(CORE_WALL_X[0], CORE_WALL_X[1], -tri[0][1], tri[0][0])
             + " ".join(f"L {-z:.3f} {y:.3f}" for y, z in tri[1:]) + "|boss|right")
    area = d * d / 2
    vol = area * (CORE_WALL_X[1] - CORE_WALL_X[0]) - area * CORE_RIB_T * len(CORE_RIB_X)
    return ribs, [chord], vol


def core_standoffs() -> list[tuple[float, float]]:
    """Holes that get a standoff: all but the forward-lower one (under the 45° overhang)."""
    zc = DECK_Z + DECK_T
    poly = core_overhang_poly()
    out = []
    for hx, hz in core_geom()["holes"]:
        if hx > CORE_DECK_X1:  # on the overhang: boss must sit above its 45° underside
            zl = poly[0][1] + (hx - poly[0][0]) + zc
            if hz - CORE_BOSS_D / 2 < zl:
                continue
        out.append((hx, hz))
    return out


def core_geom() -> dict:
    """P9: core board in the chassis frame (u along -x from CORE_X1, v up from CORE_ZB)."""
    L, W, t = CORE_PCB
    y_out = -(CAN_HW - CAN_T) + CORE_GAP + CORE_COMP_H  # PCB outer (parts) face: -40.2
    y_back = y_out + t  # -38.7
    y_wall = y_back + (5.0 - CORE_WALL_T)  # wall's outboard face: -35.7
    hu, hv = (L - CORE_HOLES[0]) / 2, (W - CORE_HOLES[1]) / 2
    holes = [(CORE_X1 - u, CORE_ZB + v) for u in (hu, L - hu) for v in (hv, W - hv)]
    return {"x": (CORE_X1 - L, CORE_X1), "z": (CORE_ZB, CORE_ZB + W), "y_out": y_out, "y_back": y_back,
            "y_wall": (y_wall, y_wall + CORE_WALL_T), "holes": holes}


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
    g = core_geom()
    zc = DECK_Z + DECK_T  # chassis z of the deck frame's 0
    wy0, wy1 = g["y_wall"]
    add += [
        ("add", ("rect", CORE_WALL_X[0], CORE_DECK_X1, wy0, -DECK_HW + 0.5), z0, z1),  # widening
        ("add", ("rect", CORE_WALL_X[0], CORE_DECK_X1, wy0, wy1), z0, CORE_WALL_TOP - zc),
    ]  # + the overhang forward of CORE_DECK_X1 (core_overhang_poly, a Top-plane prism)
    add += core_stiffeners()[0]  # P9b ribs (+ the chord, a Right-plane prism in deck_lines)
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
    g = core_geom()
    vol = features_volume(
        feats, (DECK_X[0] - 1, DECK_TONGUE[0] + 1), (g["y_wall"][0] - 1, DECK_HW + 1)
    )
    zc = DECK_Z + DECK_T
    yb, yw1 = g["y_back"], g["y_wall"][1]
    boss = []
    wy0, wy1 = g["y_wall"]
    pts = core_overhang_poly()
    boss.append(f"prof|{wy0:.3f} {wy1:.3f}|M {pts[0][0]:.3f} {-pts[0][1]:.3f} "
                + " ".join(f"L {x:.3f} {-z:.3f}" for x, z in pts[1:]) + "|boss|top")
    vol += _poly_area(pts) * CORE_WALL_T
    _, chord, cvol = core_stiffeners()  # P9b
    boss += chord
    vol += cvol
    for hx, hz in core_standoffs():  # P9 standoffs: board back -> wall's inboard face, insert through
        boss.append(f"cyl|y|{hx:.3f} {hz - zc:.3f}|{yb:.3f} {yw1:.3f}|{CORE_BOSS_D / 2}|boss")
        boss.append(f"cyl|y|{hx:.3f} {hz - zc:.3f}|{yb - 0.1:.3f} {yw1 + 0.1:.3f}|{CORE_INS_D / 2}|cut")
        vol += math.pi * (CORE_BOSS_D / 2) ** 2 * (g["y_wall"][0] - yb)  # outboard of the wall
        vol -= math.pi * (CORE_INS_D / 2) ** 2 * (yw1 - yb)
    return [
        f"part|{path}",
        *feature_lines(feats),
        *boss,
        PART_LABELS["deck"],
        f"expect|vol {vol:.1f} {vol * 0.004:.1f}|box {DECK_X[0]} {DECK_TONGUE[0]} {yb:.2f} {DECK_HW} {-DECK_T} {CORE_WALL_TOP - zc:.2f} 0.01",
        "save",
    ]


def core_board_lines(path: str) -> list[str]:
    """P9 envelope (interference only), chassis frame: PCB, the parts layer outboard, the
    lead layer inboard (clear Ø8.4 round each standoff), USB-C and jack proud of the edge."""
    g = core_geom()
    (x0, x1), (z0, z1) = g["x"], g["z"]
    yo, yb = g["y_out"], g["y_back"]
    ycomp, ylead = yo - CORE_COMP_H, yb + CORE_LEAD_H

    def blk(xa, xb, ya, yb_, za, zb_):  # Top plane (x, -z) prism along y
        return (f"prof|{min(ya, yb_):.3f} {max(ya, yb_):.3f}|M {xa:.3f} {-za:.3f} L {xb:.3f} {-za:.3f} "
                f"L {xb:.3f} {-zb_:.3f} L {xa:.3f} {-zb_:.3f}|boss|top")

    ln = [f"part|{path}", blk(x0, x1, ycomp, ylead, z0, z1)]
    v = (x1 - x0) * (z1 - z0) * (ylead - ycomp)
    for u0, u1, proud, top in (CORE_USB, CORE_JACK):
        ln.append(blk(CORE_X1 - u1, CORE_X1 - u0, yo - top, yo, z0 - proud, z0 + 0.5))
        v += (u1 - u0) * proud * top
    rc = CORE_BOSS_D / 2 + 0.2
    for hx, hz in g["holes"]:
        ln.append(f"cyl|y|{hx:.3f} {hz:.3f}|{yb:.3f} {ylead + 0.1:.3f}|{rc}|cut")
        ln.append(f"cyl|y|{hx:.3f} {hz:.3f}|{ycomp - 0.1:.3f} {ylead + 0.1:.3f}|1.65|cut")
        # 2026-11-10: parts keep-out Ø5 round each hole on the parts face (the F8 heads)
        ln.append(f"cyl|y|{hx:.3f} {hz:.3f}|{ycomp - 0.1:.3f} {yo + 0.05:.3f}|2.5|cut")
        v -= math.pi * rc * rc * CORE_LEAD_H + math.pi * 1.65**2 * (yb - ycomp)
        v -= math.pi * (2.5**2 - 1.65**2) * (yo - ycomp)
    ln += [f"expect|vol {v:.1f} {v * 0.01:.1f}|box {x0:.2f} {x1:.2f} {ycomp:.2f} {ylead:.2f} "
           f"{z0 - CORE_JACK[2]:.2f} {z1:.2f} 0.05", "save"]
    return ln


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

# Reflex board (KiCad hardware/kicad/robot-buddy-reflex), from board_outline.py:
# 52.5 x 46 since 2026-11-09 (was 65 x 60 with encoder notches), M3 holes 3.5 in from
# each edge (45.5 x 39 pattern). Frame: origin at the hole-pattern centre on the PCB's
# bottom face, KiCad Y flipped. TBD: component heights (12 top, 2 bottom).
REFLEX_X = (-pcb_outline.HOLE_CX, pcb_outline.W - pcb_outline.HOLE_CX)
REFLEX_Y = (pcb_outline.HOLE_CY - pcb_outline.H, pcb_outline.HOLE_CY)
REFLEX_HOLES = pcb_outline.HOLE_HALF
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
    # (encoder-socket notches removed 2026-11-09: the 46 mm board spans |y| <= 23, inside
    # the sockets' |y| 23.9, along its whole length; board_outline.py)
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
    pcb_outline.REAR_EDGE_CHASSIS_X + pcb_outline.HOLE_CX,  # rear edge (USB-C) stays at x -40
    0.0,  # board centred on the chassis centreline: |y| <= 23, the encoder sockets at 23.9
    5.0,
)  # between the motors, x -40..12.5 (was -40..25 at 65 x 60)
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
    "plate": f"text|front|11.5 -6.75|{-PLATE_T - 0.5} {-PLATE_T + 0.6}|4|RB-001 r2|mirror",  # rev 2
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
        f"expect|vol {m_vol:.1f} 5.0|box {MOT_CAN_END} {MOT_GEAR_END} {-MOT_CONN_OUT} "
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
        *wheel_lines(sprocket, dt.sprocket_layers(True), SPROCKET_SPOKES),
        *wheel_lines(idler, dt.idler_layers(2)),
        *wheel_lines(road, dt.road_wheel_layers()),
        *road_axle_lines(road_axle),
        # P7 / P8 (tick 93): speaker clamp, gasket and module envelope
        *speaker_clamp_lines(cad + r"\parts\RB-PRT-060_speaker_clamp.SLDPRT"),
        *speaker_gasket_lines(cad + r"\parts\RB-PRT-061_speaker_gasket.SLDPRT"),
        *speaker_module_lines(cad + r"\library\speaker_module_envelope.SLDPRT"),
        # 2026-11-09: Camera Module 3 envelope (on the bulkhead's camera bosses)
        *camera_module_lines(cad + r"\library\camera_module3_envelope.SLDPRT"),
        *hcsr04_lines(cad + r"\library\hcsr04_envelope.SLDPRT"),
        *pam8302_lines(cad + r"\library\pam8302_envelope.SLDPRT"),
        *sonar_holder_lines(cad + r"\parts\RB-PRT-070_sonar_holder.SLDPRT"),
        # P6m2 (2026-11-08): the mic disc envelope + its TPU washers (the disc hangs in the canopy's hump)
        *mic_disc_lines(cad + r"\library\mic_disc_envelope.SLDPRT"),
        *mic_washer_lines(cad + r"\parts\RB-PRT-062_mic_washer.SLDPRT"),
        # 2026-11-09 (Ben): spacer between the idler's two 624 inner races
        *idler_spacer_lines(cad + r"\parts\RB-PRT-023_idler_spacer.SLDPRT"),
        # 2026-11-10: bought hardware envelopes (tools/hardware.py), placed below
        *[ln for it in hardware_items().values() for ln in hw.item_lines(it, cad + "\\library\\" + it.name + ".SLDPRT")],
        # P9 (tick 99): XVF3800 core-board envelope (on the deck's wall)
        *core_board_lines(cad + r"\library\xvf_core_envelope.SLDPRT"),
        # D6 (tick 89): follower-slide fit coupon (not in the assembly, not in the robot mass)
        *coupon_slide_strip_lines(cad + r"\parts\RB-CPN-001_slide_strip.SLDPRT"),
        *coupon_slide_rail_lines(cad + r"\parts\RB-CPN-002_slide_rail.SLDPRT"),
        # D6 (2026-11-06): heat-set insert ladder (Ben's M3 x 5.7 x 4.6, M2.5 x 4)
        *coupon_insert_ladder_lines(cad + r"\parts\RB-CPN-003_insert_ladder.SLDPRT"),
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
        f"comp|spk_clamp|{cad}\\parts\\RB-PRT-060_speaker_clamp.SLDPRT|{row(*speaker_tilt())}",
        f"comp|spk_gasket|{cad}\\parts\\RB-PRT-061_speaker_gasket.SLDPRT|{row(*speaker_tilt())}",
        f"comp|spk_module|{cad}\\library\\speaker_module_envelope.SLDPRT|{row(*speaker_tilt())}",
        f"comp|camera|{cad}\\library\\camera_module3_envelope.SLDPRT|{row(*speaker_tilt())}",
        f"comp|hcsr04|{cad}\\library\\hcsr04_envelope.SLDPRT|{row(*speaker_tilt())}",
        f"comp|sonar_holder|{cad}\\parts\\RB-PRT-070_sonar_holder.SLDPRT|{row(*speaker_tilt())}",
        f"comp|mic_disc|{cad}\\library\\mic_disc_envelope.SLDPRT|{row(ROT_I, (0, 0, 0))}",
        f"comp|xvf_core|{cad}\\library\\xvf_core_envelope.SLDPRT|{row(ROT_I, (0, 0, 0))}",
        *[
            f"comp|mic_washer_{i}{tag}|{cad}\\parts\\RB-PRT-062_mic_washer.SLDPRT|{row(ROT_I, (hx, hy, z))}"
            for i, (hx, hy) in enumerate(mic_geom()["holes"])
            for tag, z in (("a", MIC_PLANE - MIC_WASHER[2]), ("b", mic_geom()["zb"] - MIC_WASHER[2]))
        ],
        *[
            f"comp|idler_spacer_{sd}|{cad}\\parts\\RB-PRT-023_idler_spacer.SLDPRT|{row(*wheel_at(dt.belt_fit()['x_fit'], s, idler_z()))}"
            for sd, s in (("L", +1), ("R", -1))
        ],
        f"comp|amp|{cad}\\library\\pam8302_envelope.SLDPRT|{row(ROT_I, (0, 0, 0))}",
        *hardware_comps(cad + r"\library"),
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
                (cad + r"\parts\RB-PRT-060_speaker_clamp.SLDPRT", "RB-PRT-060_speaker_clamp"),
                (cad + r"\parts\RB-PRT-070_sonar_holder.SLDPRT", "RB-PRT-070_sonar_holder"),
                (cad + r"\parts\RB-PRT-061_speaker_gasket.SLDPRT", "RB-PRT-061_speaker_gasket"),
                (cad + r"\parts\RB-PRT-062_mic_washer.SLDPRT", "RB-PRT-062_mic_washer"),
                (cad + r"\parts\RB-PRT-023_idler_spacer.SLDPRT", "RB-PRT-023_idler_spacer"),
                (cad + r"\parts\RB-CPN-001_slide_strip.SLDPRT", "RB-CPN-001_slide_strip"),
                (cad + r"\parts\RB-CPN-002_slide_rail.SLDPRT", "RB-CPN-002_slide_rail"),
                (cad + r"\parts\RB-CPN-003_insert_ladder.SLDPRT", "RB-CPN-003_insert_ladder"),
            )
        ],
    ]
    return lines


# D6 (tick 89): the follower's slide fit. The carriage's two 4.0 x 3.6 rails (11 apart,
# CAR_RAIL_W/D) run in the plate's guide slots (GUIDE_W, 4.7 when printed; 4.5 after) with an M3 clamp
# slot between. The strip carries three slot pairs, 4.5 / 4.7 / 4.9 wide, each with its
# clamp slot and its width engraved; the rail stub is the carriage foot section. Slide it in
# each pair: the narrowest that slides freely over the full travel sets GUIDE_W.
CPN_SLIDE_W = (4.5, 4.7, 4.9)  # as printed; 4.5 won (GUIDE_W)


def _stadium(x0: float, x1: float, y: float, r: float) -> str:
    """Front-plane slot (x0 .. x1 centre line at y, radius r), arcs CCW."""
    a, b = x0 + r, x1 - r
    return (
        f"M {a:g} {y - r:g} L {b:g} {y - r:g} A {b:g} {y:g} {b:g} {y + r:g} "
        f"L {a:g} {y + r:g} A {a:g} {y:g} {a:g} {y - r:g}"
    )


# P7 / P8 (tick 93): speaker clamp plate (PET-CF) and gasket (TPU 85A), plus the module's
# envelope. All three are modelled in the bulkhead's PRE-TILT frame (the wall vertical, its
# back face at x BH_XF - BH_T) and placed with the wall's 15° tilt about BH_PIVOT.
def speaker_tilt() -> tuple[list[float], tuple[float, float, float]]:
    t = math.radians(BH_TILT)
    c, s_ = math.cos(t), math.sin(t)
    R = [c, 0, -s_, 0, 1, 0, s_, 0, c]  # local +z -> (-sin, 0, cos): the wall leans back
    px, py, pz = BH_PIVOT
    tx = px - (c * px - s_ * pz)
    tz = pz - (s_ * px + c * pz)
    return R, (tx, py, tz)


def _spk_geom() -> dict:
    x0 = BH_XF - BH_T
    (sy_, sz_), (ml, mw, md) = SPK_CTR, SPK_MOD
    iy0, iy1 = sy_ - mw / 2 - SPK_CLR, sy_ + mw / 2 + SPK_CLR
    iz0, iz1 = sz_ - ml / 2 - SPK_CLR, sz_ + ml / 2 + SPK_CLR
    return {
        "x0": x0, "xb": x0 - SPK_DEPTH, "sy": sy_, "sz": sz_, "ml": ml, "mw": mw, "md": md,
        "iy": (iy0, iy1), "iz": (iz0, iz1), "oy": (iy0 - SPK_RIM_T, iy1 + SPK_RIM_T),
        "oz": (iz0 - SPK_RIM_T, SPK_BOSS_Z + INS_BOSS / 2),
    }


def speaker_clamp_lines(path: str) -> list[str]:
    """1.6 plate over the pocket's rim and both boss faces, two Ø3.4 holes for M3 x 8 into
    the bosses' inserts, and a 0.15 pad on the speaker's magnet that squeezes the gasket
    SPK_PRELOAD at nominal depth. Hidden behind the wall: square edges are fine."""
    g = _spk_geom()
    xb, (oy0, oy1), (oz0, oz1) = g["xb"], g["oy"], g["oz"]
    (iy0, iy1), (iz0, iz1) = g["iy"], g["iz"]
    oy1 = iy1 + 0.6  # tick 93: the outboard edge stops 0.6 over the rim (at 27.9 it touched the left mount, 3.6 mm3)
    pt, pad = SPK_CLAMP_T, SPK_PAD
    # tick 97: a square pad on the magnet boss only (the lead's glue blob sits 0.6 proud
    # of the frame at one end; the old full-face pad would have landed on it)
    py0, py1 = g["sy"] - SPK_PAD_W / 2, g["sy"] + SPK_PAD_W / 2
    pz0, pz1 = g["sz"] - SPK_PAD_W / 2, g["sz"] + SPK_PAD_W / 2
    vol = (oy1 - oy0) * (oz1 - oz0) * pt + (py1 - py0) * (pz1 - pz0) * pad
    vol -= len(SPK_BOSS_Y) * math.pi * (CLR_M3 / 2) ** 2 * pt
    return [
        f"part|{path}",
        f"box|{xb - pt:.3f} {xb:.3f}|{oy0:.3f} {oy1:.3f}|{oz0:.3f} {oz1:.3f}",
        f"box|{xb:.3f} {xb + pad:.3f}|{py0:.3f} {py1:.3f}|{pz0:.3f} {pz1:.3f}",
        *[f"cyl|x|{by} {SPK_BOSS_Z:.3f}|{xb - pt - 0.1:.3f} {xb + 0.1:.3f}|{CLR_M3 / 2}|cut" for by in SPK_BOSS_Y],
        # notch for the left mount's end-stop corner (pre-tilt y 26.4-26.9, z' 23.5-25.3):
        # the edge steps back to 25.9 there, still over the module's edge (26.0)
        f"prof|{SPK_NOTCH_Z[0]} {SPK_NOTCH_Z[1]}|M {xb - pt - 0.1:.3f} {SPK_NOTCH_Y} L {xb + pad + 0.1:.3f} {SPK_NOTCH_Y} "
        f"L {xb + pad + 0.1:.3f} {oy1 + 0.1:.3f} L {xb - pt - 0.1:.3f} {oy1 + 0.1:.3f}|cut",
        f"expect|vol {vol - (oy1 - SPK_NOTCH_Y) * (SPK_NOTCH_Z[1] - SPK_NOTCH_Z[0]) * pt:.1f} {vol * 0.01:.1f}|box {xb - pt:.2f} {xb + pad:.2f} {oy0:.2f} {oy1:.2f} {oz0:.2f} {oz1:.2f} 0.05",
        "save",
    ]


def _stadium_right(sy: float, sz: float, length: float, width: float) -> str:
    """Stadium (full-round ends) along z', width along y, as a Right-plane loop (sketch
    x = -z, y = y), drawn like the canopy vent slots."""
    r = width / 2
    ulo, uhi = -(sz - length / 2 + r), -(sz + length / 2 - r)
    return (
        f"M {ulo:.4f} {sy - r:.4f} L {uhi:.4f} {sy - r:.4f} a {uhi:.4f} {sy:.4f} {uhi:.4f} {sy + r:.4f} "
        f"L {ulo:.4f} {sy + r:.4f} a {ulo:.4f} {sy:.4f} {ulo:.4f} {sy - r:.4f}"
    )


def _stadium_area(length: float, width: float) -> float:
    return (length - width) * width + math.pi * (width / 2) ** 2


def speaker_gasket_lines(path: str) -> list[str]:
    """P8: TPU 85A ring, SPK_GASKET_T thick, between the speaker's face and the wall, round
    the grille slots. Tick 97: follows the speaker's stadium outline (a rectangular ring
    left the four corners open: front and back waves would meet), SPK_GASKET_BAND wide."""
    g = _spk_geom()
    x0, sy, sz, ml, mw = g["x0"], g["sy"], g["sz"], g["ml"], g["mw"]
    b = SPK_GASKET_BAND
    vol = (_stadium_area(ml, mw) - _stadium_area(ml - 2 * b, mw - 2 * b)) * SPK_GASKET_T
    return [
        f"part|{path}",
        f"prof|{x0 - SPK_GASKET_T:.3f} {x0:.3f}|{_stadium_right(sy, sz, ml, mw)}|boss|right",
        f"prof|{x0 - SPK_GASKET_T - 0.1:.3f} {x0 + 0.1:.3f}|{_stadium_right(sy, sz, ml - 2 * b, mw - 2 * b)}|cut|right",
        f"expect|vol {vol:.1f} {vol * 0.02:.1f}|box {x0 - SPK_GASKET_T:.2f} {x0:.2f} {sy - mw / 2:.2f} {sy + mw / 2:.2f} {sz - ml / 2:.2f} {sz + ml / 2:.2f} 0.05",
        "save",
    ]


def speaker_module_lines(path: str) -> list[str]:
    """Envelope of the speaker (interference only): its stadium outline at the thinnest
    depth the datasheet allows (SPK_MOD depth - SPK_TOL, less 0.02 so touching doesn't read
    as an interference), face on the gasket. That part just meets the clamp pad: every
    thicker one squeezes the gasket."""
    g = _spk_geom()
    x1 = g["x0"] - SPK_GASKET_T
    d = g["md"] - SPK_TOL - 0.02
    sy, sz, ml, mw = g["sy"], g["sz"], g["ml"], g["mw"]
    v = _stadium_area(ml, mw) * d
    return [
        f"part|{path}",
        f"prof|{x1 - d:.3f} {x1:.3f}|{_stadium_right(sy, sz, ml, mw)}|boss|right",
        f"expect|vol {v:.1f} {v * 0.005:.1f}|box {x1 - d:.2f} {x1:.2f} {sy - mw / 2:.2f} {sy + mw / 2:.2f} {sz - ml / 2:.2f} {sz + ml / 2:.2f} 0.05",
        "save",
    ]


def camera_module_lines(path: str) -> list[str]:
    """Camera Module 3 envelope (interference only), in the bulkhead's pre-tilt frame like the
    speaker module (placed with speaker_tilt()): PCB, lens block, barrel and the FFC
    connector, each 0.02 off the faces it bears on so touching doesn't read as interference."""
    x0 = BH_XF - BH_T
    cy, cz, _ = BH_CAM
    w, h, t = CAM_PCB
    zb = cz - CAM_LENS_UP
    xf = x0 - CAM_BLOCK_D - 0.02  # PCB front
    cw, chh, cd = CAM_CONN
    hb = CAM_BLOCK / 2
    xbf = x0 - 0.02  # block front
    lines = [
        f"part|{path}",
        f"box|{xf - t:.3f} {xf:.3f}|{cy - w / 2} {cy + w / 2}|{zb:.3f} {zb + h:.3f}",
        f"box|{xf:.3f} {xbf:.3f}|{cy - hb} {cy + hb}|{cz - hb} {cz + hb}",
        f"cyl|x|{cy} {cz}|{xbf - 0.1:.3f} {xbf + CAM_BARREL_L:.3f}|{CAM_BARREL_R}|boss",
        f"box|{xf - t - cd:.3f} {xf - t:.3f}|{cy - cw / 2} {cy + cw / 2}|{zb + h - chh:.3f} {zb + h:.3f}",
        # 2026-11-10: the PCB's 4 x Ø2.2 mounting holes (F16)
        *[f"cyl|x|{cy + dy} {cz + dz}|{xf - t - 0.1:.3f} {xf + 0.1:.3f}|1.1|cut" for dy, dz in CAM_HOLES],
    ]
    v = w * h * t + CAM_BLOCK**2 * (xbf - xf) + math.pi * CAM_BARREL_R**2 * CAM_BARREL_L + cw * chh * cd
    v -= len(CAM_HOLES) * math.pi * 1.1**2 * t
    lines += [
        f"expect|vol {v:.1f} {v * 0.01:.1f}|box {xf - t - cd:.2f} {xbf + CAM_BARREL_L:.2f} {cy - w / 2:.2f} {cy + w / 2:.2f} {zb:.2f} {zb + h:.2f} 0.05",
        "save",
    ]
    return lines


def _disc_in_rect(cy: float, cz: float, r: float, y0: float, y1: float, z0: float, z1: float) -> float:
    """Area of a disc inside an axis-aligned rectangle (numeric, for expect volumes)."""
    import numpy as np

    st = 0.01
    ys = np.arange(cy - r + st / 2, cy + r, st)
    zs = np.arange(cz - r + st / 2, cz + r, st)
    Y, Z = np.meshgrid(ys, zs)
    m = ((Y - cy) ** 2 + (Z - cz) ** 2 <= r * r) & (Y >= y0) & (Y <= y1) & (Z >= z0) & (Z <= z1)
    return float(m.sum()) * st * st


HC_HOLE_R, HC_HEAD_KEEP_R = 0.9, 1.75  # 2026-11-10: PCB holes Ø1.8, parts keep-out Ø3.5 (F17 heads Ø3.2; Ø3.6 is tangent to the PCB edge)


def hcsr04_lines(path: str) -> list[str]:
    """HC-SR04 envelope (interference only), pre-tilt frame, seated in the merged holder: PCB
    45 x 20 x 1.6 (front on the pocket step), two Ø16 x 13 cans, a 1.5 back-parts zone kept
    1 mm off the long edges (the snap ridges), and the header bent straight back with a
    Dupont plug (2.54 x 10.2, 4.7 + 14 long) at the top (upside down)."""
    xf = SR_FRONT - 12.25 - 0.02  # PCB front
    xb = xf - 1.6
    yc, zc = sr_map(31.0, 12.0)  # centred in the pocket (zh 1.5 .. 22.5); the cans sit 0.5 off it
    # 19.6 tall: the PCB's edges pass the snap ridges (0.17 a side) by design
    lines = [f"part|{path}", f"box|{xb:.3f} {xf:.3f}|{yc - 22.5} {yc + 22.5}|{zc - 9.8} {zc + 9.8}"]
    v = 45 * 19.6 * 1.6
    for xh, zh in SR_HOLES:
        hy, hz = sr_map(xh, zh)
        lines.append(f"cyl|x|{hy} {hz}|{xf - 0.1:.3f} {xf + 13:.3f}|8.0|boss")
        v += math.pi * 64 * 13
    lines.append(f"box|{xb - 1.5:.3f} {xb + 0.1:.3f}|{yc - 21.5} {yc + 21.5}|{zc - 9} {zc + 9}")
    v += 43 * 18 * 1.5
    # 2026-11-10: the mounting holes and a parts keep-out round them (the F17 screw heads)
    for xh, zh in SR_PCB_HOLES:
        hy, hz = sr_map(xh, zh)
        lines.append(f"cyl|x|{hy} {hz}|{xb - 1.6:.3f} {xf + 0.1:.3f}|{HC_HOLE_R}|cut")
        lines.append(f"cyl|x|{hy} {hz}|{xb - 1.6:.3f} {xb + 0.05:.3f}|{HC_HEAD_KEEP_R}|cut")
        v -= _disc_in_rect(hy, hz, HC_HOLE_R, yc - 22.5, yc + 22.5, zc - 9.8, zc + 9.8) * 1.6
        v -= _disc_in_rect(hy, hz, HC_HEAD_KEEP_R, yc - 21.5, yc + 21.5, zc - 9, zc + 9) * 1.5
    py, pz = sr_map(31.0, 4.5)
    lines.append(f"box|{xb - 18.7:.3f} {xb - 1.5 + 0.1:.3f}|{py - 5.1} {py + 5.1}|{pz - 1.27} {pz + 1.27}")
    v += 10.2 * 2.54 * 17.2
    lines += [
        f"expect|vol {v:.1f} {v * 0.01:.1f}|box {xb - 18.7:.2f} {xf + 13:.2f} {yc - 22.5:.2f} {yc + 22.5:.2f} {zc - 9.8:.2f} {zc + 9.8:.2f} 0.05",
        "save",
    ]
    return lines


def coupon_slide_strip_lines(path: str) -> list[str]:
    L, W, T = 52.0, 60.0, 4.0  # rev-1 plate thickness: the coupon stays as printed
    sx0, sx1 = 5.0, 5.0 + RAIL_L + TRAVEL  # rail length + travel, like the plate
    half = (GUIDE_Y[1] - GUIDE_Y[0]) / 2  # 5.5
    vol = L * W * T
    lines = [f"part|{path}", f"box|0 {L}|0 {W}|0 {T}"]
    for k, w in enumerate(CPN_SLIDE_W):
        yc = 10.0 + 20.0 * k
        for yy in (yc - half, yc + half):
            lines.append(f"prof|-0.1 {T + 0.1}|{_stadium(sx0, sx1, yy, w / 2)}|all")
            vol -= ((sx1 - sx0 - w) * w + math.pi * (w / 2) ** 2) * T
        cw = CLR_M3
        lines.append(f"prof|-0.1 {T + 0.1}|{_stadium(sx0 + 5, sx1 - 5, yc, cw / 2)}|all")
        vol -= ((sx1 - sx0 - 10 - cw) * cw + math.pi * (cw / 2) ** 2) * T
        # its width, read from above (0.6 deep)
        lines.append(f"text|front|{sx1 + 2.5} {yc - 2}|{T - 0.6} {T + 0.5}|3.5|{w:.1f}")
    lines += [
        f"expect|vol {vol:.1f} {vol * 0.02:.1f}|box 0 {L} 0 {W} 0 {T} 0.05",
        "save",
    ]
    return lines


def coupon_slide_rail_lines(path: str) -> list[str]:
    """The carriage foot section: a 20 x 20 x 4 foot with the two rails under it."""
    hx = RAIL_L / 2
    half = (GUIDE_Y[1] - GUIDE_Y[0]) / 2
    rw, rd = CAR_RAIL_W, CAR_RAIL_D
    vol = RAIL_L * 20.0 * CAR_FOOT_T + 2 * RAIL_L * rw * rd - math.pi * (CLR_M3 / 2) ** 2 * CAR_FOOT_T
    return [
        f"part|{path}",
        f"box|{-hx} {hx}|-10 10|0 {CAR_FOOT_T}",
        *[f"box|{-hx} {hx}|{s * half - rw / 2} {s * half + rw / 2}|{-rd} 0" for s in (-1, 1)],
        f"cyl|z|0 0|-0.1 {CAR_FOOT_T + 0.1}|{CLR_M3 / 2}|cut",
        f"expect|vol {vol:.1f} {vol * 0.01:.1f}|box {-hx} {hx} -10 10 {-rd} {CAR_FOOT_T} 0.05",
        "save",
    ]


# D6 (2026-11-06): heat-set insert ladder, 07 §4.2. Ben's M3 inserts: 5.7 long, knurl Ø4.6,
# lead-in Ø3.9; M2.5 x 4 in hand. Three rows of seven, drawn hole -0.3 .. +0.3 round the
# placeholder (INS_HOLE 4.0, CORE_INS_D 3.6), each size engraved beside it:
#   H: M3, axis horizontal (as the motor-mount uprights print), in a 9.2-deep block, 7.2 deep
#   A: M3, vertical, in Ø9.2 (INS_BOSS) bosses, 7.2 deep (INS_DEPTH)
#   B: M2.5, vertical, in Ø8 (CORE_BOSS_D) bosses, 5.0 deep (the mic / core-board pockets)
# Print it in PET-CF and in PC; press at ~245 / ~260 °C; pick per row the largest hole that
# seats square with no spin at the §4.3 torque. That replaces INS_HOLE / CORE_INS_D.
CPN_INS_STEP = (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3)
CPN_INS_PITCH, CPN_INS_X0 = 12.0, 7.0
CPN_INS_BASE = 4.0  # ladder centre, fixed so the coupon stays as printed
CPN_M25_DEPTH = 5.0


def coupon_insert_ladder_lines(path: str) -> list[str]:
    n = len(CPN_INS_STEP)
    L = CPN_INS_X0 * 2 + CPN_INS_PITCH * (n - 1)  # 86
    tb, hb, hz = 2.0, 12.0, 6.0  # base, block height, horizontal hole axis z
    yb = INS_BOSS  # block depth (y 0 .. 9.2), holes open on its y = 0 face
    ya, yB = yb + 2.0 + INS_BOSS / 2, 0.0  # row A boss centre y
    yB = ya + INS_BOSS / 2 + 6.0 + CORE_BOSS_D / 2  # row B, labels for A between
    W = yB + CORE_BOSS_D / 2 + 6.5
    za, zb = tb + 8.2, tb + 6.0  # boss tops: 1 mm floor under each pocket
    vol = L * W * tb + L * yb * (hb - tb)
    lines = [f"part|{path}", f"box|0 {L:g}|0 {W:g}|0 {tb:g}", f"box|0 {L:g}|0 {yb:g}|{tb:g} {hb:g}"]
    for k, dd in enumerate(CPN_INS_STEP):
        x = CPN_INS_X0 + CPN_INS_PITCH * k
        d3, d25 = CPN_INS_BASE + dd, CORE_INS_D + dd
        lines += [
            f"cyl|z|{x:g} {ya:g}|{tb:g} {za:g}|{INS_BOSS / 2:g}|boss",
            f"cyl|z|{x:g} {yB:g}|{tb:g} {zb:g}|{CORE_BOSS_D / 2:g}|boss",
        ]
        vol += math.pi * ((INS_BOSS / 2) ** 2 * (za - tb) + (CORE_BOSS_D / 2) ** 2 * (zb - tb))
    for k, dd in enumerate(CPN_INS_STEP):
        x = CPN_INS_X0 + CPN_INS_PITCH * k
        d3, d25 = CPN_INS_BASE + dd, CORE_INS_D + dd
        lines += [
            f"cyl|y|{x:g} {hz:g}|-0.1 {INS_DEPTH:g}|{d3 / 2:g}|cut",
            f"cyl|z|{x:g} {ya:g}|{za - INS_DEPTH:g} {za + 0.1:g}|{d3 / 2:g}|cut",
            f"cyl|z|{x:g} {yB:g}|{zb - CPN_M25_DEPTH:g} {zb + 0.1:g}|{d25 / 2:g}|cut",
            # sizes, read from above (0.6 deep): on the block top, then beside each boss row
            f"text|front|{x - 3.6:g} {yb - 5.5:g}|{hb - 0.6:g} {hb + 0.5:g}|3.0|{d3:.1f}",
            f"text|front|{x - 3.6:g} {ya + INS_BOSS / 2 + 1.2:g}|{tb - 0.6:g} {tb + 0.5:g}|3.0|{d3:.1f}",
            f"text|front|{x - 3.6:g} {yB + CORE_BOSS_D / 2 + 1.2:g}|{tb - 0.6:g} {tb + 0.5:g}|3.0|{d25:.1f}",
        ]
        vol -= math.pi * ((d3 / 2) ** 2 * 2 * INS_DEPTH + (d25 / 2) ** 2 * CPN_M25_DEPTH)
    lines += [
        f"expect|vol {vol:.1f} {vol * 0.02:.1f}|box 0 {L:g} 0 {W:g} 0 {max(za, hb):g} 0.05",
        "save",
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
BH_XF, BH_T, BH_W, BH_H, BH_TILT = 85.0, 3.0, 106.0, 130.0, 15.0  # BH_H 126 -> 130 (2026-11-09, Ben: room for the camera over the face board)
BH_PIVOT = (BH_XF - BH_T, 0.0, 0.0)
# P6m3 (Ben 2026-11-08): the bulkhead is the robot's whole FRONT CAP. Full canopy width
# (BH_W = 2 x CAN_HW) up to the hood top (BH_TOP = BH_H + CAN_LUG_GAP + CAN_T), with a
# CAP_T return flange CAP_D deep (front face to the seam) along its top and both sides down
# to the canopy's skirt line; r CAP_R on its front edges and top corners, the same r 8 as the
# canopy's side and hood rounds, so the canopy runs into it flush; r CAP_R - CAP_T inside
# keeps the 3 mm shell round the bends. Below the skirt line the plate is BH_W_LOW wide
# (was the S2a cheeks: it closes the finger gap to the belts the same way).
BH_W0 = 94.0  # the tick-1 wall width: the inner side flanges and the BH_RIB_Z rib keep it
BH_W_LOW = 104.0  # below the skirt line
BH_TOP = 131.9  # = BH_H + CAN_LUG_GAP + CAN_T (asserted in the canopy section)
CAP_D, CAP_T, CAP_R = 9.0, 3.0, 8.0  # cap depth to the seam, flange / plate thickness, outer round
BH_FACE_Z = 77.0  # face-board centre height (pre-tilt)
BH_WIN_R = 2.4  # P6m4: window corner radius; the AA corner (1 mm in from each side) stays clear up to r 3.4
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
# HC-SR04 holder (2026-11-09, Ben): his off-the-shelf "Sensorgehäuse Ultraschallsensor HC-SR04"
# (CAD/Sensorgehäuse_Sensorhalter_Ultraschallsensor_HC-SR04.3mf; the sensor snaps in from the
# back and "fits really well") merged into the wall 1:1, read off its mesh. Holder frame: xh
# along its length (0..62, sensor centre 31), yh = depth from its front face, zh across
# (0..25, centre 12.5; crystal slot up, pin slot down). Front plate yh 0..2.25 with two Ø17
# holes at xh 18 / 44 and a 9 x 4 crystal slot (zh 17.5..21.5); a 50 x 25 box (3 / 2.5 walls)
# behind it; from yh 12.25 the PCB pocket 46 x 21 (the PCB's front face seats on that step),
# with a 0.67 snap ridge on its long sides at the PCB's back face (yh 13.75) ramping out to
# yh 17.75. Its mounting ears (yh 10..20.4) are dropped: the wall holds it.
# Placement: the right motor mount stands within 73.7 (pre-tilt x) behind the left
# transducer, so the PCB back can't be further aft than ~75.5 (1.5 solder-joint clearance
# plus 0.3): the holder's front sits 4.35 proud of the wall face and the box is trimmed at
# x 74 (the ridge's ramp is cut to 1.6 of its 4). Upside down (zh -> -z), so the 4-pin
# header (bent straight back, Ben) is at the top, clear of the mount. 4 x M1.6 x 6 thread-
# forming screws from behind through the PCB's Ø1.8 holes (42 x 17) into corner bosses.
SR_FRONT = 89.85  # holder front face, pre-tilt x (= PCB front 77.6 + 12.25; build 11: 0.5 further forward cleared the mount)
SR_TRIM = 74.5  # holder cut off behind this x
SR_HOLES = ((18.0, 12.5), (44.0, 12.5))  # transducer holes (xh, zh), Ø17
SR_HOLE_R = 8.5
SR_PCB_HOLES = ((10.0, 4.0), (52.0, 4.0), (10.0, 21.0), (52.0, 21.0))  # 42 x 17 about (31, 12.5)
SR_BOSS_R, SR_PILOT_R, SR_PILOT_D = 1.6, 0.65, 5.0
# 2026-11-09 (Ben): split out as RB-PRT-070_sonar_holder. Merged, it cost the bulkhead its flat
# face-down print face (D3). The holder's box goes through a window in the wall (SR_WIN_CLR a
# side); its front frame gets lips that bear on the face: SR_LIP_TOP above (zh -6..0, holds
# the screws) and SR_LIP_BOT below (zh 25..28, stops 1.5 over the foot ledge). Two M2 x 8 pan
# head thread-forming screws (head Ø4 x 1.6) through the top lip into Ø4.4 bosses on the wall's
# back. The box in the window takes the moment; the lips take the push back.
SR_LIP_TOP, SR_LIP_BOT = 6.0, 3.0
SR_WIN_CLR = 0.2  # snug, print-dfm 0.15-0.25
SR_SCREW_XH, SR_SCREW_ZH = (13.0, 49.0), -3.0  # chassis y -4 / -40, z 41.5
SR_SCREW_CLR, SR_SCREW_CB_R, SR_SCREW_CB_D = 1.2, 2.2, 1.8  # Ø2.4 through, Ø4.4 x 1.8 c'bore
SR_WALL_BOSS_R, SR_WALL_BOSS_X0 = 2.2, 78.5  # bosses behind the wall, back to x 78.5
SR_WALL_PILOT_R, SR_WALL_PILOT_X0 = 0.85, 79.5  # Ø1.7 (as the camera's M2 pilots)


def sr_map(xh: float, zh: float) -> tuple[float, float]:
    """Holder (xh, zh) -> pre-tilt chassis (y, z): centred on BH_SONAR_Y/Z, upside down."""
    return BH_SONAR_Y - (xh - 31.0), BH_SONAR_Z - (zh - 12.5)


def sr_box(xh0: float, xh1: float, yh0: float, yh1: float, zh0: float, zh1: float) -> tuple:
    ya, za = sr_map(xh0, zh0)
    yb, zb = sr_map(xh1, zh1)
    return ("box", SR_FRONT - yh1, SR_FRONT - yh0, min(ya, yb), max(ya, yb), min(za, zb), max(za, zb))


SR_EDGE_R, SR_HOLE_EDGE_R = 2.0, 0.5  # holder: outer edges round (Ben 2026-11-09), hole/slot front edges


def sonar_holder_rounds() -> list[tuple[str, float]]:
    """(manifest line, dvol): r SR_EDGE_R on the protruding holder's 8 outer edges (the front
    face's perimeter and the 4 corner edges back to the wall face), then r SR_HOLE_EDGE_R on
    the front face's inner loops (2 x Ø17, the crystal slot). Pre-tilt, picked by edge
    midpoints."""
    xf, xw = SR_FRONT, BH_XF
    ya, za = sr_map(56.0, 25.0 + SR_LIP_BOT)
    yb, zb = sr_map(6.0, -SR_LIP_TOP)
    y0, y1, z0, z1 = min(ya, yb), max(ya, yb), min(za, zb), max(za, zb)
    ym, zm, xm = (y0 + y1) / 2, (z0 + z1) / 2, (xf + xw) / 2
    e = 0.3
    bx = [
        f"{xf - e} {ym - 2} {z0 - e} {xf + e} {ym + 2} {z0 + e}",
        f"{xf - e} {ym - 2} {z1 - e} {xf + e} {ym + 2} {z1 + e}",
        f"{xf - e} {y0 - e} {zm - 2} {xf + e} {y0 + e} {zm + 2}",
        f"{xf - e} {y1 - e} {zm - 2} {xf + e} {y1 + e} {zm + 2}",
    ]
    for yy in (y0, y1):
        for zz in (z0, z1):
            bx.append(f"{xm - 2.5} {yy - e} {zz - e} {xm + 3.5} {yy + e} {zz + e}")
    q = 1 - math.pi / 4
    L = 2 * (y1 - y0) + 2 * (z1 - z0) + 4 * (xf - xw)
    dv = q * SR_EDGE_R**2 * L
    out = [(f"fillet|{SR_EDGE_R}|any|{';'.join(bx)}|8|{-dv:.2f} {0.35 * dv + 2:.2f}", -dv)]
    per = 2 * 2 * math.pi * SR_HOLE_R + 2 * 5.0 + 2 * math.pi * 2.0
    per += len(SR_SCREW_XH) * 2 * math.pi * SR_SCREW_CB_R
    dvh = q * SR_HOLE_EDGE_R**2 * per
    out.append(
        (
            f"filletface|{SR_HOLE_EDGE_R}|x:1|{xf}|{y0} {z0} {y1} {z1}|1|{-dvh:.2f} {0.3 * dvh + 1:.2f}"
            f"|loops:{y0} {z0} {y1} {z1}",
            -dvh,
        )
    )
    return out


def sonar_holder_features() -> list[tuple]:
    """(op, shape) list for RB-PRT-070 (the holder alone), pre-tilt (see the SR_* note)."""
    yt = SR_FRONT - SR_TRIM  # trim depth
    yl = SR_FRONT - BH_XF  # lip depth: the front frame down to the wall face
    f: list[tuple] = []
    # The outboard end (xh 56 -> y -47) stands 2 mm onto the front cap's r 8 side round (the
    # face is flat to |y| 45): its lip floats <= 0.25 off the face there.
    f.append(("add", sr_box(6, 56, 0, 2.25, 0, 25)))  # front plate
    f.append(("add", sr_box(6, 56, 0, yl, -SR_LIP_TOP, 0)))  # top lip (screws)
    f.append(("add", sr_box(6, 56, 0, yl, 25, 25 + SR_LIP_BOT)))  # bottom lip
    for a in ((6, 9, 0, 25), (53, 56, 0, 25), (9, 53, 0, 2.5), (9, 53, 21.5, 25)):  # box to the pocket
        f.append(("add", sr_box(a[0], a[1], 2.25, 12.25, a[2], a[3])))
    for a in ((6, 8, 0, 25), (54, 56, 0, 25), (8, 54, 0, 1.5), (8, 54, 22.5, 25)):  # pocket walls
        f.append(("add", sr_box(a[0], a[1], 12.25, yt, a[2], a[3])))
    f.append(("add", sr_box(26.5, 35.5, 2.25, 9.0, 16.5, 17.5)))  # crystal-channel shelf
    # snap ridges on the pocket's long sides, truncated at the trim
    rz = 0.67 * (1 - (yt - 13.75) / 4.0)
    ya, _ = sr_map(8.0, 0.0)
    yb, _ = sr_map(54.0, 0.0)
    for zw, sgn in ((1.5, 1), (22.5, -1)):
        za_ = sr_map(31.0, zw)[1]
        zt_ = sr_map(31.0, zw + sgn * 0.67)[1]
        zr_ = sr_map(31.0, zw + sgn * rz)[1]
        poly = [(SR_FRONT - 13.75, za_), (SR_FRONT - 13.75, zt_), (SR_TRIM, zr_), (SR_TRIM, za_)]
        f.append(("add", ("prismy", poly, min(ya, yb), max(ya, yb))))
    # M1.6 bosses in the box's corners, PCB front (yh 12.25) forward 6, each in a corner
    # column from the front plate back to the PCB (the wall's corner blocks are kept for
    # them; a column leaves no stray face in the wall's front plane)
    for xh, zh in SR_PCB_HOLES:
        by, bz = sr_map(xh, zh)
        f.append(("add", ("cylx", by, bz, SR_FRONT - 12.25, SR_FRONT - 6.25, SR_BOSS_R)))
    for xh0, xh1 in ((9.0, 11.6), (50.4, 53.0)):
        for zh0, zh1 in ((2.5, 5.6), (19.4, 21.5)):
            f.append(("add", sr_box(xh0, xh1, 2.25, 12.25, zh0, zh1)))
    # cuts: the front holes, the crystal slot, the pilots, the lip screws
    for xh in SR_SCREW_XH:
        sy_, sz_ = sr_map(xh, SR_SCREW_ZH)
        f.append(("cut", ("cylx", sy_, sz_, BH_XF - 0.1, SR_FRONT + 0.1, SR_SCREW_CLR)))
        f.append(("cut", ("cylx", sy_, sz_, SR_FRONT - SR_SCREW_CB_D, SR_FRONT + 0.1, SR_SCREW_CB_R)))
    for xh, zh in SR_HOLES:
        hy, hz = sr_map(xh, zh)
        f.append(("cut", ("cylx", hy, hz, SR_FRONT - 2.35, SR_FRONT + 0.1, SR_HOLE_R)))
    f.append(("cut", sr_box(28.5, 33.5, -0.1, 9.0, 17.5, 21.5)))  # crystal slot + channel
    for xc in (28.5, 33.5):
        cy_, cz_ = sr_map(xc, 19.5)
        f.append(("cut", ("cylx", cy_, cz_, SR_FRONT - 9.0, SR_FRONT + 0.1, 2.0)))
    for xh, zh in SR_PCB_HOLES:
        by, bz = sr_map(xh, zh)
        f.append(("cut", ("cylx", by, bz, SR_FRONT - 12.35, SR_FRONT - 12.25 + SR_PILOT_D, SR_PILOT_R)))
    return f


def bulkhead_sonar_features() -> list[tuple]:
    """(op, shape) the bulkhead keeps for RB-PRT-070, pre-tilt: the window for the holder's
    box (SR_WIN_CLR a side) and the two M2 bosses + pilots behind the top lip."""
    c = SR_WIN_CLR
    ya, za = sr_map(56.0, 25.0)
    yb, zb = sr_map(6.0, 0.0)
    x0 = BH_XF - BH_T
    f: list[tuple] = []
    for xh in SR_SCREW_XH:
        sy_, sz_ = sr_map(xh, SR_SCREW_ZH)
        f.append(("add", ("cylx", sy_, sz_, SR_WALL_BOSS_X0, x0 + 0.01, SR_WALL_BOSS_R)))
    f.append(("cut", ("box", x0 - 0.1, BH_XF + 0.1, min(ya, yb) - c, max(ya, yb) + c, min(za, zb) - c, max(za, zb) + c)))
    for xh in SR_SCREW_XH:
        sy_, sz_ = sr_map(xh, SR_SCREW_ZH)
        f.append(("cut", ("cylx", sy_, sz_, SR_WALL_PILOT_X0, BH_XF + 0.1, SR_WALL_PILOT_R)))
    return f


def _pre_volume(feats: list[tuple], lo: tuple, hi: tuple, step: float = 0.1) -> float:
    """Voxel volume of an (op, shape) list applied in order, no rotation."""
    import numpy as np

    xs = np.arange(lo[0] + step / 2, hi[0], step)
    ys = np.arange(lo[1] + step / 2, hi[1], step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    vol = 0.0
    for z in np.arange(lo[2] + step / 2, hi[2], step):
        P = np.stack([X, Y, np.full_like(X, z)], axis=-1)
        solid = np.zeros_like(X, dtype=bool)
        for op, sh in feats:
            m = _shape_mask3(sh, P)
            solid = solid | m if op == "add" else solid & ~m
        vol += int(solid.sum()) * step**3
    return vol


def sonar_holder_lines(path: str) -> list[str]:
    """RB-PRT-070: the HC-SR04 holder alone, pre-tilt frame (placed with speaker_tilt(), like
    the speaker clamp). Prints front face down."""

    def emit(op: str, sh: tuple) -> str:
        kind = "boss" if op == "add" else "cut"
        if sh[0] == "box":
            _, x0, x1, y0, y1, z0, z1 = sh
            return f"prof|{x0} {x1}|{_right_rect(y0, y1, z0, z1)}|{kind}|right"
        if sh[0] == "cylx":
            _, cy, cz, x0, x1, r = sh
            return f"cyl|x|{cy} {cz}|{x0} {x1}|{r}|{kind}"
        _, poly, y0, y1 = sh  # prismy
        pts = [f"{x:.4f} {-z:.4f}" for x, z in poly]
        return f"prof|{y0} {y1}|M {pts[0]}{''.join(' L ' + q for q in pts[1:])}|{kind}|top"

    f = sonar_holder_features()
    ya, za = sr_map(56.0, 25.0 + SR_LIP_BOT)
    yb, zb = sr_map(6.0, -SR_LIP_TOP)
    bb = (SR_TRIM, SR_FRONT, min(ya, yb), max(ya, yb), min(za, zb), max(za, zb))
    vol = _pre_volume(f, (bb[0] - 0.5, bb[2] - 0.5, bb[4] - 0.5), (bb[1] + 0.5, bb[3] + 0.5, bb[5] + 0.5), 0.05)
    vol += sum(dv for _, dv in sonar_holder_rounds())
    return [
        f"part|{path}",
        *[emit(op, sh) for op, sh in f if op == "add"],
        *[emit(op, sh) for op, sh in f if op == "cut"],
        *[ln for ln, _ in sonar_holder_rounds()],
        f"expect|vol {vol:.1f} {vol * 0.015:.1f}|box {' '.join(f'{v:.2f}' for v in bb)} 0.1",
        "save",
    ]

BH_SPK = (
    16.0,
    26.0,
    10.0,
)  # grille centre y, z and its loop-pick radius. P7 (tick 92, Q25 a): centred on the speaker
# module (SPK_CTR), equal slots BH_GRILLE_HALF each side, inside the pocket (was y 24 / Ø34
# round for the CE40P-8)
BH_GRILLE_HALF = 8.5  # slot half-length: y 7.5 .. 24.5, 1.8 inside the pocket's inner wall
BH_SLOT_W, BH_SLOT_DZ = (
    2.0,
    (-10.0, -6.0, -2.0, 2.0, 6.0, 10.0),
)  # grille slots <= 2 mm (audio §4.3)
BH_GRILLE_EDGE_R = 0.5  # tick 86: grille slot face edges
# P7 (tick 92): speaker module pocket on the bulkhead's back face (pre-tilt wall frame)
SPK_MOD = (30.0, 20.0, 5.6)  # length (z'), width (y), depth: Same Sky CMS-30205-158L120-67 (ordered
# 2026-11-05, datasheet rev 1.03): 30 +-0.3 x 20 +-0.2 x 5.6 +-0.3, full-round (stadium) ends,
# Ø17 magnet boss is the rearmost face, 120 mm lead out of one short end
SPK_TOL = 0.3  # depth tolerance (datasheet)
SPK_PRELOAD = 0.3  # gasket squeeze at nominal depth = SPK_TOL: the thinnest part (5.3) still touches
SPK_PAD, SPK_PAD_W = 0.15, 16.0  # clamp pad: thickness, square side (presses the Ø17 magnet only)
SPK_GASKET_T = 1.0  # TPU 85A gasket between the module's face and the wall (P8)
SPK_CLR = 0.3  # module in the pocket, per side
SPK_RIM_T = 1.6
SPK_DEPTH = SPK_GASKET_T + SPK_MOD[2] + SPK_PAD - SPK_PRELOAD  # rim stand-off (6.45): the clamp
# seats on the rim, so the squeeze is set by geometry (0 .. 0.6 over the depth tolerance)
SPK_LEAD = (3.0, 2.5)  # lead notch in the rim's top end (z' high): width (y), depth from the open edge
SPK_CTR = (16.0, 26.0)  # y, z' of the module centre (grille centre y 24: overlaps its inboard half)
SPK_CLAMP_T = 1.6  # clamp plate (P7)
SPK_NOTCH_Y, SPK_NOTCH_Z = 25.6, (21.0, 28.0)  # tick 93: clamp notch round the left mount's end stop (25.9 still touched: 0.0 mm3)
SPK_GASKET_BAND = 2.0  # gasket ring width (P8)
SPK_BOSS_Y, SPK_BOSS_Z = (9.0, 23.0), 26.0 + 15.0 + 0.3 + 1.6 + 4.6 - 0.6  # above the pocket, 0.6 into the rim (tangent contact gave a null boss)
# Camera (2026-11-09, Ben): Arducam IMX708 75° AF = Raspberry Pi Camera Module 3 standard
# geometry (RPi mechanical drawing): PCB 25 x 23.862 x 1.12, 4 x Ø2.2 at 21 x 12.5 (2.0 in
# from the sides and the bottom edge, pads Ø4.75), lens centred across, 14.4 up from the
# bottom edge; lens block 10.8 square x 3.875 off the PCB front, barrel Ø5.75 x 3.105
# beyond it; FFC connector 19.61 x 5.71 x 3.2 on the back at the top edge (image rotation
# is software). The barrel passes through the wall (tip at the face: the full 75° with no
# vignetting) and the block bears on the back face, which locates the camera; 4 x M2 x 5
# thread-forming screws through the PCB into printed bosses. Its PCB (x 76.9-78) sits 0.8
# in front of the face board's edge-entry plugs (top edge, back side, x <= 76.1) and above
# the board's top (z 102): that needs the lens at z 117, hence BH_H 130.
BH_CAM = (0.0, 117.0, 3.1)  # lens hole y, z, r: the Ø5.75 barrel + 0.22/side
CAM_PCB = (25.0, 23.862, 1.12)  # width (y), height (z), thickness
CAM_LENS_UP = 14.4  # lens centre above the PCB's bottom edge
CAM_HOLES = ((-10.5, 0.1), (10.5, 0.1), (-10.5, -12.4), (10.5, -12.4))  # (dy, dz) from the lens
CAM_BLOCK, CAM_BLOCK_D = 10.8, 3.875  # lens block side, depth off the PCB front
CAM_BARREL_R, CAM_BARREL_L = 5.75 / 2, 3.105
CAM_CONN = (19.61, 5.71, 3.2)  # FFC connector: width (y), height (z), depth behind the PCB
CAM_BOSS_R, CAM_PILOT_R, CAM_PILOT_D = 2.2, 0.85, 5.0  # Ø4.4 (pads Ø4.75), M2 thread-forming pilot Ø1.7
BH_LUG_Y, BH_LUG_Z = 38.0, (112.0, BH_H - 2.0)  # canopy screw lugs (F9) behind the wall top; P6m3: tops 2 lower, under the canopy's 2 mm screw bosses
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
BH_FLANGE_GAP = 0.3  # side-flange bottoms clear the plate (2026-11-06)
# 2026-11-09 (Ben): the foot's vertical front stood 2.4 proud of the tilted wall at its top.
# Flush is impossible: the F1 pockets (BULK_X, Ø4.1 x 7.2) would break the wall's plane, and
# moving them aft hits the motor-mount feet (0.7 mm behind the foot). So the front goes to
# the wall's 15° above the pockets, BH_FOOT_SKIN in front of each pocket's top edge.
BH_FOOT_SKIN = 1.2


def bh_foot_slope() -> tuple[float, float, float]:
    """(x0, z_kink, x_top): the foot's sloped front is x = x0 - z tan(BH_TILT); it leaves the
    vertical face at z_kink and meets the foot top at x_top."""
    t = math.tan(math.radians(BH_TILT))
    (_, fx1), _, (_, fz1) = BH_FOOT
    x0 = BULK_X + INS_HOLE / 2 + BH_FOOT_SKIN + INS_DEPTH * t
    return x0, (x0 - fx1) / t, x0 - fz1 * t


BH_TAB = (4.0, 9.8, 3.6)  # into the 4.6 x 10.4 plate slots (0.3/side)
# Knee gusset (P1b): the only clear slot behind the lower band is between the sonar
# sleeves (y <= 0.8) and the speaker (y >= 4); it stays below the face board (z <= 44).
# Its tail pad is bolted down through the plate (M3 up into an insert, like F1).
BH_KNEE_Y = (1.2, 3.6)  # 2.4 thick
BH_KNEE_TOP = 44.0  # top of the gusset, chassis z
BH_KNEE_TAIL = 56.0  # rear end on the plate (the wire slot ends at x 55)
# 2026-11-09: the split HC-SR04 holder (RB-PRT-070) runs through the gusset's plane (y 0..3
# vs 1.2..3.6) from the wall back to x 74.5. The gusset is notched round it (SR_NOTCH_CLR), and
# its top's rear corner goes back from the wall (x 70.8) to BH_KNEE_TOP_X, so a >= 5 mm band
# runs round the holder's back: the wall above the holder (z 37..44) still braces to the tail.
BH_KNEE_TOP_X = 60.0
SR_NOTCH_CLR = 0.2
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


BH_LUG_AFT = 7.9  # Q27 (a): lugs 3 mm aft of the tick-47 position; P6m3: 4.9 more, so the flush hood screws sit on the hood's flat behind the front cap (axis 11.5 behind the wall's back face)
BH_LUG_WEB = INS_BOSS  # web from each lug back to the wall, as wide as the lug (tick 94: a 4 mm web put S5c at 8.14 MPa on its side face)


def cap_z_low() -> float:
    """Pre-tilt z of the cap's flange bottoms: the flange's back edge (the seam, x_pre
    BH_XF - CAP_D) lands on the canopy's skirt line (chassis z CAN_Z0)."""
    dx = (BH_XF - CAP_D) - BH_PIVOT[0]
    s, c = math.sin(math.radians(BH_TILT)), math.cos(math.radians(BH_TILT))
    return (CAN_Z0 - s * dx) / c


def bh_lug_x() -> float:
    """Pre-tilt x of the canopy lugs' axis (bulkhead and canopy hole share it)."""
    return BH_XF - BH_T - INS_BOSS / 2 + 1.0 - BH_LUG_AFT


def grille_half(dz: float) -> float:
    """Half-length (y) of the grille slot at z offset dz. P7 (tick 92): equal slots inside
    the speaker pocket (the old Ø34 round grille, sized for the CE40P-8, ran under the
    pocket rim and put S5c's peak on that crossing: 7.48 -> 9.02 MPa)."""
    return BH_GRILLE_HALF


def bulkhead_features() -> tuple[list[tuple], list[tuple]]:
    """(pre, post): pre-tilt features (wall frame = chassis, vertical wall) and
    post-tilt features (chassis frame). Each: (op, shape) with op 'add' | 'cut'.
    Shapes: ('box', x0, x1, y0, y1, z0, z1), ('cylx', y, z, x0, x1, r), ('cylz', x, y, z0, z1, r)."""
    x0, x1 = BH_XF - BH_T, BH_XF
    hw = BH_W0 / 2
    zl, xs_ = cap_z_low(), BH_XF - CAP_D
    ch = BH_W / 2
    # P6m3 front cap: the plate (narrower below the skirt line), the top and side return flanges
    pre: list[tuple] = [
        ("add", ("box", x0, x1, -BH_W_LOW / 2, BH_W_LOW / 2, 0.0, zl)),
        ("add", ("box", x0, x1, -ch, ch, zl, BH_TOP)),
        ("add", ("box", xs_, x0, -ch, ch, BH_TOP - CAP_T, BH_TOP)),
    ]
    for sgn in (-1, 1):
        pre.append(("add", ("box", xs_, x0, *sorted((sgn * ch, sgn * (ch - CAP_T))), zl, BH_TOP)))
    fd, ft = BH_FLANGE
    for sgn in (-1, 1):  # inner side flanges (tick 1), now only below the skirt line
        ys = sorted((sgn * hw, sgn * (hw - ft)))
        pre.append(("add", ("box", x0 - fd, x0, *ys, 0.0, zl)))
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
    # (HC-SR04 holder: merged after the front cap's rounds, see bulkhead_lines; it stood in
    # the r 8 side round's way and stopped it rolling down the lower plate)
    # canopy lugs (vertical before the tilt). Q27 (a) (Ben 2026-11-02, tick 94): BH_LUG_AFT
    # further from the wall, joined to it by a web, so the hood screws clear the hood's front
    # edge and can sit in counterbored collars
    lug_x = bh_lug_x()
    for sgn in (-1, 1):
        pre.append(("add", ("cylz", lug_x, sgn * BH_LUG_Y, *BH_LUG_Z, INS_BOSS / 2)))
        pre.append(
            ("add", ("box", lug_x, x0 + 0.5, sgn * BH_LUG_Y - BH_LUG_WEB / 2, sgn * BH_LUG_Y + BH_LUG_WEB / 2, *BH_LUG_Z))
        )
    # (S2a side cheeks: replaced by the full-width plate, P6m3)
    # cuts
    aw, ah = FACE_AA[1] + 2.0, FACE_AA[0] + 2.0  # window: AA + 1 mm all round
    # P6m4: corners r BH_WIN_R in the face plane (two crossed boxes + four corner cylinders)
    wr = BH_WIN_R
    for hy, hz in ((aw / 2, ah / 2 - wr), (aw / 2 - wr, ah / 2)):
        pre.append(("cut", ("box", x0 - 0.1, x1 + 0.1, -hy, hy, BH_FACE_Z - hz, BH_FACE_Z + hz)))
    for sy in (-1, 1):
        for sz in (-1, 1):
            pre.append(("cut", ("cylx", sy * (aw / 2 - wr), BH_FACE_Z + sz * (ah / 2 - wr), x0 - 0.1, x1 + 0.1, wr)))
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
    sy, sz, sr = BH_SPK
    # D2 (tick 77): full-radius ends (box + two Ø2 end cylinders), same overall length;
    # they were square-ended boxes on the face side
    sr_end = BH_SLOT_W / 2
    for dz in BH_SLOT_DZ:
        half = grille_half(dz)
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
    # camera bosses (2026-11-09): from the wall's back face to the PCB front, which sits
    # CAM_BLOCK_D behind it (the lens block bears on the wall)
    xc = x0 - CAM_BLOCK_D
    for dy, dz in CAM_HOLES:
        pre.append(("add", ("cylx", cy + dy, cz + dz, xc, x0 + 0.5, CAM_BOSS_R)))
        pre.append(("cut", ("cylx", cy + dy, cz + dz, xc - 0.1, xc + CAM_PILOT_D, CAM_PILOT_R)))
    # P7 (tick 92, Q25 (a) Ben 2026-11-02): pocket for a pre-boxed micro speaker on the back
    # face, behind the grille's inboard half: a 1.6 rim standing SPK_DEPTH off the face round
    # the module + gasket, and two M3 insert bosses above it for the clamp plate's screws
    # (no room below: the foot is 1.4 behind the wall; nor at the sides: knee gusset /
    # left motor mount; free depth mapped by ray-casting the mount, motor and face envelopes)
    (sy_, sz_), (ml, mw, md) = SPK_CTR, SPK_MOD
    iy0, iy1 = sy_ - mw / 2 - SPK_CLR, sy_ + mw / 2 + SPK_CLR
    iz0, iz1 = sz_ - ml / 2 - SPK_CLR, sz_ + ml / 2 + SPK_CLR
    rt = SPK_RIM_T
    xb = x0 - SPK_DEPTH
    for yy0, yy1, zz0, zz1 in (
        (iy0 - rt, iy0, iz0 - rt, iz1 + rt),
        (iy1, iy1 + rt, iz0 - rt, iz1 + rt),
        (iy0, iy1, iz0 - rt, iz0),
        (iy0, iy1, iz1, iz1 + rt),
    ):
        pre.append(("add", ("box", xb, x0, yy0, yy1, zz0, zz1)))
    for by in SPK_BOSS_Y:
        pre.append(("add", ("cylx", by, SPK_BOSS_Z, xb, x0, INS_BOSS / 2)))
        pre.append(("cut", ("cylx", by, SPK_BOSS_Z, xb - 0.1, xb + INS_DEPTH, INS_HOLE / 2)))
    # tick 97: lead notch in the rim's top end, between the bosses (the lead leaves one
    # short end at the speaker's back; the clamp closes the notch into a tunnel and the
    # lead runs up between the bosses past the clamp's top edge)
    lw, ld = SPK_LEAD
    pre.append(("cut", ("box", xb - 0.1, xb + ld, sy_ - lw / 2, sy_ + lw / 2, iz1 - 0.1, iz1 + rt + 0.1)))
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
    # 2026-11-09: the front slopes at the wall's angle above the F1 pockets (bh_foot_slope)
    sx0, szk, _ = bh_foot_slope()
    st, za, zb = math.tan(math.radians(BH_TILT)), szk - 0.3, fz1 + 0.3
    wedge = [(sx0 - za * st, za), (fx1 + 1.0, za), (fx1 + 1.0, zb), (sx0 - zb * st, zb)]
    post.append(("cut", ("prismy", wedge, fy0 - 0.5, fy1 + 0.5)))
    # 2026-11-06: the tilt swings the side flanges' bottoms ~1 mm under the plate top at
    # |y| 45-47, x ~78; the old front chamfer had no plate there. Trim them to BH_FLANGE_GAP
    # over the plate, outboard of the tabs (|y| <= 15.9) and the foot (29.5): a flat at z 0
    # would bear on the plate, and S5's "fix plane z 0" bonded it (S5c 5.72 -> 9.91 MPa at
    # the flange root). The foot stays the only seat.
    for sgn in (-1, 1):
        ys = sorted((sgn * (fy1 + 0.5), sgn * (BH_W / 2 + 1)))
        post.append(("trim", ("box", fx0 - 15.0, BH_XF + 1.0, *ys, -5.0, BH_FLANGE_GAP)))
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
        (BH_KNEE_TOP_X, BH_KNEE_TOP),
    ]
    post.append(("add", ("prismy", knee, *BH_KNEE_Y)))
    # notch for RB-PRT-070 behind the wall (pre-tilt box, tilted into the chassis frame); it
    # also takes the inner side flange's stretch at y -47..-45.2
    R, t = speaker_tilt()
    c_ = SR_NOTCH_CLR
    ya, za = sr_map(56.0, 25.0)
    yb, zb = sr_map(6.0, 0.0)
    z0, z1 = min(za, zb) - c_, max(za, zb) + c_
    notch = [
        (R[0] * x + R[2] * z + t[0], R[6] * x + R[8] * z + t[2])
        for x, z in ((SR_TRIM - c_, z0), (BH_XF - BH_T - 0.05, z0), (BH_XF - BH_T - 0.05, z1), (SR_TRIM - c_, z1))
    ]
    post.append(("cut", ("prismy", notch, min(ya, yb) - c_ - 0.2, BH_KNEE_Y[1] + 0.1)))
    # ... and the gusset's 0.6 overlap into the wall, inside the window only (beside the
    # window that overlap is buried in the wall)
    cw = SR_WIN_CLR
    front = [
        (R[0] * x + R[2] * z + t[0], R[6] * x + R[8] * z + t[2])
        for x, z in ((BH_XF - BH_T - 0.1, z0 + c_ - cw), (BH_XF, z0 + c_ - cw), (BH_XF, z1 - c_ + cw), (BH_XF - BH_T - 0.1, z1 - c_ + cw))
    ]
    post.append(("cut", ("prismy", front, min(ya, yb) - cw, max(ya, yb) + cw)))
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
    pre = pre + bulkhead_sonar_features()  # applied after the rounds in the build
    xs = np.arange(30.0 + step / 2, 90.0, step)  # tick 94: the lugs moved aft reach x 38.6
    yh = BH_W / 2 + 1
    ys = np.arange(-yh + step / 2, yh, step)
    zs = np.arange(-5.0 + step / 2, BH_TOP + 2, step)
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


def _cap_round_sets() -> list[tuple[float, list[str], float]]:
    """(radius, edge boxes, dvol) for the cap's outer and inner rounds (pre-tilt frame).
    Each set: the front-top edge, both front-side edges, both top-side edges; a 3-edge
    corner removes (adds) 0.168 r³ less than the three strips counted to the vertex."""
    zl, xs_ = cap_z_low(), BH_XF - CAP_D
    out = []
    for r, xf, hy, zt, sgn in (
        (CAP_R, BH_XF, BH_W / 2, BH_TOP, -1.0),
        (CAP_R - CAP_T, BH_XF - CAP_T, BH_W / 2 - CAP_T, BH_TOP - CAP_T, 1.0),
    ):
        zm = (zl + zt) / 2
        xm = (xs_ + xf) / 2
        boxes = [f"{xf - 0.1:.3f} -1 {zt - 0.1:.3f} {xf + 0.1:.3f} 1 {zt + 0.1:.3f}"]
        for sy in (-1, 1):
            boxes.append(f"{xf - 0.1:.3f} {sy * hy - 0.1:.3f} {zm - 1:.3f} {xf + 0.1:.3f} {sy * hy + 0.1:.3f} {zm + 1:.3f}")
            boxes.append(f"{xm - 0.5:.3f} {sy * hy - 0.1:.3f} {zt - 0.1:.3f} {xm + 0.5:.3f} {sy * hy + 0.1:.3f} {zt + 0.1:.3f}")
        q = (1 - math.pi / 4) * r * r
        L = 2 * hy + 2 * (zt - zl) + 2 * (xf - xs_)
        over = 3 * (1 - math.pi / 4) - (1 - math.pi / 6)  # strips vs the vertex blend, per r³ (0.167)
        dv = sgn * (q * L - 2 * over * r**3)
        if sgn < 0:
            dv += cap_lower_corner()["dv_lower"]  # the outer round runs on down the lower plate
        out.append((r, boxes, dv))
    return out


def cap_lower_corner() -> dict:
    """The r CAP_R front-side round continued down the lower plate (0 .. skirt line): plan
    area it removes per side (plate x BH_XF - BH_T .. BH_XF, out to BH_W_LOW / 2), the
    edge where its arc meets the back face, and the r 1 there."""
    r, xf, x0 = CAP_R, BH_XF, BH_XF - BH_T
    cy, cx = BH_W / 2 - r, xf - r  # round's axis (the upper corner's)
    yl = BH_W_LOW / 2
    n, area = 400, 0.0
    for k in range(n):
        x = x0 + (k + 0.5) * BH_T / n
        ym = cy + math.sqrt(max(r * r - (x - cx) ** 2, 0.0))
        area += max(0.0, yl - min(ym, yl)) * BH_T / n
    yb = cy + math.sqrt(r * r - (x0 - cx) ** 2)  # arc meets the back face here
    zl = cap_z_low()
    alpha = 180.0 - math.degrees(math.acos(-(x0 - cx) / r))  # wedge between the arc and the back face
    # SolidWorks removes 107.4 mm3 here (P6m3 build), not the 62.6 of the plane-wedge formula
    # for this ~51° edge: the round also runs onto the trimmed bottom; use the measured ratio
    dv_r1 = -2 * _round_area(alpha, PLATE_EDGE_R) * zl * (107.44 / 62.63)
    boxes = [f"{x0 - 0.3:.3f} {sg * yb - 0.3:.3f} {zl / 2 - 1:.3f} {x0 + 0.3:.3f} {sg * yb + 0.3:.3f} {zl / 2 + 1:.3f}" for sg in (-1, 1)]
    return {"area": area, "yb": yb, "alpha": alpha, "dv_lower": -2 * area * zl, "dv_r1": dv_r1, "boxes": boxes}


def cap_round_dv() -> float:
    return sum(dv for _, _, dv in _cap_round_sets())


def cap_round_lines() -> list[str]:
    return [
        f"fillet|{r}|any|{';'.join(boxes)}|5|{dv:.1f} {abs(dv) * 0.15 + 5:.1f}"
        for r, boxes, dv in _cap_round_sets()
    ]


SEAM_R = 0.5  # P6m4: edge break on both seam edges (cap back, canopy front): a 1 mm V shadow line
FLANGE_END_R = 1.0  # P6m4: the cap side flanges' bottom ends (kid rule r >= 1)
FOOT_TOP_R = 2.0  # P6m4: foot ledge top front edge (it stands 2.5 proud of the wall there)


def seam_break_lines(xs: float, z_low: float) -> list[tuple[str, float]]:
    """(manifest line, dvol) for r SEAM_R on the five outer edges of a seam face in the
    pre-tilt frame (plane x = xs): both sides (|y| BH_W/2, from z_low up to the r CAP_R
    corners), the two r CAP_R corner arcs and the top (z BH_TOP). Picked by their end-vertex
    midpoints ("vmid"); the inner edges and the bottom ends are left alone."""
    hy, zt, r = BH_W / 2, BH_TOP, CAP_R
    zc = zt - r
    zs = (z_low + zc) / 2
    am = r * (1 - 1 / 2)  # arc chord midpoint, r/2 in from both tangents
    boxes = [f"{xs - 0.2:.3f} -1 {zt - 0.1:.3f} {xs + 0.2:.3f} 1 {zt + 0.1:.3f}"]
    for sy in (-1, 1):
        boxes.append(f"{xs - 0.2:.3f} {sy * hy - 0.1:.3f} {zs - 2:.3f} {xs + 0.2:.3f} {sy * hy + 0.1:.3f} {zs + 2:.3f}")
        ya, za = sy * (hy - am), zt - am
        boxes.append(f"{xs - 0.2:.3f} {ya - 0.4:.3f} {za - 0.4:.3f} {xs + 0.2:.3f} {ya + 0.4:.3f} {za + 0.4:.3f}")
    L = 2 * (zc - z_low) + math.pi * r + 2 * (hy - r)
    dv = -(1 - math.pi / 4) * SEAM_R**2 * L
    return [(f"fillet|{SEAM_R}|vmid|{';'.join(boxes)}|5|{dv:.2f} {abs(dv) * 0.2 + 1:.2f}", dv)]


def _flange_end_edges() -> list[str]:
    """Edge boxes (vmid) on the cap side flanges' bottom face (pre-tilt z = cap_z_low):
    the back edge (seam plane), the outer edge (|y| BH_W/2, back to the r CAP_R round)
    and the inner edge (|y| BH_W/2 - CAP_T, back to the plate's back face)."""
    zl, xs = cap_z_low(), BH_XF - CAP_D
    hy, x0 = BH_W / 2, BH_XF - BH_T
    out = []
    for sy in (-1, 1):
        for x, y in ((xs, sy * (hy - CAP_T / 2)), ((xs + BH_XF - CAP_R) / 2, sy * hy), ((xs + x0) / 2, sy * (hy - CAP_T))):
            out.append(f"{x - 0.3:.3f} {y - 0.3:.3f} {zl - 0.1:.3f} {x + 0.3:.3f} {y + 0.3:.3f} {zl + 0.1:.3f}")
    return out


def flange_end_dv() -> float:
    xs, x0 = BH_XF - CAP_D, BH_XF - BH_T
    L = CAP_T + (BH_XF - CAP_R - xs) + (x0 - xs)
    return -(1 - math.pi / 4) * FLANGE_END_R**2 * 2 * L


def flange_end_line() -> str:
    dv = flange_end_dv()
    return f"fillet|{FLANGE_END_R}|vmid|{';'.join(_flange_end_edges())}|6|{dv:.2f} {abs(dv) * 0.4 + 1:.2f}"


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
    face_len = 2 * (aw + ah) - (8 - 2 * math.pi) * BH_WIN_R + 2 * math.pi * BH_CAM[2]
    dvf = (1 - math.pi / 4) * PLATE_EDGE_R**2 * face_len
    lines.append(
        f"filletface|{PLATE_EDGE_R}|x:1|{BH_XF}|-50 -5 50 130|1|{-dvf:.2f} {0.15 * dvf:.2f}|loops:-45 10 10 125"
    )
    # P-kid (tick 86): r 0.5 on the speaker-grille slots' face-side edges (2 wide: r 1 would
    # round through), the bulkhead's biggest accessible sharp cluster (330 mm, edgeaudit)
    sy_, sz_, sr_ = BH_SPK
    gl = 0.0
    for dz in BH_SLOT_DZ:
        half = grille_half(dz)
        gl += 2 * (2 * half - BH_SLOT_W) + math.pi * BH_SLOT_W
    dvg = (1 - math.pi / 4) * BH_GRILLE_EDGE_R**2 * gl
    lines.append(
        f"filletface|{BH_GRILLE_EDGE_R}|x:1|{BH_XF}|-50 -5 50 130|1|{-dvg:.2f} {0.25 * dvg:.2f}"
        f"|loops:{sy_ - sr_ - 1} {sz_ - sr_ - 1} {sy_ + sr_ + 1} {sz_ + sr_ + 1}"
    )
    # P6m3 front cap rounds, pre-tilt: r CAP_R on the outer front-top edge, the two front-side
    # edges (skirt line to top) and the two top-side edges (front to seam); then r CAP_R -
    # CAP_T on the matching inner edges, so the shell stays CAP_T round the bends
    lines += cap_round_lines()
    # The cap's r 8 front-side rounds carry on down the lower plate (SolidWorks rolls them past
    # the step at the skirt line, P6m3 build): below it each corner is an r 8 arc in plan
    # through the 3 mm plate, meeting the back face at ~51°. r 1 on that edge (kid safety).
    lo = cap_lower_corner()
    lines.append(
        f"fillet|{PLATE_EDGE_R}|z|{';'.join(lo['boxes'])}|2|{lo['dv_r1']:.2f} {abs(lo['dv_r1']) * 0.25 + 1:.2f}"
    )
    # P6m4: seam edge break and flange ends (edge audit 2026-11-08), pre-tilt
    for ln_, _ in seam_break_lines(BH_XF - CAP_D, cap_z_low()):
        lines.append(ln_)
    lines.append(flange_end_line())
    # 2026-11-09: window + M2 bosses for RB-PRT-070 (the holder, split out), after the cap
    # rounds (pre-tilt frame): the window's outboard end reaches the side round
    sr = bulkhead_sonar_features()
    lines += [emit(op, sh) for op, sh in sr if op == "add"]
    lines += [emit(op, sh) for op, sh in sr if op == "cut"]
    lines.append(f"rotbody|{BH_PIVOT[0]} {BH_PIVOT[1]} {BH_PIVOT[2]}|y|{-BH_TILT}")
    for op, sh in post:
        if op == "trim":  # applied last, after the side-face rounds (below)
            continue
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
            - (8 - 2 * math.pi) * BH_WIN_R
            + 2 * math.pi * BH_CAM[2]
        )
    )  # S1b2 front-face opening rounds
    vol += cap_round_dv()  # P6m3 cap rounds (outer removes, inner adds; incl. the lower corners)
    vol += cap_lower_corner()["dv_r1"]  # r 1 where the lower corners meet the back face
    vol += sum(dv for _, dv in seam_break_lines(BH_XF - CAP_D, cap_z_low())) + flange_end_dv()
    # P-kid (tick 87): r 1.0 on the foot's exposed front: its top front edge (x BH_XF, z top,
    # along y; the foot stands ~2.4 proud of the tilted wall there) and the two vertical
    # front corners (|y| foot half-width). One feature; the bottom edge sits on the plate
    q = (1 - math.pi / 4) * PLATE_EDGE_R**2
    (fx0, fx1), (fy0, fy1), (fz0, fz1) = BH_FOOT
    # P6m4: the top front edge goes to r FOOT_TOP_R (the ledge read square), first and alone.
    # 2026-11-09: that edge is now the sloped face's top (x_top), 105° inside, not 90°
    _, szk, sxt = bh_foot_slope()
    ia = math.radians(90 + BH_TILT)
    dvtop = (1 / math.tan(ia / 2) - (math.pi - ia) / 2) * FOOT_TOP_R**2 * (fy1 - fy0)
    lines.append(
        f"fillet|{FOOT_TOP_R}|y|{sxt - 0.1} {fy0 - 0.1} {fz1 - 0.1} {sxt + 0.1} {fy1 + 0.1} {fz1 + 0.1}|1|{-dvtop:.2f} {0.15 * dvtop:.2f}"
    )
    # r 1 on the front corners: the vertical edges (z 0..kink) and the sloped ones above
    sl = (fz1 - szk) / math.cos(math.radians(BH_TILT)) - FOOT_TOP_R / math.tan(ia / 2)
    dvft = q * 2 * (szk - fz0 + sl)
    xm, zm = (fx1 + sxt) / 2, (szk + fz1 - 1.0) / 2
    cb = []
    for yy in (fy0, fy1):
        cb.append(f"{fx1 - 0.1} {yy - 0.1} {fz0} {fx1 + 0.1} {yy + 0.1} {szk}")
        cb.append(f"{xm - 0.6} {yy - 0.1} {zm - 1.2} {xm + 0.6} {yy + 0.1} {zm + 1.2}")
    lines.append(f"fillet|{PLATE_EDGE_R}|any|{';'.join(cb)}|4|{-dvft:.2f} {0.3 * dvft + 0.5:.2f}")
    vol -= dvft + dvtop
    lines += [emit("cut", sh) for op, sh in post if op == "trim"]
    # P6m3: the top is the cap's r 8 front-top round after the tilt (the voxel box has no rounds)
    s15, c15 = math.sin(math.radians(BH_TILT)), math.cos(math.radians(BH_TILT))
    rx, rz = BH_XF - CAP_R, BH_TOP - CAP_R
    bb[5] = s15 * (rx - BH_PIVOT[0]) + c15 * rz + CAP_R
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
    for x, y in MOUNT_FOOT_HOLES:
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
        f"expect|vol {vol:.1f} {vol * 0.006:.1f}|box {-hx} {hx} {-hy} {hy} {PLATE_BOTTOM} {max(DECK_Z, MM_TOP)} 0.01",
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
)  # 4.0 in the 4.5 slots (0.25/side, coupon); stops 0.4 above the belly
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


# Sprocket spokes (Ben 2026-11-08, with the 624 seat fix): radial webs from the hub tube to
# the rim over the full height above the bed-face web, so the D-bore end and the rim's
# inboard disc are tied to each other, not only through the hub tube down to the 4 mm web
# (the one joint that split when the 624 was pressed). Each ends 0.4 into the rim wall, at
# its inner radius per zone: under the band (lug pockets just outside) it stops in the
# band wall. Not on the idler: the carriage's journal boss enters its open inboard side.
SPROCKET_SPOKES = (6, 2.0)  # count, thickness
SPOKE_R_IN, SPOKE_SINK = 7.0, 0.4  # start inside the r 7.5 tube; reach into the rim wall


def spoke_lines(layers: list, n: int, w: float) -> tuple[list[str], float]:
    """Prof bosses for n radial spokes (part frame, axis z) and the volume they add, from the
    wheel's own layers: per layer, spoke = r from max(SPOKE_R_IN, hub outer) .. rim inner."""
    z_web = layers[0][1]  # the bed-face web's top (one solid annulus below it)
    zones = []  # (z0, z1, r_hub_outer, r_rim_inner, under the band?)
    r_out = max(float(ann[-1][1].max()) for _, _, ann in layers)  # running-disc radius
    for z0, z1, ann in layers:
        if z0 < z_web - 1e-9 or len(ann) < 2:
            continue
        hub_o = float(ann[0][1].max())
        rim_i = float(ann[-1][0].min())
        band = float(ann[-1][1].max()) < r_out - 1e-6  # the band's outer is the pocket floor
        zones.append((z0, z1, hub_o, rim_i, band))
    r_disc = max(ri for _, _, _, ri, band in zones if not band)  # rim inner under the discs
    # one extrude per run: under the band stop in its wall (lug pockets just outside); off
    # the band (discs and the 45° ramp: solid rim outward) run to the disc's inner wall
    lines, vol = [], 0.0
    spans = []
    for z0, z1, ho, ri, band in zones:
        r1 = (ri if band else r_disc) + SPOKE_SINK
        if spans and abs(spans[-1][3] - r1) < 1e-6:
            spans[-1][1] = z1
        else:
            spans.append([z0, z1, ho, r1])
    for z0, z1, _, r1 in spans:
        for k in range(n):
            a = 2 * math.pi * k / n
            dx, dy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
            pts = [
                (SPOKE_R_IN * dx + w / 2 * nx, SPOKE_R_IN * dy + w / 2 * ny),
                (r1 * dx + w / 2 * nx, r1 * dy + w / 2 * ny),
                (r1 * dx - w / 2 * nx, r1 * dy - w / 2 * ny),
                (SPOKE_R_IN * dx - w / 2 * nx, SPOKE_R_IN * dy - w / 2 * ny),
            ]
            path = "M " + " L ".join(f"{x:.4f} {y:.4f}" for x, y in pts)
            lines.append(f"prof|{z0 - 0.05:.3f} {z1:.3f}|{path}")
    for z0, z1, ho, ri, _ in zones:  # new material: between the hub's and the rim's surfaces
        vol += n * w * max(0.0, ri - max(SPOKE_R_IN, ho)) * (z1 - z0)
    return lines, vol


def wheel_lines(path: str, layers: list, spokes: tuple[int, float] | None = None) -> list[str]:
    vol = dt.check(dt.mesh(layers))[1]
    sp, dvs = spoke_lines(layers, *spokes) if spokes else ([], 0.0)
    vol += dvs
    r = max(float(ro.max()) for _, _, ann in layers for _, ro in ann)
    # S1c (kid safety): r 1.0 on the outboard rim, the running disc's outer edge on the bed
    # face (part z 0), the wheel edge a hand meets from the side: (1 - pi/4) r² x 2 pi R
    r0 = float(layers[0][2][0][1].max())  # bed-face layer's outer radius
    dvr = (1 - math.pi / 4) * PLATE_EDGE_R**2 * 2 * math.pi * r0
    vol -= dvr
    return [
        f"part|{path}",
        *ring_lines(layers),
        *sp,
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
    r = RW_SPACER_R
    # P13c (tick 91): the frame's blade sits mid-span (belt centre, RA_T thick), so the
    # spacer is two tubes, inner race -> blade face (0.1 clear)
    m0, m1 = bw / 2 - RA_T / 2 - 0.1, bw / 2 + RA_T / 2 + 0.1
    v = math.pi * (4.0 * bw + (RW_SPACER_R**2 - 4.0) * ((m0 - bd - 0.05) + (bw - bd - 0.05 - m1)))
    return [
        f"part|{path}",
        f"cyl|y|0 0|0 {bw}|2.0|boss",
        f"cyl|y|0 0|{bd + 0.05} {m0}|{r}|boss",
        f"cyl|y|0 0|{m1} {bw - bd - 0.05}|{r}|boss",
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
CAN_RIBS_X = (-62.0, -40.0, -18.0, 3.0)  # ribs along y. P6m2: -62 at the ramp foot, the rest under the hump roof, placed through the roof bosses (-18: the +-27 pair) and clear of the port tubes (x -27 / 17)
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
    17.5  # hood depth behind the wall's back face (face board 10.6 + lugs 8.2 + room); P6m3: 15 -> 17.5, the flush screw counterbores clear the round at D
)
CAP_GAP = 0.1  # P6m3: canopy front (its seam with the front cap) this far behind the cap's back
HOOD_BOSS = (5.0, 2.0)  # P6m3: canopy boss under the hood ceiling at each lug: radius, thickness (the lug tops are 2 lower)
HOOD_CB = (7.5, 1.8)  # flush counterbore square to the hood top: Ø (ISO 7380-2 M3 flange Ø6.9), depth (flange 1.65 + 0.15)
CAN_R = (
    20.0,
    8.0,
    8.0,
)  # rear plan corners (= plate R20), hood edges, top edges (E1 8)
CAN_WIN_HW = CAN_HW - CAN_T  # front opening. P6m3: the whole front between the side walls (the front cap closes it; no lips)
CAN_APRON_HW = 26.0  # (pre 2026-11-06) rear apron, inside the carriages (|y| >= 28)
# Ben (2026-11-06): the open rear corners beside the apron showed the carriages and jack
# blocks. The rear wall now runs to the plate across the full width and round both R20
# plan corners, stopping on a radial face where its INNER surface is CAN_REAR_CLR aft of
# the carriages' aft-most position (taut station - pedestal half-length - travel).
CAN_REAR_CLR = 1.0
CAN_BOSS = (
    -80.4,
    12.0,
    12.0,
)  # rear insert bosses: x, |y|, height (clear of the deck at x -75)
HOOD_COLLAR_R = 5.5  # Q27 (a): collar round each hood screw (Ø11)
HOOD_CBORE_D = 7.5  # counterbore for the ISO 7380-2 M3 flange (Ø6.9)
HOOD_HEAD_SINK = 0.15  # head top under the collar rim
CAN_LUG_HOLE = 3.4  # P6m3: M3 clearance square to the hood top (was a vertical Ø3.9 through the 15° ceiling)
CAN_LUG_AXIS = (-math.sin(math.radians(BH_TILT)), 0.0, math.cos(math.radians(BH_TILT)))  # the lugs' (tilted) axis
CAN_LUG_GAP = 0.1  # ceiling over the lug tops (touching on the 15° tilt read as 2 x 0.1 mm3 interference, tick 47); the screws close it
# P6f (tick 74): crown along x over the body top (E1 §2: no flat panel > 60 x 60; white
# shows layer lines on flats). An arc through the top's rear and hood ends (both at
# CAN_TOP) rising CAN_CROWN in the middle; the shell keeps it on the ceiling (radius - t),
# the ribs and keels follow it (tops CAN_RIB_SINK into the skin, bottoms flat as before).
CAN_CROWN = 2.5
CAN_RIB_SINK = 0.5
CAN_RIB_W45 = 4.5  # P6f (tick 95): cross-rib 45° wedge run (= rib depth + sink)

# P6m2 (Ben 2026-11-08, replaces the P6m pod RB-PRT-005): the mic disc hangs from a
# full-width HUMP that is part of the canopy (no separate pod, no posts). Side profile:
# today's crown up to a 45° ramp, a crowned plateau (the roof) at HUMP_Z, and a 45° slope
# from the plateau up to the hood's back top edge D, replacing the hood's 25 mm back step
# (Q29: the support it needed). Every corner of the top is a tangent round (HUMP_BLEND), so
# the top is one tangent chain from the rear edge to D; its side edges take one r 8 round.
# The canopy prints rear wall down: both 45° faces and the roof print without support.
# The disc (reSpeaker Flex XVF3800 circular-4, audio-hardware §3) hangs under the roof: per
# hole an M2.5 x 8 SHCS up through a TPU washer, the disc and a TPU washer into an M2.5 x 4
# insert in a roof boss; 4 ports through the roof. Inside it is open to the canopy, so the
# disc goes in from below with the canopy off and the FPC drops straight down.
HUMP_Z = 110.0  # roof outer z at the plateau's ends (Ben 2026-11-08)
HUMP_CROWN = 1.5  # plateau crown (E1 §2: no flat panel > 60 x 60)
HUMP_XH = -48.0  # ramp top / plateau rear end before the rounds (disc rear edge -41.25)
HUMP_BLEND = (12.0, 15.0, 10.0)  # top rounds: ramp foot (concave), ramp top (convex), plateau -> slope (concave)
HUMP_RIB_X1 = 32.0  # lengthwise ribs end on the slope, short of the hood's lugs (x >= 38)
HUMP_KEEL_X1 = -27.0  # keels end aft of the disc (it reaches |y| 31.5 only at x -22.9..12.9)
MIC_D, MIC_PCB_T, MIC_COMP_H = 72.5, 1.5, 1.4  # board Ø, thickness, components (down)
MIC_SQ = 44.0  # mics on a square, at 45° to the hole pattern
MIC_PCD, MIC_HOLE_ANG = 62.5, (0.0, 120.0, 240.0)  # 3 x Ø3.3 holes
MIC_CTR = (-5.0, 0.0)
MIC_WASHER = (7.0, 3.0, 1.0)  # TPU 85A washer OD, ID (M2.5 clear), thickness; 2 per hole
MIC_BOSS_D, MIC_INS = 8.0, (3.6, 5.0)  # M2.5 x 4 insert (Ben: OK): drawn hole, pocket (L + 1)
MIC_INS_L = 4.0  # the insert's length (thread engagement)
MIC_PLANE = HUMP_Z - CAN_T - CAN_RIB[1]  # roof-boss and plateau-rib bottoms = the upper washers' tops
MIC_TUBE = (3.2, 1.2, 0.3)  # port tube OD, port Ø, reach below MIC_PLANE (foam squeeze)
MIC_SCREW_L = 8.0  # M2.5 x 8 SHCS (ISO 4762): washer 1 + disc 1.5 + washer 1 + insert 4 = 7.5

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


# ------------------------------------------------ P6m2 top chain (crown -> hump -> D)
_S2 = math.sqrt(0.5)
_U45, _N45 = (_S2, _S2), (-_S2, _S2)  # 45° faces: direction (+x up), outward normal


def _blend(P, u, n, o, R, r, concave, near):
    """Tangent round of radius r between the line (point P, unit direction u, outward
    normal n) and the convex circle (o, R) the solid lies inside. Concave: the round's
    centre is outside the solid (|Q - o| = R + r); convex: inside (R - r). Returns the
    centre and the tangent points on the line and on the circle (root nearest `near`)."""
    s = 1.0 if concave else -1.0
    rq = R + r if concave else R - r
    bx, bz = P[0] + s * r * n[0] - o[0], P[1] + s * r * n[1] - o[1]
    bu = bx * u[0] + bz * u[1]
    sq = math.sqrt(bu * bu - (bx * bx + bz * bz - rq * rq))
    qs = [(o[0] + bx + t * u[0], o[1] + bz + t * u[1]) for t in (-bu + sq, -bu - sq)]
    q = min(qs, key=lambda c: math.dist(c, near))
    tl = (q[0] - s * r * n[0], q[1] - s * r * n[1])
    k = R / math.dist(q, o)
    tc = (o[0] + (q[0] - o[0]) * k, o[1] + (q[1] - o[1]) * k)
    return q, tl, tc


def hump_plateau() -> tuple[float, float, float, float]:
    """(x centre, z centre, radius, x of the slope's foot XS) of the plateau's arc."""
    d = canopy_profile()[3]
    xs = d[0] - (d[1] - HUMP_Z)  # 45° from the plateau up to D
    c, sg = xs - HUMP_XH, HUMP_CROWN
    r = (c * c / 4 + sg * sg) / (2 * sg)
    return (HUMP_XH + xs) / 2, HUMP_Z + sg - r, r, xs


def hump_chain() -> list[dict]:
    """The canopy's top in side view, B (rear top) to D (hood back top), as tangent
    segments: {"k": "arc", "c", "r", "cv" (convex), "p0", "p1"} or {"k": "line", "p0",
    "p1", "n"}; x rises along it."""
    p = canopy_profile()
    b, d = p[1], p[3]
    xc, zc, rc = canopy_crown()
    xp, zp, rp, xs = hump_plateau()
    r1, r2, r3 = HUMP_BLEND
    # the ramp foot's corner on the crown (for picking the root)
    x = HUMP_XH - 15.0
    for _ in range(60):
        x = HUMP_XH - (HUMP_Z - can_top_z(x))
    q1, tl1, tc1 = _blend((HUMP_XH, HUMP_Z), _U45, _N45, (xc, zc), rc, r1, True, (x, can_top_z(x)))
    q2, tl2, tc2 = _blend((HUMP_XH, HUMP_Z), _U45, _N45, (xp, zp), rp, r2, False, (HUMP_XH, HUMP_Z))
    q3, tl3, tc3 = _blend(d, _U45, _N45, (xp, zp), rp, r3, True, (xs, HUMP_Z))
    segs = [
        {"k": "arc", "c": (xc, zc), "r": rc, "cv": True, "p0": b, "p1": tc1},
        {"k": "arc", "c": q1, "r": r1, "cv": False, "p0": tc1, "p1": tl1},
        {"k": "line", "p0": tl1, "p1": tl2, "n": _N45},
        {"k": "arc", "c": q2, "r": r2, "cv": True, "p0": tl2, "p1": tc2},
        {"k": "arc", "c": (xp, zp), "r": rp, "cv": True, "p0": tc2, "p1": tc3},
        {"k": "arc", "c": q3, "r": r3, "cv": False, "p0": tc3, "p1": tl3},
        {"k": "line", "p0": tl3, "p1": d, "n": _N45},
    ]
    xs_ = [sg["p0"][0] for sg in segs] + [d[0]]
    assert all(a < b_ for a, b_ in zip(xs_, xs_[1:])), xs_
    return segs


def _seg_normal(sg: dict, q) -> tuple[float, float]:
    """Outward unit normal of a chain segment at its point q."""
    if sg["k"] == "line":
        return sg["n"]
    cx, cz = sg["c"]
    k = 1.0 if sg["cv"] else -1.0
    return (k * (q[0] - cx) / sg["r"], k * (q[1] - cz) / sg["r"])


def chain_offset(ins: float, segs: list[dict] | None = None) -> list[dict]:
    """The chain moved ins inward (the shell's inside at CAN_T; a rib's top / bottom)."""
    out = []
    for sg in segs if segs is not None else hump_chain():
        n0, n1 = _seg_normal(sg, sg["p0"]), _seg_normal(sg, sg["p1"])
        q = dict(sg)
        q["p0"] = (sg["p0"][0] - ins * n0[0], sg["p0"][1] - ins * n0[1])
        q["p1"] = (sg["p1"][0] - ins * n1[0], sg["p1"][1] - ins * n1[1])
        if sg["k"] == "arc":
            q["r"] = sg["r"] - ins if sg["cv"] else sg["r"] + ins
        out.append(q)
    return out


def _seg_z(sg: dict, x: float) -> float:
    if sg["k"] == "line":
        (x0, z0), (x1, z1) = sg["p0"], sg["p1"]
        return z0 + (x - x0) * (z1 - z0) / (x1 - x0)
    cx, cz = sg["c"]
    h = math.sqrt(max(sg["r"] ** 2 - (x - cx) ** 2, 0.0))
    return cz + h if sg["cv"] else cz - h


def chain_z(x: float, ins: float = 0.0) -> float:
    """z of the top (ins 0) or of the surface ins under it, at x (ends extend their segment)."""
    segs = chain_offset(ins)
    for sg in segs:
        if x <= sg["p1"][0]:
            return _seg_z(sg, x)
    return _seg_z(segs[-1], x)


def canopy_top_z(x: float) -> float:
    """Outer top of the canopy at x (edgeaudit, S8's heel pad)."""
    return chain_z(x)


def chain_clip(segs: list[dict], x0: float, x1: float) -> list[dict]:
    out = []
    for sg in segs:
        a, b = max(sg["p0"][0], x0), min(sg["p1"][0], x1)
        if b - a <= 1e-9:
            continue
        q = dict(sg)
        q["p0"], q["p1"] = (a, _seg_z(sg, a)), (b, _seg_z(sg, b))
        out.append(q)
    return out


def chain_entries(segs: list[dict], reverse: bool = False) -> list:
    """_prism_y entries walking the segments (their first point not included)."""
    out: list = []
    seq = list(reversed(segs)) if reverse else segs
    for sg in seq:
        end = sg["p0"] if reverse else sg["p1"]
        if sg["k"] == "arc":
            out.append(("arc", sg["c"][0], sg["c"][1], end[0], end[1]))
        else:
            out.append(end)
    return out


def chain_sample(segs: list[dict], step_deg: float = 2.0) -> list[tuple[float, float]]:
    """Points along the segments (first point included), arcs every step_deg or finer."""
    pts = [segs[0]["p0"]]
    for sg in segs:
        if sg["k"] == "line":
            pts.append(sg["p1"])
            continue
        cx, cz = sg["c"]
        a0 = math.atan2(sg["p0"][1] - cz, sg["p0"][0] - cx)
        a1 = math.atan2(sg["p1"][1] - cz, sg["p1"][0] - cx)
        n = max(2, int(abs(math.degrees(a1 - a0)) / step_deg) + 1)
        pts += [(cx + sg["r"] * math.cos(a0 + (a1 - a0) * k / n), cz + sg["r"] * math.sin(a0 + (a1 - a0) * k / n)) for k in range(1, n + 1)]
    return pts


def band_profile(x0: float, x1: float, ins_top: float, ins_bot: float) -> list:
    """Side profile of a strip under the top: between the surfaces ins_top and ins_bot under
    it, x0..x1 (a lengthwise rib)."""
    top = chain_clip(chain_offset(ins_top), x0, x1)
    bot = chain_clip(chain_offset(ins_bot), x0, x1)
    return [top[0]["p0"], *chain_entries(top), bot[-1]["p1"], *chain_entries(bot, reverse=True)]


def _polyline_len(pts, xa: float = -1e9, xb: float = 1e9) -> float:
    tot = 0.0
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        lo, hi = max(min(x0, x1), xa), min(max(x0, x1), xb)
        if hi <= lo or x1 == x0:
            continue
        tot += math.hypot(x1 - x0, z1 - z0) * (hi - lo) / abs(x1 - x0)
    return tot

def canopy_profile() -> list[tuple[float, float]]:
    """Outer side profile A..F (clockwise in XZ): rear bottom, rear top, hood back foot,
    hood back top, hood front top (on the wall's back-face plane), front bottom."""
    top_pre = (
        BH_H + CAN_LUG_GAP + CAN_T
    )  # hood ceiling just over the wall top / lug tops (z_pre BH_H)
    assert abs(top_pre - BH_TOP) < 1e-9, (top_pre, BH_TOP)
    assert abs(BH_W / 2 - CAN_HW) < 1e-9
    # P6m3: the front (E, F) is the seam with the front cap, CAP_D + CAP_GAP behind the cap's
    # face; F on the skirt line
    xsm = BH_XF - CAP_D - CAP_GAP
    xd, zd = _pre2ch(BH_PIVOT[0] - CAN_HOOD_D, top_pre)
    xe, ze = _pre2ch(xsm, top_pre)
    s15, c15 = math.sin(math.radians(BH_TILT)), math.cos(math.radians(BH_TILT))
    xf, _ = _pre2ch(xsm, (CAN_Z0 - s15 * (xsm - BH_PIVOT[0])) / c15)
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


def canopy_ribs() -> list[tuple[float, ...]]:
    """Rib grid plan extents (x0, x1, y0, y1): the lengthwise ribs from the rear seam up the
    ramp and along the hump roof to HUMP_RIB_X1 on the slope; the cross ribs inside the
    inner side rounds (|y| 45). Their side profiles follow the top (band_profile)."""
    t, _ = CAN_RIB
    ya = CAN_HW - CAN_T - (CAN_R[2] - CAN_T)  # 45
    out = [(canopy_rear_seam(), HUMP_RIB_X1, y - t / 2, y + t / 2) for y in CAN_RIBS_Y]
    out += [(x - t / 2, x + t / 2, -ya, ya) for x in CAN_RIBS_X]
    return out


def canopy_rear_seam() -> float:
    """x of the tangent seam between the crowned ceiling (inset CAN_T) and the rear inner
    round. Flat: -77. Crowned the r 8 round's centre sits on the arc's R - 8 circle, so the
    seam moves back to -77.45 (tick 74c: ribs ending at -77 left a 0.45 sliver of ceiling
    behind their ends, and S8 peaked there: 38 / 83 MPa)."""
    xc, _, R = canopy_crown()
    xf = CAN_X0 + CAN_R[2]  # the round's centre x
    return xc + (xf - xc) * (R - CAN_T) / (R - CAN_R[2])


def canopy_cross_rib_profile(x0: float, x1: float) -> list:
    """Side profile (XZ) of a cross rib x0..x1, constant depth under the top (P6m2: follows
    the chain). P6f (tick 95, Q26 a: the canopy prints rear wall down, building +x): a 45°
    wedge on the rib's -x face from its bottom edge up to the skin CAN_RIB_W45 further back,
    so the 4 mm fin doesn't print as an overhang."""
    t_top, t_bot = CAN_T - CAN_RIB_SINK, CAN_T + CAN_RIB[1]
    top = chain_clip(chain_offset(t_top), x0 - CAN_RIB_W45, x1)
    bot = chain_clip(chain_offset(t_bot), x0, x1)
    return [top[0]["p0"], *chain_entries(top), bot[-1]["p1"], *chain_entries(bot, reverse=True)]


def canopy_rib_profile() -> list:
    """Side profile (XZ) of the lengthwise ribs: constant depth CAN_RIB[1] under the top from
    the rear seam to HUMP_RIB_X1, top sunk CAN_RIB_SINK into the skin. Under the hump roof
    the bottoms sit at MIC_PLANE, 1.0 over the disc (the upper washer's thickness)."""
    xa, xb = canopy_ribs()[0][:2]
    return band_profile(xa, xb, CAN_T - CAN_RIB_SINK, CAN_T + CAN_RIB[1])


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


def canopy_keel_profile() -> list:
    """Keel side profile (XZ). Rev 3 (tick 49): tied into the rear wall (x -83.2, chamfered
    inside the r 6.2 inner round). P6m2: the top follows the chain (crown, ramp, hump roof)
    to HUMP_KEEL_X1, aft of the disc; the end drops at a slope to the keel bottom 20 back.
    Built as a Top-plane profile (a `box` came out 2.4 thick, not 1.8, tick 49)."""
    _, _, kz = CAN_KEEL
    zc = CAN_TOP - CAN_T
    xr = CAN_X0 + CAN_T  # rear wall inner face
    ri = CAN_R[2] - CAN_T  # inner top round
    x1 = HUMP_KEEL_X1
    top = chain_clip(chain_offset(CAN_T - CAN_RIB_SINK), canopy_rear_seam(), x1)
    return [
        (xr, kz),
        (xr, zc - ri),
        top[0]["p0"],
        *chain_entries(top),
        (x1, chain_z(x1, CAN_T + CAN_RIB[1])),
        (x1 - 20.0, kz),
    ]


def canopy_top_round_boxes(h: float = 0.6) -> list[str]:
    """Pick boxes (around each edge's END-VERTEX midpoint, swbuild 'vmid') for the top's single
    r 8 round, as the edges stand after the r CAN_R[0] plan corners: the rear edge, the two
    plan arcs, both side edges of each chain segment (the crown's from the plan corner's end),
    edge D and the hood ceiling's side edges."""
    p = canopy_profile()
    a, b, d, e = p[0], p[1], p[3], p[4]
    rr, hw = CAN_R[0], CAN_HW
    xc0 = CAN_X0 + rr  # the plan corners end here
    z0 = can_top_z(xc0)
    pts = [(a[0], 0.0, b[1]), (d[0], 0.0, d[1])]  # rear edge, edge D
    for sg in (-1, 1):
        pts.append(((a[0] + xc0) / 2, sg * (hw - rr / 2), (b[1] + z0) / 2))  # plan arc
        for k, sgm in enumerate(hump_chain()):
            (x0, z0_), (x1, z1) = sgm["p0"], sgm["p1"]
            if k == 0:
                x0, z0_ = xc0, z0
            pts.append(((x0 + x1) / 2, sg * hw, (z0_ + z1) / 2))
        pts.append(((d[0] + e[0]) / 2, sg * hw, (d[1] + e[1]) / 2))  # hood ceiling side edge
    return [f"{x - h:.3f} {y - h:.3f} {z - h:.3f} {x + h:.3f} {y + h:.3f} {z + h:.3f}" for x, y, z in pts]


def front_cut_corner_area() -> float:
    """Per top corner of the front opening: the area (y-z, pre-tilt) inside the old square
    corner, outside the inner r CAP_R - CAN_T round and inside the outer r CAP_R round
    (both about (BH_W/2 - CAP_R, BH_TOP - CAP_R)): shell the P6m4 cut no longer removes."""
    ri, ro = CAP_R - CAN_T, CAP_R
    n, a = 400, 0.0
    h = (CAN_WIN_HW - (BH_W / 2 - CAP_R)) / n
    for i in range(n):
        for j in range(n):
            u, v = (i + 0.5) * h, (j + 0.5) * h
            if ri * ri < u * u + v * v <= ro * ro:
                a += h * h
    return a


def front_cut_lines(x0p: float, x1p: float, zw: float) -> list[str]:
    """P6m4: the cut that opens the canopy's front end (a slab x0p..x1p round the front wall,
    pre-tilt), with its top corners on the shell's inner r CAP_R - CAN_T round instead of
    square: the square corners (8.77 from the round's axis) broke through the outer r CAP_R
    skin, a 0.8 deep notch at both front top corners. Two crossed boxes + two corner
    cylinders, in the wall frame."""
    piv = f"{BH_PIVOT[0]} {BH_PIVOT[1]} {BH_PIVOT[2]}"
    hi, ri = CAN_WIN_HW, CAP_R - CAN_T
    yc, zc = BH_W / 2 - CAP_R, BH_TOP - CAP_R
    assert abs(yc + ri - hi) < 1e-9 and abs(zc + ri - zw) < 1e-6, (yc + ri, hi, zc + ri, zw)
    return [
        f"rotbody|{piv}|y|{BH_TILT}",
        f"prof|{x0p:.4f} {x1p:.4f}|{_right_rect(-hi, hi, 20.0, zc)}|cut|right",
        f"prof|{x0p:.4f} {x1p:.4f}|{_right_rect(-yc, yc, 20.0, zw)}|cut|right",
        *[f"cyl|x|{sg * yc} {zc}|{x0p:.4f} {x1p:.4f}|{ri}|cut" for sg in (-1, 1)],
        f"rotbody|{piv}|y|{-BH_TILT}",
    ]


def canopy_seam() -> dict:
    """P6m4: r SEAM_R on the canopy's front-end outer edges (the seam face, pre-tilt plane
    x = BH_XF - CAP_D - CAP_GAP), turned into the wall frame like hood_screw()."""
    piv = f"{BH_PIVOT[0]} {BH_PIVOT[1]} {BH_PIVOT[2]}"
    (ln, dv), = seam_break_lines(BH_XF - CAP_D - CAP_GAP, cap_z_low())
    return {"lines": [f"rotbody|{piv}|y|{BH_TILT}", ln, f"rotbody|{piv}|y|{-BH_TILT}"], "vol": dv}


def hood_screw() -> dict:
    """P6m3 (Ben: flush top screws): per lug a boss under the hood ceiling (the lug top sits
    CAN_LUG_GAP under it), an M3 clearance hole and a flat counterbore whose rim is flush
    with the hood top, all square to the hood top: the body is turned into the wall's
    pre-tilt frame (hood top horizontal at BH_TOP), cut, rounded (r 0.5 on the rims) and
    turned back. Head: ISO 7380-2 M3 flange, 0.15 under the surface."""
    lx = bh_lug_x()
    rb, tb = HOOD_BOSS
    dcb, hcb = HOOD_CB
    ceil = BH_TOP - CAN_T
    bz = ceil - tb
    assert abs(bz - (BH_LUG_Z[1] + CAN_LUG_GAP)) < 1e-9, (bz, BH_LUG_Z)
    assert lx + rb <= BH_XF - CAP_D - CAP_GAP - 0.4, "screw boss runs into the front cap"
    piv = f"{BH_PIVOT[0]} {BH_PIVOT[1]} {BH_PIVOT[2]}"
    lines = [f"rotbody|{piv}|y|{BH_TILT}"]
    for sg in (-1, 1):
        y = sg * BH_LUG_Y
        lines += [
            f"cyl|z|{lx:.4f} {y}|{bz:.3f} {ceil + 0.3:.3f}|{rb}|boss",
            f"cyl|z|{lx:.4f} {y}|{bz - 0.1:.3f} {BH_TOP + 0.1:.3f}|{CAN_LUG_HOLE / 2}|cut",
            f"cyl|z|{lx:.4f} {y}|{BH_TOP - hcb:.3f} {BH_TOP + 0.1:.3f}|{dcb / 2}|cut",
        ]
    q = (1 - math.pi / 4) * 0.5**2
    dvr = 2 * q * 2 * math.pi * (dcb / 2 + 0.11)
    boxes = ";".join(
        f"{lx - dcb / 2 - 0.5:.3f} {sg * BH_LUG_Y - dcb / 2 - 0.5:.3f} {BH_TOP - 0.1:.3f} {lx + dcb / 2 + 0.5:.3f} {sg * BH_LUG_Y + dcb / 2 + 0.5:.3f} {BH_TOP + 0.1:.3f}"
        for sg in (-1, 1)
    )
    lines.append(f"fillet|0.5|curve|{boxes}|2|{-dvr:.2f} {0.5 * dvr + 0.5:.2f}")
    lines.append(f"rotbody|{piv}|y|{-BH_TILT}")
    vol = 2 * (
        math.pi * rb * rb * tb
        - math.pi * (CAN_LUG_HOLE / 2) ** 2 * (tb + CAN_T)
        - math.pi * ((dcb / 2) ** 2 - (CAN_LUG_HOLE / 2) ** 2) * hcb
    ) - dvr
    return {"lines": lines, "vol": vol}


def canopy_rear_wall() -> dict:
    """The rear wall below the skirt (z 0 .. CAN_Z0), plan view: the rear flat plus both
    corner arcs (outer r CAN_R[0], inner r - CAN_T) to a radial end at angle phi (from +x,
    about the corner centre (CAN_X0 + rr, +-(hw - rr))). Returns the plan profile, its
    area and the end points."""
    rr, hw, t = CAN_R[0], CAN_HW, CAN_T
    cx, cy, ri = CAN_X0 + rr, hw - rr, rr - t
    x_aft = dt.belt_fit()["x_fit"] - CAR_PED[0] - dt.TRAVEL  # carriage's aft-most face
    phi = math.acos((x_aft - CAN_REAR_CLR - cx) / ri)  # inner end on x_aft - clr
    co, si = math.cos(phi), math.sin(phi)
    pi_, po = (cx + ri * co, cy + ri * si), (cx + rr * co, cy + rr * si)
    prof = " ".join(
        [
            f"M {pi_[0]:.6f} {-pi_[1]:.6f}",
            f"a {cx:.6f} {-cy:.6f} {cx - ri:.6f} {-cy:.6f}",  # a = clockwise
            f"L {cx - ri:.6f} {cy:.6f}",
            f"a {cx:.6f} {cy:.6f} {pi_[0]:.6f} {pi_[1]:.6f}",
            f"L {po[0]:.6f} {po[1]:.6f}",
            f"A {cx:.6f} {cy:.6f} {cx - rr:.6f} {cy:.6f}",
            f"L {cx - rr:.6f} {-cy:.6f}",
            f"A {cx:.6f} {-cy:.6f} {po[0]:.6f} {-po[1]:.6f}",
        ]
    )
    sweep = math.pi - phi  # each arc, rear tangent (angle pi) to the end
    area = t * 2 * cy + 2 * 0.5 * sweep * (rr * rr - ri * ri)
    return {"prof": prof, "area": area, "phi": phi, "pi": pi_, "po": po, "x_aft": x_aft}


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
    rw = canopy_rear_wall()
    rear = 0.0  # 2026-11-06: the rear wall reaches the plate; no rim along the rear flat
    sides = 2 * ((wx0 - (CAN_X0 + rr)) + (xf - wx1))
    cbar = r * (10 - 3 * math.pi) / (3 * (4 - math.pi))
    arcs = 2 * q90 * (rr - cbar) * (rw["phi"] - math.pi / 2)  # end face to the side tangent
    lips = 0.0  # P6m3: the front wall is gone; the side walls' front-end bottoms stay square
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
    # inner corner arcs (r rr - t, centre (x0 + rr, +-(hw - rr))) from the rear wall's end to
    # the side seam: chord midpoint; and the concave junction with the wall's radial end face
    cx, cy = CAN_X0 + rr, hw - rr
    (pix, piy), (pox, poy) = rw["pi"], rw["po"]
    mx, my = (pix + cx) / 2, (piy + hw - t) / 2
    ex, ey = (pix + pox) / 2, (piy + poy) / 2
    for sg in (-1, 1):
        skips += [box(mx - 0.4, mx + 0.4, sg * my - 0.4, sg * my + 0.4)]
        skips += [box(ex - 0.5, ex + 0.5, sg * ey - 0.5, sg * ey + 0.5)]
    for xw in (wx0, wx1):  # web junctions (concave)
        skips += [box(xw - 0.4, xw + 0.4, -60, 60)]
    # front-wall inner edge (back-face line minus t along the normal), beside the window
    xfi = xf - t / math.cos(math.radians(BH_TILT))
    skips += [box(xfi - 0.6, xfi + 0.6, -60, 60)]
    # P6m3: the side walls' front-end bottom edges sit on the seam with the cap: square
    for sg in (-1, 1):
        skips += [box(xf - 0.6, xf + 0.6, sg * (hw - t / 2) - 1.2, sg * (hw - t / 2) + 1.2)]
    del ai
    return vol, skips


def canopy_side_poly(inset: float = 0.0) -> list[tuple[float, float]]:
    """Side profile as a polygon A, B, top chain (sampled), D, E, F; inset > 0 gives the
    shell's cavity (every edge but the open bottom moved in)."""
    p = canopy_profile()
    poly = [p[0], *chain_sample(hump_chain()), p[4], p[5]]
    return _inset_profile(poly, inset) if inset else poly


def canopy_solid_volume(poly, hw: float, rr: float, rh: float, rt: float) -> dict:
    """Solid (unshelled) canopy volume and each round's share (P6m2: the top is the chain).
    rear = the vertical plan corners (r rr, A to B); top = r rt along the top's rear edge,
    its plan arcs and both side edges from the plan corners to D (one tangent chain); hood =
    r rh on D (along y) and the hood ceiling's side edges D -> E."""
    a, b = poly[0], poly[1]
    d, e = poly[-3], poly[-2]
    q90 = _round_area(90.0, 1.0)
    v1 = (d[0] - poly[-4][0], d[1] - poly[-4][1])
    v2 = (e[0] - d[0], e[1] - d[1])
    turn = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]))
    alpha_d = 180.0 - abs(turn)
    cbar = rt * (10 - 3 * math.pi) / (3 * (4 - math.pi))
    side = _polyline_len(poly[1:-2], a[0] + rr, d[0])
    return {
        "base": _poly_area(poly) * 2 * hw,
        "rear": -2 * q90 * rr * rr * (b[1] - a[1]),
        "top": -(q90 * rt * rt * (2 * side + (2 * hw - 2 * rr)) + q90 * rt * rt * math.pi * (rr - cbar)),
        "hood": -(_round_area(alpha_d, rh) * 2 * hw + 2 * q90 * rh * rh * math.dist(d, e)),
        "alpha_d": alpha_d,
        "side": side,
    }


def canopy_rib_volumes() -> dict:
    """Ribs, cross ribs and keels below the inside of the shell (their CAN_RIB_SINK in the
    skin adds nothing), overlaps taken out once; and the r CAN_ROOT_R root rounds on the
    two ceiling faces that get them (crown, hump roof)."""
    t, dep = CAN_RIB
    ky, kt, kz = CAN_KEEL
    ins, sink = CAN_T, CAN_RIB_SINK
    xa, xb = canopy_ribs()[0][:2]
    ya = canopy_ribs()[-1][3]
    nY = len(CAN_RIBS_Y)
    a_rib = _poly_area(_profile_poly(band_profile(xa, xb, ins, ins + dep)))
    a_x = {}
    for x in CAN_RIBS_X:
        prof = canopy_cross_rib_profile(x - t / 2, x + t / 2)
        a_x[x] = _poly_area(_profile_poly(prof)) - _poly_area(
            _profile_poly(band_profile(x - t / 2 - CAN_RIB_W45, x + t / 2, ins - sink, ins))
        )
    xk1 = HUMP_KEEL_X1
    a_keel = _poly_area(_profile_poly(canopy_keel_profile())) - _poly_area(
        _profile_poly(band_profile(canopy_rear_seam(), xk1, ins - sink, ins))
    )
    keel_x = [x for x in CAN_RIBS_X if x < xk1]
    ribs = (
        nY * t * a_rib
        + sum(a * 2 * ya for a in a_x.values())
        - nY * t * sum(a_x.values())  # cross ribs inside the lengthwise ribs
        + 2 * kt * a_keel
        - 2 * kt * sum(a_x[x] for x in keel_x)  # cross ribs through the keels
    )
    # roots: crown face (rear seam .. its tangent seam into the ramp-foot round) and hump
    # roof face (between its two tangent seams); concave rounds (1 - pi/4) r² per mm, the
    # cross ribs' -x roots at 135° on their 45° wedges
    inner = chain_offset(ins)
    faces = [(xa, inner[0]["p1"][0]), (inner[4]["p0"][0], inner[4]["p1"][0])]
    q90 = (1 - math.pi / 4) * CAN_ROOT_R**2
    q135 = (1 / math.tan(math.radians(67.5)) - math.pi / 8) * CAN_ROOT_R**2
    per = []
    for k, (f0, f1) in enumerate(faces):
        xs_in = [x for x in CAN_RIBS_X if f0 < x < f1]
        # roof: no lengthwise-rib roots forward of the last cross rib (the ribs run on over
        # the tangent seam into the slope round, where a root round can't end: P6m2 build)
        L = (max(xs_in) + t / 2 if k == 1 else f1) - f0
        v = q90 * nY * 2 * (L - len(xs_in) * t)  # lengthwise ribs
        kl = max(0.0, min(f1, xk1) - f0)  # keels on this face
        nk = len([x for x in xs_in if x < xk1])
        v += q90 * 2 * 2 * max(0.0, kl - nk * t)
        for x in xs_in:
            span = 2 * ya - nY * t - (2 * kt if x < xk1 else 0.0)
            v += (q90 + q135) * span
        per.append(v)
    return {"ribs": ribs, "roots": sum(per), "roots_crown": per[0], "roots_roof": per[1], "faces": faces}


def canopy_features() -> dict:
    p = canopy_profile()
    rr, rh, rt = CAN_R
    poly = canopy_side_poly()
    pin = canopy_side_poly(CAN_T)
    out = canopy_solid_volume(poly, CAN_HW, rr, rh, rt)
    inn = canopy_solid_volume(pin, CAN_HW - CAN_T, rr - CAN_T, rh - CAN_T, rt - CAN_T)
    v_out = out["base"] + out["rear"] + out["hood"] + out["top"]
    v_in = inn["base"] + inn["rear"] + inn["hood"] + inn["top"]
    # front opening: the 1.8 front wall at |y| <= CAN_WIN_HW, from the skirt (z_pre at
    # mid-wall) up to the hood ceiling's underside (z_pre BH_H)
    xm = BH_XF - CAP_D - CAP_GAP - CAN_T / 2
    s, c_ = math.sin(math.radians(BH_TILT)), math.cos(math.radians(BH_TILT))
    zp0 = (CAN_Z0 - s * (xm - BH_PIVOT[0])) / c_
    win = CAN_T * 2 * CAN_WIN_HW * (BH_H + CAN_LUG_GAP - zp0)
    win -= CAN_T * 2 * front_cut_corner_area()  # P6m4: the cut's top corners follow the inner round
    # lug holes: lug axis on the wall's (tilted) z, at mid-ceiling
    lug_x = bh_lug_x()
    hx, hz = _pre2ch(lug_x, BH_H + CAN_LUG_GAP + CAN_T / 2)
    holes = 2 * math.pi * (CAN_LUG_HOLE / 2) ** 2 * CAN_T / c_
    # rear apron + bosses (the boss's slice inside the apron counted once)
    apron = canopy_rear_wall()["area"] * CAN_Z0
    bx, by, bh = CAN_BOSS
    r = INS_BOSS / 2
    dd = bx - (CAN_X0 + CAN_T)
    seg = r * r * math.acos(dd / r) - dd * math.sqrt(r * r - dd * dd)
    boss = 2 * (math.pi * r * r - seg) * bh
    pockets = 2 * math.pi * (INS_HOLE_PC / 2) ** 2 * INS_DEPTH
    rv = canopy_rib_volumes()
    rib_vol, roots = rv["ribs"], rv["roots"]
    (wx0, wx1), (tx0, tx1), td, _ = CAN_TAB
    tabs = 2 * CAN_T * ((wx1 - wx0) * CAN_Z0 + (tx1 - tx0) * td)
    return {
        "p": p,
        "pin": pin,
        "out": out,
        "inn": inn,
        "v_out": v_out,
        "v_in": v_in,
        "win": win,
        "win_zp0": zp0,
        "lug_hole": (hx, hz),
        "holes": holes,
        "apron": apron,
        "boss": boss,
        "pockets": pockets,
        "ribs": rib_vol,
        "roots": roots,
        "root_faces": rv["faces"],
        "roots_crown": rv["roots_crown"],
        "roots_roof": rv["roots_roof"],
        "tabs": tabs,
        "rim": canopy_rim_round()[0],
        "vol": -canopy_rear_edges()[0]
        - canopy_rim_round()[0]
        + v_out
        - v_in
        - win
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


CAN_VENT_EDGE_R = 0.5  # P6e (tick 85): vent slot outer edges (2 wide slots, 1.8 wall)


def canopy_rear_edges() -> tuple[float, list[str]]:
    """P6e (tick 85), kid-safety edges the canopy audit lists on the rear wall: r 0.5 on the
    26 vent slots' OUTER edges (inner loops of the x -85 face) and r 1.0 on the rear wall's
    two outer vertical end edges (2026-11-06: at the radial ends round the plan corners;
    were the apron's corners at y +-26). Returns (volume removed, lines)."""
    r = CAN_VENT_W / 2
    n = int(round(2 * CAN_VENT_HY / CAN_VENT_PITCH)) + 1
    per = sum(2 * (z1 - z0 - 2 * r) + 2 * math.pi * r for z0, z1 in CAN_VENT_Z) * n
    dv_v = (1 - math.pi / 4) * CAN_VENT_EDGE_R**2 * per
    zs = [z for zz in CAN_VENT_Z for z in zz]
    vent = (
        f"filletface|{CAN_VENT_EDGE_R}|x:-1|{CAN_X0}|{-CAN_HW} {CAN_Z0} {CAN_HW} {CAN_TOP}|1"
        f"|{-dv_v:.2f} {0.25 * dv_v:.2f}"
        f"|loops:{-CAN_VENT_HY - 2} {min(zs) - 2} {CAN_VENT_HY + 2} {max(zs) + 2}"
    )
    L = CAN_Z0 - CAN_EDGE_R  # 0 .. under the skirt rim's r 1
    dv_a = (1 - math.pi / 4) * CAN_EDGE_R**2 * L
    pox, poy = canopy_rear_wall()["po"]
    apron = [
        f"fillet|{CAN_EDGE_R}|z|{pox - 0.1:.3f} {s * poy - 0.1:.3f} {L / 2 - 3:.2f} {pox + 0.1:.3f} {s * poy + 0.1:.3f} {L / 2 + 3:.2f}"
        f"|1|{-dv_a:.2f} {0.2 * dv_a:.2f}"
        for s in (-1, 1)
    ]
    return dv_v + 2 * dv_a, [vent, *apron]


def mic_geom() -> dict:
    """Mic-disc layout in the chassis frame (P6m2 hump): hole and mic xy, the board's z
    span and the lower washers' bottoms (the screw heads' seat)."""
    cx, cy = MIC_CTR
    r = MIC_PCD / 2
    holes = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in MIC_HOLE_ANG]
    h = MIC_SQ / 2
    mics = [(cx + sx * h, cy + sy * h) for sx in (-1, 1) for sy in (-1, 1)]
    zt = MIC_PLANE - MIC_WASHER[2]  # board top (port face)
    zb = zt - MIC_PCB_T
    seat = zb - MIC_WASHER[2]  # under the lower washer: the SHCS head
    return {"holes": holes, "mics": mics, "zt": zt, "zb": zb, "seat": seat}


def _strip_circle(d: float, w: float, r: float, n: int = 400) -> float:
    """Area of a circle (radius r) inside a strip of width w whose centre line is d away."""
    lo, hi = max(d - w / 2, -r), min(d + w / 2, r)
    if hi <= lo:
        return 0.0
    s = (hi - lo) / n
    return sum(2 * math.sqrt(max(r * r - (lo + (i + 0.5) * s) ** 2, 0.0)) for i in range(n)) * s


def canopy_mic_lines() -> tuple[list[str], float]:
    """P6m2: what the hump roof carries for the disc: 3 bosses with M2.5 x 4 insert pockets
    from below and 4 port tubes with the Ø1.2 ports through the roof, all from MIC_PLANE up
    into the roof. Built after the root rounds. Volume: bosses less the rib material already
    inside them (strip x circle areas; the cross rib's wedge and the root rounds inside are
    ignored), tubes, less pockets and ports."""
    g = mic_geom()
    t, dep = CAN_RIB
    rb, (pd, pl) = MIC_BOSS_D / 2, MIC_INS
    to, tp, reach = MIC_TUBE
    lines: list[str] = []
    vol = 0.0
    for hx, hy in g["holes"]:
        zin, zout = chain_z(hx, CAN_T), chain_z(hx)
        assert MIC_PLANE + pl + 0.6 <= zout, (hx, zout)  # 0.6 skin over the insert pocket
        out_min = min(chain_z(hx + rb * (k / 20 - 1)) for k in range(41))
        if zin + 0.3 <= out_min - 0.6:
            lines.append(f"cyl|z|{hx:.4f} {hy:.4f}|{MIC_PLANE:.3f} {zin + 0.3:.3f}|{rb}|boss")
            v = math.pi * rb * rb * (zin - MIC_PLANE)
        else:
            # P6m4b: on the rise to the hood (x 26) a flat top at the centre's roof height
            # broke 0.37 out of the outer skin at the boss's rear edge. Square column, top
            # following the roof 0.3 into the skin; volume to the inner surface.
            x0, x1 = hx - rb, hx + rb
            top = chain_clip(chain_offset(CAN_T - 0.3), x0, x1)
            lines.append(_prism_y([(x0, MIC_PLANE), (x1, MIC_PLANE), top[-1]["p1"],
                                   *chain_entries(top, reverse=True)], hy - rb, hy + rb, "boss"))
            n = 80
            v = sum(chain_z(x0 + (i + 0.5) * 2 * rb / n, CAN_T) - MIC_PLANE for i in range(n)) * 2 * rb / n * 2 * rb
        lines.append(f"cyl|z|{hx:.4f} {hy:.4f}|{MIC_PLANE - 0.1:.3f} {MIC_PLANE + pl:.3f}|{pd / 2}|cut")
        rib_bot = chain_z(hx, CAN_T + dep)
        sq = not lines[-2].startswith("cyl")

        def strip(d: float) -> float:
            if sq:  # square column: the strip's width inside it, times its side
                return max(0.0, min(d + t / 2, rb) - max(d - t / 2, -rb)) * 2 * rb
            return _strip_circle(d, t, rb)

        for y in CAN_RIBS_Y:
            v -= strip(abs(hy - y)) * (zin - max(rib_bot, MIC_PLANE))
        for x in CAN_RIBS_X:
            v -= strip(abs(hx - x)) * (zin - max(rib_bot, MIC_PLANE))
        v -= math.pi * (pd / 2) ** 2 * pl
        vol += v
    for mx, my in g["mics"]:
        zin, zout = chain_z(mx, CAN_T), chain_z(mx)
        lines.append(f"cyl|z|{mx:.4f} {my:.4f}|{MIC_PLANE - reach:.3f} {zin + 0.3:.3f}|{to / 2}|boss")
        lines.append(f"cyl|z|{mx:.4f} {my:.4f}|{MIC_PLANE - reach - 0.1:.3f} {zout + 0.5:.3f}|{tp / 2}|cut")
        vol += math.pi * (to / 2) ** 2 * (zin - MIC_PLANE + reach) - math.pi * (tp / 2) ** 2 * (zout - MIC_PLANE + reach)
    return lines, vol


# Idler axle stack (2026-11-09, Ben: "add the spacer and shims"). The idler's two 624s sit
# flush with the hub tube's ends (wheel frame z 0..5 and 18..23) with 13 mm of free shoulder
# between their inner races; the carriage boss stops 0.5 short of the inner bearing and the
# track-frame plate stands 1.0 off the outer one. Clamped stack on the Ø4 shoulder, head
# (inboard) -> carriage boss -> 0.5 shim -> 624 -> this spacer -> 624 -> 2 x 0.5 shim ->
# frame plate -> M3 nyloc: only the outer races and the wheel turn (05 "Spin").
IDLER_SPACER = (8.0, 5.8, 4.2, 0.6)  # body Ø, end-land Ø (on the inner race only: 624 d1 ~6.1), bore, land height
IDLER_SHIM = (4.0, 8.0, 0.5)  # DIN 988 shim ring, bought: 1 at the boss + 2 at the frame per idler


def idler_spacer_lines(path: str) -> list[str]:
    """Spacer between the idler's two 624 inner races, in the wheel part frame (z from the
    bed / outboard face): z 5..18, so it sits in place with wheel_at(). Ø8 body, Ø5.8 x 0.6
    lands at each end, Ø4.2 bore (slip on the shoulder). Prints standing (+z)."""
    do, dl, di, h = IDLER_SPACER
    z0 = dt.BRG_W
    z1 = dt.BELT_W / 2  # inner bearing's outboard face (tube end BELT_W/2 + BRG_W, less BRG_W)
    L = z1 - z0
    assert abs(L - 13.0) < 1e-9, L
    v = math.pi / 4 * (do * do * (L - 2 * h) + dl * dl * 2 * h - di * di * L)
    return [
        f"part|{path}",
        f"cyl|z|0 0|{z0 + h:.3f} {z1 - h:.3f}|{do / 2}|boss",
        f"cyl|z|0 0|{z0:.3f} {z0 + h + 0.1:.3f}|{dl / 2}|boss",
        f"cyl|z|0 0|{z1 - h - 0.1:.3f} {z1:.3f}|{dl / 2}|boss",
        f"cyl|z|0 0|{z0 - 0.1:.3f} {z1 + 0.1:.3f}|{di / 2}|cut",
        f"expect|vol {v:.2f} {v * 0.02:.2f}|box {-do / 2} {do / 2} {-do / 2} {do / 2} {z0} {z1} 0.05",
        "save",
    ]


def mic_washer_lines(path: str) -> list[str]:
    """P8: TPU 85A washer (2 per hole: boss side and screw-head side) that floats the mic
    disc (audio §4.2). Part frame: centred on the origin, z 0..t."""
    od, idd, t = MIC_WASHER
    v = math.pi * ((od / 2) ** 2 - (idd / 2) ** 2) * t
    return [
        f"part|{path}",
        f"cyl|z|0 0|0 {t}|{od / 2}|boss",
        f"cyl|z|0 0|-0.1 {t + 0.1}|{idd / 2}|cut",
        f"expect|vol {v:.2f} {v * 0.02:.2f}|box {-od / 2} {od / 2} {-od / 2} {od / 2} 0 {t} 0.05",
        "save",
    ]


def mic_disc_lines(path: str) -> list[str]:
    """Envelope (interference only): the board plus a component layer under it, chassis
    frame; the component layer is clear round each hole (Ø6 pads; Ø7.4 for the washer).
    (P6m: the tick-98 keel strips are gone with the keel windows.)"""
    g = mic_geom()
    cx, cy = MIC_CTR
    r, rc = MIC_D / 2, MIC_WASHER[0] / 2 + 0.2
    v = math.pi * r * r * (MIC_PCB_T + MIC_COMP_H) - 3 * math.pi * (1.65**2 * MIC_PCB_T + rc**2 * MIC_COMP_H)
    return [
        f"part|{path}",
        f"cyl|z|{cx} {cy}|{g['zb'] - MIC_COMP_H:.3f} {g['zt']:.3f}|{r}|boss",
        *[f"cyl|z|{hx:.4f} {hy:.4f}|{g['zb'] - 0.1:.3f} {g['zt'] + 0.1:.3f}|1.65|cut" for hx, hy in g["holes"]],
        *[f"cyl|z|{hx:.4f} {hy:.4f}|{g['zb'] - MIC_COMP_H - 0.1:.3f} {g['zb']:.3f}|{rc}|cut" for hx, hy in g["holes"]],
        f"expect|vol {v:.1f} {v * 0.01:.1f}|box {cx - r} {cx + r} {cy - r} {cy + r} {g['zb'] - MIC_COMP_H:.2f} {g['zt']:.2f} 0.05",
        "save",
    ]


def _prism_y(poly: list, y0: float, y1: float, kind: str) -> str:
    """Top plane: sketch (x, -z), extrude +Y. Entries (x, z) or ("arc", xc, zc, x1, z1): a
    minor arc from the previous point; its sense is taken in sketch coordinates (z -> -z
    mirrors it)."""
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


# 2026-11-10 (Ben): PAM8302A amp (audio-hardware §2, Adafruit #2130: 24 x 15 x 1.6, no mounting
# holes) on the canopy's inner LEFT side wall at the front, beside the speaker (bulkhead back,
# y 6..26). Two rails along x grip its long edges (AMP_GRIP over each, AMP_SLOT for the 1.6
# PCB) and a stop at the rear end; it slides in from the canopy's open front (canopy off) and
# takes a dot of hot glue. Screw terminals at the front end, toward the speaker. The canopy
# prints rear wall down, so the rails stand vertical (no overhang but their ends).
AMP_PCB = (24.0, 15.0, 1.6)  # length (x), height (z), thickness
AMP_X0, AMP_ZB = 34.0, 36.0  # PCB rear end, bottom edge (the canopy front follows the 15° wall: x ~62 at z 53)
AMP_SLOT, AMP_GRIP, AMP_LIP, AMP_RAIL, AMP_CLR = 1.9, 1.0, 1.2, 2.0, 0.25


def amp_geom() -> dict:
    yw = CAN_HW - CAN_T  # wall inner face
    x0, x1 = AMP_X0, AMP_X0 + AMP_PCB[0]
    zb, zt = AMP_ZB, AMP_ZB + AMP_PCB[1]
    return {"yw": yw, "x": (x0, x1), "z": (zb, zt), "y_pcb": (yw - (AMP_SLOT + AMP_PCB[2]) / 2, yw - (AMP_SLOT - AMP_PCB[2]) / 2)}


def canopy_amp_boxes() -> list[tuple[float, float, float, float, float, float]]:
    g = amp_geom()
    yw, (x0, x1), (zb, zt) = g["yw"], g["x"], g["z"]
    c, xs = AMP_CLR, x0 - AMP_CLR - AMP_RAIL  # rails start behind the stop
    yl = yw - AMP_SLOT - AMP_LIP  # lip inner face
    return [
        (xs, x1, yl, yw, zb - c - AMP_RAIL, zb - c),  # bottom rail body
        (xs, x1, yl, yw - AMP_SLOT, zb - c, zb + AMP_GRIP),  # bottom lip
        (xs, x1, yl, yw, zt + c, zt + c + AMP_RAIL),  # top rail body
        (xs, x1, yl, yw - AMP_SLOT, zt - AMP_GRIP, zt + c),  # top lip
        (xs, x0 - c, yw - AMP_SLOT, yw, zb - c, zt + c),  # rear stop (PCB edge only)
    ]


def canopy_amp_lines() -> tuple[list[str], float]:
    """Rail boxes (0.1 into the wall) and their volume (wall side clipped at yw)."""
    yw = amp_geom()["yw"]
    bx = canopy_amp_boxes()
    lines = [f"box|{a:.3f} {b:.3f}|{c:.3f} {d + (0.1 if d >= yw - 1e-9 else 0):.3f}|{e:.3f} {f:.3f}" for a, b, c, d, e, f in bx]
    # volume: union of the boxes (the stop overlaps the rails' slot strip; lips overlap bodies at z)
    import numpy as np

    st = 0.05
    xs_ = np.arange(min(b[0] for b in bx) + st / 2, max(b[1] for b in bx), st)
    ys_ = np.arange(min(b[2] for b in bx) + st / 2, yw, st)
    zs_ = np.arange(min(b[4] for b in bx) + st / 2, max(b[5] for b in bx), st)
    Y, Z = np.meshgrid(ys_, zs_, indexing="ij")
    area = 0.0
    m_all = np.zeros(Y.shape, bool)
    # rails are prismatic in x except the stop: integrate per x slab
    vol = 0.0
    for x in xs_:
        m = np.zeros(Y.shape, bool)
        for a, b, c, d, e, f in bx:
            if a <= x <= b:
                m |= (Y >= c) & (Y <= d) & (Z >= e) & (Z <= f)
        vol += m.sum() * st**3
    del area, m_all
    return lines, float(vol)


def pam8302_lines(path: str) -> list[str]:
    """PAM8302A envelope (interference only, chassis frame): PCB in the rails, a 2.0 parts
    layer 1.2 off the long edges, the 2-pos 3.5 mm terminal block at the front end (7.6 x 7 x
    10 tall) and the 5-pin header at the rear end (2.5 x 12.7 x 8.5). TBD: measure the board."""
    g = amp_geom()
    (x0, x1), (zb, zt), (yp0, yp1) = g["x"], g["z"], g["y_pcb"]
    zc = (zb + zt) / 2
    bx = [
        (x0, x1, yp0, yp1, zb, zt),
        (x0 + 3.2, x1 - 7.8, yp0 - 2.0, yp0 + 0.05, zb + 1.2, zt - 1.2),
        (x1 - 7.6, x1, yp0 - 10.0, yp0 + 0.05, zc - 3.5, zc + 3.5),
        (x0 + 0.5, x0 + 3.0, yp0 - 8.5, yp0 + 0.05, zc - 6.35, zc + 6.35),
    ]
    v = (x1 - x0) * (zt - zb) * AMP_PCB[2] + (x1 - 7.8 - x0 - 3.2) * 2.0 * (zt - zb - 2.4) + 7.6 * 10.0 * 7.0 + 2.5 * 8.5 * 12.7
    return [
        f"part|{path}",
        *[f"box|{a:.3f} {b:.3f}|{c:.3f} {d:.3f}|{e:.3f} {f:.3f}" for a, b, c, d, e, f in bx],
        f"expect|vol {v:.1f} {v * 0.02:.1f}|box {x0:.2f} {x1:.2f} {yp0 - 10:.2f} {yp1:.2f} {zb:.2f} {zt:.2f} 0.05",
        "save",
    ]


def canopy_lines(path: str) -> list[str]:
    f = canopy_features()
    p = f["p"]
    a, b, c, d, e, fp = p
    rr, rh, rt = CAN_R
    hw = CAN_HW
    o = f["out"]
    xcr, zcr, rcr = canopy_crown()
    xpl, zpl, rpl, _ = hump_plateau()
    chain = hump_chain()
    (cf0, cf1), (pf0, pf1) = f["root_faces"]  # inner crown face, inner roof face (x spans)
    xr_in = canopy_rear_seam()  # -77.45: tangent seam into the rear inner round
    yr_in = (
        CAN_HW - CAN_T - (CAN_R[2] - CAN_T)
    )  # 45: tangent seams into the side rounds

    def seam_skip(x0, x1, z0, z1, y0=-CAN_HW - 1, y1=CAN_HW + 1):
        return f"{x0:.3f} {y0:.3f} {z0:.3f} {x1:.3f} {y1:.3f} {z1:.3f}"

    prismy = _prism_y

    def tol(v, k=0.2):
        return f"{v:.1f} {abs(v) * k + 5:.1f}"

    # front opening: a slab round the front wall in the wall's own frame (P6m3: at the seam)
    xsm = BH_XF - CAP_D - CAP_GAP
    x0p, x1p = xsm - CAN_T - 0.5, xsm + 0.5
    zw = BH_H + CAN_LUG_GAP
    hx, _ = f["lug_hole"]
    bx, by, bh = CAN_BOSS
    lines = [
        f"part|{path}",
        prismy([a, b, *chain_entries(chain), e, fp], -hw, hw, "boss"),
        # plan corners at the rear (vertical edges)
        f"fillet|{rr}|z|{a[0] - 0.1} {-hw - 0.1} {a[1]} {a[0] + 0.1} {hw + 0.1} {b[1]}|2|{tol(o['rear'], 0.05)}",
        # P6m3 top: ONE r 8 round on every edge of the top, picked by box (curve mode): the rear
        # edge, the two plan arcs, both side edges of each chain segment (crown, ramp rounds,
        # ramp, hump roof, slope), edge D and the hood ceiling's side edges to the seam. (P6m2
        # propagated from the crown face instead and the hood's side rounds died out before the
        # seam: a square cowl corner against the cap's r 8.)
        f"fillet|{rt}|vmid|{';'.join(canopy_top_round_boxes())}|{len(canopy_top_round_boxes())}|{tol(o['top'] + o['hood'])}",
        f"shell|{CAN_T}|z:-1|{CAN_Z0}|{a[0] - 1} {-hw - 1} {fp[0] + 1} {hw + 1}|1|{-f['v_in']:.1f} {0.04 * (f['v_out'] - f['v_in']):.1f}",
        *front_cut_lines(x0p, x1p, zw),
        *hood_screw()["lines"],
        *[
            prismy(canopy_rib_profile(), y0, y1, "boss")
            for _, _, y0, y1 in canopy_ribs()[: len(CAN_RIBS_Y)]
        ],
        *[
            prismy(canopy_cross_rib_profile(x0, x1), y0, y1, "boss")
            for x0, x1, y0, y1 in canopy_ribs()[len(CAN_RIBS_Y) :]
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
        # face of the grid, outer loops) on the two faces that carry the grid: the crown and
        # the hump roof (P6m2). Not their tangent seams (rear round, ramp rounds, side rounds).
        f"filletface|{CAN_ROOT_R}|cyl|{rcr - CAN_T:.4f}|{CAN_X0} {-CAN_HW} {cf1 + 1:.3f} {CAN_HW}|any"
        f"|{f['roots_crown']:.1f} {0.3 * f['roots_crown'] + 2:.1f}"
        f"|skip:{seam_skip(CAN_X0 - 1, xr_in + 0.4, 80, 100)}"
        f";{seam_skip(cf1 - 0.4, cf1 + 1, 80, 100)}"
        f";{seam_skip(CAN_X0 - 1, cf1 + 1, 80, 100, yr_in - 0.4, CAN_HW + 1)}"
        f";{seam_skip(CAN_X0 - 1, cf1 + 1, 80, 100, -CAN_HW - 1, -yr_in + 0.4)}",
        f"filletface|{CAN_ROOT_R}|cyl|{rpl - CAN_T:.4f}|{pf0 - 1:.3f} {-CAN_HW} {pf1 + 1:.3f} {CAN_HW}|any"
        f"|{f['roots_roof']:.1f} {0.3 * f['roots_roof'] + 2:.1f}"
        f"|skip:{seam_skip(pf0 - 1, pf0 + 0.4, 100, 115)}"
        f";{seam_skip(CAN_RIBS_X[-1] + CAN_RIB[0] / 2 + 0.6, pf1 + 1, 100, 115)}"
        f";{seam_skip(pf0 - 1, pf1 + 1, 100, 115, yr_in - 0.4, CAN_HW + 1)}"
        f";{seam_skip(pf0 - 1, pf1 + 1, 100, 115, -CAN_HW - 1, -yr_in + 0.4)}",
        *[
            ln
            for sg in (-1, 1)
            for ln in (
                f"box|{CAN_TAB[0][0]} {CAN_TAB[0][1]}|{min(sg * (CAN_HW - CAN_T), sg * CAN_HW)} {max(sg * (CAN_HW - CAN_T), sg * CAN_HW)}|0 {CAN_Z0}",
                f"box|{CAN_TAB[1][0]} {CAN_TAB[1][1]}|{min(sg * (CAN_HW - CAN_T), sg * CAN_HW)} {max(sg * (CAN_HW - CAN_T), sg * CAN_HW)}|{-CAN_TAB[2]} 0",
            )
        ],
        f"prof|0 {CAN_Z0}|{canopy_rear_wall()['prof']}",
        *[f"cyl|z|{bx} {sg * by}|0 {bh}|{INS_BOSS / 2}|boss" for sg in (-1, 1)],
        *[
            f"cyl|z|{bx} {sg * by}|-0.1 {INS_DEPTH}|{INS_HOLE_PC / 2}|cut"
            for sg in (-1, 1)
        ],
        f"filletface|{CAN_EDGE_R}|z:-1|{CAN_Z0}|{CAN_X0 - 1} {-hw - 1} {fp[0] + 1} {hw + 1}|any"
        f"|{-f['rim']:.2f} {0.25 * f['rim']:.2f}|skip:"
        + ";".join(canopy_rim_round()[1]),
        *canopy_vents()[0],
        *canopy_rear_edges()[1],
        *canopy_mic_lines()[0],
        *canopy_seam()["lines"],
        *canopy_amp_lines()[0],
        PART_LABELS["canopy"],
        f"expect|vol {f['vol'] + hood_screw()['vol'] + canopy_mic_lines()[1] + canopy_seam()['vol'] + canopy_amp_lines()[1]:.1f} {f['vol'] * 0.03:.1f}|box {CAN_X0} {fp[0]:.2f} {-hw} {hw} {-CAN_TAB[2]} {e[1]:.2f} 0.5",
        "save",
    ]
    return lines


# S8 (P6c, heel; was "S7" in BACKLOG): analysis-only copy of the canopy with a Ø30 x 0.5 heel pad on the flat top at
# the middle of its unsupported span, so the study can load exactly that patch (split
# lines don't work through the API, tick 12). Not printed.
CAN_HEEL = (
    -29.0,
    7.5,
    15.0,
    0.5,
)  # x, y, r, pad height. P6m2: on the hump roof, centred on a rib cell (-40..-18, 0..15)


def canopy_heel() -> tuple[float, float, float]:
    """S8 pad on the crowned top: (bottom z, flat top z, volume added above the skin).
    Bottom 0.1 under the lowest skin point it covers; top hh over the highest."""
    hx, _, hr, hh = CAN_HEEL
    zs = [canopy_top_z(hx + hr * k / 20) for k in range(-20, 21)]
    z0, z1 = min(zs) - 0.1, max(zs) + hh
    n, add = 60, 0.0
    for i in range(n):
        for j in range(n):
            u, v = -hr + (i + 0.5) * 2 * hr / n, -hr + (j + 0.5) * 2 * hr / n
            if u * u + v * v <= hr * hr:
                add += (z1 - canopy_top_z(hx + u)) * (2 * hr / n) ** 2
    return z0, z1, add


def canopy_fea_lines(path: str) -> list[str]:
    body = [ln for ln in canopy_lines(path) if not ln.startswith("text|")]  # R3 labels: not in FEA
    assert body[-1] == "save" and body[-2].startswith("expect|vol ")
    hx, hy, hr, hh = CAN_HEEL
    z0, z1, pad = canopy_heel()
    vol = canopy_features()["vol"] + pad + hood_screw()["vol"] + canopy_mic_lines()[1] + canopy_seam()["vol"]
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
    3.6,  # tick 91c experiment: 2.4 -> 3.6 against the road axles' twist (S9)
    14.0,
)  # off the wheel faces, thickness, height (bar stadium)
# S2b (Q22 F2, tick 66): the bar grows into a SIDE PLATE over the belt loop's window, so a
# finger can't reach the lug <-> pocket nips: rounded rectangle round both axles, z
# TF_PLATE_Z (8 over the ground line, ~3-4 mm diagonally to the runs' lug tips), corners
# r 8 (E1). 3.6 -> 2.4 thick (a 48-tall plate is far stiffer in tension than the bar).
TF_PLATE_Z, TF_PLATE_R = (-10.0, 38.0), 8.0
TF_SLOT = (dt.TRAVEL, 3.4)  # +- travel round the taut station, M3 clearance
TF_BOSS = (5.0, 0.0)  # dowel boss r, height outboard. 3 -> 0 (Ben 2026-11-08): the frames print
# outer face down and stood on this boss, floating the whole face 3 mm (all of it supported)
TF_DOWEL = 3.95  # Ø4 h8 dowel press hole (07 press fits: tune on the coupon)
TF_DOWEL_SKIN = 0.8  # blind from the inboard face: the dowel presses in from inboard and can't
# walk out outboard; press grip TF_T - skin = 2.8 (was 6.6 through frame + boss)


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
        - math.pi * (TF_DOWEL / 2) ** 2 * (TF_T + bh - TF_DOWEL_SKIN)
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


# P13c (tick 91, Q24 (a) Ben 2026-11-02): the track frame carries the road-wheel axles.
# Per axle: an r 5 boss extends the side plate below its z -10 edge round a Ø4.1 bore; an
# arm runs inboard from the plate's inner face 1.0 over the outer disc's top; a 3 mm blade
# drops from it between the two discs (3.6 to each) into the lug row and carries the axle
# mid-span in a second Ø4.1 bore, its bottom 1.0 over the lug tips (z -13.4).
RA_BORE = 4.1
RA_BOSS_R = 5.0
RA_HALF_X = 5.0  # blade half-length along x (6 -> 5, tick 91c: the shelf's end touched the sprocket rim)
RA_T = 4.0  # blade thickness (tick 91b: 3 -> 4; 3.1 to each disc)
RA_ARM_T = 5.0  # the shelf joining both blades to the plate (tick 91b: S9 3 mm arms 22 MPa / 1.24 mm)
RA_GAP = 1.0  # arm over the disc top, blade over the lug tips


def road_axle_carrier(side: int) -> tuple[list[str], float, tuple[float, float]]:
    """Lines (Top-plane / Front-plane features in chassis coordinates), the volume added,
    and the |y| span (signed) the carrier reaches. Placed after the slot cut and before the
    outer-face round, so the boss joins the plate's outline."""
    g = trackframe_geom()
    y0, y1 = g["y"]
    s = 1 if side > 0 else -1
    zr = dt.wheels()[1][2]  # road axle z (-8.40)
    disc_top = zr + dt.RW_R
    lug_tip = zr - dt.RW_R + dt.LUG_H
    yc = (track_y()[0] + track_y()[1]) / 2  # belt centre = the lug row (74.5)
    ba, bb = yc - RA_T / 2, yc + RA_T / 2  # blade |y|
    za0, za1 = disc_top + RA_GAP, disc_top + RA_GAP + RA_ARM_T  # shelf z
    zb0 = lug_tip + RA_GAP  # blade bottom
    lines, vol = [], 0.0
    zp0 = TF_PLATE_Z[0]
    d = zp0 - zr  # plate bottom below the axle centre (negative)
    seg = RA_BOSS_R**2 * math.acos(-d / RA_BOSS_R) + d * math.sqrt(RA_BOSS_R**2 - d * d)
    def Y(a, b):
        return (a, b) if s > 0 else (-b, -a)

    xr1, xr2 = dt.wheels()[1][1], dt.wheels()[2][1]
    sx0, sx1 = xr1 - RA_HALF_X, xr2 + RA_HALF_X
    a0, a1 = Y(bb, y0 + 0.01)
    # one shelf over both outer discs, both blades hang from it (tick 91b)
    lines.append(f"box|{sx0:.3f} {sx1:.3f}|{a0:.2f} {a1:.2f}|{za0:.3f} {za1:.3f}")
    vol += (sx1 - sx0) * (y0 - bb) * RA_ARM_T
    for x in (xr1, xr2):
        p0, p1 = Y(y0, y1)
        lines.append(f"cyl|y|{x:.3f} {zr:.3f}|{p0:.2f} {p1:.2f}|{RA_BOSS_R}|boss")
        b0, b1 = Y(ba, bb)
        lines.append(f"box|{x - RA_HALF_X:.3f} {x + RA_HALF_X:.3f}|{b0:.2f} {b1:.2f}|{zb0:.3f} {za1:.3f}")
        c0, c1 = Y(ba - 0.1, y1 + 0.1)
        lines.append(f"cyl|y|{x:.3f} {zr:.3f}|{c0:.2f} {c1:.2f}|{RA_BORE / 2}|cut")
        vol += seg * TF_T  # boss below the plate edge
        vol += 2 * RA_HALF_X * RA_T * (za1 - zb0)  # blade (its top overlaps the shelf's end)
        vol -= math.pi * (RA_BORE / 2) ** 2 * (TF_T + RA_T)
    return lines, vol, (s * ba, s * y1)


RA_BOSS_Z = (dt.wheels()[1][2] - 5.0, 0.0)  # frame z bottom with the bosses (box check)


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
    da, db = ys(y0 - 0.1, y1 + bh - TF_DOWEL_SKIN)  # blind: TF_DOWEL_SKIN left outboard
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
        *([f"cyl|y|{xs} {z}|{ba} {bb}|{br}|boss"] if bh > 0 else []),
        f"cyl|y|{xs} {z}|{da} {db}|{TF_DOWEL / 2}|cut",
        f"prof|{ya - 0.1} {yb + 0.1}|{stadium(xi - tr, xi + tr, sw / 2)}|cut|top",
        *road_axle_carrier(side)[0],
        f"filletface|1.0|y:{s}|{s * y1:.2f}|{xa - r - 1} {zb - 1} {xs + r + 1} {zt + 1}|1|{-dvo:.2f} {0.15 * dvo:.2f}",
        trackframe_label(side),
        f"expect|vol {vol - dvo + road_axle_carrier(side)[1]:.1f} {vol * 0.01:.1f}|box {xa - r:.2f} {xs + r:.2f} "
        f"{min(ya, ba, *road_axle_carrier(side)[2]):.2f} {max(yb, bb, *road_axle_carrier(side)[2]):.2f} "
        f"{RA_BOSS_Z[0]:.2f} {TF_PLATE_Z[1]:.2f} 0.05",
        "save",
    ]


# ------------------------------------------------------------------- hardware (07 §4.4)
# 2026-11-10 (Ben): every bought fastener / bearing / pin in the assembly. Envelopes come from
# tools/hardware.py (drawn at the engaged thread / pocket Ø, so a clean interference check
# means the joint is right). Seats and axes are the code's own geometry (07 vs code audit,
# 2026-11-10: code wins). Each entry: (joint, item, [(seat, axis toward the head/out)], frame)
# where frame is "ch" (chassis) or "pre" (bulkhead pre-tilt, placed with speaker_tilt()).
def hardware_layout() -> list[tuple[str, "hw.Item", list, str]]:
    I3 = hw.insert(3.0, 5.7, INS_HOLE_PC)  # Ø4.0: fits the 4.1 (PET-CF) and 4.0 (PC) pockets
    I25 = hw.insert(2.5, 4.0, 3.6)
    UP, DN = (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)
    out: list = []

    def add(joint: str, item, seats: list, frame: str = "ch") -> None:
        out.append((joint, item, seats, frame))

    # F1: plate -> bulkhead foot, low head up from the belly into the foot's inserts; + knee
    belly = PLATE_BOTTOM if not BOTTOM_RIBS else -PLATE_T
    f1 = [(BULK_X, y) for y in BULK_HOLES_Y]
    add("F1", hw.screw("lowhead", 3.0, 10.0), [((x, y, belly), DN) for x, y in f1])
    add("F1 knee", hw.screw("lowhead", 3.0, 10.0), [((*BH_KNEE_HOLE, belly + 2.0), DN)])  # in its 2.0 counterbore
    add("F1", I3, [((x, y, 0.0), UP) for x, y in [*f1, BH_KNEE_HOLE]])
    # F2: motor mount -> plate, SHCS + washer down from the foot top, inserts flush from the top
    mh = mount_holes()
    add("F2", hw.screw("shcs", 3.0, 8.0), [((x, y, 3.5), UP) for x, y in mh])
    add("F2", hw.ring_part("hw_washer_M3", "Washer ISO 7089 M3 (3.2 x 7 x 0.5, A2)", 7.0, 3.2, 0.5), [((x, y, 3.0), UP) for x, y in mh])
    add("F2", I3, [((x, y, -5.7), UP) for x, y in mh])
    # F3: TT motor -> mount, M3 x 28 through the gearbox, head on its outer face at |y| 55
    f3 = [(32.9, s, z) for s in (1, -1) for z in (13.5 - MOT_HOLE_PITCH / 2, 13.5 + MOT_HOLE_PITCH / 2)]
    add("F3", hw.screw("shcs", 3.0, 28.0), [((x, s * 55.0, z), (0.0, s, 0.0)) for x, s, z in f3])
    add("F3", I3, [((x, s * 26.7, z), (0.0, s, 0.0)) for x, s, z in f3])
    # F4: idler axle (05, 2026-11-09 stack): shoulder bolt, head inboard on the pedestal
    xf, iz = dt.belt_fit()["x_fit"], idler_z()
    sb = hw.Item(
        "hw_shoulder_4x53.5_M3",
        "Shoulder bolt ISO 7379 Ø4 x 53.5, M3 thread (head Ø8 x 4)",
        (
            "cyl|z|0 0|0 4|4|boss",
            "cyl|z|0 0|-53.5 0.01|1.99|boss",
            "cyl|z|0 0|-61.5 -53.49|1.5|boss",
            f"expect|vol {math.pi * (16 * 4 + 1.99**2 * 53.5 + 2.25 * 8):.1f} 2|box -4 4 -4 4 -61.5 4 0.05",
        ),
        0.0,
    )
    add("F4 axle", sb, [((xf, s * CAR_PED[1], iz), (0.0, -s, 0.0)) for s in (1, -1)])
    add("F4 axle", hw.ring_part("hw_nyloc_M3", "Nyloc nut DIN 985 M3 (envelope Ø6 x 4)", 6.0, 3.02, 4.0),
        [((xf, s * 97.1, iz), (0.0, s, 0.0)) for s in (1, -1)])
    shim = hw.ring_part("hw_shim_4x8x0.5", "Shim ring DIN 988 4 x 8 x 0.5", 8.0, 4.02, 0.5)
    add("F4 axle", shim, [((xf, s * y0, iz), (0.0, s, 0.0)) for s in (1, -1) for y0 in (69.0, 92.5, 93.0)])
    b624 = hw.bearing("624", 4.0, 13.0, 5.0)
    add("Idler", b624, [((xf, s * y0, iz), (0.0, s, 0.0)) for s in (1, -1) for y0 in (69.5, 87.5)])
    # F4 clamp: M3 x 12 up from the belly into the insert pressed up into the carriage foot
    add("F4 clamp", hw.screw("shcs", 3.0, 12.0), [((xf, s * CLAMP_Y, belly), DN) for s in (1, -1)])
    add("F4 clamp", I3, [((xf, s * CLAMP_Y, 0.0), UP) for s in (1, -1)])
    # F4b: tension jack, insert at the block's front end, tip on the carriage pad (x_fit + 10)
    add("F4b", hw.screw("shcs", 3.0, 30.0), [((xf + 10.0 + 30.0, s * JACK_Y, JACK_Z), (1.0, 0.0, 0.0)) for s in (1, -1)])
    add("F4b", I3, [((JACK_BLOCK_X[1] - 5.7, s * JACK_Y, JACK_Z), (1.0, 0.0, 0.0)) for s in (1, -1)])
    # Sprocket: 624 at the outboard face, Ø4 x 8 dowel from the frame plate, F15 clamp screw
    sx, sz = 52.7, 13.5
    add("Sprocket", b624, [((sx, s * 87.5, sz), (0.0, s, 0.0)) for s in (1, -1)])
    add("Sprocket pin", hw.pin("hw_dowel_4x8", "Dowel pin Ø4 h8 x 8, bearing steel (drawn Ø3.95)", 3.95, 8.0),
        [((sx, s * 88.3, sz), (0.0, s, 0.0)) for s in (1, -1)])
    add("F15", hw.screw("shcs", 2.5, 6.0), [((sx, s * 65.0, sz), (0.0, s, 0.0)) for s in (1, -1)])
    # Road wheels: one 684 per disc, on the belt edges
    yi, yo = track_y()
    add("Road wheel", hw.bearing("684", 4.0, 9.0, 4.0),
        [((x, s * y0, z), (0.0, s, 0.0)) for x, z in road_axles() for s in (1, -1) for y0 in (yi, yo - 4.0)])
    # F5: Pi deck -> plate posts
    add("F5", hw.screw("shcs", 3.0, 8.0), [((x, y, DECK_Z + DECK_T), UP) for x, y in DECK_POSTS])
    add("F5", I3, [((x, y, DECK_Z - 5.7), UP) for x, y in DECK_POSTS])
    # F6: Pi stack -> deck, up through the deck into the stack's brass standoffs (in its envelope)
    add("F6", hw.screw("shcs", 2.5, 6.0), [((x, y, DECK_Z), DN) for x, y in pi_holes_chassis()])
    # F7: reflex board -> plate standoffs
    rx, ry, rz = REFLEX_AT
    rh = [(rx + dx, ry + dy) for dx, dy in corners(*REFLEX_HOLES)]  # follows board_outline.py
    add("F7", hw.screw("shcs", 3.0, 8.0), [((x, y, REFLEX_STANDOFF + 1.6), UP) for x, y in rh])
    add("F7", I3, [((x, y, REFLEX_STANDOFF - 5.7), UP) for x, y in rh])
    # F8: XVF core board -> deck wall (tick 99): M2.5 x 6 into M2.5 x 4 inserts
    add("F8", hw.screw("shcs", 2.5, 6.0), [((x, -40.2, z), (0.0, -1.0, 0.0)) for x, z in core_standoffs()])
    add("F8", I25, [((x, -38.7, z), (0.0, 1.0, 0.0)) for x, z in core_standoffs()])
    # F9 front: flanged button down through the hood into the bulkhead lugs (pre-tilt)
    lx = bh_lug_x()
    add("F9 front", hw.screw("flanged", 3.0, 8.0), [((lx, s * BH_LUG_Y, 130.1), UP) for s in (1, -1)], "pre")
    add("F9 front", I3, [((lx, s * BH_LUG_Y, 128.0 - 5.7), UP) for s in (1, -1)], "pre")
    # F9 rear: button head up from the belly into the canopy apron bosses
    cbx, cby, _ = CAN_BOSS
    add("F9 rear", hw.screw("button", 3.0, 12.0), [((cbx, s * cby, belly), DN) for s in (1, -1)])
    add("F9 rear", I3, [((cbx, s * cby, 0.0), UP) for s in (1, -1)])
    # F10: mic disc, M2.5 x 8 up through washer / disc / washer into the hump's inserts
    mh_ = mic_geom()["holes"]
    add("F10", hw.screw("shcs", 2.5, 8.0), [((x, y, MIC_PLANE - 3.5), DN) for x, y in mh_])
    add("F10", I25, [((x, y, MIC_PLANE), UP) for x, y in mh_])
    # F11: face board -> bulkhead standoffs (pre-tilt): M3 x 6 (the 6.0 pocket bottoms an x 8)
    fh = [(y, z) for y in (42.08, -35.92) for z in (56.0, 98.0)]
    add("F11", hw.screw("shcs", 3.0, 6.0), [((76.1, y, z), (-1.0, 0.0, 0.0)) for y, z in fh], "pre")
    add("F11", I3, [((77.7, y, z), (1.0, 0.0, 0.0)) for y, z in fh], "pre")
    # F12: speaker clamp, M3 x 8 into the boss inserts (pre-tilt)
    xb = BH_XF - BH_T - SPK_DEPTH
    add("F12", hw.screw("shcs", 3.0, 8.0), [((xb - SPK_CLAMP_T, y, SPK_BOSS_Z), (-1.0, 0.0, 0.0)) for y in SPK_BOSS_Y], "pre")
    add("F12", I3, [((xb, y, SPK_BOSS_Z), (1.0, 0.0, 0.0)) for y in SPK_BOSS_Y], "pre")
    # F16: camera, M2 x 5 thread-forming into the bosses' Ø1.7 pilots (pre-tilt)
    cy_, cz_, _ = BH_CAM
    add("F16", hw.screw("pan", 2.0, 5.0, CAM_PILOT_R * 2, tf=True),
        [((77.005, cy_ + dy, cz_ + dz), (-1.0, 0.0, 0.0)) for dy, dz in CAM_HOLES], "pre")
    # F17: HC-SR04 -> holder, M1.6 x 6 thread-forming (pre-tilt)
    add("F17", hw.screw("pan", 1.6, 6.0, SR_PILOT_R * 2, tf=True),
        [((SR_FRONT - 12.25 - 1.6 - 0.02, *sr_map(xh, zh)), (-1.0, 0.0, 0.0)) for xh, zh in SR_PCB_HOLES], "pre")
    # F18: sonar holder -> bulkhead, M2 x 8 pan thread-forming from the front (pre-tilt)
    add("F18", hw.screw("pan", 2.0, 8.0, SR_WALL_PILOT_R * 2, tf=True),
        [((SR_FRONT - SR_SCREW_CB_D, *sr_map(xh, SR_SCREW_ZH)), (1.0, 0.0, 0.0)) for xh in SR_SCREW_XH], "pre")
    return out


def hardware_items() -> dict[str, "hw.Item"]:
    return {it.name: it for _, it, _, _ in hardware_layout()}


def hardware_comps(lib: str) -> list[str]:
    lines, n = [], {}
    tilt = speaker_tilt()
    for joint, it, seats, frame in hardware_layout():
        for seat, axis in seats:
            pl = hw.place(seat, axis)
            if frame == "pre":
                pl = hw.compose(tilt, pl)
            k = n[it.name] = n.get(it.name, 0) + 1
            lines.append(f"comp|{it.name}_{k}|{lib}\\{it.name}.SLDPRT|{row(*pl)}")
    return lines


def hardware_bom() -> list[tuple[str, str, int]]:
    """(description, joints, qty per robot) from the layout."""
    agg: dict[str, list] = {}
    for joint, it, seats, _ in hardware_layout():
        a = agg.setdefault(it.desc, [set(), 0])
        a[0].add(joint.split()[0])
        a[1] += len(seats)
    return sorted(((d, ", ".join(sorted(j)), q) for d, (j, q) in agg.items()), key=lambda r: r[0])


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
    "RB-PRT-060": "PET-CF",  # speaker clamp (P7)
    "RB-PRT-070": "PET-CF",  # HC-SR04 holder (split from the bulkhead 2026-11-09)
    "RB-PRT-061": "TPU",  # speaker gasket (P8)
    "RB-PRT-062": "TPU",  # mic-disc washers (P8, tick 98)
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
    "RB-PRT-023": "PET-CF",  # idler spacer x 2 (2026-11-09)
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


def cache_parts(lines: list[str], tool: str, full: bool) -> tuple[list[str], dict]:
    """Part cache (tick 88: SW rebuilds had slowed to > 1 h). Each `part|path` .. `save`
    block is hashed with swbuild.cs; a block whose hash matches the last successful build
    and whose file exists becomes `mass|path` (its MASS line for the totals), and its `stl`
    export is skipped. The assembly, interference and shots always run. Returns the new
    lines and the {path: hash} to record once the build reports BUILD OK."""
    import hashlib

    eng = open(os.path.join(sw.REPO, "tools", "swbuild.cs"), "rb").read()
    cpath = os.path.join(tool, "part_cache.json")
    old = {} if full or not os.path.exists(cpath) else json.load(open(cpath))
    out: list[str] = []
    new: dict = {}
    skipped: set = set()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("part|"):
            j = i
            while j < len(lines) and lines[j] != "save":
                j += 1
            block = lines[i : j + 1]
            path = ln.split("|", 1)[1]
            h = hashlib.sha1(eng + "\n".join(block).encode()).hexdigest()
            new[path] = h
            wsl = "/mnt/" + path[0].lower() + path[2:].replace("\\", "/")
            if old.get(path) == h and os.path.exists(wsl):
                out.append(f"mass|{path}")
                skipped.add(path)
            else:
                out += block
            i = j + 1
            continue
        if ln.startswith("stl|") and ln.split("|")[1] in skipped:
            i += 1
            continue
        out.append(ln)
        i += 1
    if skipped:
        print(f"part cache: {len(skipped)} unchanged part(s) not rebuilt")
    return out, new


def run(lines: list[str], dry: bool, full: bool = False) -> None:
    stage = sw.staging()
    tool = os.path.join(stage, "tools")
    os.makedirs(tool, exist_ok=True)
    os.makedirs(os.path.join(stage, "shots"), exist_ok=True)
    mass_lines = lines
    lines, hashes = cache_parts(lines, tool, full or dry)
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
    mass_report(mass_lines, out)
    if not any(x.strip() == "BUILD OK" for x in out.splitlines()):
        sys.exit("swbuild did not report BUILD OK")
    with open(os.path.join(tool, "part_cache.json"), "w") as fh:
        json.dump(hashes, fh, indent=0)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("what", choices=["rebuild", "hwbom"], help="hwbom: print the bought-hardware bill (markdown)")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("--full", action="store_true", help="rebuild every part (ignore the part cache)")
    a = ap.parse_args()
    win = sw.winpath(sw.staging())
    if a.what == "hwbom":
        print("| Qty | Item | Joints |\n|---:|---|---|")
        for d, j, q in hardware_bom():
            print(f"| {q} | {d} | {j} |")
        return
    if a.what == "rebuild":
        run(rebuild_manifest(win), a.dry_run, a.full)


if __name__ == "__main__":
    main()
