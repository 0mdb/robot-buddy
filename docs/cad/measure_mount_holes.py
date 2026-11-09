#!/usr/bin/env python3
"""Measure a printed-bracket STL: bounding box + through-hole pattern.

No external deps beyond numpy. Parses binary STL, then for each principal axis
casts axis-aligned rays on a grid and counts mesh crossings. Columns with zero
crossings that are *enclosed* by material = through-holes. Reports hole centers
(world coords), equivalent diameters, and pairwise spacings.
"""
import sys, struct
import numpy as np

def read_binary_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        data = np.frombuffer(f.read(n * 50), dtype=np.uint8)
    if data.size != n * 50:
        raise SystemExit(f"truncated STL: {path}")
    rec = data.reshape(n, 50)
    floats = rec[:, :48].copy().view("<f4").reshape(n, 12)
    tris = floats[:, 3:12].reshape(n, 3, 3)  # (n,3verts,xyz)
    return tris

def enclosed_holes(tris, k, res=0.3, min_dia=1.0, max_dia=8.0):
    """Find through-holes whose axis == k (0/1/2). Returns list of dicts."""
    i, j = [a for a in (0, 1, 2) if a != k]
    V = tris.reshape(-1, 3)
    lo = V.min(0); hi = V.max(0)
    pad = 1.0
    gi = np.arange(lo[i] - pad, hi[i] + pad, res)
    gj = np.arange(lo[j] - pad, hi[j] + pad, res)
    Gi, Gj = np.meshgrid(gi, gj, indexing="ij")
    count = np.zeros(Gi.shape, dtype=np.int32)

    a = tris[:, 0]; b = tris[:, 1]; c = tris[:, 2]
    ai, aj = a[:, i], a[:, j]; bi, bj = b[:, i], b[:, j]; ci, cj = c[:, i], c[:, j]
    denom = (bj - cj) * (ai - ci) + (ci - bi) * (aj - cj)
    for t in range(tris.shape[0]):
        d = denom[t]
        if abs(d) < 1e-9:      # wall triangle (parallel to k) — skip
            continue
        l1 = ((bj[t] - cj[t]) * (Gi - ci[t]) + (ci[t] - bi[t]) * (Gj - cj[t])) / d
        l2 = ((cj[t] - aj[t]) * (Gi - ci[t]) + (ai[t] - ci[t]) * (Gj - cj[t])) / d
        l3 = 1.0 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        count[inside] += 1

    empty = count == 0
    # flood fill from border to mark background; enclosed empties = holes
    bg = np.zeros_like(empty)
    from collections import deque
    dq = deque()
    R, C = empty.shape
    for r in range(R):
        for cc in (0, C - 1):
            if empty[r, cc] and not bg[r, cc]: bg[r, cc] = True; dq.append((r, cc))
    for cc in range(C):
        for r in (0, R - 1):
            if empty[r, cc] and not bg[r, cc]: bg[r, cc] = True; dq.append((r, cc))
    while dq:
        r, cc = dq.popleft()
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
            nr, nc = r+dr, cc+dc
            if 0<=nr<R and 0<=nc<C and empty[nr,nc] and not bg[nr,nc]:
                bg[nr,nc]=True; dq.append((nr,nc))
    holes_mask = empty & ~bg

    # connected components of holes_mask
    lab = np.zeros_like(holes_mask, dtype=np.int32)
    cur = 0; comps = []
    for r in range(R):
        for cc in range(C):
            if holes_mask[r,cc] and lab[r,cc]==0:
                cur += 1; cells=[]; dq.append((r,cc)); lab[r,cc]=cur
                while dq:
                    q=dq.popleft(); cells.append(q)
                    for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)):
                        nr,nc=q[0]+dr,q[1]+dc
                        if 0<=nr<R and 0<=nc<C and holes_mask[nr,nc] and lab[nr,nc]==0:
                            lab[nr,nc]=cur; dq.append((nr,nc))
                comps.append(cells)
    out=[]
    cell_area = res*res
    for cells in comps:
        area = len(cells)*cell_area
        dia = 2*np.sqrt(area/np.pi)
        if dia < min_dia or dia > max_dia:  # ignore slots/noise outside bolt range
            continue
        ci_ = np.mean([Gi[r,cc] for r,cc in cells])
        cj_ = np.mean([Gj[r,cc] for r,cc in cells])
        out.append({"axis":"XYZ"[k], "center_%s"%"XYZ"[i]:round(float(ci_),2),
                    "center_%s"%"XYZ"[j]:round(float(cj_),2),
                    "dia_mm":round(float(dia),2), "i":i, "j":j,
                    "ci":ci_, "cj":cj_})
    return out, (lo, hi)

def main(path):
    tris = read_binary_stl(path)
    V = tris.reshape(-1,3); lo=V.min(0); hi=V.max(0); dim=hi-lo
    print(f"\n=== {path.split('/')[-1]} ===")
    print(f"triangles: {tris.shape[0]}")
    print(f"bbox mm  X[{lo[0]:.2f},{hi[0]:.2f}] Y[{lo[1]:.2f},{hi[1]:.2f}] Z[{lo[2]:.2f},{hi[2]:.2f}]")
    print(f"dims mm  X={dim[0]:.2f}  Y={dim[1]:.2f}  Z={dim[2]:.2f}")
    best=None
    for k in (0,1,2):
        holes,_ = enclosed_holes(tris,k)
        if holes:
            print(f"\n-- through-holes with axis {'XYZ'[k]}: {len(holes)} found --")
            for h in holes:
                keys=[x for x in h if x.startswith('center_')]
                print(f"   {'  '.join(f'{key}={h[key]:+.2f}' for key in keys)}  Ø{h['dia_mm']:.2f}")
            if best is None or len(holes)>len(best[1]):
                best=('XYZ'[k],holes)
    if best:
        axis,holes=best
        pts=np.array([[h['ci'],h['cj']] for h in holes])
        print(f"\n-- bolt pattern (axis {axis}, {len(holes)} holes) --")
        # pairwise spacings
        for m in range(len(pts)):
            for n in range(m+1,len(pts)):
                d=np.hypot(*(pts[m]-pts[n]))
                di=abs(pts[m][0]-pts[n][0]); dj=abs(pts[m][1]-pts[n][1])
                print(f"   holes {m}-{n}: center dist {d:.2f} mm  (Δ={di:.2f} x {dj:.2f})")
        i=holes[0]['i']; j=holes[0]['j']
        print(f"   pattern span: {pts[:,0].max()-pts[:,0].min():.2f} ({'XYZ'[i]}) "
              f"x {pts[:,1].max()-pts[:,1].min():.2f} ({'XYZ'[j]})")
        dias=[h['dia_mm'] for h in holes]
        print(f"   hole Ø: min {min(dias):.2f}  max {max(dias):.2f}  mean {np.mean(dias):.2f}")

if __name__=="__main__":
    for p in sys.argv[1:]:
        main(p)
