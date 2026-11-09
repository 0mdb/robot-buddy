"""Reflex board outline + mounting holes: ONE source for layout_pcb.py, route_pcb.py,
pcb_qc.py and the chassis (tools/chassis.py imports this as pcb_outline).

KiCad drawing mm: origin at the board's top-left corner, y down. x runs rear -> front
(x 0 is the rear edge, chassis x -40, where the USB-C exits; R2c), y runs left -> right.

2026-11-09 shrink (Ben): 65 x 60 with encoder notches -> 52.5 x 46, no notches.
The encoder TT socket stands to chassis |y| 23.9 (8.5 mm inboard of the mount face,
chassis x -9..7.8; Ben's measurement 2026-11-08). A 46 mm board centred on the chassis
centreline spans |y| <= 23, so it clears the sockets along its whole length. The
2026-11-08 notches (x 28.5-50, 7 deep) were the same clearance on a 60 mm board.
Possible because v2 dropped the NeoPixels (U3/J11/R11) and the power LED (J10/R10).

Chassis frame (tools/chassis.py REFLEX_*): origin at the hole-pattern centre on the PCB's
bottom face, KiCad y flipped: chassis x = REFLEX_AT.x + (kx - HOLE_CX),
chassis y = REFLEX_AT.y + (HOLE_CY - ky).
"""

W, H = 52.5, 46.0  # board, mm

# M3 holes, 4 in a rectangle (the base plate's standoffs are corners() of a symmetric
# pattern). 3.5 mm in from each edge: the Ø6.2 head keepout stays on the board.
HOLE_INSET = 3.5
HOLES = [
    (HOLE_INSET, HOLE_INSET),
    (W - HOLE_INSET, HOLE_INSET),
    (HOLE_INSET, H - HOLE_INSET),
    (W - HOLE_INSET, H - HOLE_INSET),
]
HOLE_CX, HOLE_CY = W / 2, H / 2  # pattern centre (the chassis envelope origin)
HOLE_HALF = (W / 2 - HOLE_INSET, H / 2 - HOLE_INSET)  # = chassis REFLEX_HOLES

# Rear edge at chassis x -40 (unchanged from the 65 x 60 board: the USB-C plug's bay),
# board centred on the chassis centreline.
REAR_EDGE_CHASSIS_X = -40.0


# Encoder-plug keep-out (found 2026-11-09, after the shrink). The encoder socket FACES
# INBOARD (Ben 2026-11-05, docs/cad/loop/QUESTIONS.md): its mating face is at chassis
# |y| 23.9, so the plug and its cable occupy |y| < 23.9 over chassis x -9..7.8 and
# z 6.8-20.2, i.e. right above the board's long edges (board top z 6.6). Nothing taller than
# the bare board may sit in that band. PLUG_DEPTH is PROVISIONAL: plug + cable bend inboard
# of the socket face is not measured yet (QUESTIONS.md "plug + cable depth"). Measure it,
# set it here, and pcb_qc.py §5 checks the layout against it.
SOCKET_X = (31.0, 47.8)  # board x (chassis -9..7.8)
SOCKET_FACE_Y = 23.9  # chassis |y| of the socket's mating face
PLUG_DEPTH = 8.0  # mm inboard of the face: PROVISIONAL until measured


def plug_keepouts() -> list[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) board-coordinate bands the encoder plugs + cables occupy."""
    edge_in = HOLE_CY - SOCKET_FACE_Y + PLUG_DEPTH  # depth from the board edge
    x0, x1 = SOCKET_X
    return [(x0, 0.0, x1, max(0.0, edge_in)), (x0, H - max(0.0, edge_in), x1, H)]


def outline() -> list[tuple[float, float]]:
    """Board edge polygon, clockwise on screen (y down), starting top-left."""
    return [(0.0, 0.0), (W, 0.0), (W, H), (0.0, H)]


def inset(pts: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Offset a rectilinear polygon inward by d (exact for 90-degree corners)."""
    n = len(pts)
    area2 = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )
    sgn = (
        1.0 if area2 > 0 else -1.0
    )  # interior is on the left of each edge when area2 > 0

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
    return 0.0 <= x <= W and 0.0 <= y <= H


if __name__ == "__main__":
    print(f"{W} x {H}, holes {HOLES}, pattern {2 * HOLE_HALF[0]} x {2 * HOLE_HALF[1]}")
    print("inset 0.3", [(round(x, 2), round(y, 2)) for x, y in inset(outline(), 0.3)])
