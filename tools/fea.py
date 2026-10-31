#!/usr/bin/env python3
"""FEA studies for robot-buddy's chassis (docs/cad/07_materials_fasteners_fea.md §3).

    python3 tools/fea.py            # run every study, write docs/cad/fea/results.md
    python3 tools/fea.py S2         # one study
    python3 tools/fea.py -n         # write the manifests only

Each study is a linear static run of tools/swsim.cs on one native part. Results are
read against 07 §3.4: deflection and stress, PET-CF judged on its Z strength.
Loads marked TBD are assumptions until measured (track tension, motor torque).
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chassis  # noqa: E402
import sw  # noqa: E402

# 07 §3.2: E = 0.8 x E(X-Y), strength judged on Z UTS, static SF >= 3.
PETCF = {"E": 0.8 * 4730e6, "nu": 0.35, "rho": 1290.0, "uts_z": 35e6, "uts_xy": 74e6}
SF = 3.0

# 07 §3.4 loads. TBD: measure track tension with a spring scale at set-up.
TRACK_T = 20.0  # N per run
STALL_TORQUE = 0.25  # N*m, Yahboom 1:48 TT [assumption]
GEAR_R = 54.34 / 2
AXLE_F = 2 * TRACK_T + STALL_TORQUE / (GEAR_R / 1000)  # both runs + tight-side excess
STACK_MASS = 0.26  # kg: Pi 5 + NVMe + UPS HAT + 2 x 18650 [assumption]
SHOCK_G = 10.0  # quasi-static bump/drop factor on the deck [assumption]


def gear_centre() -> tuple[float, float, float]:
    """Drive-gear centre, left side, chassis frame: shaft station, gear plane, axle height."""
    x = chassis.mount_tx() - (chassis.MOUNT_HOLE[0] - chassis.MOT_SHAFT_X)
    y = chassis.PLATE_W / 2 + chassis.GEAR_GAP + chassis.GEAR_W / 2
    return x, y, chassis.MOUNT_HOLE[2]


def s1a() -> dict:
    """Plate: track tension. The axle pull acts at each drive-gear centre (remote load,
    coupled to that side's four mount-insert pockets); the jack-screw bores hold."""
    gx, gy, gz = gear_centre()
    f = AXLE_F
    return {
        "name": "S1a",
        "title": "Plate, track tension at the axles",
        "part": r"\CAD\parts\RB-PRT-001_base_plate.SLDPRT",
        "lines": [
            "discard_open",
            "fix cyl 1 0 0 2.0 0.05",  # jack-screw insert bores (only X-axis cylinders of r 2)
            f"remote left {gx:.2f} {gy:.2f} {gz:.2f} cyl 0 0 1 2.0 0.05 box 40 0 -9 80 60 1",
            f"remote right {gx:.2f} {-gy:.2f} {gz:.2f} cyl 0 0 1 2.0 0.05 box 40 -60 -9 80 0 1",
            "disp mounts cyl 0 0 1 2.0 0.05 box 40 -60 -9 80 60 1",
            "probe pockets 38 -60 -9 82 60 1",
            "probe jackstops -40 -45 -1 -26 45 11",
            "probe midplate -20 -50 -9 35 50 1",
            "mesh 2.0 0.1",
            f"case tension left:{-f:.2f},0,0 right:{-f:.2f},0,0",
        ],
        "applied": (-2 * f, 0, 0),
        "limit_disp_mm": 0.2,
    }


def s1b() -> dict:
    """Plate: Pi stack payload on the deck posts, held at the drive and follower stations."""
    f = STACK_MASS * 9.81 * SHOCK_G
    return {
        "name": "S1b",
        "title": "Plate, deck payload (10 g on the Pi stack)",
        "part": r"\CAD\parts\RB-PRT-001_base_plate.SLDPRT",
        "lines": [
            "discard_open",
            "fix cyl 1 0 0 2.0 0.05",
            "fix cyl 0 0 1 2.0 0.05 box 40 -60 -9 80 60 1",
            f"load deck plane 0 0 1 {chassis.DECK_Z}",
            f"disp deck plane 0 0 1 {chassis.DECK_Z}",
            "probe posts -55 -30 -1 37 30 25",
            "probe midplate -30 -50 -9 35 50 1",
            "mesh 2.0 0.1",
            f"case payload deck:0,0,{-f:.2f}",
        ],
        "applied": (0, 0, -f),
        "limit_disp_mm": 0.5,
    }


def s2() -> dict:
    """Motor mount (TT_Motor_Mount_L, right side) in its own part frame.

    The axle load acts at the drive-gear centre: shaft at part x -5.3, z 11.5; gear
    centre plane at part y = motor outer face (-28 + 22.6) + gap 1 + 31.6/2 = 11.4.
    Chassis rearward is the part's +x (Rz180). The motor bears on the upright's
    motor-side face (y = -28) and its two Ø3 screw holes: the remote load couples there.
    """
    hx, hy, hz = chassis.MOUNT_HOLE
    gx = hx - chassis.MOT_SHAFT_X
    gy = hy + chassis.MOT_THICK + chassis.GEAR_GAP + chassis.GEAR_W / 2
    return {
        "name": "S2",
        "title": "Motor mount, track pull + stall torque",
        "part": r"\CAD\parts\TT_Motor_Mount_L.SLDPRT",
        "lines": [
            "fix plane 0 0 1 0",  # foot underside on the plate
            "fix cyl 0 0 1 1.75 0.05",  # 4 foot screw holes
            f"remote axle {gx:.2f} {gy:.2f} {hz:.2f} cyl 0 1 0 1.5 0.05",
            f"remote axle {gx:.2f} {gy:.2f} {hz:.2f} plane 0 1 0 {hy}",
            "disp motorholes cyl 0 1 0 1.5 0.05",
            "probe root -20 -32 -1 21 -27 5",  # upright-to-foot junction
            "probe holes 10 -32 0 19 -27 23",
            "probe gusset -21 -32 2 -16 -8 20",
            "mesh 1.0 0.05",
            f"case pull axle:{AXLE_F:.2f},0,0",
            f"case pull_torque axle:{AXLE_F:.2f},0,0,0,{STALL_TORQUE},0",
            "case up axle:0,0,10",
        ],
        "applied": None,  # remote loads: reaction sum checked against the pull case below
        "limit_disp_mm": 0.2,
    }


STUDIES = {"S1a": s1a, "S1b": s1b, "S2": s2}


def compile_sim(tool: str) -> str:
    shutil.copyfile(
        os.path.join(sw.REPO, "tools", "swsim.cs"), os.path.join(tool, "swsim.cs")
    )
    dlls = (*sw.DLLS, "SolidWorks.Interop.cosworks.dll")
    for dll in dlls:
        if not os.path.exists(os.path.join(tool, dll)):
            shutil.copyfile(os.path.join(sw.SWAPI, dll), os.path.join(tool, dll))
    w = sw.winpath(tool)
    refs = " ".join(f'/reference:"{w}\\{d}"' for d in dlls)
    bat = os.path.join(tool, "build_swsim.bat")
    with open(bat, "w", newline="") as fh:
        fh.write(
            f'@echo off\r\n"{sw.CSC}" /nologo /target:exe /platform:x64 '
            f'/out:"{w}\\swsim.exe" {refs} "{w}\\swsim.cs"\r\n'
        )
    r = subprocess.run(
        ["cmd.exe", "/c", sw.winpath(bat)], capture_output=True, text=True, cwd="/mnt/c"
    )
    if r.returncode or "error CS" in r.stdout:
        sys.exit(r.stdout.replace("\r", "") + "csc failed")
    return w + "\\swsim.exe"


POLL_S = 20  # dialog watchdog period
UNKNOWN_DIALOG_POLLS = (
    3  # an unknown dialog still up after this many polls fails the run
)
MAX_RUN_S = 3 * 3600


def dialogs(answer: bool) -> list[str]:
    """Run tools/swdialog.ps1: report (and with answer=True, answer known) modal
    dialogs owned by the solver (star.exe) or SolidWorks."""
    tool = os.path.join(sw.staging(), "tools")
    shutil.copyfile(
        os.path.join(sw.REPO, "tools", "swdialog.ps1"),
        os.path.join(tool, "swdialog.ps1"),
    )
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        sw.winpath(os.path.join(tool, "swdialog.ps1")),
    ]
    if answer:
        args.append("-Answer")
    r = subprocess.run(args, capture_output=True, text=True, cwd="/mnt/c", timeout=120)
    return [
        ln.strip()
        for ln in r.stdout.replace("\r", "").splitlines()
        if ln.strip().startswith(("DIALOG", "ANSWERED"))
    ]


