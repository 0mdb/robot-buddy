#!/usr/bin/env python3
"""Printed TPU track system for robot-buddy: belt, drive sprocket, idler (R&D).

Standalone: numpy (+ matplotlib for the preview), no SOLIDWORKS. The track,
sprocket and idler are designed as one system, not to the kit track.
Spec and rationale: docs/cad/08_tpu_track_rnd.md.

    python3 tools/drivetrain.py report            # system numbers + sweep
    python3 tools/drivetrain.py build [-o DIR]    # STLs + preview PNG

Concept (centre-lug "positive drive", as on rubber tracks of compact track
loaders): a TPU belt with one row of inward drive/guide lugs on the centre line
and a tread outside (staggered pads; bars and smooth as variants). Two road
wheels per side carry the bottom run; the sprocket rides RAISE off the floor. Sprocket and idler are the same toothed wheel: two
running discs carry the belt, a centre band with pockets takes the lugs, and the
pocket walls guide the belt sideways, so no flanges. The sprocket's hub is a
D-bore on the TT shaft; the idler's hub is two 624 bearings on the Ø4 shoulder
axle (05 spec).

Part frames: Z = wheel/belt axis, Z = 0 on the face that goes on the bed
(the wheels' outboard face). Chassis placement is in the doc (§5); nothing here
touches tools/chassis.py.
"""

from __future__ import annotations

import argparse
import math
import os
import struct
import sys

import numpy as np

# ------------------------------------------------------------ system (08 §3)
PITCH = 10.0  # lug pitch on the belt's neutral axis
N_TEETH = 18  # pockets per wheel; with PITCH sets the wheel size (08 §3: clearance)
T_BASE = 2.5  # belt base thickness
R_RUN = (
    N_TEETH * PITCH / (2 * math.pi) - T_BASE / 2
)  # wheel running radius (belt inner face)
BELT_W = 36.0  # belt width (kit 44.2)
LUG_W = 9.0  # lug width across the belt, at its root
LUG_CHAMFER = (
    2.0  # 45° chamfer on each lug end: the lug's lower end is a 2 mm ledge, not 4
)
LUG_H = 4.0  # lug height (inward)
LUG_L, LUG_TIP_L = 5.0, 3.0  # lug length along the belt at root / tip
GROUSER_H, GROUSER_L = 1.5, 3.0  # tread bar, one per lug, outside face
CLR = 0.6  # lug-to-pocket clearance, all round (TPU stretch, FDM)
TOOTH_DROP = 0.6  # tooth tops sit this far below R_RUN so the discs carry the belt
RIM_T = 2.4  # rim wall under the running discs (4 perimeters at 0.6)
BAND_WALL = 2.4  # wall under the pocket floors

# outside of the belt (08 §5): pads = mostly-smooth contact, shallow cross grooves,
# split at the centre line with the halves staggered, groove spacing jittered so the
# tread doesn't sing at one pitch. "bars" (GROUSER_*) is the control, "smooth" the other.
TREAD = "bars_stagger"  # Ben 2026-11-01: lugged (carpet), staggered halves (quieter)
PAD_H = 1.0  # pad height over the base
GROOVE_L = 3.0  # groove length along the belt
PAD_JITTER = 0.15  # ± fraction of the groove spacing, fixed seed
SPLIT_W = 1.0  # centre split between the staggered halves
EDGE_CH = 1.2  # 45° chamfer on both outer belt edges (bed side prints, fingers)

# suspension (08 §4b): the idler sits RAISE below the TT shaft so the sprocket rides
# clear of the floor (approach ramp, ride height); two road wheels per side carry the
# bottom run, ROCKER below the idler line so pivot turns load them, not the idler.
RAISE = 3.0
ROCKER = 0.5
RW_R = 9.0  # road wheel running radius: two discs straddle the lug row on one axle; lug tips
# pass 5 mm off the axle, room for a Ø7 spacer between the discs
RW_GAP = 2.5  # road wheel to sprocket running surfaces (inside the loop)
RW_BRG_D, RW_BRG_W = 9.1, 4.0  # 684 (4 x 9 x 4) slip pocket
RW_SHOULDER_R = 3.7  # bears on the 684 outer race only

# chassis numbers this depends on (06 §4, 05; read-only here)
X_DRIVE = 52.7  # TT shaft station
X_IDLER = -60.0  # follower axle, mid travel (±5)
Z_AXLE = 13.5  # TT shaft above the plate top (motor mount v2)
PLATE_HALF_W = 55.0
SIDE_GAP = 1.5  # belt inner edge to the plate edge / gearbox face
PLATE_X = (-85.0, 85.0)
PLATE_UNDERSIDE_Z = -8.0  # lowest point under the plate (insert bosses, ribs)
PLATE_T_UNDER = 4.0  # plate thickness: its flat underside is at z -4

# hubs
TT_SHAFT_D, TT_FLAT = 5.4, 3.7  # TT output: Ø5.4 double-D, 3.7 across flats
BORE_CLR = 0.15  # per side: TT bore ladder, 3 notches (Ben 2026-11-08, PET-CF)
TT_ENGAGE = 8.0  # TBD: shaft length into the hub (measure; drawing ~9)
TUBE_R = 7.5  # sprocket hub tube
BRG_D, BRG_W = 13.1, 5.0  # 624 slip pocket (05)
BRG_SHOULDER_R = 5.0  # bears on the outer race only (624 outer race ID ~10.3)
SCREW_R = 3.0  # M2 retaining screw + driver access along the axis

# material, loads
RHO_PETCF, RHO_TPU = 1.29, 1.22  # g/cm³ (07 / Bambu TDS)
# tensile modulus as printed, MPa [assumption, both on hand: 85A per print-bom, 95A from
# fpv250]; the strip test in 08 §7 replaces these
E_TPU = {"85A": (10.0, 25.0), "95A": (25.0, 60.0)}
TENSION = (
    10.0  # N per track, design (positive drive needs less than the 20 N in fea.py)
)
TT_STALL = 0.25  # N·m, Yahboom 1:48 [assumption, 07 S2]
MASS_G = {  # name: (g, x, z), chassis frame; 07 §3.3 + metrics.csv + 06 §3
    "Pi stack + UPS + cells": (260, -10.0, 59.5),
    "TT motors x2": (100, 28.0, 13.5),
    "plate": (101, 0.0, -2.0),
    "motor mounts": (16, 45.0, 8.0),
    "bulkhead": (44, 80.0, 50.0),
    "Pi deck": (40, -10.0, 25.5),
    "canopy": (180, -5.0, 75.0),
    "face, audio, misc": (150, 75.0, 60.0),
}
G = 9.81


