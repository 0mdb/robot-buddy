"""
Split a binary STL containing multiple disconnected meshes into separate files.
Uses union-find on triangles that share vertices (with rounding to handle FP drift).

Usage:
    python3 split_stl.py <input.stl> <output_prefix>

Outputs:
    <output_prefix>_part1.stl, _part2.stl, ...

Also prints each component's triangle count and bounding box so you can
identify which is left vs right by X coordinate.
"""
import sys
import struct
import numpy as np
from pathlib import Path


def read_binary_stl(path):
    """Return (header, normals, vertices) where vertices is (N, 3, 3)."""
    with open(path, "rb") as f:
        header = f.read(80)
        n_tris = struct.unpack("<I", f.read(4))[0]
        # Each triangle = 50 bytes: 12 (normal) + 36 (3 verts) + 2 (attr)
        data = f.read(n_tris * 50)
    dtype = np.dtype([
        ("normal", "<f4", (3,)),
        ("verts", "<f4", (3, 3)),
        ("attr", "<u2"),
    ])
    arr = np.frombuffer(data, dtype=dtype, count=n_tris)
    return header, arr["normal"].copy(), arr["verts"].copy()


def write_binary_stl(path, header, normals, verts):
    n = len(normals)
    dtype = np.dtype([
        ("normal", "<f4", (3,)),
        ("verts", "<f4", (3, 3)),
        ("attr", "<u2"),
    ])
    arr = np.zeros(n, dtype=dtype)
    arr["normal"] = normals
    arr["verts"] = verts
    arr["attr"] = 0
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", n))
        f.write(arr.tobytes())


def find_components(verts, decimals=4):
    """Union-find on triangles sharing any vertex (rounded to handle FP)."""
    n_tris = verts.shape[0]
    # Flatten to (n_tris*3, 3), then map each unique vertex to an id
    flat = np.round(verts.reshape(-1, 3), decimals)
    # Hashable key per vertex
    keys = [tuple(v) for v in flat]
    vid_map = {}
    next_id = 0
    tri_verts = np.empty((n_tris, 3), dtype=np.int64)
    for i, k in enumerate(keys):
        if k not in vid_map:
            vid_map[k] = next_id
            next_id += 1
        tri_verts[i // 3, i % 3] = vid_map[k]
    n_verts = next_id

    # Union-Find over vertices
    parent = np.arange(n_verts)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for tri in tri_verts:
        union(tri[0], tri[1])
        union(tri[1], tri[2])

    # Group triangles by their root vertex
    roots = np.array([find(tri_verts[i, 0]) for i in range(n_tris)])
    unique_roots, inv = np.unique(roots, return_inverse=True)
    return inv, len(unique_roots)


def main():
    if len(sys.argv) != 3:
        print("Usage: split_stl.py <input.stl> <output_prefix>")
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_prefix = Path(sys.argv[2])

    header, normals, verts = read_binary_stl(in_path)
    n_tris = verts.shape[0]
    print(f"Input: {in_path.name}")
    print(f"  Triangles: {n_tris}")
    bbox_min = verts.reshape(-1, 3).min(axis=0)
    bbox_max = verts.reshape(-1, 3).max(axis=0)
    print(f"  Overall bbox (mm): "
          f"X[{bbox_min[0]:.2f}, {bbox_max[0]:.2f}] "
          f"Y[{bbox_min[1]:.2f}, {bbox_max[1]:.2f}] "
          f"Z[{bbox_min[2]:.2f}, {bbox_max[2]:.2f}]")
    print(f"  Overall size (mm): "
          f"{bbox_max[0]-bbox_min[0]:.2f} x "
          f"{bbox_max[1]-bbox_min[1]:.2f} x "
          f"{bbox_max[2]-bbox_min[2]:.2f}")

    comp_id, n_comps = find_components(verts)
    print(f"\nFound {n_comps} connected component(s)")

    # Compute bbox + center for each component
    info = []
    for c in range(n_comps):
        mask = comp_id == c
        cv = verts[mask].reshape(-1, 3)
        cmin = cv.min(axis=0)
        cmax = cv.max(axis=0)
        center = (cmin + cmax) / 2
        info.append({
            "id": c,
            "n_tris": int(mask.sum()),
            "min": cmin,
            "max": cmax,
            "center": center,
        })

    # Sort by center X so output is reproducible (left = negative X)
    info.sort(key=lambda d: d["center"][0])

    for k, comp in enumerate(info, start=1):
        side = "L" if comp["center"][0] < info[len(info)//2]["center"][0] else "R"
        if n_comps == 2:
            side = "L" if k == 1 else "R"
        elif n_comps == 1:
            side = "single"
        print(f"\n  Component {k} (suggested label: {side}):")
        print(f"    triangles: {comp['n_tris']}")
        print(f"    bbox X: [{comp['min'][0]:.2f}, {comp['max'][0]:.2f}]  "
              f"size {comp['max'][0]-comp['min'][0]:.2f}")
        print(f"    bbox Y: [{comp['min'][1]:.2f}, {comp['max'][1]:.2f}]  "
              f"size {comp['max'][1]-comp['min'][1]:.2f}")
        print(f"    bbox Z: [{comp['min'][2]:.2f}, {comp['max'][2]:.2f}]  "
              f"size {comp['max'][2]-comp['min'][2]:.2f}")
        print(f"    center: ({comp['center'][0]:.2f}, "
              f"{comp['center'][1]:.2f}, {comp['center'][2]:.2f})")

        # Write file
        mask = comp_id == comp["id"]
        out_name = f"{out_prefix}_{side}.stl" if n_comps == 2 else \
                   f"{out_prefix}_part{k}.stl"
        write_binary_stl(out_name, header, normals[mask], verts[mask])
        print(f"    -> wrote {out_name}")


if __name__ == "__main__":
    main()