def run_watched(exe: str, man: str) -> str:
    """Run swsim while polling for blocking dialogs (BACKLOG T8). A solver dialog leaves
    SolidWorks idle and 'not responding' forever, so a plain blocking call would hang."""
    import threading
    import time

    proc = subprocess.Popen(
        ["cmd.exe", "/c", exe, sw.winpath(man)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        cwd="/mnt/c",
    )
    chunks: list[str] = []
    reader = threading.Thread(target=lambda: chunks.extend(proc.stdout), daemon=True)
    reader.start()
    t0, seen = time.monotonic(), {}
    while proc.poll() is None:
        time.sleep(POLL_S)
        for ln in dialogs(answer=True):
            print(f"  [watchdog {time.monotonic() - t0:5.0f} s] {ln}")
            if ln.startswith("DIALOG"):
                hwnd = ln.split()[1]
                seen[hwnd] = seen.get(hwnd, 0) + 1
                if seen[hwnd] > UNKNOWN_DIALOG_POLLS:
                    proc.kill()
                    sys.exit(
                        f"unknown dialog {hwnd} is blocking the solver: {ln}  (answer it by hand)"
                    )
        if time.monotonic() - t0 > MAX_RUN_S:
            proc.kill()
            sys.exit(f"swsim ran longer than {MAX_RUN_S} s")
    reader.join(timeout=10)
    return "".join(chunks).replace("\r", "")


def run_study(st: dict, exe: str, dry: bool, mesh_scale: float = 1.0) -> str:
    stage = sw.staging()
    win = sw.winpath(stage)
    tag = st["name"] + ("" if mesh_scale == 1.0 else f"_m{mesh_scale:g}")
    out = os.path.join(stage, "fea", tag)
    if mesh_scale != 1.0:  # convergence run (07 §3.1): same study, finer mesh
        st = dict(st)
        st["lines"] = [
            f"mesh {float(ln.split()[1]) * mesh_scale:g} {float(ln.split()[2]) * mesh_scale:g}"
            if ln.startswith("mesh ")
            else ln
            for ln in st["lines"]
        ]
    os.makedirs(out, exist_ok=True)
    m = PETCF
    lines = [
        f"part {win}{st['part']}",
        f"out {sw.winpath(out)}",
        f"material {m['E']:.4g} {m['nu']} {m['rho']} {m['uts_z']:.4g} PET-CF",
        *st["lines"],
    ]
    man = os.path.join(stage, "tools", f"fea_{tag}.txt")
    with open(man, "w", newline="") as fh:
        fh.write("\r\n".join(lines) + "\r\n")
    print(f"== {st['name']}: {st['title']}  ({man})")
    if dry:
        print("\n".join(lines))
        return ""
    text = run_watched(exe, man)
    print(text, end="")
    if "SIM OK" not in text:
        sys.exit(f"{st['name']}: swsim did not report SIM OK")
    # equilibrium: the fixture must react exactly the applied total (catches per-face loads)
    if st["applied"]:
        for line in text.splitlines():
            if "reaction sum (" in line:
                got = [float(v) for v in line.split("(")[1].split(")")[0].split(",")]
                err = max(abs(g + a) for g, a in zip(got, st["applied"]))
                ok = err <= 0.01 * max(abs(a) for a in st["applied"]) + 0.05
                print(
                    f"  {'ok' if ok else 'FAIL'}   equilibrium: reaction {got} vs applied {st['applied']}"
                )
                if not ok:
                    sys.exit(f"{st['name']}: reactions do not balance the applied load")
    return os.path.join(out, "results.csv")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("studies", nargs="*", default=list(STUDIES))
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument(
        "--mesh-scale", type=float, default=1.0, help="0.5 = convergence run"
    )
    a = ap.parse_args()
    tool = os.path.join(sw.staging(), "tools")
    exe = "" if a.dry_run else compile_sim(tool)
    for name in a.studies:
        st = STUDIES[name]()
        path = run_study(st, exe, a.dry_run, a.mesh_scale)
        if path:
            with open(path) as fh:
                for row in csv.DictReader(fh):
                    print("   ", row)


if __name__ == "__main__":
    main()
