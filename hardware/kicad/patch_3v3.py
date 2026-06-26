#!/usr/bin/env python3
"""
Patch the two unconnected +3V3 nets (R4-1 and U2-10) that freerouting missed.
Route on F.Cu only, tapping from the existing +3V3 via at (13.30, 24.27).

Clearance analysis (Power class = 0.25mm edge-to-edge):
  - R4.2 (/ESTOP) pad: 0.540x0.640mm at (30.00,20.49), right edge at 30.270mm
    x=30.70: track left edge 30.575, clearance 0.305mm ✓
  - /ESTOP diagonal (26.80,22.67)→(28.98,20.49): line x+y=49.47
    corner at (27.20,21.40): distance 0.615mm, edge-to-edge 0.365mm ✓
  - /ESTOP horizontal (28.98,20.49)→(30.00,20.49): clears by >0.39mm ✓
"""

import pcbnew

PCB = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb"

b = pcbnew.LoadBoard(PCB)
net = b.FindNet("+3V3")
if net is None:
    raise RuntimeError("+3V3 net not found")

# ── Remove previously added patch tracks ─────────────────────────────────────
OLD = {
    ((13.300, 24.270), (13.300, 21.400)),
    ((13.300, 21.400), (27.200, 21.400)),
    ((27.200, 21.400), (28.500, 19.850)),
    ((28.500, 19.850), (30.700, 19.850)),
    ((30.700, 19.850), (30.700, 20.380)),
    ((30.700, 20.380), (55.500, 20.380)),
    ((55.500, 20.380), (56.160, 21.650)),
    ((30.700, 20.380), (30.700, 21.510)),
    ((30.700, 21.510), (30.000, 21.510)),
}


def coord(nm):
    return round(pcbnew.ToMM(nm), 3)


removed = 0
for t in list(b.GetTracks()):
    if t.GetClass() == "PCB_VIA":
        continue
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    if t.GetNetname() != "+3V3":
        continue
    key = ((coord(t.GetX()), coord(t.GetY())), (coord(t.GetEndX()), coord(t.GetEndY())))
    rev = (key[1], key[0])
    if key in OLD or rev in OLD:
        b.Remove(t)
        removed += 1

print(f"Removed {removed} old patch tracks")

# ── Add corrected patch tracks ────────────────────────────────────────────────
# x=30.70 keeps 0.305mm clearance from R4.2 right edge (30.270mm)
# corner at (27.20,21.40) keeps 0.615mm from /ESTOP diagonal, edge-to-edge 0.365mm
segments = [
    ((13.30, 24.27), (13.30, 21.40)),  # vertical from +3V3 via
    ((13.30, 21.40), (27.20, 21.40)),  # horizontal east
    ((27.20, 21.40), (28.50, 19.70)),  # diagonal bypassing /ESTOP diagonal
    (
        (28.50, 19.70),
        (30.70, 19.70),
    ),  # horizontal east (y=19.70: 0.345mm from R4.2 top)
    ((30.70, 19.70), (30.70, 20.38)),  # vertical south
    ((30.70, 20.38), (55.50, 20.38)),  # long horizontal to near U2-10
    ((55.50, 20.38), (56.16, 21.65)),  # diagonal to U2-10 pad
    ((30.70, 20.38), (30.70, 21.51)),  # vertical south to R4-1 row
    ((30.70, 21.51), (30.00, 21.51)),  # horizontal west to R4-1 pad
]

for (x1, y1), (x2, y2) in segments:
    t = pcbnew.PCB_TRACK(b)
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    t.SetWidth(pcbnew.FromMM(0.25))
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    b.Add(t)
    print(f"  Added F.Cu ({x1},{y1})→({x2},{y2})")

b.Save(PCB)
print("Saved.")

conn = b.GetConnectivity()
conn.RecalculateRatsnest()
print(f"Unconnected: {conn.GetUnconnectedCount(False)}")
