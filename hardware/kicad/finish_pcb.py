#!/usr/bin/env python3
"""
Post-route finishing pass for robot-buddy-reflex.

Runs AFTER freerouting has imported its SES, because everything here depends on
the board's final copper:

  0. drop exact-duplicate copper left by seed + SES-import stacking
  1. drop track segments with a free end        (DRC track_dangling)
  1b. slide segments out of clearance violations into legal space
  2. re-place Reference/Value silk into clear space   (silk_over_copper / silk_overlap)
  3. clip silk graphics to the board outline (silk_edge_clearance)

This lives in the pipeline rather than in a KiCad session on purpose. Register
P1: the v1 DFM fixes were applied by hand after the last layout run, lived
nowhere in the scripts, and were silently reverted by the next regeneration —
37 defects reintroduced into a board that looked ready to fab. Anything fixed
by hand and not encoded here must be assumed gone after the next run.

Idempotent: safe to run twice on the same board.
"""

import sys

import pcbnew

PCB = "/home/ben/robot-buddy/hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb"

EDGE_MARGIN_MM = 0.5  # board setup edge clearance
SILK_GAP_MM = 0.15  # breathing room when testing silk collisions


def mm(v):
    return pcbnew.ToMM(v)


def nm(v):
    return pcbnew.FromMM(v)


class DegradedBoard(RuntimeError):
    """pcbnew handed back a BOARD whose Python proxy has no methods."""


def load_board(path):
    """LoadBoard + assert the proxy is usable.

    pcbnew 10.0.5's static init is flaky: it emits
        property.h(607): assert "m_choices.GetCount() > 0" failed in PROPERTY_ENUM()
    and when that fires the property manager is left half-registered, so SWIG cannot
    build the BOARD proxy and LoadBoard returns a bare SwigPyObject. Every later call
    then dies with 'SwigPyObject has no attribute GetTracks'.

    It is intermittent — the same script on the same board file succeeds or fails run
    to run — so it is caught here and retried by the driver in a fresh interpreter
    rather than worked around in the geometry code.
    """
    board = pcbnew.LoadBoard(path)
    if not hasattr(board, "GetTracks"):
        raise DegradedBoard(
            "pcbnew returned a degraded BOARD proxy (flaky PROPERTY_ENUM init)"
        )
    return board


# ══════════════════════════════════════════════════════════════════════════
# 0. Duplicate copper
# ══════════════════════════════════════════════════════════════════════════
# layout_pcb.py deliberately keeps traceItems as freerouting seeds (starting from
# bare copper makes freerouting hang on this board), and route_pcb.py's SES import
# then ADDS the router's own version of the same routing on top. The seed and the
# result are identical geometry, so every run leaves another copy behind — 71 exact
# duplicates out of 450 segments when this was found, including 8 stacked copies of
# the same 13.9mm +3V3 run.
#
# It is not just wasted file size: DRC reports a violation once per copy, so a single
# geometric problem showed up 16 times and looked far worse than it was. Deduping
# here also cleans the seeds for the NEXT run, so the count does not creep.
#
# Exact duplicates only — same net, layer, width and endpoints (either direction).
# Overlapping-but-not-identical copper is left alone; that is the router's business.
def drop_duplicate_tracks(board):
    seen = set()
    victims = []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        s, e = t.GetStart(), t.GetEnd()
        key = (t.GetNetCode(), t.GetLayer(), t.GetWidth()) + tuple(
            sorted([(s.x, s.y), (e.x, e.y)])
        )
        if key in seen:
            victims.append(t)
        else:
            seen.add(key)
    for t in victims:
        board.Remove(t)
    return len(victims)