# ------------------------------------------------------------ derived geometry
def pitch_radius(n: int = N_TEETH) -> float:
    return n * PITCH / (2 * math.pi)  # belt neutral axis on the wheel


def pitch(n: int = N_TEETH) -> float:
    return PITCH


TRAVEL = 5.0  # follower travel either side of X_IDLER (06 §4: 10 mm)


def tread_h(tread: str = TREAD) -> float:
    return {"pads": PAD_H, "bars": GROUSER_H, "bars_stagger": GROUSER_H, "smooth": 0.0}[
        tread
    ]


def wheels(x_idler: float = X_IDLER, r_run: float = R_RUN) -> list[tuple]:
    """(name, x, z, running r) in belt order, counter-clockwise seen from the left:
    bottom run rear → front, then over the top. Chassis frame (plate top = 0)."""
    z_idl = Z_AXLE - RAISE
    z_rw = z_idl - r_run - ROCKER + RW_R  # road wheel bottoms ROCKER under the idler's
    dz = Z_AXLE - z_rw
    x_rw2 = X_DRIVE - math.sqrt((r_run + RW_R + RW_GAP) ** 2 - dz**2)
    x_rw1 = (X_IDLER + x_rw2) / 2  # fixed to the chassis, split the bottom span
    return [
        ("idler", x_idler, z_idl, r_run),
        ("road1", x_rw1, z_rw, RW_R),
        ("road2", x_rw2, z_rw, RW_R),
        ("sprocket", X_DRIVE, Z_AXLE, r_run),
    ]


def belt_path(ws: list[tuple]) -> dict:
    """Belt neutral axis round convex wheels in order: length, tangent points, wraps."""
    c = [(w[1], w[2], w[3] + T_BASE / 2) for w in ws]
    n = len(c)
    phi_out, phi_in, segs = [0.0] * n, [0.0] * n, []
    length = 0.0
    for i in range(n):
        (x1, z1, r1), (x2, z2, r2) = c[i], c[(i + 1) % n]
        dl = math.hypot(x2 - x1, z2 - z1)
        th = math.atan2(z2 - z1, x2 - x1)
        phi = th - math.acos((r1 - r2) / dl)  # outward normal, right of travel
        phi_out[i], phi_in[(i + 1) % n] = phi, phi
        length += math.sqrt(dl**2 - (r1 - r2) ** 2)
        segs.append(
            (
                (x1 + r1 * math.cos(phi), z1 + r1 * math.sin(phi)),
                (x2 + r2 * math.cos(phi), z2 + r2 * math.sin(phi)),
            )
        )
    wrap = [(phi_out[i] - phi_in[i]) % (2 * math.pi) for i in range(n)]
    length += sum(c[i][2] * wrap[i] for i in range(n))
    return {"length": length, "segs": segs, "wrap": wrap, "phi_in": phi_in}


def _path_len(x_idler: float, r_run: float = R_RUN) -> float:
    return belt_path(wheels(x_idler, r_run))["length"]


def belt_fit(c_nom: float = X_DRIVE - X_IDLER, n: int = N_TEETH) -> dict:
    """Round the belt DOWN to whole lugs: a new belt fits forward of mid travel and
    leaves the rear travel for set-up tension and TPU creep."""
    r_run = pitch_radius(n) - T_BASE / 2
    links = math.floor(_path_len(X_DRIVE - c_nom, r_run) / PITCH)
    length = links * PITCH
    lo, hi = X_IDLER - 30.0, X_IDLER + 30.0  # path length falls as the idler moves fwd
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _path_len(mid, r_run) > length else (lo, mid)
    x_fit = (lo + hi) / 2  # idler station with the belt just taut
    return {
        "links": links,
        "length": length,
        "c_fit": X_DRIVE - x_fit,
        "x_fit": x_fit,
        "install_slack": length - _path_len(X_IDLER + TRAVEL, r_run),
        "creep_pct": 100 * (_path_len(X_IDLER - TRAVEL, r_run) / length - 1),
    }


def outer_r(tread: str = TREAD) -> float:
    return R_RUN + T_BASE + tread_h(tread)


# ------------------------------------------------------------ polar-stack mesher
# A part = Z layers; each layer = annuli (inner curve, outer curve); a curve = radii
# at M equal angles, shared by the whole part. Faces between layers come from the
# XOR of the radial intervals, so the mesh is closed if curves never cross.
def _pts(r: np.ndarray, z: float) -> np.ndarray:
    th = np.linspace(0, 2 * np.pi, len(r), endpoint=False)
    return np.stack([r * np.cos(th), r * np.sin(th), np.full_like(r, z)], 1)


def _ring(a: np.ndarray, b: np.ndarray, flip: bool) -> list[np.ndarray]:
    """Quads between point loops a, b (same length), as triangles."""
    a1, b1 = np.roll(a, -1, 0), np.roll(b, -1, 0)
    t1, t2 = np.stack([a, b, b1], 1), np.stack([a, b1, a1], 1)
    if flip:
        t1, t2 = t1[:, ::-1], t2[:, ::-1]
    return [t1, t2]


def mesh(
    layers: list[tuple[float, float, list[tuple[np.ndarray, np.ndarray]]]],
) -> np.ndarray:
    tris: list[np.ndarray] = []
    for z0, z1, ann in layers:
        for ri, ro in ann:
            tris += _ring(_pts(ro, z0), _pts(ro, z1), flip=True)  # outer wall, outward
            tris += _ring(_pts(ri, z0), _pts(ri, z1), flip=False)  # inner wall, inward
    zs = [layers[0][0]] + [lay[1] for lay in layers]
    for k, z in enumerate(zs):
        below = layers[k - 1][2] if k > 0 else []
        above = layers[k][2] if k < len(layers) else []
        curves: list[np.ndarray] = []
        for c in [c for a in below + above for c in a]:
            if not any(np.array_equal(c, d) for d in curves):
                curves.append(c)
        curves.sort(key=lambda c: float(c.mean()))
        for lo, hi in zip(curves, curves[1:]):
            mid = (lo + hi) / 2

            def inside(ann: list) -> bool:
                m = np.zeros_like(mid, bool)
                for ri, ro in ann:
                    m |= (mid >= ri) & (mid <= ro)
                return bool(m[np.argmax(hi - lo)])

            a, b = inside(below), inside(above)
            if (
                a != b
            ):  # top face of the solid below (+Z) or bottom of the one above (-Z)
                tris += _ring(_pts(lo, z), _pts(hi, z), flip=b)
    t = np.concatenate(tris)
    area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    return t[area > 1e-9]


