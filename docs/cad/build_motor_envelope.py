"""
Generate a rough envelope STL of the Yahboom encoder TT worm-gear motor.

Coordinate system (matches what's useful in SolidWorks):
  Origin at the OUTPUT SHAFT END (where it pokes out, axis end).
  +X axis points BACKWARD along the motor body (toward the encoder).
  +Z axis points UP (encoder PCB sticks up in +Z).
  +Y axis perpendicular.
  Output shaft axis is the X axis.

Dimensions read from Motor_Yahboom_15_2048x2048.webp:
  - Overall length (incl. shaft):           80 mm
  - Body length (gear case):                75 mm
  - Body width:                             25 mm
  - Body height (gear case):                19.20 mm
  - Output shaft diameter:                  5.4 mm
  - Output shaft length (past body):        5 mm
  - Encoder PCB / housing bump above body:  8.70 mm
  - Encoder back-face width:                35.95 mm
  - Encoder back-face depth:                26 mm
  - Encoder side overhang:                  ~6.80 mm beyond body
  - Mounting hole pattern (M3 clearance):   Ø3.2 mm, on the gear body
  - Mounting flange tabs:                   ~5 mm out from body

NOTE: this is a ROUGH ENVELOPE for clearance checks and mate references.
Not dimensioned for accurate motor model — refine if needed.
"""
import struct
import numpy as np
from pathlib import Path


# --- Triangulation helpers ---------------------------------------------------

def box(xmin, xmax, ymin, ymax, zmin, zmax):
    """Return (N, 3, 3) triangle vertex array for an axis-aligned box."""
    v = np.array([
        [xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymax, zmin], [xmin, ymax, zmin],  # bottom
        [xmin, ymin, zmax], [xmax, ymin, zmax], [xmax, ymax, zmax], [xmin, ymax, zmax],  # top
    ])
    # 12 triangles, 2 per face. Wind so normals point outward.
    faces = [
        # bottom (z=zmin, normal -Z)
        (0, 2, 1), (0, 3, 2),
        # top (z=zmax, +Z)
        (4, 5, 6), (4, 6, 7),
        # -Y face
        (0, 1, 5), (0, 5, 4),
        # +Y face
        (3, 6, 2), (3, 7, 6),
        # -X face
        (0, 4, 7), (0, 7, 3),
        # +X face
        (1, 2, 6), (1, 6, 5),
    ]
    return np.array([[v[a], v[b], v[c]] for a, b, c in faces], dtype=np.float32)


def cylinder_x(x_start, x_end, radius, y_center, z_center, segments=32):
    """Cylinder with axis along X, capped at both ends."""
    tris = []
    angles = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring_start = np.array([
        [x_start, y_center + radius * np.cos(a), z_center + radius * np.sin(a)]
        for a in angles
    ])
    ring_end = np.array([
        [x_end, y_center + radius * np.cos(a), z_center + radius * np.sin(a)]
        for a in angles
    ])
    cap_start = np.array([x_start, y_center, z_center])
    cap_end = np.array([x_end, y_center, z_center])

    for i in range(segments):
        j = (i + 1) % segments
        # side
        tris.append([ring_start[i], ring_end[i], ring_end[j]])
        tris.append([ring_start[i], ring_end[j], ring_start[j]])
        # cap at x_start (normal -X)
        tris.append([cap_start, ring_start[j], ring_start[i]])
        # cap at x_end (normal +X)
        tris.append([cap_end, ring_end[i], ring_end[j]])

    return np.array(tris, dtype=np.float32)


def compute_normals(tris):
    """Compute outward normals from triangle winding."""
    v0 = tris[:, 0]
    v1 = tris[:, 1]
    v2 = tris[:, 2]
    n = np.cross(v1 - v0, v2 - v0)
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return (n / norm).astype(np.float32)


def write_binary_stl(path, tris, header_text="Yahboom encoder TT motor envelope"):
    normals = compute_normals(tris)
    n = len(tris)
    header = header_text.encode("ascii")[:80].ljust(80, b"\0")
    dtype = np.dtype([
        ("normal", "<f4", (3,)),
        ("verts", "<f4", (3, 3)),
        ("attr", "<u2"),
    ])
    arr = np.zeros(n, dtype=dtype)
    arr["normal"] = normals
    arr["verts"] = tris
    arr["attr"] = 0
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", n))
        f.write(arr.tobytes())


# --- Motor envelope geometry -------------------------------------------------

# All dimensions in mm. Origin: output shaft TIP, axis along X (+X = into motor body).

