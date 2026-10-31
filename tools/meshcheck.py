#!/usr/bin/env python3
"""DFM checks on a printed part's STL (docs/print-dfm.md, docs/cad/loop BACKLOG T2).

    uv run --project tools --extra cad python tools/meshcheck.py CAD/exports/part.stl
    ... --up -z            # print orientation: which part axis points up on the bed
    ... --rho 1.29 --json  # density g/cm3; one JSON line instead of the table

Reports, in print orientation (mm):
  - watertight, volume, mass (solid, at --rho), bounding box and fit on the P2S bed
  - overhang: area of downward faces steeper than --overhang deg from vertical,
    excluding the bed face (dfm: <= 45 deg prints without support), split (D3) into
    bridges (a flat underside with material within --bridge mm on both sides along x or
    y, which a slicer bridges), ledges (support on one side only, cantilever > 1 mm) and
    floating area: only ledges and floating area need support
  - min wall: ray-cast inward from sampled faces to the opposite surface
    (dfm: >= 1.2 mm, 2 perimeters at 0.6)
  - sharp edges: convex edges with a dihedral turn > --sharp deg (an unfilleted
    corner; tessellated fillets turn a few degrees per facet), as total length
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import trimesh

BED = (256.0, 256.0, 256.0)  # Bambu P2S build volume, mm
AXES = {
    "+z": np.eye(3),
    "-z": np.diag([1.0, -1.0, -1.0]),
    "+x": np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float),
    "-x": np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float),
    "+y": np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float),
    "-y": np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float),
}


def orient(mesh: trimesh.Trimesh, up: str) -> trimesh.Trimesh:
    """Rotate so the part's `up` axis is +Z, then sit it on the bed at Z = 0."""
    m = mesh.copy()
    t = np.eye(4)
    t[:3, :3] = AXES[up]
    m.apply_transform(t)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m


def overhang_area(m: trimesh.Trimesh, limit_deg: float, bed_tol: float = 0.05) -> float:
    nz = m.face_normals[:, 2]
    down = nz < -np.cos(np.radians(limit_deg))  # steeper than the limit, facing down
    on_bed = m.triangles[:, :, 2].max(axis=1) < bed_tol
    return float(m.area_faces[down & ~on_bed].sum())


def overhang_split(
    m: trimesh.Trimesh,
    limit_deg: float,
    bridge_mm: float,
    samples: int = 4000,
    seed: int = 0,
) -> dict:
    """Split the overhang area into bridge / ledge / floating / steep (D3, tick 30).

    Flat downward faces are sampled by area; from 0.3 mm below each sample, rays run along
    +-x and +-y to the first wall. A bridge has walls on both sides of one axis within
    bridge_mm in total; a ledge has a wall on some side but no such pair (a cantilever of
    <= 1 mm is ignored); floating has none. Steep (not flat) downward faces are reported
    as they are."""
    nz = m.face_normals[:, 2]
    on_bed = m.triangles[:, :, 2].max(axis=1) < 0.05
    down = (nz < -np.cos(np.radians(limit_deg))) & ~on_bed
    flat = down & (nz < -0.98)
    out = {"steep_cm2": float(m.area_faces[down & ~flat].sum()) / 100}
    a_flat = float(m.area_faces[flat].sum())
    if a_flat == 0:
        return {**out, "bridge_cm2": 0.0, "ledge_cm2": 0.0, "float_cm2": 0.0}
    rng = np.random.default_rng(seed)
    fidx = np.nonzero(flat)[0]
    pick = rng.choice(fidx, size=samples, p=m.area_faces[fidx] / a_flat)
    tri = m.triangles[pick]
    u, v = rng.random(samples), rng.random(samples)
    swap = u + v > 1
    u[swap], v[swap] = 1 - u[swap], 1 - v[swap]
    pts = (
        tri[:, 0]
        + u[:, None] * (tri[:, 1] - tri[:, 0])
        + v[:, None] * (tri[:, 2] - tri[:, 0])
    )
    pts[:, 2] -= 0.3
    dirs = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]], float)
    dist = np.full((samples, 4), np.inf)
    for k, d in enumerate(dirs):
        loc, ray, _ = m.ray.intersects_location(
            pts, np.repeat(d[None], samples, 0), multiple_hits=False
        )
        if len(ray):
            dist[ray, k] = np.linalg.norm(loc - pts[ray], axis=1)
    span_x, span_y = dist[:, 0] + dist[:, 1], dist[:, 2] + dist[:, 3]
    bridge = (span_x <= bridge_mm) | (span_y <= bridge_mm) | (dist.min(axis=1) <= 1.0)
    floating = ~bridge & np.isinf(dist).all(axis=1)
    ledge = ~bridge & ~floating
    w = a_flat / samples / 100
    return {
        **out,
        "bridge_cm2": float(bridge.sum() * w),
        "ledge_cm2": float(ledge.sum() * w),
        "float_cm2": float(floating.sum() * w),
    }