def check(t: np.ndarray) -> tuple[bool, float]:
    """Closed + consistently wound (every directed edge has its reverse); volume mm³."""
    v = np.round(t, 6).reshape(-1, 3)
    _, idx = np.unique(v, axis=0, return_inverse=True)
    f = idx.reshape(-1, 3)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    fwd = set(map(tuple, e))
    ok = len(fwd) == len(e) and all((b, a) in fwd for a, b in fwd)
    vol = float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)
    return ok, vol


def write_stl(path: str, t: np.ndarray, name: str) -> None:
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, t
    with open(path, "wb") as fh:
        fh.write(name.encode()[:80].ljust(80, b" "))
        fh.write(struct.pack("<I", len(t)))
        fh.write(rec.tobytes())


# ------------------------------------------------------------ curves
def circle(r: float, m: int) -> np.ndarray:
    return np.full(m, float(r))


def _blend(
    u: np.ndarray, a_in: np.ndarray | float, a_out: np.ndarray | float
) -> np.ndarray:
    """1 inside |u| < a_in, 0 outside a_out, cosine between (rounded trapezoid)."""
    s = np.clip((np.abs(u) - a_in) / np.maximum(a_out - a_in, 1e-9), 0, 1)
    return 0.5 * (1 + np.cos(np.pi * s))


def _u(m: int, n: int) -> np.ndarray:
    th = np.linspace(0, 2 * np.pi, m, endpoint=False)
    return (th + np.pi / n) % (2 * np.pi / n) - np.pi / n  # angle from the nearest lug


def wheel_band(m: int, n: int = N_TEETH) -> np.ndarray:
    """Centre band: teeth at R_RUN - TOOTH_DROP, pockets for the lugs + CLR."""
    r_top, r_bot = R_RUN - TOOTH_DROP, R_RUN - LUG_H - CLR
    half_top = (LUG_L / 2 + CLR) / R_RUN
    half_bot = (LUG_TIP_L / 2 + CLR) / r_bot
    return r_top - (r_top - r_bot) * _blend(_u(m, n), half_bot, half_top)


def dbore(m: int, clr: float = BORE_CLR) -> np.ndarray:
    th = np.linspace(0, 2 * np.pi, m, endpoint=False)
    f = TT_FLAT / 2 + clr
    return np.minimum(TT_SHAFT_D / 2 + clr, f / np.maximum(np.abs(np.cos(th)), 1e-9))


def notched(r: float, m: int, k: int, depth: float = 0.8) -> np.ndarray:
    """Circle with k small notches: an ID mark on a coupon."""
    th = np.linspace(0, 2 * np.pi, m, endpoint=False)
    out = np.full(m, float(r))
    for j in range(k):
        d = np.angle(np.exp(1j * (th - j * 0.35)))
        out -= depth * _blend(d, 0.03, 0.08)
    return out


def crush(r: float, m: int, interf: float, ribs: int = 3) -> np.ndarray:
    """Bore with `ribs` crush ribs that stand `interf` proud of r."""
    th = np.linspace(0, 2 * np.pi, m, endpoint=False)
    d = np.angle(np.exp(1j * ribs * th)) / ribs
    return (
        r - (interf + 0.0) * _blend(d, 0.02, 0.12)
        if interf > 0
        else np.full(m, float(r))
    )


# ------------------------------------------------------------ parts
def _rim_layers(
    m: int, z_band: tuple[float, float]
) -> list[tuple[float, float, np.ndarray]]:
    """(z0, z1, outer curve) of the rim: disc / band / disc across BELT_W."""
    run = circle(R_RUN, m)
    b0, b1 = z_band
    return [(0.0, b0, run), (b0, b1, wheel_band(m)), (b1, BELT_W, run)]


def _wheel(
    m: int,
    hub: list[tuple[float, float, list[tuple[np.ndarray, np.ndarray]] | None]],
    web: tuple[float, np.ndarray],
) -> list:
    """Rim + hub tube; a web on the bed face (Z 0..web_t) joins them.

    hub: [(z0, z1, inner curve, tube outer r)] spans of the hub tube.
    """
    web_t, web_ri = web
    band = ((BELT_W - LUG_W) / 2 - CLR, (BELT_W + LUG_W) / 2 + CLR)
    rim = _rim_layers(m, band)
    cuts = sorted(
        {0.0, web_t, BELT_W, *band, *[h[0] for h in hub], *[h[1] for h in hub]}
    )
    # rim inner radius: RIM_T under the discs, deeper under the band; the step on the
    # bed side of the band is a 45° ramp (stepped) so it prints without support
    ri_disc, ri_band = R_RUN - RIM_T, R_RUN - LUG_H - CLR - BAND_WALL
    ramp = ri_disc - ri_band
    nr = max(1, round(ramp / 0.4))
    cuts = sorted(set(cuts) | {band[0] - ramp * (1 - j / nr) for j in range(nr)})

    def ri_rim(zm: float) -> np.ndarray:
        if band[0] <= zm < band[1]:
            return circle(ri_band, m)
        if band[0] - ramp <= zm < band[0]:
            j = math.floor((zm - (band[0] - ramp)) / (ramp / nr))
            return circle(ri_disc - (j + 0.5) * ramp / nr, m)
        return circle(ri_disc, m)

    layers = []
    for z0, z1 in zip(cuts, cuts[1:]):
        if z1 - z0 < 1e-9:
            continue
        zm = (z0 + z1) / 2
        ro = next(c for a, b, c in rim if a <= zm < b) if zm < BELT_W else None
        h = next((x for x in hub if x[0] <= zm < x[1]), None)
        ann = []
        if zm < web_t:
            ann.append((web_ri if h is None else h[2], ro))
        else:
            if h is not None:
                ann.append((h[2], circle(h[3], m)))
            if ro is not None:
                ann.append((ri_rim(zm), ro))
        layers.append((z0, z1, ann))
    return layers


def sprocket(outrigger: bool = True, m: int = N_TEETH * 48) -> np.ndarray:
    """Drive sprocket mesh; geometry in sprocket_layers()."""
    return mesh(sprocket_layers(outrigger, m))


