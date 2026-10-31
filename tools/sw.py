#!/usr/bin/env python3
"""WSL <-> SOLIDWORKS plumbing for robot-buddy's CAD.

The repo's CAD/ is the master. SOLIDWORKS cannot open \\\\wsl.localhost\\ paths,
so it works on a mirror under C:\\Users\\<you>\\robot-buddy-sw\\CAD and we sync:

    python3 tools/sw.py push [-n]       # repo CAD/ -> Windows mirror
    python3 tools/sw.py pull [-n]       # Windows mirror -> repo CAD/  (then commit)
    python3 tools/sw.py probe           # attach to the running SOLIDWORKS, list open docs
    python3 tools/sw.py refs CAD/assemblies/RB-ASM-100_chassis.SLDASM

push/pull never overwrite a newer file on the receiving side (rsync --update),
and print every change. Close documents in SOLIDWORKS before `pull` -- a
"~$name" lock file means unsaved work may still be in memory.

Rules and the API reference: .claude/skills/solidworks/SKILL.md,
docs/cad/solidworks-api.md.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAD = os.path.join(REPO, "CAD")
CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
SWAPI = "/mnt/c/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist"
DLLS = ("SolidWorks.Interop.sldworks.dll", "SolidWorks.Interop.swconst.dll")
EXCLUDE = (
    "~$*",
    "*.~*",
    "*.SLDBAK",
    "Backup/",
    "SOLIDWORKS Backup*/",
    "desktop.ini",
    # Simulation results written next to studied parts (tools/fea.py): never pull them
    "*.CWR",
    "*.gsz",
    "*.LOG",
    "PerformanceLog.txt",
)


def winpath(p: str) -> str:
    return subprocess.run(
        ["wslpath", "-w", p], capture_output=True, text=True, check=True
    ).stdout.strip()


def staging() -> str:
    users = glob.glob("/mnt/c/Users/*/")
    me = next(
        u
        for u in users
        if os.path.basename(u.rstrip("/"))
        not in ("Public", "Default", "Default User", "All Users")
    )
    return os.path.join(me, "robot-buddy-sw")


def sync(src: str, dst: str, dry: bool) -> None:
    os.makedirs(dst, exist_ok=True)
    # --modify-window: NTFS via drvfs rounds mtimes; don't let that look like an edit.
    cmd = ["rsync", "-rt", "--update", "--modify-window=2", "--itemize-changes"]
    cmd += [f"--exclude={e}" for e in EXCLUDE]
    if dry:
        cmd.append("--dry-run")
    r = subprocess.run(
        [*cmd, src.rstrip("/") + "/", dst.rstrip("/") + "/"],
        capture_output=True,
        text=True,
    )
    changed = [ln for ln in r.stdout.splitlines() if ln.startswith(">f")]
    for ln in changed:
        print(ln)
    if r.returncode:
        sys.exit(f"rsync failed ({r.returncode}): {r.stderr.strip()}")
    print(f"{'would copy' if dry else 'copied'} {len(changed)} file(s): {src} -> {dst}")


def locks(root: str) -> list[str]:
    return [
        os.path.join(d, f)
        for d, _, fs in os.walk(root)
        for f in fs
        if f.startswith("~$")
    ]


def run_probe(*args: str) -> None:
    tool = os.path.join(staging(), "tools")
    os.makedirs(tool, exist_ok=True)
    shutil.copyfile(
        os.path.join(REPO, "tools", "swprobe.cs"), os.path.join(tool, "swprobe.cs")
    )
    for dll in (
        DLLS
    ):  # must sit next to the exe or it throws FileNotFoundException at run time
        if not os.path.exists(os.path.join(tool, dll)):
            shutil.copyfile(os.path.join(SWAPI, dll), os.path.join(tool, dll))
    w = winpath(tool)
    refs = " ".join(f'/reference:"{w}\\{d}"' for d in DLLS)
    # A .bat, not an inline command: cmd.exe /c mangles quoted argv from WSL.
    bat = os.path.join(tool, "build_swprobe.bat")
    with open(bat, "w", newline="") as fh:
        fh.write(
            f'@echo off\r\n"{CSC}" /nologo /target:exe /platform:x64 '
            f'/out:"{w}\\swprobe.exe" {refs} "{w}\\swprobe.cs"\r\n'
        )
    r = subprocess.run(
        ["cmd.exe", "/c", winpath(bat)], capture_output=True, text=True, cwd="/mnt/c"
    )
    if r.returncode or "error CS" in r.stdout:
        sys.exit(r.stdout.replace("\r", "") + "csc failed")
    r = subprocess.run(
        ["cmd.exe", "/c", f"{w}\\swprobe.exe", *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd="/mnt/c",
    )
    out = r.stdout.replace("\r", "")
    print(out, end="")
    # cmd.exe swallows .NET exit codes through WSL interop -- trust the tool's last line.
    if "PROBE OK" not in out:
        sys.exit("swprobe did not report PROBE OK")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("push", "pull"):
        sub.add_parser(name).add_argument("-n", "--dry-run", action="store_true")
    sub.add_parser("probe")
    sub.add_parser("refs").add_argument(
        "file", help="repo path under CAD/, e.g. CAD/assemblies/X.SLDASM"
    )
    a = ap.parse_args()

    mirror = os.path.join(staging(), "CAD")
    if a.cmd == "push":
        sync(CAD, mirror, a.dry_run)
    elif a.cmd == "pull":
        held = locks(mirror)
        for f in held:
            print(
                f"warning: SOLIDWORKS lock {f} -- that document is open; save and close it first"
            )
        sync(mirror, CAD, a.dry_run)
    elif a.cmd == "probe":
        run_probe()
    elif a.cmd == "refs":
        rel = os.path.relpath(os.path.abspath(a.file), CAD)
        if rel.startswith(".."):
            sys.exit(f"{a.file} is not under CAD/")
        run_probe("refs", winpath(os.path.join(mirror, rel)))


if __name__ == "__main__":
    main()