# ══════════════════════════════════════════════════════════════════════════
# 1. Dangling tracks
# ══════════════════════════════════════════════════════════════════════════
# KiCad's own DRC is the oracle for "dangling", not a geometric test written here.
#
# The hand-rolled version this replaces asked "does either endpoint touch same-net
# copper?" and found ZERO of the 14 segments KiCad reports. It counted a point lying
# anywhere along another track's width as connected, which is more permissive than
# KiCad's connectivity graph, so every stub looked attached to the track it stubbed
# off. Guessing at the rule produced a pass that ran clean and fixed nothing.
#
# What these actually are is worth knowing: several are STALE SEED TRACKS. layout_pcb.py
# deliberately preserves traceItems as freerouting seeds, and a seed whose pad has since
# moved keeps its net — so the netless-orphan dropper (register P2) does not see it. The
# +5V stub at (49.42, 25.0) points at where C3's pad 1 sat before this session moved it.

import os as _os  # noqa: E402
import re  # noqa: E402
import shutil as _shutil  # noqa: E402
import subprocess as _sp  # noqa: E402

_DRC_TRACK = re.compile(
    r"Track \[(?P<net>[^\]]*)\] on (?P<layer>[\w.]+), length (?P<len>[\d.]+) mm"
)
# Vias report as "Buried via [NET] on F.Cu - B.Cu" with no length, so they need
# their own pattern — matching on net + position is enough to identify one.
_DRC_VIA = re.compile(r"(?:Buried|Blind|Through) ?via \[(?P<net>[^\]]*)\]")


