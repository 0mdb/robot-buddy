#!/usr/bin/env python3
"""Read the fab zip the way a fab's importer would (gerbonara, not KiCad) and check it.

    uv run --no-project --with gerbonara==1.5.0 python -I gerber_check.py ZIP OUTDIR [W H]

W H: the board size in mm (pcb_qc.py passes board_outline.W/H). Runs isolated (-I), so it
can't import board_outline itself; without them the outline size is reported, not checked.

Called by pcb_qc.py. Prints "PASS|FAIL|WARN message" lines; exit 1 on FAIL. Writes one
black-on-white PNG per layer plus sheet.png to OUTDIR (needs ImageMagick's convert/montage).
"""

import subprocess
import sys
import warnings
from pathlib import Path

from gerbonara import LayerStack

warnings.filterwarnings("ignore")
zip_path, out = Path(sys.argv[1]), Path(sys.argv[2])
want_wh = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else None
out.mkdir(parents=True, exist_ok=True)
fails = 0


def say(ok: bool, msg: str, warn: bool = False) -> None:
    global fails
    print(("PASS" if ok else ("WARN" if warn else "FAIL")), msg)
    fails += 0 if ok or warn else 1


ls = LayerStack.open(str(zip_path))
want = [
    ("top", "copper"),
    ("inner_1", "copper"),
    ("inner_2", "copper"),
    ("bottom", "copper"),
    ("top", "mask"),
    ("bottom", "mask"),
    ("top", "silk"),
    ("bottom", "silk"),
]
have = set(ls.graphic_layers)
say(
    all(w in have for w in want) and ls.outline is not None,
    f"gerbonara identifies {len(have)} layers + outline from file names alone "
    f"{[w for w in want if w not in have] or ''}",
)
drills = list(ls.drill_layers)
say(len(drills) >= 2, f"drill files read: {[d.original_path.name for d in drills]}")

(ox0, oy0), (ox1, oy1) = ls.outline.bounding_box()
if want_wh:
    say(
        abs((ox1 - ox0) - want_wh[0] - 0.05) < 0.1
        and abs((oy1 - oy0) - want_wh[1] - 0.05) < 0.1,
        f"outline {ox1 - ox0:.2f} x {oy1 - oy0:.2f} mm ({want_wh[0]:g} x {want_wh[1]:g} + line width)",
    )
else:
    print(
        f"info outline {ox1 - ox0:.2f} x {oy1 - oy0:.2f} mm (no size given, not checked)"
    )
tol = 0.01
for key, layer in sorted(ls.graphic_layers.items()):
    bb = layer.bounding_box()
    if bb is None:  # empty layer (e.g. B.Paste: no bottom SMD parts)
        print("info", f"{key[0]} {key[1]} is empty")
        continue
    (x0, y0), (x1, y1) = bb
    inside = x0 >= ox0 - tol and y0 >= oy0 - tol and x1 <= ox1 + tol and y1 <= oy1 + tol
    # silk past the edge (connector bodies overhang) is clipped by the fab: warn only
    say(inside, f"{key[0]} {key[1]} inside the outline", warn=key[1] == "silk")
for d in drills:
    (x0, y0), (x1, y1) = d.bounding_box()
    say(
        x0 >= ox0 and y0 >= oy0 and x1 <= ox1 and y1 <= oy1,
        f"drill {d.original_path.name} inside the outline",
    )

# layer sheet for a person to look at
bounds = ls.outline.bounding_box()
pngs = []
order = [
    ("top", "copper"),
    ("inner_1", "copper"),
    ("inner_2", "copper"),
    ("bottom", "copper"),
    ("top", "mask"),
    ("top", "silk"),
    ("bottom", "mask"),
    ("bottom", "silk"),
]
for key in order:
    if key in ls.graphic_layers:
        svg = out / f"L_{key[0]}_{key[1]}.svg"
        svg.write_text(
            str(
                ls.graphic_layers[key].to_svg(
                    fg="black", bg="white", margin=1, force_bounds=bounds
                )
            )
        )
        pngs.append(svg.with_suffix(".png"))
for i, d in enumerate(drills):
    svg = out / f"L_drill{i}.svg"
    svg.write_text(str(d.to_svg(fg="black", bg="white", margin=1, force_bounds=bounds)))
    pngs.append(svg.with_suffix(".png"))
try:
    for p in pngs:
        subprocess.run(
            ["convert", "-density", "400", str(p.with_suffix(".svg")), str(p)],
            check=True,
            capture_output=True,
        )
        p.with_suffix(".svg").unlink()
    subprocess.run(
        [
            "montage",
            *map(str, pngs),
            "-tile",
            "4x",
            "-geometry",
            "700x650+8+8",
            "-background",
            "gray",
            str(out / "sheet.png"),
        ],
        check=True,
        capture_output=True,
    )
    say(
        True,
        f"layer sheet: {out / 'sheet.png'} (top row: F.Cu In1 In2 B.Cu; then masks/silk; drills)",
    )
    # silk ink on exposed copper (first-order defect): silk pixels inside mask openings
    for side in ("top", "bottom"):
        silk, mask = out / f"L_{side}_silk.png", out / f"L_{side}_mask.png"
        if not (silk.exists() and mask.exists()):
            continue
        px = subprocess.run(
            [
                "convert",
                "(",
                str(silk),
                "-threshold",
                "50%",
                "-negate",
                ")",
                "(",
                str(mask),
                "-threshold",
                "50%",
                "-negate",
                ")",
                "-compose",
                "Multiply",
                "-composite",
                "-format",
                "%[fx:round(mean*w*h)]",
                "info:",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        say(px == "0", f"{side} silk inside mask openings: {px} px at 400 dpi")
except (OSError, subprocess.CalledProcessError) as e:
    say(False, f"layer sheet not rendered ({e})", warn=True)
sys.exit(1 if fails else 0)
