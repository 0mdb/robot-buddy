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
import math
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
# M1: Fiberon PA6-CF20, TDS V1.1 (as fpv250 params.yaml `pa6cf`). Dry: E 8636.5, UTS
# 109.3 / 54.0 Z (measured). Conditioned ("wet", 3.3 % water): E 2508, UTS XY 54.7;
# Z wet is not published, so it is scaled like XY (54.0 x 54.7 / 109.3 = 27.0) [assumption].
PA6CF_DRY = {
    "E": 0.8 * 8636.5e6,
    "nu": 0.35,
    "rho": 1170.0,
    "uts_z": 54.0e6,
    "uts_xy": 109.3e6,
}
PA6CF_COND = {
    "E": 0.8 * 2508.1e6,
    "nu": 0.35,
    "rho": 1170.0,
    "uts_z": 27.0e6,
    "uts_xy": 54.7e6,
}
MATERIALS = {"PET-CF": PETCF, "PA6CF_DRY": PA6CF_DRY, "PA6CF_COND": PA6CF_COND}
SF = 3.0

# 07 §3.4 loads. TBD: measure track tension with a spring scale at set-up.
TRACK_T = 20.0  # N per run
STALL_TORQUE = 0.25  # N*m, Yahboom 1:48 TT [assumption]
# P12: the drive wheel is the 08 sprocket; its pitch radius sets the tight-side excess.
# TRACK_T stays 20 N until the set-up spring-scale reading (08 designs for 10 N).
GEAR_R = chassis.dt.pitch_radius()
AXLE_F = 2 * TRACK_T + STALL_TORQUE / (GEAR_R / 1000)  # both runs + tight-side excess
STACK_MASS = 0.26  # kg: Pi 5 + NVMe + UPS HAT + 2 x 18650 [assumption]
SHOCK_G = 10.0  # quasi-static bump/drop factor on the deck [assumption]


def gear_centre() -> tuple[float, float, float]:
    """Drive-gear centre, left side, chassis frame: shaft station, gear plane, axle height."""
    x = chassis.mount_tx() - (chassis.MOUNT_HOLE[0] - chassis.MOT_SHAFT_X)
    y0, y1 = chassis.track_y()  # belt centre plane (08: |y| 74.5)
    return x, (y0 + y1) / 2, chassis.MOUNT_HOLE[2]


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
            "probe posts -77 -30 -1 37 30 25",
            "probe midplate -30 -50 -9 35 50 1",
            "mesh 2.0 0.1",
            f"case payload deck:0,0,{-f:.2f}",
        ],
        "applied": (0, 0, -f),
        "limit_disp_mm": 0.5,
    }


def s1d() -> dict:
    """Pi deck alone (P4): the stack's 10 g shock through its four M2.5 holes, deck
    held at the four M3 post holes (screw clamps; conservative: no bearing on the post tops)."""
    f = STACK_MASS * 9.81 * SHOCK_G
    z0, z1 = -chassis.DECK_T, 0.0  # deck part frame (top at z 0)
    return {
        "name": "S1d",
        "title": "Pi deck, stack payload (10 g)",
        "part": r"\CAD\parts\RB-PRT-003_pi_deck.SLDPRT",
        "lines": [
            "discard_open",
            f"fix cyl 0 0 1 {chassis.CLR_M3 / 2} 0.05",
            f"load pi cyl 0 0 1 {chassis.CLR_M25 / 2} 0.05",
            f"disp pi cyl 0 0 1 {chassis.CLR_M25 / 2} 0.05",
            f"probe deck -70 -35 {z0 - 1} 40 35 {z1 + 1}",
            "mesh 1.5 0.1",
            f"case payload pi:0,0,{-f:.2f}",
        ],
        "applied": (0, 0, -f),
        "limit_disp_mm": 0.5,
    }


def s6() -> dict:
    """Follower carriage (P5, left part): the belt pulls the idler toward the sprocket
    (+X) at the belt centre plane, through the axle bore. Held where it is held in use:
    the jack screw on the front face (x +10) and the clamp screw in its hole."""
    f = AXLE_F  # as S2 (both runs + the tight-side excess); the idler sees ~2 x TRACK_T
    yc = sum(chassis.track_y()) / 2
    za = chassis.dt.Z_AXLE
    return {
        "name": "S6",
        "title": "Follower carriage, belt tension at the idler axle",
        "part": r"\CAD\parts\RB-PRT-030_carriage_L.SLDPRT",
        "lines": [
            "discard_open",
            f"fix plane 1 0 0 {chassis.CAR_L / 2}",
            f"fix cyl 0 0 1 {chassis.INS_HOLE / 2} 0.05",  # the clamp insert (R2a)
            f"remote axle 0 {yc:.2f} {za} cyl 0 1 0 {chassis.CAR_BORE / 2} 0.05",
            f"disp bore cyl 0 1 0 {chassis.CAR_BORE / 2} 0.05",
            "hotspots 5",
            "mesh 1.0 0.05",
            f"case tension axle:{f:.2f},0,0",
        ],
        "applied": (f, 0, 0),
        "limit_disp_mm": 0.2,
    }


