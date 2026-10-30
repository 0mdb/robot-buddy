"""
Generate a rough envelope STL of a Raspberry Pi 5 for use in the chassis assembly.

Coordinate system:
  Origin: CENTER of PCB BOTTOM face. This is the surface that sits on standoffs.
  +X axis: along the long PCB dimension (85 mm).
  +Y axis: along the short PCB dimension (56 mm).
  +Z axis: up (away from base plate). PCB top at Z = 1.6, components above.

Why bottom-face-center as origin: makes it trivial to mate to the base plate.
Just align the Pi's origin point to the base plate's Pi-position datum and
the Pi's Top plane (or any horizontal Z plane) to the base plate top + standoff height.

Mount hole positions (use these for standoffs in the base plate):
   (+29, +24.5)   (-29, +24.5)
   (+29, -24.5)   (-29, -24.5)
all at Z = 0 to Z = 1.6 (through PCB), M2.5 thread.

PCB centered: 85 mm long x 56 mm wide x 1.6 mm thick.

Components modeled (rough envelopes, not faithful):
  - USB + Ethernet cluster on +X edge, tallest features at ~17 mm above PCB
  - 40-pin GPIO header on +Y edge, 8.5 mm tall
  - micro-HDMI + USB-C cluster on -X edge, ~6 mm tall, slight overhang
  - SD card slot stub on -Y edge, projects 2 mm below PCB

NOT modeled: ICs, RAM, FFC connectors, power button, active cooler.
If you're using the official Active Cooler, total stack height becomes ~31 mm
above PCB top; model that separately if you need clearance check.
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from build_motor_envelope import box, cylinder_x, write_binary_stl  # noqa


# === Dimensions =============================================================
PCB_L = 85.0     # long dimension (X)
PCB_W = 56.0     # short dimension (Y)
PCB_T = 1.6      # thickness (Z)

# Mount hole pattern: 58 x 49 mm centered, M2.5
MOUNT_DX = 58.0 / 2  # 29
MOUNT_DY = 49.0 / 2  # 24.5

# === Build geometry =========================================================
parts = []

# PCB body
parts.append(box(
    xmin=-PCB_L / 2, xmax=+PCB_L / 2,
    ymin=-PCB_W / 2, ymax=+PCB_W / 2,
    zmin=0, zmax=PCB_T,
))

# USB + Ethernet cluster on +X edge.
# Real Pi 5: USB ports overhang PCB edge by ~3 mm, ethernet flush.
# Ports occupy roughly Y = -22 (USB stack) to Y = +24 (ethernet).
# Tallest = USB 3.0 stack at ~16-17 mm above PCB top.
parts.append(box(
    xmin=PCB_L / 2 - 14,            # 14 mm of port body inboard of PCB edge
    xmax=PCB_L / 2 + 3,             # 3 mm overhang past PCB
    ymin=-PCB_W / 2 + 2,
    ymax=+PCB_W / 2 - 2,
    zmin=PCB_T,
    zmax=PCB_T + 17,
))

# 40-pin GPIO header on +Y edge of PCB.
# Standard 2x20 header: ~51 mm long, ~5 mm wide, ~8.5 mm tall above PCB.
# Header is offset slightly from PCB centerline along X.
parts.append(box(
    xmin=-25, xmax=26,              # ~51 mm length
    ymin=PCB_W / 2 - 4,             # snug against +Y edge
    ymax=PCB_W / 2 - 1.5,           # ~2.5 mm header body width
    zmin=PCB_T,
    zmax=PCB_T + 8.5,
))

# micro-HDMI + USB-C + power button cluster on -X edge.
# Real Pi 5: 2x micro-HDMI, 1x USB-C power, power button.
# Roughly 6-7 mm tall above PCB. micro-HDMI overhangs ~1 mm.
parts.append(box(
    xmin=-PCB_L / 2 - 1,            # 1 mm overhang
    xmax=-PCB_L / 2 + 8,
    ymin=-15,
    ymax=+15,
    zmin=PCB_T,
    zmax=PCB_T + 6.5,
))

# SD card slot stub on -Y edge, projecting 2 mm BELOW PCB.
# Card itself extends past board, but we model just the slot housing.
parts.append(box(
    xmin=-PCB_L / 2 + 6, xmax=-PCB_L / 2 + 18,
    ymin=-PCB_W / 2,
    ymax=-PCB_W / 2 + 12,
    zmin=-2.0,
    zmax=0,
))

# CSI/DSI FFC connector envelope (one block representing both)
# These are tall flip-cap connectors on top of the PCB
parts.append(box(
    xmin=-12, xmax=+12,
    ymin=-PCB_W / 2 + 8, ymax=-PCB_W / 2 + 12,
    zmin=PCB_T,
    zmax=PCB_T + 3.0,
))

# === Mount hole indicator pegs (visible bosses to show where standoffs land) ==
# Small cylindrical pegs sticking 3 mm UP from PCB top at each hole location.
# Helps you visually align the standoffs in the assembly. NOT physical features
# of a real Pi -- just modeling aids. Delete in SolidWorks if you don't want them.
PEG_R = 1.4    # roughly M2.5 minor radius
PEG_TOP = PCB_T + 3.0

for sx in [+MOUNT_DX, -MOUNT_DX]:
    for sy in [+MOUNT_DY, -MOUNT_DY]:
        # Cylinder along Z axis. Adapt cylinder_x by swapping axes via numpy.
        # Reuse box() to make a small square peg instead -- visually distinct,
        # avoids extra triangulation.
        parts.append(box(
            xmin=sx - PEG_R, xmax=sx + PEG_R,
            ymin=sy - PEG_R, ymax=sy + PEG_R,
            zmin=0, zmax=PEG_TOP,
        ))

# === Assemble & write =======================================================
all_tris = np.concatenate(parts, axis=0)

bbox_min = all_tris.reshape(-1, 3).min(axis=0)
bbox_max = all_tris.reshape(-1, 3).max(axis=0)
size = bbox_max - bbox_min
print(f"Triangles: {len(all_tris)}")
print(f"Bounding box (mm): "
      f"X[{bbox_min[0]:.2f}, {bbox_max[0]:.2f}] "
      f"Y[{bbox_min[1]:.2f}, {bbox_max[1]:.2f}] "
      f"Z[{bbox_min[2]:.2f}, {bbox_max[2]:.2f}]")
print(f"Size: {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm")
print(f"  PCB:               {PCB_L} x {PCB_W} x {PCB_T} mm")
print(f"  Max stack height:  {bbox_max[2]:.2f} mm above standoff top")
print(f"  Below-PCB drop:    {-bbox_min[2]:.2f} mm (SD card slot)")

print("\nMount hole positions for base plate (relative to Pi center):")
for sx in [+MOUNT_DX, -MOUNT_DX]:
    for sy in [+MOUNT_DY, -MOUNT_DY]:
        print(f"  ({sx:+.1f}, {sy:+.1f})  M2.5 through")

# repo-relative: <repo>/CAD/exports/ (script lives in docs/cad/)
out_path = (Path(__file__).resolve().parents[2]
            / "CAD" / "exports" / "RaspberryPi5_envelope.stl")
write_binary_stl(out_path, all_tris, header_text="Raspberry Pi 5 envelope (rough)")
print(f"\nWrote: {out_path}")
print(f"Size:  {out_path.stat().st_size} bytes")
