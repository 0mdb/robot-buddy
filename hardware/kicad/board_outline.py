"""Reflex board outline, shared by layout_pcb.py and route_pcb.py.

KiCad drawing mm: origin at the board's top-left corner, y down.
Chassis frame (tools/chassis.py, REFLEX_AT): chassis x = board x - 40, chassis y = 30 - board y.

Encoder-connector notches (2026-11-08, Ben): the encoder TT motor's socket stands 8.5 mm
inboard of the mount face (to chassis |y| 23.9), 16.8 x 13.35, centred on the motor axis:
chassis z 6.8-20.2, 0.2 over the bare PCB (z 5-6.6) and through the parts on it (to 13.6).
From Ben's photo it starts ~1 mm in from the encoder end: chassis x -9..7.8, board x 31..47.8. Both side edges get a pocket
over that span; the mounting holes, and the 65 x 60 outline elsewhere, are unchanged.
"""

W, H = 65.0, 60.0  # overall board, mm
NOTCH_X = (28.5, 50.0)  # board x span (connector ~31..48 from the photo); 50 not 51: at 51
# the notch end pinched the routing past the MH2/MH4 screw heads (x 51.75) to 0.25 mm
NOTCH_D = 7.0  # depth from each long edge: chassis |y| 23.0 (connector inboard face 23.9)


def outline() -> list[tuple[float, float]]:
    """Board edge polygon, clockwise on screen (y down), starting top-left."""
    x0, x1, d = NOTCH_X[0], NOTCH_X[1], NOTCH_D
    return [
        (0.0, 0.0), (x0, 0.0), (x0, d), (x1, d), (x1, 0.0), (W, 0.0),
        (W, H), (x1, H), (x1, H - d), (x0, H - d), (x0, H), (0.0, H),
    ]


def inset(pts: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Offset a rectilinear polygon inward by d (exact for 90-degree corners)."""
    n = len(pts)
    area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1.0 if area2 > 0 else -1.0  # interior is on the left of each edge when area2 > 0

    def normal(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        ex, ey = b[0] - a[0], b[1] - a[1]
        length = (ex * ex + ey * ey) ** 0.5
        return (-ey / length * sgn, ex / length * sgn)

    out = []
    for i in range(n):
        p, v, q = pts[i - 1], pts[i], pts[(i + 1) % n]
        n1, n2 = normal(p, v), normal(v, q)
        out.append((v[0] + d * (n1[0] + n2[0]), v[1] + d * (n1[1] + n2[1])))
    return out


def contains(x: float, y: float) -> bool:
    """Point inside the board outline (edges count as inside)."""
    x0, x1, d = NOTCH_X[0], NOTCH_X[1], NOTCH_D
    if not (0.0 <= x <= W and 0.0 <= y <= H):
        return False
    return not (x0 < x < x1 and (y < d or y > H - d))


if __name__ == "__main__":
    print("outline", outline())
    print("inset 0.3", [(round(x, 2), round(y, 2)) for x, y in inset(outline(), 0.3)])