def sprocket_layers(outrigger: bool = True, m: int = N_TEETH * 48) -> list:
    """Drive sprocket. Bed face = outboard. Inboard face (Z = BELT_W) sits SIDE_GAP off
    the gearbox; the D-bore takes the TT shaft from that end. With `outrigger`, a 624
    pocket on the outboard face takes the outboard support of Q4(a)/P2o."""
    pocket, shoulder = circle(BRG_D / 2, m), circle(BRG_SHOULDER_R, m)
    tube = circle(SCREW_R, m)
    web_t = 3.0
    hub = []
    if outrigger:
        hub += [(0.0, BRG_W, pocket, TUBE_R), (BRG_W, BRG_W + 1.5, shoulder, TUBE_R)]
        z = BRG_W + 1.5
    else:
        z = 0.0
    hub += [
        (z, BELT_W - TT_ENGAGE, tube, TUBE_R),
        (BELT_W - TT_ENGAGE, BELT_W, dbore(m), TUBE_R),
    ]
    # web: pocket (outrigger) or screw hole through it
    return _wheel(m, hub, (web_t, pocket if outrigger else tube))


def idler(bearings: int = 2, interf: float = 0.15, m: int = N_TEETH * 48) -> np.ndarray:
    """Idler mesh; geometry in idler_layers()."""
    return mesh(idler_layers(bearings, interf, m))


def idler_layers(
    bearings: int = 2, interf: float = 0.15, m: int = N_TEETH * 48
) -> list:
    """Idler: same rim as the sprocket, hub = 624 pocket(s) on the Ø4 shoulder axle.
    Bed face = outboard (axle head side). Two bearings span the tube so a single
    cantilevered bearing can't cock (05 tilt note); the carriage boss reaches into
    the open inboard side up to the tube."""
    pocket = crush(BRG_D / 2, m, interf)
    bore = circle(BRG_SHOULDER_R, m)
    tube_r = BRG_D / 2 + 3.0  # ≥ 3 mm wall round the bearing (05)
    tube_end = BELT_W / 2 + BRG_W  # inner bearing reaches past the belt centre plane
    hub = [(0.0, BRG_W, pocket, tube_r), (BRG_W, tube_end - BRG_W, bore, tube_r)]
    if bearings == 2:
        hub.append((tube_end - BRG_W, tube_end, pocket, tube_r))
    else:
        hub[-1] = (BRG_W, BRG_W + 1.5, bore, tube_r)
    return _wheel(m, hub, (3.0, pocket))


def _tread_curves(tread: str, m: int, links: int, r_out: float) -> tuple:
    """Outer curves (half A, half B) of the printed ring for a tread style."""
    u = _u(m, links)
    if tread == "smooth":
        c = circle(r_out, m)
        return c, c
    if tread == "bars":  # full width, one per lug (rev 0)
        c = r_out + GROUSER_H * _blend(
            u, (GROUSER_L / 2 - 0.5) / r_out, (GROUSER_L / 2 + 0.5) / r_out
        )
        return c, c
    th = np.linspace(0, 2 * np.pi, m, endpoint=False)
    rng = np.random.default_rng(7)  # fixed: every build gives the same belt
    k = np.arange(links) + rng.uniform(-PAD_JITTER, PAD_JITTER, links)
    if tread == "bars_stagger":  # GROUSER bars, split + staggered + jittered (Ben)
        a_in, a_out = (GROUSER_L / 2 - 0.5) / r_out, (GROUSER_L / 2 + 0.5) / r_out
    else:  # pads: raised everywhere but the grooves
        a_in, a_out = (GROOVE_L / 2 - 0.4) / r_out, (GROOVE_L / 2 + 0.4) / r_out

    def half(shift: float) -> np.ndarray:
        cen = 2 * np.pi * (k + shift) / links
        d = np.abs(np.angle(np.exp(1j * (th[:, None] - cen[None, :])))).min(1)
        if tread == "bars_stagger":
            return r_out + GROUSER_H * _blend(d, a_in, a_out)
        return r_out + PAD_H * (1 - _blend(d, a_in, a_out))

    return half(0.0), half(0.5)  # B staggered by half a groove spacing


def belt(
    n: int = N_TEETH, steps: int = 8, tread: str = TREAD
) -> tuple[np.ndarray, dict]:
    """Belt as printed: an upright ring (Z = belt width), lugs inward, tread outward.
    The lug ends get a 45° chamfer (LUG_CHAMFER) and the outer edges EDGE_CH, both
    built from thin steps, so the ring prints without support."""
    fit = belt_fit(n=n)
    links, length = fit["links"], fit["length"]
    m = links * 24
    r_pl = length / (2 * math.pi)
    r_in, r_out = r_pl - T_BASE / 2, r_pl + T_BASE / 2
    u = _u(m, links)
    out_a, out_b = _tread_curves(tread, m, links, r_out)
    split = np.minimum(out_a, out_b) if tread in ("pads", "bars_stagger") else out_a
    s0, s1 = (BELT_W - SPLIT_W) / 2, (BELT_W + SPLIT_W) / 2

    def lug(h: float) -> np.ndarray:
        if h <= 0:
            return circle(r_in, m)
        half_root = LUG_L / 2 / r_in
        half_tip = LUG_TIP_L / 2 / (r_in - LUG_H)
        return r_in - h * _blend(u, half_tip, half_root)

    l0, l1 = (BELT_W - LUG_W) / 2, (BELT_W + LUG_W) / 2
    full = LUG_H - LUG_CHAMFER
    dz, de = LUG_CHAMFER / steps, EDGE_CH / steps
    cuts = {0.0, BELT_W, l0, l1, s0, s1}
    cuts |= {l0 + i * dz for i in range(steps)} | {l1 - i * dz for i in range(steps)}
    cuts |= {i * de for i in range(steps)} | {BELT_W - i * de for i in range(steps)}
    cuts = sorted(cuts)

    def inner(zm: float) -> np.ndarray:
        if l0 <= zm < l0 + LUG_CHAMFER:  # lower chamfer: ledge, then 45°
            j = math.floor((zm - l0) / dz)
            return lug(full + (j + 0.5) * dz)
        if l1 - LUG_CHAMFER <= zm < l1:
            j = math.floor((l1 - zm) / dz)
            return lug(full + (j + 0.5) * dz)
        return lug(LUG_H) if l0 <= zm < l1 else circle(r_in, m)

    def outer(zm: float) -> np.ndarray:
        base = split if s0 <= zm < s1 else (out_a if zm < s0 else out_b)
        e = min(zm, BELT_W - zm)
        if e < EDGE_CH:
            j = math.floor(e / de)
            return base - (EDGE_CH - (j + 0.5) * de)
        return base

    layers = [
        (z0, z1, [(inner((z0 + z1) / 2), outer((z0 + z1) / 2))])
        for z0, z1 in zip(cuts, cuts[1:])
        if z1 - z0 > 1e-9
    ]
    return mesh(layers), {
        **fit,
        "ring_od": 2 * (r_out + tread_h(tread)),
        "tread": tread,
    }