def min_wall(m: trimesh.Trimesh, samples: int, seed: int = 0) -> tuple[float, float]:
    """Min and 1st-percentile wall thickness from inward rays at area-weighted faces."""
    rng = np.random.default_rng(seed)
    p = m.area_faces / m.area_faces.sum()
    idx = rng.choice(len(m.faces), size=min(samples, len(m.faces) * 4), p=p)
    origins = m.triangles_center[idx] - m.face_normals[idx] * 1e-4
    dirs = -m.face_normals[idx]
    loc, ray_i, _ = m.ray.intersects_location(origins, dirs, multiple_hits=False)
    if len(ray_i) == 0:
        return float("nan"), float("nan")
    d = np.linalg.norm(loc - origins[ray_i], axis=1)
    d = d[d > 1e-3]
    return float(d.min()), float(np.percentile(d, 1))


def sharp_edges(m: trimesh.Trimesh, sharp_deg: float) -> tuple[int, float]:
    ang = m.face_adjacency_angles
    convex = m.face_adjacency_convex
    sel = convex & (ang > np.radians(sharp_deg))
    edges = m.face_adjacency_edges[sel]
    length = np.linalg.norm(m.vertices[edges[:, 0]] - m.vertices[edges[:, 1]], axis=1)
    return int(sel.sum()), float(length.sum())


def check(
    path: str,
    up: str,
    rho: float,
    overhang: float,
    sharp: float,
    samples: int,
    bridge: float = 40.0,
) -> dict:
    mesh = trimesh.load_mesh(path, force="mesh")
    m = orient(mesh, up)
    ext = m.bounds[1] - m.bounds[0]
    wmin, w1 = min_wall(m, samples)
    n_sharp, l_sharp = sharp_edges(m, sharp)
    vol = float(m.volume) if m.is_watertight else float("nan")
    return {
        "file": path,
        "up": up,
        "watertight": bool(m.is_watertight),
        "volume_mm3": round(vol, 1),
        "mass_g_solid": round(vol * rho / 1000, 2),
        "bbox_mm": [round(float(v), 2) for v in ext],
        "fits_bed": bool(all(e <= b for e, b in zip(sorted(ext), sorted(BED)))),
        "overhang_cm2": round(overhang_area(m, overhang) / 100, 2),
        **{k: round(v, 2) for k, v in overhang_split(m, overhang, bridge).items()},
        "min_wall_mm": round(wmin, 2),
        "wall_p1_mm": round(w1, 2),
        "sharp_edges": n_sharp,
        "sharp_len_mm": round(l_sharp, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("stl", nargs="+")
    ap.add_argument("--up", default="+z", choices=list(AXES))
    ap.add_argument("--rho", type=float, default=1.29, help="g/cm3 (PET-CF 1.29)")
    ap.add_argument("--overhang", type=float, default=45.0)
    ap.add_argument("--sharp", type=float, default=30.0)
    ap.add_argument(
        "--bridge", type=float, default=40.0, help="max bridge span, mm (D3)"
    )
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    bad = 0
    for path in a.stl:
        r = check(path, a.up, a.rho, a.overhang, a.sharp, a.samples, a.bridge)
        if a.json:
            print(json.dumps(r))
            continue
        print(f"{r['file']}  (up {r['up']})")
        for k, v in r.items():
            if k not in ("file", "up"):
                print(f"  {k:14} {v}")
        bad += (not r["watertight"]) or (not r["fits_bed"]) or r["min_wall_mm"] < 1.2
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
