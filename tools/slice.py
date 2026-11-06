#!/usr/bin/env python3
"""Headless slicing of robot-buddy's printed parts (BACKLOG T4): real grams, print
time and support per part, and a .3mf per part (what Ben opens to print; nothing is
sent to the printer from here).

    python3 tools/slice.py                  # every part in PARTS
    python3 tools/slice.py --only plate,canopy
    python3 tools/slice.py --no-3mf         # G-code + numbers only

Ported from ~/fpv250/fpv250 (print/slicer_env.py, print/gen_presets.py,
print/slicemass.py; docs/print-settings.md §3). The traps that port carries:
  1. OrcaSlicer's Windows build prints nothing; the G-code header is the only record of
     what was applied and what it weighs. A missing G-code = a failed slice.
  2. The CLI does not resolve `inherits`, and says nothing: a sparse system preset
     slices at compiled-in defaults (PLA density, 0.2 layers). So every preset is
     flattened here (parents first, then `include`, then the leaf) and the G-code is
     checked against what was asked (CHECK keys) before any number is believed.
  3. A flattened filament needs `--curr-bed-type` (else -61).
  4. Machine and process go together in one `--load-settings` (else -17).
  5. `--export-3mf` with `--slice` fails (-13) after writing the G-code: two calls.

Orientation per part from docs/cad/loop/D3_print_orientation.md; the STL (part frame,
CAD/exports/gen) is turned so that axis points up and dropped onto the bed centre.
Process per 07 §4: >= 4 walls, 40 % gyroid. Grams are FILAMENT (support included where
it is on), checked against the CAD volume x rho of chassis.PART_MATERIAL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import trimesh

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(REPO, "CAD", "exports", "gen")
OUT = os.path.join(REPO, "CAD", "exports", "print")
STAGE = "/mnt/c/Users/Ben/robot-buddy-sw/slice"  # .bat + work files on a real C:\ path

ORCA_EXE = r"C:\Program Files\OrcaSlicer\orca-slicer.exe"
ORCA_SYS = "/mnt/c/Program Files/OrcaSlicer/resources/profiles/BBL"
ORCA_USER = "/mnt/c/Users/Ben/AppData/Roaming/OrcaSlicer/user/default"

# material -> (machine, process parent, filament parent, bed, rho g/cm3)
# PET-CF on the 0.6 hardened nozzle, PC on the 0.4 (print-bom); TPU on the 0.6 with
# Ben's belt presets (docs/cad/belt_print.md).
MATS = {
    "PET-CF": (
        "Bambu Lab P2S 0.6 nozzle",
        "0.24mm Balanced Quality @BBL P2S 0.6 nozzle",
        "Bambu PET-CF @BBL P2S",
        "Engineering Plate",
        1.29,
    ),
    "PC": (
        "Bambu Lab P2S 0.4 nozzle",
        "0.20mm Standard @BBL P2S",
        "Bambu PC @BBL P2S 0.4 nozzle",
        "Engineering Plate",
        1.20,
    ),
    # M6 (tick 83): Fiberon PA6-CF20, Ben's calibrated fpv250 preset on the 0.4 hardened
    # nozzle (290 °C, bed <= 50, fan off, flow 0.97: ~/fpv250/fpv250/docs/print-calibration.md);
    # not Bambu's PA6-CF profile, which is a different material
    "PA6-CF": (
        "Bambu Lab P2S 0.4 nozzle",
        "0.20mm Standard @BBL P2S",
        "fpv250 PA6-CF core_body filament",
        "Engineering Plate",
        1.17,
    ),
    "TPU": (
        "Bambu Lab P2S 0.6 nozzle",
        "robot-buddy belt TPU85A 0.6",
        "robot-buddy belt TPU85A hot",
        "Engineering Plate",  # Ben 2026-11-06: TPU goes on the engineering plate, not textured PEI
        1.22,
    ),
}

# 07 §4: >= 4 walls, >= 40 % gyroid. Pinned, not left to the parent (fpv250: grid vs
# crosshatch at the same density differ ~3 % in mass).
STRUCT = {
    "wall_loops": "4",
    "sparse_infill_density": "40%",
    "sparse_infill_pattern": "gyroid",
    "top_shell_layers": "5",
    "bottom_shell_layers": "4",
}
SUPPORT = {"enable_support": "1", "support_type": "tree(auto)"}

# stem -> (material, up axis, qty, support?, note). D3 orientation; qty per robot.
PARTS = {
    "RB-PRT-001_base_plate": (
        "PET-CF",
        "+z",
        1,
        True,
        "ribs down; tree support at the perimeter ledges (D3)",
    ),
    "RB-PRT-002_bulkhead": ("PET-CF", "-x", 1, False, "face down (D3)"),
    "RB-PRT-003_pi_deck": ("PET-CF", "+z", 1, False, "flat"),
    "RB-PRT-004_canopy": (
        "PC",
        "+x",
        1,
        True,
        "rear wall on the bed (Q26 a, Ben 2026-11-02): cross ribs 45° (tick 95); the hood back wall still needs support until its ramp",
    ),
    "RB-PRT-010_motor_mount_R": ("PET-CF", "+z", 1, False, "foot down"),
    "RB-PRT-011_motor_mount_L": ("PET-CF", "+z", 1, False, "foot down"),
    "RB-PRT-020_sprocket": ("PET-CF", "+z", 2, False, "outboard face down (08)"),
    "RB-PRT-021_idler": ("PET-CF", "+z", 2, False, "outboard face down (08)"),
    "RB-PRT-022_road_disc": ("PET-CF", "+z", 8, False, "bed face down"),
    "RB-PRT-030_carriage_L": ("PET-CF", "-x", 1, False, "front face down (D3)"),
    "RB-PRT-031_carriage_R": ("PET-CF", "-x", 1, False, "front face down (D3)"),
    "RB-PRT-040_trackframe_L": (
        "PET-CF",
        "-y",
        1,
        True,
        "outer face down (P13c: the road-axle shelf + blades stand off the inner face; tree support under the blades)",
    ),
    "RB-PRT-041_trackframe_R": (
        "PET-CF",
        "+y",
        1,
        True,
        "outer face down (P13c), tree support under the blades",
    ),
    # P7 / P8 (tick 93): speaker clamp (pad side up) and gasket, flat
    "RB-PRT-060_speaker_clamp": ("PET-CF", "+x", 1, False, "flat, pad up"),
    "RB-PRT-061_speaker_gasket": ("TPU", "+x", 1, False, "flat ring, 1 mm"),
    "RB-PRT-062_mic_washer": ("TPU", "+z", 6, False, "flat, 1 mm; 2 per mic-disc screw"),
    # T13 (tick 84): the belts and the 08 §7 test pieces, from drivetrain.py's exports
    # (CAD/exports/rnd/drivetrain, SRC below). qty 0 = test piece, not in the robot total.
    "belt_shrink0.56": ("TPU", "+z", 2, False, "upright ring, lugs in (belt_print.md); 0.56 % shrink"),
    "belt_strip150": ("TPU", "+z", 0, False, "test: hang / creep strip, standing"),
    "belt_lug6": ("TPU", "+z", 0, False, "test: 6-lug length, standing"),
    "coupon_ttbore_10": ("PET-CF", "+z", 0, False, "test: TT D-bore 0.10/side"),
    "coupon_624_10": ("PET-CF", "+z", 0, False, "test: 624 seat (M6: also --mat PA6-CF)"),
    "coupon_624_15": ("PET-CF", "+z", 0, False, "test: 624 seat"),
    "coupon_624_20": ("PET-CF", "+z", 0, False, "test: 624 seat"),
    "coupon_684_10": ("PET-CF", "+z", 0, False, "test: 684 seat (M6: also --mat PA6-CF)"),
    "coupon_band_slice": ("PET-CF", "+z", 0, False, "test: lug mesh on a TT"),
    # D6 (tick 89): follower-slide fit, native parts from chassis.py (CAD/exports/gen)
    "RB-CPN-001_slide_strip": ("PET-CF", "+z", 0, False, "test: guide slot pairs 4.5 / 4.7 / 4.9"),
    "RB-CPN-002_slide_rail": ("PET-CF", "-z", 0, False, "test: carriage rail stub, foot down"),
    "RB-CPN-003_insert_ladder": ("PET-CF", "+z", 0, False, "test: insert ladder M3 H/V + M2.5 (also --mat PC)"),
}
RND = os.path.join(REPO, "CAD", "exports", "rnd", "drivetrain")
SRC = {k: RND for k in PARTS if not k.startswith(("RB-PRT-", "RB-CPN-"))}  # drivetrain.py build output
ALIAS = {
    "plate": "RB-PRT-001_base_plate",
    "bulkhead": "RB-PRT-002_bulkhead",
    "deck": "RB-PRT-003_pi_deck",
    "canopy": "RB-PRT-004_canopy",
    "mounts": "RB-PRT-010_motor_mount_R,RB-PRT-011_motor_mount_L",
    "sprocket": "RB-PRT-020_sprocket",
    "idler": "RB-PRT-021_idler",
    "disc": "RB-PRT-022_road_disc",
    "carriages": "RB-PRT-030_carriage_L,RB-PRT-031_carriage_R",
    "frames": "RB-PRT-040_trackframe_L,RB-PRT-041_trackframe_R",
    "belts": "belt_shrink0.56",
    "tests": "belt_strip150,belt_lug6,coupon_ttbore_10,coupon_624_10,coupon_624_15,coupon_624_20,coupon_684_10,coupon_band_slice",
    "m6": "coupon_624_10,coupon_624_15,coupon_624_20,coupon_684_10",
    "slide": "RB-CPN-001_slide_strip,RB-CPN-002_slide_rail",
    "inserts": "RB-CPN-003_insert_ladder",
    "speaker": "RB-PRT-060_speaker_clamp,RB-PRT-061_speaker_gasket",
}


# --------------------------------------------------------------------- presets
class Profiles:
    """Orca's BBL system profiles plus the user presets, by preset name."""

    def __init__(self) -> None:
        self.idx: dict[str, str] = {}
        for root in (ORCA_USER, ORCA_SYS):  # user first: a user name shadows nothing
            for kind in ("filament", "process", "machine"):
                d = os.path.join(root, kind)
                if not os.path.isdir(d):
                    continue
                for dp, _, fs in os.walk(d):
                    for f in fs:
                        if f.endswith(".json"):
                            self.idx.setdefault(f[:-5], os.path.join(dp, f))

    def resolve(self, name: str) -> dict:
        if name not in self.idx:
            sys.exit(f"preset not found: {name!r}")
        with open(self.idx[name], encoding="utf-8") as fh:
            leaf = json.load(fh)
        out: dict = {}
        if leaf.get("inherits"):
            out.update(self.resolve(leaf["inherits"]))
        for inc in leaf.get("include") or []:
            if inc in self.idx:
                out.update(self.resolve(inc))
        out.update(leaf)
        out.pop("inherits", None)
        out.pop("include", None)
        return out