def road_wheel_w() -> float:
    """Disc width: from the belt edge to CLR off the lug row."""
    return (BELT_W - LUG_W) / 2 - CLR


def road_wheel_layers(interf: float = 0.10, m: int = 360) -> list:
    """One road-wheel disc (two per axle, one each side of the lug row). Bed face =
    the 684 pocket side, flush with the belt edge; the Ø4 shoulder axle runs under the
    lugs between the discs."""
    return [
        (0.0, RW_BRG_W, [(crush(RW_BRG_D / 2, m, interf), circle(RW_R, m))]),
        (RW_BRG_W, road_wheel_w(), [(circle(RW_SHOULDER_R, m), circle(RW_R, m))]),
    ]


def road_wheel(interf: float = 0.10, m: int = 360) -> np.ndarray:
    return mesh(road_wheel_layers(interf, m))


def coupons() -> dict[str, np.ndarray]:
    """Cheap prints that settle the fits before a wheel (BACKLOG D6 pattern)."""
    m = 720
    out = {}
    # TT bore ladder: 4 rings, clearance 0.05..0.20 per side, k notches = rung k
    for k, c in enumerate((0.05, 0.10, 0.15, 0.20), 1):
        out[f"coupon_ttbore_{int(c * 100):02d}"] = mesh(
            [(0.0, TT_ENGAGE, [(dbore(m, c), notched(TUBE_R, m, k))])]
        )
    # 624 seat ladder: crush-rib interference 0.10..0.20 + the shoulder
    for k, i in enumerate((0.10, 0.15, 0.20), 1):
        out[f"coupon_624_{int(i * 100):02d}"] = mesh(
            [
                (0.0, 1.5, [(circle(BRG_SHOULDER_R, m), notched(BRG_D / 2 + 3, m, k))]),
                (
                    1.5,
                    1.5 + BRG_W,
                    [(crush(BRG_D / 2, m, i), notched(BRG_D / 2 + 3, m, k))],
                ),
            ]
        )
    # 684 seat (road wheels): one rung, the disc itself is cheap enough to iterate
    out["coupon_684_10"] = mesh(
        [
            (0.0, 1.5, [(circle(RW_SHOULDER_R, m), circle(RW_R, m))]),
            (1.5, 1.5 + RW_BRG_W, [(crush(RW_BRG_D / 2, m, 0.10), circle(RW_R, m))]),
        ]
    )
    # lug/pocket slice: 6 mm of sprocket band on a TT bore, to test-mesh a belt coupon
    mm = N_TEETH * 48
    out["coupon_band_slice"] = mesh([(0.0, 6.0, [(dbore(mm), wheel_band(mm))])])
    return out


# ------------------------------------------------------------ system analysis
_WG: list[float] = []


def _wheel_g() -> float:
    if not _WG:
        _WG.append(check(idler(2))[1] / 1000 * RHO_PETCF)
    return _WG[0]


def climb_max(
    r_front: float,
    gap_front: float,
    x_rear: float,
    xc: float,
    h: float,
    wt: float,
    mu: float,
) -> float:
    """Highest square step (mm) the front wheel can mount, quasi-static: edge force in
    its friction cone, rear contact pushing within its own, both motors at stall.
    Rigid parts, sharp edge: an upper bound to check on the step blocks (08 §7)."""
    try:
        from scipy.optimize import linprog
    except ImportError:
        return float("nan")
    zc = r_front + gap_front  # sprocket centre over the floor
    f_max = 2 * TT_STALL / (pitch_radius() / 1000)
    best = 0.0
    for hs in np.arange(0.5, zc, 0.5):
        phi = math.acos(min(1.0, (zc - hs) / r_front)) if hs > gap_front else 0.0
        n = (-math.sin(phi), math.cos(phi))
        t = (math.cos(phi), math.sin(phi))
        e = (X_DRIVE + r_front * math.sin(phi), hs)

        def mom(p, f):
            return (p[0] - xc) * f[1] - (p[1] - h) * f[0]

        a_eq = [
            [n[0], t[0], 0, 1],
            [n[1], t[1], 1, 0],
            [mom(e, n), mom(e, t), mom((x_rear, 0), (0, 1)), mom((x_rear, 0), (1, 0))],
        ]
        a_ub = [
            [-mu, 1, 0, 0],
            [0, 0, -mu, 1],
            [0, 1, 0, 1],
            [-1, 0, 0, 0],
            [0, 0, -1, 0],
        ]
        r = linprog(
            np.zeros(4),
            A_ub=a_ub,
            b_ub=[0, 0, f_max, 0, 0],
            A_eq=a_eq,
            b_eq=[0, wt, 0],
            bounds=[(None, None)] * 4,
        )
        if r.status == 0:
            best = float(hs)
    return best


