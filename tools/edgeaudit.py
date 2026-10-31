#!/usr/bin/env python3
"""Accessible sharp-edge audit for kid safety (docs/cad/loop BACKLOG S1).

    uv run --project tools --extra cad python tools/edgeaudit.py [--md docs/cad/loop/S1_edge_audit.md]

Reads the generated STLs (CAD/exports/gen, part frames) and finds convex edges with a
dihedral turn > --sharp deg, the same test as meshcheck.py: an unfilleted corner (a
tessellated fillet turns only a few degrees per facet). Each part has an accessibility
rule for where a child's hand can reach with the canopy fitted; sharp edges inside it are
listed in clusters with their location, so they can be fixed in the generators.

Rule (BACKLOG kid-safety): accessible external edges get a radius >= 1.0 mm.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chassis  # noqa: E402

GEN = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "CAD", "exports", "gen"
)


def _plate(p: np.ndarray, n: np.ndarray) -> np.ndarray:
    # The canopy covers the plate top; the perimeter and the whole belly are handled.
    hx, hy = chassis.PLATE_L / 2, chassis.PLATE_W / 2
    edge_d = np.minimum.reduce(
        [
            hx - np.abs(p[:, 0]),
            hy - np.abs(p[:, 1]),
            (hx + hy - chassis.FRONT_CHAMFER - (p[:, 0] + np.abs(p[:, 1])))
            / np.sqrt(2),
        ]
    )
    rear = p[:, 0] < -(hx - chassis.REAR_RADIUS)
    corner = np.hypot(
        p[:, 0] + hx - chassis.REAR_RADIUS, np.abs(p[:, 1]) - (hy - chassis.REAR_RADIUS)
    )
    edge_d = np.where(
        rear & (np.abs(p[:, 1]) > hy - chassis.REAR_RADIUS),
        np.minimum(edge_d, chassis.REAR_RADIUS - corner),
        edge_d,
    )
    return (edge_d < 1.0) | (p[:, 2] < -chassis.PLATE_T + 0.01)


def _bulkhead(p: np.ndarray, n: np.ndarray) -> np.ndarray:
    # The face side (normals forward) and the outer sides are outside the canopy.
    return (n[:, 0] > 0.3) | (np.abs(p[:, 1]) > np.abs(p[:, 1]).max() - 1.0)


def _wheel(p: np.ndarray, n: np.ndarray) -> np.ndarray:
    # Outboard (bed) face at part z ~ 0 faces out of the robot; the rest runs in the belt.
    return p[:, 2] < 0.5


def _covered(p: np.ndarray, n: np.ndarray) -> np.ndarray:
    return np.zeros(len(p), bool)


PARTS = [
    ("RB-PRT-001_base_plate", "plate perimeter + belly", _plate),
    ("RB-PRT-002_bulkhead", "face side + outer sides", _bulkhead),
    ("RB-PRT-010_motor_mount_R", "covered (motor, sprocket, canopy)", _covered),
    ("RB-PRT-011_motor_mount_L", "covered (motor, sprocket, canopy)", _covered),
    ("RB-PRT-020_sprocket", "outboard face", _wheel),
    ("RB-PRT-021_idler", "outboard face", _wheel),
]


def audit(path: str, rule, sharp_deg: float):
    m = trimesh.load(path)
    sel = m.face_adjacency_convex & (m.face_adjacency_angles > np.radians(sharp_deg))
    e = m.face_adjacency_edges[sel]
    a, b = m.vertices[e[:, 0]], m.vertices[e[:, 1]]
    mid, ln = (a + b) / 2, np.linalg.norm(a - b, axis=1)
    fn = m.face_normals[m.face_adjacency[sel]]  # (k, 2, 3)
    acc = rule(mid, fn[:, 0]) | rule(mid, fn[:, 1])
    # cluster accessible edges on a 5 mm grid so a long edge reads as one line
    groups: dict[tuple, list] = {}
    for p, length in zip(mid[acc], ln[acc]):
        key = tuple(np.round(p / 5.0).astype(int))
        groups.setdefault(key, [0.0, p])[0] += length
    merged: list[list] = []
    for length, p in sorted(groups.values(), key=lambda g: -g[0]):
        for g in merged:
            if np.linalg.norm(g[1] - p) < 12.0:
                g[0] += length
                break
        else:
            merged.append([length, p])
    return float(ln.sum()), float(ln[acc].sum()), merged


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--sharp", type=float, default=30.0)
    ap.add_argument("--md", help="write the audit table here as Markdown")
    a = ap.parse_args()
    out = [
        "| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |",
        "|---|---|---|---|---|",
    ]
    for name, zone, rule in PARTS:
        path = os.path.join(GEN, name + ".STL")
        tot, acc, cl = audit(path, rule, a.sharp)
        top = "; ".join(
            f"{g[0]:.0f} @ ({g[1][0]:.0f}, {g[1][1]:.0f}, {g[1][2]:.0f})"
            for g in cl[:6]
        )
        out.append(f"| {name} | {zone} | {tot:.0f} | {acc:.0f} | {top or '—'} |")
    text = "\n".join(out)
    print(text)
    if a.md:
        with open(a.md, "w") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