def s2() -> dict:
    """Motor mount v2 (RB-PRT-010, right side) in its own part frame (P2).

    The axle load acts at the drive-gear centre: shaft at part x -5.3, z 11.5; gear
    centre plane at part y = motor outer face (-28 + 22.6) + gap 1 + 31.6/2 = 11.4.
    Chassis rearward is the part's +x (Rz180). The motor bears on the upright's
    motor-side face (y = -28) and its two Ø3 screw holes: the remote load couples there.
    """
    hx, hy, hz = chassis.MOUNT_HOLE
    gx = hx - chassis.MOT_SHAFT_X
    gy = (
        hy + chassis.MOT_THICK + chassis.dt.SIDE_GAP + chassis.dt.BELT_W / 2
    )  # belt centre plane
    return {
        "name": "S2",
        "title": "Motor mount, track pull + stall torque",
        "part": r"\CAD\parts\RB-PRT-010_motor_mount_R.SLDPRT",
        "lines": [
            "discard_open",
            "fix plane 0 0 1 0",  # foot underside on the plate
            f"fix cyl 0 0 1 {chassis.CLR_M3 / 2} 0.05",  # 4 foot screw holes
            f"remote axle {gx:.2f} {gy:.2f} {hz:.2f} cyl 0 1 0 {chassis.INS_HOLE / 2} 0.05",  # motor-screw inserts
            f"remote axle {gx:.2f} {gy:.2f} {hz:.2f} plane 0 1 0 {hy}",  # motor bears on the face
            f"disp motorholes cyl 0 1 0 {chassis.INS_HOLE / 2} 0.05",
            "hotspots 5",  # T9: where the peaks are
            "probe root -22 -40 -1 21 -27 9",  # upright-to-foot junction, inboard chamfer
            "probe holes 10 -35 0 19 -27 27",
            "probe gusset -21 -35 2 -16 -8 23",
            "mesh 1.0 0.05",
            f"case pull axle:{AXLE_F:.2f},0,0",
            f"case pull_torque axle:{AXLE_F:.2f},0,0,0,{STALL_TORQUE},0",
            "case up axle:0,0,10",
        ],
        "applied": None,  # remote loads: reaction sum checked against the pull case below
        "limit_disp_mm": 0.2,
    }


def s5(canopy: bool = False) -> dict:
    """Bulkhead: a child pokes the screen (load through the face board into its four
    standoff inserts) or pushes the bezel (load on the front face). 50 N into the robot,
    along the tilted wall's normal. Held at the foot underside and its insert pockets."""
    t = math.radians(chassis.BH_TILT)
    n = (
        math.cos(t),
        0.0,
        math.sin(t),
    )  # front-face normal after the tilt (forward, up)
    piv = chassis.BH_PIVOT
    front = chassis._rotate_y([chassis.BH_XF, 0.0, 0.0], -chassis.BH_TILT, piv)
    d = sum(a * b for a, b in zip(n, front))
    scr = chassis._rotate_y(
        [chassis.BH_XF - chassis.BH_T, 0.0, chassis.BH_FACE_Z], -chassis.BH_TILT, piv
    )
    f = 50.0
    F = tuple(-f * c for c in n)
    ax = f"{n[0]:.9f} 0 {n[2]:.9f}"
    # with the canopy on, its screws hold the two lugs (pre-tilt axis z -> tilted)
    lug_ax = f"{-math.sin(t):.9f} 0 {math.cos(t):.9f}"
    extra = [f"fix cyl {lug_ax} 2.0 0.05"] if canopy else []
    return {
        "name": "S5c" if canopy else "S5",
        "title": "Bulkhead, 50 N poke"
        + (", canopy lugs held" if canopy else ", standalone"),
        "part": r"\CAD\parts\RB-PRT-002_bulkhead.SLDPRT",
        "lines": [
            "discard_open",
            "fix plane 0 0 1 0",  # foot underside on the plate
            "fix cyl 0 0 1 2.0 0.05",  # foot + knee-pad insert pockets (F1)
            *extra,
            f"remote screen {scr[0]:.3f} {scr[1]:.3f} {scr[2]:.3f} cyl {ax} 2.0 0.05",
            f"load bezel plane {n[0]:.9f} 0 {n[2]:.9f} {d:.4f}",
            f"disp standoffs cyl {ax} 2.0 0.05",
            f"disp bezel plane {n[0]:.9f} 0 {n[2]:.9f} {d:.4f}",
            "probe foot 76 -48 -4 86 48 12",
            "probe window 40 -32 40 86 32 110",
            "mesh 2.0 0.1",
            f"case screen screen:{F[0]:.3f},{F[1]:.3f},{F[2]:.3f}",
            f"case bezel bezel:{F[0]:.3f},{F[1]:.3f},{F[2]:.3f}",
        ],
        "applied": F,
        "limit_disp_mm": 0.5,
    }