# Output shaft: protrudes 5 mm in -X (i.e., the tip is at X=0, base at X=+5 where
# it enters the gear body face). Diameter 5.4. The Z offset is the shaft's
# vertical position on the gear body face — the 17.50 dim in the drawing puts
# the shaft 17.50 from one face, i.e. offset 5 mm from body centerline.
SHAFT_DIA = 5.4
SHAFT_LEN_PROTRUDE = 5.0
SHAFT_Z_OFFSET = 0.0   # set to 0 = shaft on body centerline; change to -5 if you
                       # want the asymmetric position shown in the drawing.

# Gear body: rectangular case. Body face is at X=5 (where shaft emerges from body).
BODY_LEN = 75.0
BODY_WIDTH = 25.0
BODY_HEIGHT = 19.2

body_x0 = SHAFT_LEN_PROTRUDE                     # front face of body
body_x1 = body_x0 + BODY_LEN                     # back face of body (encoder side)
body_y0 = -BODY_WIDTH / 2
body_y1 = +BODY_WIDTH / 2
body_z0 = -BODY_HEIGHT / 2
body_z1 = +BODY_HEIGHT / 2

# Mounting flange tabs sticking out 5 mm on each side (Y direction), thin (~3 mm tall)
# Approximate the tabs that hold the M3 mounting bolts.
FLANGE_OUT = 5.0
FLANGE_THICK = 3.0
flange_z0 = body_z0
flange_z1 = body_z0 + FLANGE_THICK

# Encoder housing: sits on top (+Z) of the rear ~30 mm of the body, bumping up 8.7 mm
ENC_BUMP = 8.7
ENC_BACK_DEPTH = 26.0
ENC_BACK_WIDTH = 35.95
ENC_LEN_ALONG_X = 30.0  # approx — encoder bump on rear portion of motor

enc_x0 = body_x1 - ENC_LEN_ALONG_X
enc_x1 = body_x1
enc_y0 = -ENC_BACK_WIDTH / 2     # slightly wider than body
enc_y1 = +ENC_BACK_WIDTH / 2
enc_z0 = body_z1                  # sits on top of body
enc_z1 = body_z1 + ENC_BUMP

# NOTE: drawing's 80 mm overall dim already covers shaft tip to back of motor body,
# so we do NOT add a connector stub past body_x1. If your unit has a wire harness
# sticking out further, model it separately.


# Assemble
parts = []

# Output shaft
parts.append(cylinder_x(
    x_start=0.0,
    x_end=SHAFT_LEN_PROTRUDE,
    radius=SHAFT_DIA / 2,
    y_center=0.0,
    z_center=SHAFT_Z_OFFSET,
    segments=24,
))

# Gear body
parts.append(box(body_x0, body_x1, body_y0, body_y1, body_z0, body_z1))

# Flange tabs (one each side) — placed near the front mount face
# Approximate as small extensions from body Y-faces
tab_x0 = body_x0 + 5.0
tab_x1 = body_x0 + 25.0
parts.append(box(tab_x0, tab_x1,
                 body_y1, body_y1 + FLANGE_OUT,
                 flange_z0, flange_z1))
parts.append(box(tab_x0, tab_x1,
                 body_y0 - FLANGE_OUT, body_y0,
                 flange_z0, flange_z1))

# Encoder housing bump
parts.append(box(enc_x0, enc_x1, enc_y0, enc_y1, enc_z0, enc_z1))


all_tris = np.concatenate(parts, axis=0)
print(f"Total triangles: {len(all_tris)}")

bbox_min = all_tris.reshape(-1, 3).min(axis=0)
bbox_max = all_tris.reshape(-1, 3).max(axis=0)
print(f"Bounding box (mm):")
print(f"  X: [{bbox_min[0]:.2f}, {bbox_max[0]:.2f}]  length {bbox_max[0]-bbox_min[0]:.2f}")
print(f"  Y: [{bbox_min[1]:.2f}, {bbox_max[1]:.2f}]  width  {bbox_max[1]-bbox_min[1]:.2f}")
print(f"  Z: [{bbox_min[2]:.2f}, {bbox_max[2]:.2f}]  height {bbox_max[2]-bbox_min[2]:.2f}")

# repo-relative: <repo>/CAD/exports/ (script lives in docs/cad/)
out_path = (Path(__file__).resolve().parents[2]
            / "CAD" / "exports" / "Yahboom_TT_Motor_envelope.stl")
write_binary_stl(out_path, all_tris)
print(f"\nWrote: {out_path}")
print(f"Size: {out_path.stat().st_size} bytes")