def _drc_dangling(pcb_path, tmp_json):
    """Ask kicad-cli which track segments have an unconnected end."""
    _sp.run(
        [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            tmp_json,
            "--severity-warning",
            "--severity-error",
            pcb_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    with open(tmp_json) as fh:
        report = json.load(fh)

    wanted = []
    for v in report.get("violations", []):
        if v.get("type") not in ("track_dangling", "via_dangling"):
            continue
        for it in v.get("items", []):
            desc = it.get("description", "")
            pos = it.get("pos")
            if not pos:
                continue
            m = _DRC_TRACK.search(desc)
            if m:
                wanted.append(
                    (
                        m.group("net"),
                        m.group("layer"),
                        float(m.group("len")),
                        pos["x"],
                        pos["y"],
                    )
                )
                continue
            mv = _DRC_VIA.search(desc)
            if mv:
                wanted.append((mv.group("net"), None, None, pos["x"], pos["y"]))
    return wanted


def _matches(trk, spec):
    net, layer, length, px, py = spec
    if trk.GetNetname() != net:
        return False
    is_via = trk.Type() == pcbnew.PCB_VIA_T
    if (layer is None) != is_via:
        return False  # a via spec must match a via, a track spec a track
    if not is_via:
        if trk.GetBoard().GetLayerName(trk.GetLayer()) != layer:
            return False
        if abs(mm(trk.GetLength()) - length) > 5e-4:
            return False
    # DRC reports GetPosition() — the start point for a track, the centre for a via
    s = trk.GetStart()
    return abs(mm(s.x) - px) < 5e-4 and abs(mm(s.y) - py) < 5e-4


def drop_dangling_tracks_via_drc(pcb_path, tmp_json, max_rounds=6):
    """Delete exactly what DRC calls dangling, repeating until it reports none.

    Iterates because removing a stub can expose the segment behind it. A dangling
    track cannot be load-bearing by definition — its free end carries nothing — but
    the routing gate re-checks 0-unconnected afterwards regardless.
    """
    total = 0
    for _ in range(max_rounds):
        specs = _drc_dangling(pcb_path, tmp_json)
        if not specs:
            break
        board = load_board(pcb_path)
        victims = [t for t in board.GetTracks() if any(_matches(t, s) for s in specs)]
        if not victims:
            print(
                f"  WARNING: DRC reports {len(specs)} dangling tracks that could "
                f"not be matched on the board — left in place",
                file=sys.stderr,
            )
            break
        for t in victims:
            board.Remove(t)
        board.Save(pcb_path)
        total += len(victims)
    else:
        print(f"  WARNING: still dangling after {max_rounds} rounds", file=sys.stderr)
    return total


# ══════════════════════════════════════════════════════════════════════════
# PRE-ROUTE. Shorting seeds
# ══════════════════════════════════════════════════════════════════════════
# Run BEFORE the DSN export, not with the other passes — it deletes copper and
# relies on freerouting to lay it again.
#
# layout_pcb.py preserves traceItems as freerouting seeds, and a seed stays on the
# board even when the thing it was routed around has changed underneath it. Changing
# C3/C6 from SMD to through-hole was enough: their pads went from F.Cu-only to
# spanning every layer, so B.Cu tracks that had legally passed beneath them became
# dead shorts — /SDA and /ENC_LB straight onto +5V, reported as shorting_items and
# solder_mask_bridge.
#
# This is the third distinct thing stale seeds have caused (duplicates, stubs
# pointing at moved pads, now shorts). Deleting the offenders lets the router
# redo those nets against the geometry that actually exists now.
_DRC_SHORT_TYPES = ("shorting_items", "solder_mask_bridge")


def drop_shorting_seeds(pcb_path, tmp_json):
    _sp.run(
        [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            tmp_json,
            "--severity-error",
            pcb_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    with open(tmp_json) as fh:
        report = json.load(fh)

    specs = []
    for v in report.get("violations", []):
        if v.get("type") not in _DRC_SHORT_TYPES:
            continue
        for it in v.get("items", []):
            m = _DRC_TRACK.search(it.get("description", ""))
            pos = it.get("pos")
            if m and pos:
                specs.append(
                    (
                        m.group("net"),
                        m.group("layer"),
                        float(m.group("len")),
                        pos["x"],
                        pos["y"],
                    )
                )
    if not specs:
        return 0

    board = load_board(pcb_path)
    victims = [
        t
        for t in board.GetTracks()
        if t.Type() != pcbnew.PCB_VIA_T and any(_matches(t, s) for s in specs)
    ]
    for t in victims:
        board.Remove(t)
    board.Save(pcb_path)
    return len(victims)


# ══════════════════════════════════════════════════════════════════════════
# 1b. Clearance repair
# ══════════════════════════════════════════════════════════════════════════
# freerouting converges on a routing that is topologically fine but sometimes sits a
# segment off-centre in a channel that is wide enough. The +3V3 run under U1 is the
# example: the gap between pad 19 (bottom y=20.88) and pad 20 (top y=21.92) is
# 1.04mm, a 0.4mm track with 0.2mm either side needs 0.80mm, so there is a 0.24mm
# legal band for the centreline — and the router put it 0.13mm above that band.
#
# So this does not re-route anything. It slides an offending segment perpendicular to
# itself into the legal window, dragging any segment endpoint that coincided with its
# own so the connection is preserved exactly (a vertical neighbour stays vertical, a
# diagonal stays a diagonal, just shorter or longer).
#
# DRC is the judge, not geometry written here — every candidate offset is applied,
# the board is re-checked, and the move is kept only if the violation count actually
# drops. That is what stops this from becoming another hand-tuned coordinate patch
# like the +3V3 fixup that had to be deleted from route_pcb.py this session.

_DRC_CLEAR = re.compile(r"clearance (?P<req>[\d.]+) mm; actual (?P<act>[\d.]+) mm")


def _clearance_violations(pcb_path, tmp_json):
    _sp.run(
        [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            tmp_json,
            "--severity-warning",
            "--severity-error",
            pcb_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    with open(tmp_json) as fh:
        report = json.load(fh)

    out = []
    for v in report.get("violations", []):
        if v.get("type") != "clearance":
            continue
        m = _DRC_CLEAR.search(v.get("description", ""))
        if not m:
            continue
        deficit = float(m.group("req")) - float(m.group("act"))
        for it in v.get("items", []):
            tm = _DRC_TRACK.search(it.get("description", ""))
            pos = it.get("pos")
            if tm and pos:
                out.append(
                    (
                        (
                            tm.group("net"),
                            tm.group("layer"),
                            float(tm.group("len")),
                            pos["x"],
                            pos["y"],
                        ),
                        deficit,
                    )
                )
    return out


def _n_clearance(pcb_path, tmp_json):
    return len(_clearance_violations(pcb_path, tmp_json))


def _slide(board, spec, dx, dy):
    """Offset the matching segment by (dx,dy), dragging coincident endpoints."""
    target = None
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T and _matches(t, spec):
            target = t
            break
    if target is None:
        return False

    old_s = pcbnew.VECTOR2I(target.GetStart().x, target.GetStart().y)
    old_e = pcbnew.VECTOR2I(target.GetEnd().x, target.GetEnd().y)
    new_s = pcbnew.VECTOR2I(old_s.x + dx, old_s.y + dy)
    new_e = pcbnew.VECTOR2I(old_e.x + dx, old_e.y + dy)

    for t in board.GetTracks():
        if t is target:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            continue  # a via is a fixed anchor — never drag one
        if t.GetNetCode() != target.GetNetCode() or t.GetLayer() != target.GetLayer():
            continue
        for getter, setter in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            p = getter()
            if p.x == old_s.x and p.y == old_s.y:
                setter(new_s)
            elif p.x == old_e.x and p.y == old_e.y:
                setter(new_e)

    target.SetStart(new_s)
    target.SetEnd(new_e)
    return True


def repair_clearance(pcb_path, tmp_json, max_rounds=10):
    """Slide offending segments into legal space; keep only what DRC accepts."""
    fixed = stuck = 0
    for _ in range(max_rounds):
        viols = _clearance_violations(pcb_path, tmp_json)
        if not viols:
            break
        before = len(viols)
        spec, deficit = viols[0]

        # perpendicular to the segment; step out from the minimum that could work
        board = load_board(pcb_path)
        seg = next(
            (
                t
                for t in board.GetTracks()
                if t.Type() != pcbnew.PCB_VIA_T and _matches(t, spec)
            ),
            None,
        )
        if seg is None:
            stuck += 1
            break
        s, e = seg.GetStart(), seg.GetEnd()
        vx, vy = e.x - s.x, e.y - s.y
        length = (vx * vx + vy * vy) ** 0.5
        if length == 0:
            stuck += 1
            break
        px, py = -vy / length, vx / length  # unit normal

        # snapshot to a scratch file, NOT to git — the board is uncommitted work in
        # progress and a `git checkout` revert here would discard the whole session
        snapshot = pcb_path + ".clearance-bak"
        _shutil.copyfile(pcb_path, snapshot)

        improved = False
        candidates = [
            (sign, extra)
            for extra in (0.02, 0.05, 0.10, 0.15, 0.20, 0.30)
            for sign in (1, -1)
        ]
        for sign, extra in candidates:
            d = nm(deficit + extra)
            dx, dy = int(round(px * d * sign)), int(round(py * d * sign))
            board = load_board(pcb_path)
            if not _slide(board, spec, dx, dy):
                break
            board.Save(pcb_path)
            if _n_clearance(pcb_path, tmp_json) < before:
                improved = True
                fixed += 1
                break
            _shutil.copyfile(snapshot, pcb_path)  # undo, try the next offset

        _os.unlink(snapshot)
        if not improved:
            stuck += 1
            break
    return fixed, stuck


# ══════════════════════════════════════════════════════════════════════════
# 2 & 3. Silkscreen
# ══════════════════════════════════════════════════════════════════════════
SILK_LAYERS = (pcbnew.F_SilkS, pcbnew.B_SilkS)
COPPER_OF_SILK = {pcbnew.F_SilkS: pcbnew.F_Cu, pcbnew.B_SilkS: pcbnew.B_Cu}

# Boxes are plain (left, top, right, bottom) integer-nm tuples, never BOX2I.
# pcbnew's BOX2I return values are not reliably wrapped in this build — the second
# call to GetBoardEdgesBoundingBox() hands back a bare SwigPyObject with no methods
# (and every call warns "memory leak of type BOX2<VECTOR2<int>>*, no destructor").
# Converting at the boundary and doing the geometry in Python sidesteps all of it.


def _box(item):
    b = item.GetBoundingBox()
    return (b.GetLeft(), b.GetTop(), b.GetRight(), b.GetBottom())


def _inflate(box, d):
    return (box[0] - d, box[1] - d, box[2] + d, box[3] + d)


def _intersects(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _contains(outer, inner):
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _contains_pt(outer, pt):
    return outer[0] <= pt.x <= outer[2] and outer[1] <= pt.y <= outer[3]


def _contains_pt2(outer, xy):
    """Same, for a plain (x, y) tuple."""
    return outer[0] <= xy[0] <= outer[2] and outer[1] <= xy[1] <= outer[3]


def _board_box(board):
    """Board outline inset by the edge-clearance rule, from Edge.Cuts directly."""
    xs, ys = [], []
    for d in board.GetDrawings():
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        b = _box(d)
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    if not xs:
        raise SystemExit("finish_pcb: no Edge.Cuts geometry — cannot bound the board")
    m = nm(EDGE_MARGIN_MM)
    return (min(xs) + m, min(ys) + m, max(xs) - m, max(ys) - m)


def _copper_boxes(board, cu_layer):
    boxes = []
    for pad in board.GetPads():
        if pad.IsOnLayer(cu_layer):
            boxes.append(_box(pad))
    for trk in board.GetTracks():
        if trk.IsOnLayer(cu_layer):
            boxes.append(_box(trk))
    return boxes


def _silk_graphic_boxes(board, silk_layer):
    """Every silk item that is NOT a movable Reference/Value field."""
    boxes = []
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() == silk_layer:
                boxes.append(_box(g))
    for d in board.GetDrawings():
        if d.GetLayer() == silk_layer:
            boxes.append(_box(d))
    return boxes


def place_silk_fields(board):
    """Move each visible Reference/Value silk field to the nearest clear spot."""
    inside = _board_box(board)
    gap = nm(SILK_GAP_MM)

    copper = {lyr: _copper_boxes(board, COPPER_OF_SILK[lyr]) for lyr in SILK_LAYERS}
    statics = {lyr: _silk_graphic_boxes(board, lyr) for lyr in SILK_LAYERS}
    # fields already placed this run become obstacles for the ones after them
    placed = {lyr: [] for lyr in SILK_LAYERS}

    fields = []
    for fp in board.GetFootprints():
        for fld in (fp.Reference(), fp.Value()):
            if fld.GetLayer() in SILK_LAYERS and fld.IsVisible():
                fields.append((fp, fld))

    # place the physically largest footprints first — they have the least slack
    def _fp_area(fp):
        b = fp.GetBoundingBox(False, False)
        return (b.GetRight() - b.GetLeft()) * (b.GetBottom() - b.GetTop())

    fields.sort(key=lambda fv: -_fp_area(fv[0]))

    moved = hidden = kept = 0
    for fp, fld in fields:
        lyr = fld.GetLayer()
        obstacles = copper[lyr] + statics[lyr] + placed[lyr]
        _fb = fp.GetBoundingBox(False, False)
        fpbb = (_fb.GetLeft(), _fb.GetTop(), _fb.GetRight(), _fb.GetBottom())
        origin = fld.GetPosition()

        def clashes():
            bb = _inflate(_box(fld), gap)
            if not _contains(inside, bb):
                return True
            return any(_intersects(bb, o) for o in obstacles)

        if not clashes():
            placed[lyr].append(_inflate(_box(fld), gap))
            kept += 1
            continue

        # candidate ring: above / below / left / right of the footprint, walking out
        h = fld.GetTextHeight()
        fl, ft, fr, fb = fpbb
        cx = (fl + fr) // 2
        cy = (ft + fb) // 2
        cands = []
        for step in range(0, 9):
            d = int(h * 0.9 * step) + h
            cands += [
                pcbnew.VECTOR2I(cx, ft - d),
                pcbnew.VECTOR2I(cx, fb + d),
                pcbnew.VECTOR2I(fl - d, cy),
                pcbnew.VECTOR2I(fr + d, cy),
                pcbnew.VECTOR2I(fl - d, ft - d),
                pcbnew.VECTOR2I(fr + d, ft - d),
                pcbnew.VECTOR2I(fl - d, fb + d),
                pcbnew.VECTOR2I(fr + d, fb + d),
            ]

        won = False
        for c in cands:
            fld.SetPosition(c)
            if not clashes():
                won = True
                break

        if won:
            placed[lyr].append(_inflate(_box(fld), gap))
            moved += 1
        else:
            # nowhere legible to put it — an invisible field beats a fab defect,
            # and the Value is still on F.Fab for assembly documentation
            fld.SetPosition(origin)
            fld.SetVisible(False)
            hidden += 1

    return moved, kept, hidden


def _clip_segment(inside, p0, p1):
    """Liang-Barsky clip of a segment to `inside`. None if wholly outside."""
    x0, y0, x1, y1 = p0[0], p0[1], p1[0], p1[1]
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, x0 - inside[0]),
        (dx, inside[2] - x0),
        (-dy, y0 - inside[1]),
        (dy, inside[3] - y0),
    ):
        if p == 0:
            if q < 0:
                return None  # parallel to this edge and outside it
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    if t0 >= t1:
        return None
    return (
        (int(x0 + t0 * dx), int(y0 + t0 * dy)),
        (int(x0 + t1 * dx), int(y0 + t1 * dy)),
    )


def trim_silk_to_board(board):
    """Clip silk to the board outline rather than only deleting what is fully outside.

    Edge-mounted connectors (J1, J2, J9, J10) have housing outlines that legitimately
    hang past the board edge — that is what an edge-mount part looks like. The ink
    cannot print there, so KiCad flags silk_edge_clearance. Deleting the whole outline
    loses the part's footprint marking; clipping keeps the part of it that prints.

    Rectangles are expanded into their four sides so each side can be clipped
    independently; a rect that straddles a corner would otherwise be all-or-nothing.

    Collects edits first and applies afterwards: mutating a footprint's child list
    while its SWIG container is being iterated invalidates the proxy, which surfaces
    as a bare 'SwigPyObject is not iterable' on a *later* footprint.
    """
    inside = _board_box(board)
    removals, additions = [], []

    for fp in list(board.GetFootprints()):
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() not in SILK_LAYERS or g.Type() != pcbnew.PCB_SHAPE_T:
                continue

            shape = g.GetShape()
            if shape == pcbnew.SHAPE_T_SEGMENT:
                sides = [
                    ((g.GetStart().x, g.GetStart().y), (g.GetEnd().x, g.GetEnd().y))
                ]
            elif shape == pcbnew.SHAPE_T_RECT:
                a, b = g.GetStart(), g.GetEnd()
                c = [(a.x, a.y), (b.x, a.y), (b.x, b.y), (a.x, b.y)]
                sides = [(c[i], c[(i + 1) % 4]) for i in range(4)]
            else:
                # circles/arcs on the edge are rare here; drop only if fully outside
                if not _intersects(inside, _box(g)):
                    removals.append((fp, g))
                continue

            # Test the GEOMETRY, not GetBoundingBox(): the bbox is inflated by half the
            # stroke width, so a segment already clipped exactly to the boundary still
            # reads as "outside" and would be re-clipped on every run forever. Comparing
            # endpoints is what makes this pass idempotent.
            if all(
                _contains_pt2(inside, p) and _contains_pt2(inside, q) for p, q in sides
            ):
                continue

            kept = [
                (p, q)
                for p, q in (
                    _clip_segment(inside, s, e) or (None, None) for s, e in sides
                )
                if p is not None
            ]
            removals.append((fp, g))
            for p, q in kept:
                seg = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
                seg.SetLayer(g.GetLayer())
                seg.SetWidth(g.GetWidth())
                seg.SetStart(pcbnew.VECTOR2I(p[0], p[1]))
                seg.SetEnd(pcbnew.VECTOR2I(q[0], q[1]))
                additions.append((fp, seg))

    for fp, g in removals:
        fp.Remove(g)
    for fp, seg in additions:
        fp.Add(seg)
    return len(removals), len(additions)


# ══════════════════════════════════════════════════════════════════════════
# Driver
# ══════════════════════════════════════════════════════════════════════════
# Each pass runs in its OWN interpreter, one subprocess per pass.
#
# This is not defensive padding. Removing an item from the board (fp.Remove) leaves
# the SWIG layer in a state where later container access on a *freshly loaded*
# board degrades: board.GetDrawings() first returns a bare SwigPyObject, then the
# BOARD proxy itself loses its methods. Reloading inside the same process does not
# clear it — only a new interpreter does. Repeated LoadBoard/Save with no mutation
# is fine, which is what pins the cause on the removal.
#
# Passes are ordered, each reading what the previous one wrote:
#   dangling -> off-board silk -> silk field placement
# Field placement must run last: it treats the surviving silk graphics as
# obstacles, so it has to see the set the edge pass leaves behind.

PASSES = ("dedupe", "dangling", "clearance", "silkedge", "silkfields")


def run_pass(name):
    if name == "unshort":
        n = drop_shorting_seeds(PCB, "/tmp/reflex-unshort-drc.json")
        print(f"  Unshort    : {n} shorting seed tracks dropped for re-routing")
        return 0

    if name == "dedupe":
        board = load_board(PCB)
        n = drop_duplicate_tracks(board)
        board.Save(PCB)
        print(f"  Duplicates : {n} identical track segments dropped")
        return 0

    if name == "dangling":
        # manages its own load/save cycle: it re-runs DRC between rounds
        n = drop_dangling_tracks_via_drc(PCB, "/tmp/reflex-dangling-drc.json")
        print(f"  Dangling   : {n} dangling tracks/vias dropped")
        return 0

    if name == "clearance":
        fixed, stuck = repair_clearance(PCB, "/tmp/reflex-clearance-drc.json")
        note = f", {stuck} could not be resolved by sliding" if stuck else ""
        print(f"  Clearance  : {fixed} segments slid into legal space{note}")
        return 0

    board = load_board(PCB)
    if name == "silkedge":
        gone, made = trim_silk_to_board(board)
        msg = (
            f"  Silk edge  : {gone} silk graphics clipped to the board outline "
            f"-> {made} segments kept"
        )
    elif name == "silkfields":
        moved, kept, hidden = place_silk_fields(board)
        msg = (
            f"  Silk fields: {kept} already clear, {moved} relocated, "
            f"{hidden} hidden (no clear spot)"
        )
    else:
        raise SystemExit(f"finish_pcb: unknown pass {name!r}")
    board.Save(PCB)
    print(msg)
    return 0


def main():
    if len(sys.argv) > 1:
        return run_pass(sys.argv[1])

    import subprocess

    ATTEMPTS = 4  # see load_board(): pcbnew's init failure is intermittent
    for name in PASSES:
        for attempt in range(1, ATTEMPTS + 1):
            r = subprocess.run(
                [sys.executable, __file__, name], capture_output=True, text=True
            )
            if r.returncode == 0:
                # pcbnew chatters wx debug lines onto stdout; keep only the report
                for line in r.stdout.splitlines():
                    if line.strip().startswith(
                        ("Unshort", "Duplicates", "Dangling", "Clearance", "Silk")
                    ):
                        print(line)
                break
            if "DegradedBoard" in r.stderr and attempt < ATTEMPTS:
                continue  # fresh interpreter, try again
            print(r.stderr.rstrip(), file=sys.stderr)
            print(f"ERROR: finish_pcb pass {name!r} failed", file=sys.stderr)
            return 1

    print(f"  Finished   : {PCB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