def system(
    n: int = N_TEETH, w: float = BELT_W, extra_g: float = 0.0, tread: str = TREAD
) -> dict:
    rpl = pitch_radius(n)
    r_run = rpl - T_BASE / 2
    fit = belt_fit(n=n)
    ws = wheels(fit["x_fit"], r_run)
    path = belt_path(ws)
    (_, x_i, z_i, _), (_, x_r1, z_r, _), (_, x_r2, _, _), _ = ws
    th = tread_h(tread)
    z_ground = z_r - RW_R - T_BASE - th  # road wheels carry it (ROCKER)
    gap_front = (Z_AXLE - r_run) - (z_r - RW_R)  # sprocket's belt over the floor
    y_c = PLATE_HALF_W + SIDE_GAP + w / 2  # track centre line
    gauge = 2 * y_c
    # masses
    items = dict(MASS_G)
    belt_g = fit["length"] * w * (T_BASE + 0.25 * (th + LUG_H)) / 1000 * RHO_TPU
    wheel_g = _wheel_g() * (r_run / R_RUN) * (w / BELT_W)  # built idler, scaled
    rw_g = 4 * 2 * math.pi * RW_R**2 * ((w - LUG_W) / 2) / 1000 * RHO_PETCF * 0.85
    x_mid = (X_DRIVE + x_i) / 2
    items["belts x2"] = (2 * belt_g, x_mid, Z_AXLE - RAISE / 2)
    items["wheels x4"] = (4 * wheel_g + extra_g, x_mid, Z_AXLE - RAISE / 2)
    items["road wheels x8 discs"] = (rw_g, (x_r1 + x_r2) / 2, z_r)
    mtot = sum(v[0] for v in items.values())
    xc = sum(v[0] * v[1] for v in items.values()) / mtot
    zc = sum(v[0] * v[2] for v in items.values()) / mtot
    h = zc - z_ground
    wt = mtot / 1000 * G
    # skid-steer pivot: resisting moment of lateral friction over the loaded span;
    # the rocker loads the two road wheels, the full span is the worst case
    spans = {"rocker": x_r2 - x_r1, "full": x_r2 - x_i}
    res = {}
    for mu in (0.5, 0.9, 1.2):
        for name, span in spans.items():
            mres = mu * wt * (span / 1000) / 2
            res[f"mu{mu}_{name}"] = mres / (gauge / 1000) * (rpl / 1000)
    # bottom run: longest unsupported span, sag under half the weight per side
    s_max = max(x_r1 - x_i, x_r2 - x_r1)
    sag = (s_max / 2) * (wt / 2) / (2 * TENSION)
    r_o = r_run + T_BASE + th
    front = max(PLATE_X[1], X_DRIVE + r_o)
    rear = min(PLATE_X[0], x_i - r_o)
    half_w = y_c + w / 2
    sweep = max(math.hypot(x - xc, half_w) for x in (front, rear))
    return {
        "n": n,
        "w": w,
        "r_run": r_run,
        "pitch": PITCH,
        "wheels": ws,
        "path": path,
        "z_ground": z_ground,
        "clearance": PLATE_UNDERSIDE_Z - z_ground,
        "clearance_flat": -PLATE_T_UNDER - z_ground,
        "gap_front": gap_front,
        "gauge": gauge,
        "spans": spans,
        "L/B": spans["full"] / gauge,
        "width": 2 * half_w,
        "mass_g": mtot,
        "belt_g": belt_g,
        "cg_x": xc,
        "cg_z_plate": zc,
        "cg_h": h,
        "nod_g": (x_r2 - xc) / h,  # braking that rocks it onto the sprocket
        "nod_deg": math.degrees(math.atan(gap_front / (X_DRIVE - x_r2))),
        "accel_g": (xc - x_i) / h,
        "side_tip_deg": math.degrees(math.atan(y_c / h)),
        "pivot_tau": res,
        "sag": sag,
        "s_max": s_max,
        "sweep_r": sweep,
        "fit": fit,
        "engaged": path["wrap"][3] / (2 * math.pi) * n,
        "climb": {
            mu: climb_max(r_o, gap_front, x_i, xc, h, wt, mu) for mu in (0.5, 0.9)
        },
        "strain_pct": {
            k: tuple(100 * TENSION / (w * T_BASE * e) for e in v)
            for k, v in E_TPU.items()
        },
    }


def report() -> None:
    s = system()
    f = s["fit"]
    print("wheels (x, z above plate top, running Ø):")
    for name, x, z, r in s["wheels"]:
        print(f"  {name:9s} x {x:+6.1f}  z {z:+6.1f}  Ø{2 * r:.1f}")
    print(
        f"belt: {f['links']} lugs x {PITCH:.0f} = {f['length']:.0f} mm; "
        f"idler taut at x {f['x_fit']:.1f} (travel {X_IDLER - TRAVEL:.0f}…"
        f"{X_IDLER + TRAVEL:.0f}): install slack {f['install_slack']:.1f} mm, rear "
        f"travel absorbs {f['creep_pct']:.1f} % stretch + creep"
    )
    print(
        f"sprocket wrap {math.degrees(s['path']['wrap'][3]):.0f}° = {s['engaged']:.1f} lugs engaged"
    )
    print(
        f"ground z {s['z_ground']:.1f}: clearance {s['clearance']:.1f} under the bosses, "
        f"{s['clearance_flat']:.1f} under the flat plate; sprocket {s['gap_front']:.1f} "
        f"off the floor"
    )
    print(
        f"track gauge {s['gauge']:.0f}, width {s['width']:.0f}; loaded span "
        f"{s['spans']['rocker']:.0f} (rocker) / {s['spans']['full']:.0f} (full), "
        f"L/B {s['L/B']:.2f}"
    )
    print(
        f"mass ~{s['mass_g']:.0f} g (belts {2 * s['belt_g']:.0f} g); CG x "
        f"{s['cg_x']:+.1f}, {s['cg_z_plate']:.1f} above plate, {s['cg_h']:.1f} above ground"
    )
    print(
        f"nod onto the sprocket above {s['nod_g']:.2f} g braking ({s['nod_deg']:.1f}° "
        f"max); rear tip {s['accel_g']:.2f} g; side tip {s['side_tip_deg']:.0f}°"
    )
    print(
        f"bottom run: longest free span {s['s_max']:.0f} mm, sag over a mid-span bump "
        f"~{s['sag']:.1f} mm (vs {s['clearance']:.1f} clearance)"
    )
    print(
        "step climb (upper bound): "
        + ", ".join(f"μ{mu} {v:.0f} mm" for mu, v in s["climb"].items())
    )
    print(f"pivot sweep Ø{2 * s['sweep_r']:.0f}")
    for k, (hi, lo) in s["strain_pct"].items():
        print(
            f"belt strain at {TENSION:.0f} N, TPU {k}: {lo:.2f}–{hi:.2f} % "
            f"(= {lo * f['length'] / 100:.1f}–{hi * f['length'] / 100:.1f} mm)"
        )
    print("pivot torque per motor, N·m (TT stall ~%.2f):" % TT_STALL)
    for k, v in s["pivot_tau"].items():
        print(f"  {k:16s} {v:.3f}  ({100 * v / TT_STALL:.0f} % stall)")
    print("\nsweep: N  W   Ørun  clear  width  sweepØ  τ(μ0.9,rocker/full)")
    for n in (16, 18, 20):
        for w in (30.0, 36.0):
            t = system(n, w)
            print(
                f"      {n:2d} {w:3.0f}  {2 * t['r_run']:5.1f} {t['clearance']:5.1f}  "
                f"{t['width']:5.0f}  {2 * t['sweep_r']:5.0f}   "
                f"{t['pivot_tau']['mu0.9_rocker']:.3f} / {t['pivot_tau']['mu0.9_full']:.3f}"
            )