def s1m() -> dict:
    """S1a on the multi-body part (T10): plate + both mount v2 bodies merged (bonded).
    The axle load enters each mount through its motor face + motor inserts (as S2), so
    the feet bear on the plate over their footprint; held at the jack-screw bores."""
    gx, gy, gz = gear_centre()
    f = AXLE_F
    face = (
        chassis.MOUNT_HOLE[1] + chassis.mount_ty()
    )  # |y| of the motor faces: -28 + 60.4 = 32.4
    ins = chassis.INS_HOLE / 2
    lines = ["discard_open", "fix cyl 1 0 0 2.0 0.05"]
    for name, sgn in (("left", 1), ("right", -1)):
        y0, y1 = sorted((sgn * (face - 7.5), sgn * (face + 0.5)))
        lines += [
            f"remote {name} {gx:.2f} {sgn * gy:.2f} {gz:.2f} cyl 0 1 0 {ins} 0.05 box 25 {y0} 0 80 {y1} 27",
            f"remote {name} {gx:.2f} {sgn * gy:.2f} {gz:.2f} plane 0 1 0 {sgn * face:.3f}",
        ]
    lines += [
        f"disp inserts cyl 0 1 0 {ins} 0.05",
        "probe pockets 38 -60 -9 82 60 1",
        "probe jackstops -40 -45 -1 -26 45 11",
        "probe midplate -20 -50 -9 35 50 1",
        "probe mounts 25 -52 0 80 52 27",
        "hotspots 5",
        "mesh 1.5 0.08",
        f"case tension left:{-f:.2f},0,0 right:{-f:.2f},0,0",
    ]
    return {
        "name": "S1m",
        "title": "Plate + mounts (bonded), track tension at the axles",
        "part": r"\CAD\fea\FEA-plate_mounts.SLDPRT",
        "lines": lines,
        "applied": (-2 * f, 0, 0),
        "limit_disp_mm": 0.2,
    }


STUDIES = {
    "S1m": s1m,
    "S1d": s1d,
    "S6": s6,
    "S1a": s1a,
    "S1b": s1b,
    "S2": s2,
    "S5": s5,
    "S5c": lambda: s5(canopy=True),
}


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


def kill_swsim(proc) -> None:
    """Kill swsim.exe itself: killing the cmd.exe wrapper leaves it orphaned (tick 6)."""
    subprocess.run(
        ["taskkill.exe", "/IM", "swsim.exe", "/F"], capture_output=True, cwd="/mnt/c"
    )
    proc.kill()


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
            # A window without buttons can't be a prompt waiting for an answer: SolidWorks
            # keeps a notification template ("Title | Description | Button1 ...", no real
            # buttons) open all the time (tick 6 false positive).
            if ln.startswith("DIALOG") and ln.endswith("buttons=[]"):
                continue
            print(f"  [watchdog {time.monotonic() - t0:5.0f} s] {ln}")
            if ln.startswith("DIALOG"):
                hwnd = ln.split()[1]
                seen[hwnd] = seen.get(hwnd, 0) + 1
                if seen[hwnd] == UNKNOWN_DIALOG_POLLS + 1:  # warn once, keep waiting
                    print(
                        f"  [watchdog] WARNING unknown dialog {hwnd} still up: answer it by hand. {ln}"
                    )
        if time.monotonic() - t0 > MAX_RUN_S:
            kill_swsim(proc)
            sys.exit(f"swsim ran longer than {MAX_RUN_S} s")
    reader.join(timeout=10)
    return "".join(chunks).replace("\r", "")


def run_study(
    st: dict, exe: str, dry: bool, mesh_scale: float = 1.0, material: str = "PET-CF"
) -> str:
    stage = sw.staging()
    win = sw.winpath(stage)
    tag = st["name"] + ("" if mesh_scale == 1.0 else f"_m{mesh_scale:g}")
    tag += "" if material == "PET-CF" else f"_{material}"
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
    m = MATERIALS[material]
    lines = [
        f"part {win}{st['part']}",
        f"out {sw.winpath(out)}",
        f"material {m['E']:.4g} {m['nu']} {m['rho']} {m['uts_z']:.4g} {material}",
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
    ap.add_argument("--material", choices=list(MATERIALS), default="PET-CF")
    a = ap.parse_args()
    tool = os.path.join(sw.staging(), "tools")
    exe = "" if a.dry_run else compile_sim(tool)
    for name in a.studies:
        st = STUDIES[name]()
        path = run_study(st, exe, a.dry_run, a.mesh_scale, a.material)
        if path:
            with open(path) as fh:
                for row in csv.DictReader(fh):
                    print("   ", row)


if __name__ == "__main__":
    main()