def write_presets(
    prof: Profiles, mat: str, support: bool, d: str
) -> tuple[str, str, str]:
    machine, process, filament, _, _ = MATS[mat]
    m = prof.resolve(machine)
    p = prof.resolve(process)
    f = prof.resolve(filament)
    tag = f"robot-buddy {mat}" + (" support" if support else "")
    if mat != "TPU":
        p.update(STRUCT)
    if support:
        p.update(SUPPORT)
    p.update(
        name=tag,
        print_settings_id=tag,
        **{"from": "User", "instantiation": "true", "compatible_printers": [machine]},
    )
    fname = f"robot-buddy {mat} filament"
    # the spool's density, not the parent's: Bambu's PC preset says 1.04 (PC is 1.20;
    # fpv250 §6: a wrong density under-reported LW-ASA 2.4x)
    nf = (
        len(f["filament_density"]) if isinstance(f.get("filament_density"), list) else 1
    )
    f["filament_density"] = [f"{MATS[mat][4]:g}"] * nf
    f.update(
        name=fname,
        filament_settings_id=[fname],
        **{"from": "User", "instantiation": "true", "compatible_printers": [machine]},
    )
    paths = []
    for kind, data in (("machine", m), ("process", p), ("filament", f)):
        path = os.path.join(d, f"{kind}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        paths.append(path)
    return paths[0], paths[1], paths[2]


# --------------------------------------------------------------------- geometry
def oriented(stem: str, up: str) -> trimesh.Trimesh:
    src = SRC.get(stem)
    m = trimesh.load(os.path.join(src, stem + ".stl") if src else os.path.join(GEN, stem + ".STL"))
    ax = {"x": 0, "y": 1, "z": 2}[up[1]]
    v = np.zeros(3)
    v[ax] = 1.0 if up[0] == "+" else -1.0
    R = trimesh.geometry.align_vectors(v, [0, 0, 1])
    m.apply_transform(R)
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return m


# --------------------------------------------------------------------- slicer
def winpath(p: str) -> str:
    return subprocess.run(
        ["wslpath", "-w", p], capture_output=True, text=True, check=True
    ).stdout.strip()


def run_orca(
    presets: tuple[str, str, str], bed: str, d: str, stl: str, extra: str = ""
) -> None:
    m, p, f = (winpath(x) for x in presets)
    bat = os.path.join(d, "run.bat")
    with open(bat, "w", newline="\r\n", encoding="utf-8") as fh:
        fh.write(
            "@echo off\n"
            f"cd /d {winpath(d)}\n"
            f'"{ORCA_EXE}" --load-settings "{m};{p}" --load-filaments "{f}"'
            f' --curr-bed-type "{bed}" {extra} --outputdir "{winpath(d)}" "{winpath(stl)}"\n'
        )
    subprocess.run(["cmd.exe", "/c", winpath(bat)], capture_output=True, cwd="/mnt/c")


# Keys the G-code must carry as asked (trap 2: a key you set is not a key that won).
CHECK = (
    "layer_height",
    "wall_loops",
    "sparse_infill_density",
    "filament_density",
    "enable_support",
)


def read_gcode(path: str) -> dict:
    t = open(path, errors="ignore").read()

    def grab(rx: str) -> str | None:
        m = re.search(rx, t, re.M)
        return m.group(1).strip() if m else None

    cfg = {
        k: grab(rf"^; {k} = (.*)$")
        for k in CHECK + ("filament_type", "sparse_infill_pattern")
    }
    return {
        "grams": float(grab(r"; filament used \[g\] = ([\d.]+)") or "nan"),
        "cm3": float(grab(r"; filament used \[cm3\] = ([\d.]+)") or "nan"),
        "time": grab(r"; model printing time: (.*?);")
        or grab(r"; estimated printing time.*= (.*)$"),
        "cfg": cfg,
    }


def slice_part(prof: Profiles, stem: str, threemf: bool, mat_override: str = "") -> dict:
    mat, up, qty, support, note = PARTS[stem]
    if mat_override:
        mat = mat_override
    machine, process, filament, bed, rho = MATS[mat]
    part = stem  # the STL it comes from
    if mat_override:  # an A/B in another material: its own files and record
        stem = f"{stem}@{mat}"
    d = os.path.join(STAGE, stem)
    os.makedirs(d, exist_ok=True)
    for fn in os.listdir(d):
        if fn.endswith((".gcode", ".3mf")):
            os.remove(os.path.join(d, fn))
    mesh = oriented(part, up)
    stl = os.path.join(d, stem + ".stl")
    mesh.export(stl)
    presets = write_presets(prof, mat, support, d)
    run_orca(presets, bed, d, stl, "--slice 0")
    g = [os.path.join(d, x) for x in os.listdir(d) if x.endswith(".gcode")]
    r = {
        "stem": stem,
        "mat": mat,
        "up": up,
        "qty": qty,
        "support": support,
        "note": note,
    }
    r["cad_g"] = mesh.volume / 1000 * rho
    r["h_mm"] = float(mesh.bounds[1][2])
    if not g:
        r["error"] = "no G-code (slice failed)"
        return r
    r.update(read_gcode(g[0]))
    want = {
        "wall_loops": None if mat == "TPU" else STRUCT["wall_loops"],
        "sparse_infill_density": None
        if mat == "TPU"
        else STRUCT["sparse_infill_density"],
        "filament_density": f"{rho:g}",
        "enable_support": "1" if support else "0",
    }
    bad = [
        f"{k}={r['cfg'].get(k)!r} (want {v})"
        for k, v in want.items()
        if v is not None and (r["cfg"].get(k) or "").rstrip("%") != v.rstrip("%")
    ]
    r["mismatch"] = bad
    os.makedirs(OUT, exist_ok=True)
    shutil.move(g[0], os.path.join(OUT, stem + ".gcode"))
    if threemf:
        mf = os.path.join(d, stem + ".3mf")
        # bare name: Orca joins --export-3mf to --outputdir
        run_orca(presets, bed, d, stl, f'--export-3mf "{stem}.3mf"')
        if os.path.exists(mf):
            shutil.move(mf, os.path.join(OUT, stem + ".3mf"))
            r["3mf"] = True
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-3mf", action="store_true")
    ap.add_argument("--mat", choices=list(MATS), default="", help="slice in another material (A/B)")
    a = ap.parse_args()
    keys = []
    for k in [x.strip() for x in a.only.split(",") if x.strip()] or list(PARTS):
        keys += ALIAS.get(k, k).split(",")
    prof = Profiles()
    rows = []
    for k in keys:
        r = slice_part(prof, k, not a.no_3mf, a.mat)
        rows.append(r)
        if "error" in r:
            print(f"{k:28s} {r['mat']:6s} {r['up']}  FAILED: {r['error']}", flush=True)
            continue
        flag = "  MISMATCH " + "; ".join(r["mismatch"]) if r["mismatch"] else ""
        print(
            f"{k:28s} {r['mat']:6s} {r['up']} x{r['qty']}  {r['grams']:7.1f} g sliced"
            f"  {r['cad_g']:6.1f} g solid  {r['grams'] / r['cad_g']:5.2f}"
            f"  {r['time']}{'  +support' if r['support'] else ''}{flag}",
            flush=True,
        )
    ok = [r for r in rows if "error" not in r]
    tot = sum(r["grams"] * r["qty"] for r in ok)
    cad = sum(r["cad_g"] * r["qty"] for r in ok)

    def minutes(t: str | None) -> float:
        u = {"d": 1440, "h": 60, "m": 1, "s": 1 / 60}
        return sum(float(n) * u[k] for n, k in re.findall(r"(\d+)([dhms])", t or ""))

    mins = sum(minutes(r["time"]) * r["qty"] for r in ok)
    print(
        f"TOTAL (x qty, {len(ok)}/{len(rows)} parts) {tot:.1f} g sliced vs {cad:.1f} g solid,"
        f" {mins / 60:.1f} h printing"
    )
    os.makedirs(OUT, exist_ok=True)
    rec_path = os.path.join(OUT, "sliced.json")
    rec = json.load(open(rec_path)) if os.path.exists(rec_path) else {}
    for r in ok:  # merge, never replace (fpv250: --only once wiped the other parts)
        rec[r["stem"]] = {
            k: r[k]
            for k in (
                "mat",
                "up",
                "qty",
                "support",
                "grams",
                "cm3",
                "time",
                "cad_g",
                "mismatch",
            )
        }
    json.dump(rec, open(rec_path, "w"), indent=1, sort_keys=True)
    print(f"wrote {os.path.relpath(rec_path, REPO)}")


if __name__ == "__main__":
    main()
