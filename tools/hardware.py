"""Bought hardware envelopes for the chassis assembly: screws, inserts, washers, bearings,
pins, shims, standoffs. Generated as simple solids (swbuild manifest lines) and placed by
tools/chassis.py rebuild_manifest() from the same constants the printed parts use.

Part frame of every envelope: axis +Z. A screw's head bears on z = 0 and stands in +z, its
shank runs down to z = -L. Inserts, bearings, washers, shims, pins and standoffs sit on
z = 0 and extend +z by their length. Placement: `place(seat, axis)` maps part +Z onto
`axis` (unit vector pointing OUT of the joint, toward the head) at the seat point.

Shank diameters are drawn at the diameter of the thread they engage, so a clean
interference check means the joint is right: a screw in a brass insert is drawn at its
major d inside an insert bore of d + 0.02; a thread-forming screw is drawn at the printed
pilot (it cuts its own thread); an insert is drawn at the drawn pocket diameter (it melts
in). Heads to ISO 4762 / DIN 7984 / ISO 7380-1 / 7380-2 / DIN 7985 nominal sizes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# head diameter, head height per (kind, d)
HEADS = {
    ("shcs", 2.0): (3.8, 2.0),
    ("shcs", 2.5): (4.5, 2.5),
    ("shcs", 3.0): (5.5, 3.0),
    ("lowhead", 3.0): (5.5, 2.0),  # DIN 7984
    ("button", 3.0): (5.7, 1.65),  # ISO 7380-1
    ("flanged", 3.0): (6.9, 1.65),  # ISO 7380-2 (flange Ø)
    ("pan", 2.0): (4.0, 1.6),  # DIN 7985 / thread-forming pan
    ("pan", 1.6): (3.2, 1.3),
}


@dataclass(frozen=True)
class Item:
    """One envelope part. `name` is the library file stem; `lines` builds it."""

    name: str
    desc: str  # BOM description
    lines: tuple[str, ...]
    vol: float


def _cyl(r: float, z0: float, z1: float) -> str:
    return f"cyl|z|0 0|{z0:.3f} {z1:.3f}|{r:.4f}|boss"


def _ring(r_out: float, r_in: float, z0: float, z1: float) -> str:
    return f"ring|{z0:.3f} {z1:.3f}|c {r_out:.4f}|c {r_in:.4f}|boss"


def _expect(vol: float, r: float, z0: float, z1: float) -> str:
    return f"expect|vol {vol:.2f} {max(vol * 0.01, 0.05):.2f}|box {-r:.3f} {r:.3f} {-r:.3f} {r:.3f} {z0:.3f} {z1:.3f} 0.02"


def screw(kind: str, d: float, length: float, shank_d: float | None = None, tf: bool = False) -> Item:
    """kind: shcs / lowhead / button / flanged / pan. `shank_d`: drawn shank (default d)."""
    dk, k = HEADS[(kind, d)]
    sd = shank_d if shank_d is not None else d
    head = {"shcs": "SHCS ISO 4762", "lowhead": "low head DIN 7984", "button": "button ISO 7380-1",
            "flanged": "flanged button ISO 7380-2", "pan": "pan head"}[kind]
    tag = "TF" if tf else "A2"
    name = f"hw_M{d:g}x{length:g}_{kind}{'_tf' if tf else ''}"
    desc = f"M{d:g} x {length:g} {head}{', thread-forming for plastics' if tf else ''} ({tag})"
    vol = math.pi * (dk / 2) ** 2 * k + math.pi * (sd / 2) ** 2 * length
    return Item(name, desc, (_cyl(dk / 2, 0, k), _cyl(sd / 2, -length, 0.01), _expect(vol, dk / 2, -length, k)), vol)


def insert(d: float, length: float, pocket_d: float) -> Item:
    """Heat-set insert, drawn at the pocket Ø with a bore of d + 0.02."""
    ro, ri = pocket_d / 2, (d + 0.02) / 2
    vol = math.pi * (ro * ro - ri * ri) * length
    name = f"hw_insert_M{d:g}x{length:g}"
    return Item(name, f"Heat-set insert M{d:g} x {length:g} (Ruthex-type, brass)",
                (_ring(ro, ri, 0, length), _expect(vol, ro, 0, length)), vol)


def ring_part(name: str, desc: str, d_out: float, d_in: float, t: float) -> Item:
    vol = math.pi * ((d_out / 2) ** 2 - (d_in / 2) ** 2) * t
    return Item(name, desc, (_ring(d_out / 2, d_in / 2, 0, t), _expect(vol, d_out / 2, 0, t)), vol)


def pin(name: str, desc: str, d: float, length: float) -> Item:
    vol = math.pi * (d / 2) ** 2 * length
    return Item(name, desc, (_cyl(d / 2, 0, length), _expect(vol, d / 2, 0, length)), vol)


def bearing(code: str, d_in: float, d_out: float, w: float) -> Item:
    """Drawn with a d_in + 0.02 bore so a Ø d_in axle or pin reads as touching, not interfering."""
    return ring_part(f"hw_bearing_{code}", f"Ball bearing {code} ({d_in:g} x {d_out:g} x {w:g}, 2RS)", d_out, d_in + 0.02, w)


def item_lines(it: Item, path: str) -> list[str]:
    return [f"part|{path}", *it.lines, "save"]


# --------------------------------------------------------------------------- placement
def place(seat: tuple[float, float, float], axis: tuple[float, float, float]) -> tuple[list[float], tuple[float, float, float]]:
    """Rotation (row-major, p' = R p + t) taking part +Z onto `axis`, origin onto `seat`."""
    ax, ay, az = axis
    n = math.sqrt(ax * ax + ay * ay + az * az)
    ax, ay, az = ax / n, ay / n, az / n
    # pick a reference not parallel to the axis for the part's X
    ref = (1.0, 0.0, 0.0) if abs(ax) < 0.9 else (0.0, 1.0, 0.0)
    # x' = normalize(ref - (ref.a) a); y' = a x x'
    dot = ref[0] * ax + ref[1] * ay + ref[2] * az
    xx, xy, xz = ref[0] - dot * ax, ref[1] - dot * ay, ref[2] - dot * az
    m = math.sqrt(xx * xx + xy * xy + xz * xz)
    xx, xy, xz = xx / m, xy / m, xz / m
    yx, yy, yz = ay * xz - az * xy, az * xx - ax * xz, ax * xy - ay * xx
    # columns are the images of part X, Y, Z
    return [xx, yx, ax, xy, yy, ay, xz, yz, az], seat


def compose(outer: tuple[list[float], tuple], inner: tuple[list[float], tuple]) -> tuple[list[float], tuple[float, float, float]]:
    """outer ∘ inner: a placement given in a part's frame, then that part's assembly transform."""
    Ro, to = outer
    Ri, ti = inner
    R = [sum(Ro[i * 3 + k] * Ri[k * 3 + j] for k in range(3)) for i in range(3) for j in range(3)]
    t = tuple(sum(Ro[i * 3 + k] * ti[k] for k in range(3)) + to[i] for i in range(3))
    return R, t  # type: ignore[return-value]