# ------------------------------------------------------------ preview
def preview(path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = system()
    fig = plt.figure(figsize=(15, 8))
    a = fig.add_subplot(2, 3, (1, 2))
    for name, x, z, r in s["wheels"]:
        a.add_patch(plt.Circle((x, z), r, fill=False, lw=1.5))
        a.plot(x, z, "k+", ms=6)
    for p, q in s["path"]["segs"]:
        a.plot([p[0], q[0]], [p[1], q[1]], color="limegreen", lw=T_BASE * 2)
    for (name, x, z, r), ph_in, wr in zip(
        s["wheels"], s["path"]["phi_in"], s["path"]["wrap"]
    ):
        t = np.linspace(ph_in, ph_in + wr, 40)
        rp = r + T_BASE / 2
        a.plot(x + rp * np.cos(t), z + rp * np.sin(t), color="limegreen", lw=T_BASE * 2)
    a.plot([PLATE_X[0], PLATE_X[1]], [-2, -2], color="0.5", lw=8, solid_capstyle="butt")
    a.axhline(s["z_ground"], color="sienna", lw=1)
    a.plot(s["cg_x"], s["cg_z_plate"], "o", ms=12, mfc="gold", mec="k")
    a.annotate(
        f"CG ({s['cg_x']:+.0f}, {s['cg_h']:.0f} above ground)",
        (s["cg_x"], s["cg_z_plate"]),
        xytext=(10, 10),
        textcoords="offset points",
    )
    a.set_aspect("equal")
    a.set_title(
        f"Side: {s['fit']['links']}-lug belt, sprocket {s['gap_front']:.1f} up, "
        f"clearance {s['clearance']:.1f} / {s['clearance_flat']:.1f} mm"
    )
    a.set_xlabel("x (mm, +fwd)")
    b = fig.add_subplot(2, 3, 3)
    m = N_TEETH * 48
    th = np.linspace(0, 2 * np.pi, m, endpoint=False)
    for r, st in ((wheel_band(m), "-"), (circle(R_RUN, m), "--")):
        b.plot(r * np.cos(th), r * np.sin(th), st, color="k", lw=1)
    for k in range(N_TEETH):  # lugs as wrapped on the wheel
        c = 2 * np.pi * k / N_TEETH
        hr, ht = LUG_L / 2 / R_RUN, LUG_TIP_L / 2 / (R_RUN - LUG_H)
        pts = [
            (R_RUN, c - hr),
            (R_RUN - LUG_H, c - ht),
            (R_RUN - LUG_H, c + ht),
            (R_RUN, c + hr),
        ]
        b.fill(
            [p[0] * np.cos(p[1]) for p in pts],
            [p[0] * np.sin(p[1]) for p in pts],
            color="limegreen",
            alpha=0.7,
        )
    b.add_patch(plt.Circle((0, 0), R_RUN + T_BASE, fill=False, color="limegreen", lw=2))
    b.set_aspect("equal")
    b.set_title(f"Wheel face: pockets + lugs (clr {CLR})")
    # tread, unrolled outside face: 120 mm of each style, dark = contact
    fit = s["fit"]
    links = fit["links"]
    mm = links * 24
    r_out = fit["length"] / (2 * math.pi) + T_BASE / 2
    xs = np.arange(mm) * fit["length"] / mm
    sel = xs < 120
    for i, tr in enumerate(("bars_stagger", "pads", "bars", "smooth")):
        ax = fig.add_subplot(2, 4, 5 + i)
        ca, cb = _tread_curves(tr, mm, links, r_out)
        img = np.vstack([np.tile(ca[sel], (17, 1)), np.tile(cb[sel], (19, 1))]) - r_out
        if tr in ("pads", "bars_stagger"):
            img[17] = np.minimum(ca, cb)[sel] - r_out
        ax.imshow(
            img,
            aspect="equal",
            cmap="Greys",
            vmin=0,
            vmax=1.5,
            extent=(0, 120, 0, BELT_W),
        )
        ax.set_title(f"tread '{tr}' (+{tread_h(tr):.1f} mm)")
        ax.set_xlabel("along the belt (mm)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def _prism(poly: list[tuple[float, float]], z0: float, z1: float) -> np.ndarray:
    """Closed triangle mesh of a CONVEX polygon (CCW) extruded z0..z1 (fan caps)."""
    p = np.asarray(poly, float)
    n = len(p)
    lo = np.c_[p, np.full(n, z0)]
    hi = np.c_[p, np.full(n, z1)]
    tris = []
    for i in range(1, n - 1):
        tris.append([lo[0], lo[i + 1], lo[i]])
        tris.append([hi[0], hi[i], hi[i + 1]])
    for i in range(n):
        j = (i + 1) % n
        tris.append([lo[i], lo[j], hi[j]])
        tris.append([lo[i], hi[j], hi[i]])
    return np.array(tris)


def test_pieces() -> dict[str, np.ndarray]:
    """T13 (08 §7): bench pieces printed like the belt (upright: belt width = Z).

    - strip: 150 x T_BASE x BELT_W plain band for the hang/creep test (1 kg, 24 h).
    - lug6: a straight 6-lug length of belt (bars outside, lugs in the centre band), to
      wrap by hand round coupon_band_slice and stall-test on a TT. Convex prisms that
      overlap by 0.05: the slicer merges them (no boolean engine here). Lug end
      chamfers left out (as T11).
    """
    out = {
        "belt_strip150": _prism(
            [(0, 0), (150, 0), (150, T_BASE), (0, T_BASE)], 0, BELT_W
        )
    }
    n, end = 6, 5.0
    length = n * PITCH + 2 * end
    shells = [_prism([(0, 0), (length, 0), (length, T_BASE), (0, T_BASE)], 0, BELT_W)]
    z0, z1 = (BELT_W - LUG_W) / 2, (BELT_W + LUG_W) / 2
    for k in range(n):
        c = end + PITCH * (k + 0.5)
        # lug on the inner face (y < 0), bar on the outer face (y > T_BASE)
        shells.append(
            _prism(
                [
                    (c - LUG_L / 2, 0.05),
                    (c - LUG_TIP_L / 2, -LUG_H),
                    (c + LUG_TIP_L / 2, -LUG_H),
                    (c + LUG_L / 2, 0.05),
                ][::-1],
                z0,
                z1,
            )
        )
        shells.append(
            _prism(
                [
                    (c - GROUSER_L / 2 - 0.5, T_BASE - 0.05),
                    (c + GROUSER_L / 2 + 0.5, T_BASE - 0.05),
                    (c + GROUSER_L / 2 - 0.5, T_BASE + GROUSER_H),
                    (c - GROUSER_L / 2 + 0.5, T_BASE + GROUSER_H),
                ],
                0,
                BELT_W,
            )
        )
    out["belt_lug6"] = np.concatenate(shells)
    return out


def belt_scaled(shrink_pct: float) -> np.ndarray:
    """The ring belt with its diameter grown by shrink_pct (TPU contracts along the
    length; width = Z untouched). 0 until the strip test measures it."""
    t, _ = belt()
    f = 1 + shrink_pct / 100
    return t * np.array([f, f, 1.0])


def build(out: str) -> None:
    os.makedirs(out, exist_ok=True)
    parts = {
        "sprocket_outrigger": sprocket(True),
        "sprocket_plain": sprocket(False),
        "idler_2brg": idler(2),
        "idler_1brg": idler(1),
        "road_wheel_disc": road_wheel(),
    }
    info = {}
    for tr in ("bars_stagger", "pads", "bars", "smooth"):
        parts[f"belt_{tr}"], info[tr] = belt(tread=tr)
    parts.update(coupons())
    parts.update(test_pieces())  # T13
    print(f"{'part':24s} {'tris':>7s}  closed  vol cm³  mass g")
    bad = False
    for name, t in parts.items():
        ok, vol = check(t)
        rho = RHO_TPU if name.startswith("belt") else RHO_PETCF
        print(
            f"{name:24s} {len(t):7d}  {'yes' if ok else 'NO ':6s} {vol / 1000:7.2f}  {vol / 1000 * rho:6.1f}"
        )
        bad |= not ok or vol <= 0
        write_stl(os.path.join(out, f"{name}.stl"), t, f"robot-buddy {name}")
    for tr, i in info.items():
        print(f"belt_{tr}: ring Ø{i['ring_od']:.0f} x {BELT_W:.0f} (bed 256)")
    preview(os.path.join(out, "drivetrain_preview.png"))
    if bad:
        sys.exit("mesh check failed")


def check_wrap(stretches=(0.0, 0.005, 0.01, 0.015, 0.02), strain_limit=0.05) -> dict:
    """T12: the installed belt on the wheels.

    - Lug <-> pocket side clearance over the wrap (180°: the 9 engaged lugs) at each belt
      stretch: the belt pitch grows to PITCH (1 + e) while the pockets stay at PITCH, so
      lug k sits (k - 4) PITCH e off its pocket with the pattern centred (best case).
      Clearance at each radius = pocket half-width - lug half-width (both rounded
      trapezoids: wheel_band and the belt's lug, the lug rigid in mm on the wheel).
    - Base bending strain: printed as a ring (pitch radius R0), bent to the wheel pitch
      radius on the wraps and straightened on the runs: (T_BASE / 2) |1/r - 1/R0|.
    - Tooth tops below the running surface: the belt rides the rim discs (R_RUN), the band
      teeth sit TOOTH_DROP lower (no chordal bump).
    """
    rp = pitch_radius()
    r_top, r_bot = R_RUN - TOOTH_DROP, R_RUN - LUG_H - CLR
    hp_top = (LUG_L / 2 + CLR) / R_RUN
    hp_bot = (LUG_TIP_L / 2 + CLR) / r_bot
    r_tip = R_RUN - LUG_H
    hl_root, hl_tip = LUG_L / 2 / R_RUN, LUG_TIP_L / 2 / r_tip

    def half_angle(r, r_full, r_zero, a_in, a_out):
        """|u| where a cosine-blended trapezoid (depth from r_zero to r_full) passes r."""
        f = np.clip((r_zero - r) / (r_zero - r_full), 0.0, 1.0)  # 1 at full depth
        s_ = np.arccos(np.clip(2 * f - 1, -1, 1)) / np.pi
        return a_in + s_ * (a_out - a_in)

    rs = np.linspace(
        r_tip, r_top, 200
    )  # lug flanks live between its tip and the teeth tops
    pocket = rs * half_angle(rs, r_bot, r_top, hp_bot, hp_top)
    lug = rs * half_angle(rs, r_tip, R_RUN, hl_tip, hl_root)
    side = float(np.min(pocket - lug))  # side clearance at zero shift, mm
    engaged = N_TEETH // 2
    rows = []
    for e in stretches:
        shift = (engaged - 1) / 2 * PITCH * e
        rows.append(
            {"stretch_pct": 100 * e, "worst_shift": shift, "clearance": side - shift}
        )
    r0 = belt_fit()["length"] / (2 * math.pi)
    strain_wrap = T_BASE / 2 * abs(1 / rp - 1 / r0)
    strain_run = T_BASE / 2 / r0
    out = {
        "side_clearance": side,
        "tip_clearance": r_tip - r_bot,
        "rows": rows,
        "max_stretch_pct": 100 * side / ((engaged - 1) / 2 * PITCH),
        "strain_wrap": strain_wrap,
        "strain_run": strain_run,
        "strain_ok": max(strain_wrap, strain_run) <= strain_limit,
        "tooth_drop": TOOTH_DROP,
    }
    print(
        f"T12 check-wrap: {engaged} lugs engaged per 180° wrap, pitch radius {rp:.2f}"
    )
    print(
        f"  side clearance (no stretch) {side:.3f} mm, tip to pocket floor {out['tip_clearance']:.2f} mm"
    )
    for rw in rows:
        ok = "ok" if rw["clearance"] >= 0 else "INTERFERES"
        print(
            f"  stretch {rw['stretch_pct']:4.1f} %: end lugs {rw['worst_shift']:.2f} mm off -> clearance {rw['clearance']:+.3f} mm  {ok}"
        )
    print(f"  stretch for zero clearance: {out['max_stretch_pct']:.2f} %")
    print(
        f"  base bending strain: wraps {100 * strain_wrap:.2f} %, runs {100 * strain_run:.2f} % (limit {100 * strain_limit:.0f} % 🟡)"
    )
    print(
        f"  tooth tops {TOOTH_DROP} mm below the running surface (rim discs at R_RUN): smooth rolling"
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["report", "build", "check-wrap"])
    ap.add_argument("-o", "--out", default="CAD/exports/rnd/drivetrain")
    ap.add_argument(
        "--shrink", type=float, default=0.0, help="T13: belt ring growth, %%"
    )
    a = ap.parse_args()
    if a.cmd == "check-wrap":
        check_wrap()
    elif a.cmd == "build" and a.shrink:
        build(a.out)
        name = f"belt_shrink{a.shrink:g}"
        write_stl(
            os.path.join(a.out, f"{name}.stl"),
            belt_scaled(a.shrink),
            f"robot-buddy {name}",
        )
        print(f"{name}.stl: ring grown {a.shrink:g} % in diameter")
    else:
        report() if a.cmd == "report" else build(a.out)


if __name__ == "__main__":
    main()
