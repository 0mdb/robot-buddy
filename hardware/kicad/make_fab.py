#!/usr/bin/env python3
"""
Generate the fabrication package for robot-buddy-reflex: gerbers, drill, BOM, CPL.

Refuses to produce anything unless DRC is clean and both pre-fab gates pass. That
refusal is the point of this script existing. Register P5: the previous gerbers sat
in the repo for weeks encoding the E1 battery short, passed the routing gate (which
asks whether copper exists, not whether the netlist was right), and needed a
DO-NOT-FABRICATE.md placed next to them by hand to stop anyone uploading them. A fab
package that cannot be generated from a failing board cannot become scrap.

The BOM and the CPL are derived from ONE list, never maintained separately —
register O1: the v1 BOM listed parts deleted in v2 (U3, R11), omitted every v2 part
(U4, R12-R17), disagreed with the schematic on R6, and had no entry at all for the
two electrolytics. That is what separately-maintained files do.

Usage:  python3 make_fab.py [--force]
        --force skips the gates. For inspecting a work-in-progress board only;
        it stamps the output README so the package cannot be mistaken for orderable.
"""

import csv
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BOARD_DIR = os.path.join(HERE, "robot-buddy-reflex")
PCB = os.path.join(BOARD_DIR, "robot-buddy-reflex.kicad_pcb")
SCH = os.path.join(BOARD_DIR, "robot-buddy-reflex.kicad_sch")
GERBER_DIR = os.path.join(BOARD_DIR, "gerbers")
ASM_DIR = os.path.join(BOARD_DIR, "jlcpcb-assembly")
ZIP_BASE = os.path.join(GERBER_DIR, "robot-buddy-reflex-gerbers")

LAYERS = (
    "F.Cu,In1.Cu,In2.Cu,B.Cu,"
    "F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
)

# Modules the fab cannot place even though their footprints carry SMD pads.
# U1 is the ESP32-S3-Zero on the flat-mount footprint — castellated SMD pads, so
# `kicad-cli pcb export pos --smd-only` happily lists it, but it is a Waveshare
# module, not an LCSC line item. U2 (TB6612 breakout) is already excluded by being
# through-hole. Everything else through-hole is excluded by --smd-only.
HAND_SOLDERED_MODULES = {"U1"}

# LCSC part numbers. VERIFIED ones only — an unknown must stay blank so it shows up
# in the "needs a part number" list below. Do not fill these from JLC's auto-matcher
# without checking the package: it silently matches the right value in the wrong
# package, which is how a 0402 order becomes an 0603 order.
LCSC = {
    ("100n", "C_0402_1005Metric"): "C1525",
    ("100k", "R_0402_1005Metric"): "C25741",
    ("10k", "R_0402_1005Metric"): "C25744",
    ("100", "R_0402_1005Metric"): "C25076",
    ("330", "R_0402_1005Metric"): "C25104",
    ("QWIIC 3V3", "JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical"): "C160390",
    ("TCA9554APWR", "TSSOP-16_4.4x5mm_P0.65mm"): "C2863976",
    # Not yet verified — deliberately absent, so they are reported:
    #   15k 0402 (R6)      — the v1 BOM's C25765 was for 20k, not 15k
    #   4.7k 0402 (R16/17) — new in v2 (the X1 I2C pull-ups)
    #   10u 0402 (C9)      — new in v2 (the X3 +3V3 bulk)
}


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r


def check_gates():
    """DRC clean + both pre-fab gates, or refuse to emit anything."""
    print("Gate 1/3  DRC ...")
    tmp = "/tmp/reflex-fab-drc.json"
    run(
        [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            tmp,
            "--severity-error",
            "--severity-warning",
            PCB,
        ]
    )
    with open(tmp) as fh:
        rep = json.load(fh)
    viols = rep.get("violations", [])
    errors = [v for v in viols if v.get("severity") == "error"]
    warnings = [v for v in viols if v.get("severity") != "error"]
    unconn = len(rep.get("unconnected_items", []))
    parity = len(rep.get("schematic_parity", []))
    print(
        f"          {len(errors)} errors, {len(warnings)} warnings, "
        f"{unconn} unconnected, {parity} parity"
    )

    # Blocks on ERRORS, unconnected and parity. Warnings are reported, loudly, but
    # do not stop the package.
    #
    # This used to demand zero violations of any severity, and that rule did real
    # harm. The silk auto-placer hides nothing now, but it used to hide a field it
    # could not place cleanly — and what it hid was J1's "MOTOR L". J1 and J2 are
    # identical 6-pin XH connectors, so the silk label is the entire mitigation for
    # the swap hazard the register accepts under C2. Chasing a zero silk count
    # deleted the mitigation for a real defect, to satisfy a warning about ink
    # overlapping ink. Rank them properly: a silk_overlap is cosmetic, an
    # unlabelled motor connector is a wiring error on an assembled robot.
    for v in warnings:
        items = " <-> ".join(
            i.get("description", "").split(" {")[0] for i in v.get("items", [])
        )
        print(f"            warn: {v.get('type')} | {items}")
    ok = not errors and unconn == 0 and parity == 0

    # check_pcb_ampacity.py added 2026-08-06: scout ran it, buddy did not.
    # It asks "can it CARRY the current" -- the question the other two do not.
    # Written after robot-scout-power passed DRC and both other gates while the
    # whole ~15A pack current crossed to a plane through ONE 0.4mm via.
    for n, gate in (
        (2, "check_pcb_routing.py"),
        (3, "check_board_review.py"),
        (4, "check_pcb_ampacity.py"),
    ):
        print(f"Gate {n}/4  {gate} ...")
        r = subprocess.run(
            [sys.executable, os.path.join(REPO, "tools", gate), PCB],
            capture_output=True,
            text=True,
        )
        print(f"          {'PASS' if r.returncode == 0 else 'FAIL'}")
        ok = ok and r.returncode == 0
    return ok


def export_gerbers():
    os.makedirs(GERBER_DIR, exist_ok=True)
    for f in os.listdir(GERBER_DIR):
        if f.endswith(
            (
                ".gbr",
                ".gbl",
                ".gtl",
                ".gbs",
                ".gts",
                ".gbp",
                ".gtp",
                ".gbo",
                ".gto",
                ".gm1",
                ".g1",
                ".g2",
                ".drl",
                ".gbrjob",
                # drill maps: KiCad's older PDF map lingered from the June export and
                # rode along in every zip after the maps went gerberx2 (register §M).
                ".pdf",
            )
        ):
            os.unlink(os.path.join(GERBER_DIR, f))
    # The v1 zip that used to live beside the BOM (merged drill, silk on pads, register
    # O1/M2/M3). The only gerber zip is ../gerbers/; never leave an orderable stale one.
    _old_zip = os.path.join(ASM_DIR, "robot-buddy-reflex-gerbers.zip")
    if os.path.exists(_old_zip):
        os.unlink(_old_zip)
        print(
            "          removed stale jlcpcb-assembly/robot-buddy-reflex-gerbers.zip (v1)"
        )

    # --subtract-soldermask is REQUIRED here and is not implied by the board's
    # (subtractmaskfromsilk yes). Verified: plotting F.Silkscreen with the board flag
    # on and off produced byte-identical gerbers. Only this CLI flag has any effect,
    # and without it silk prints onto pads — including C3/C6's polarity bars, which
    # are drawn across their own pads on purpose.
    run(
        [
            "kicad-cli",
            "pcb",
            "export",
            "gerbers",
            "--subtract-soldermask",
            "--no-protel-ext",
            "--layers",
            LAYERS,
            "--output",
            GERBER_DIR,
            PCB,
        ]
    )
    run(
        [
            "kicad-cli",
            "pcb",
            "export",
            "drill",
            "--format",
            "excellon",
            "--excellon-separate-th",
            "--generate-map",
            "--map-format",
            "gerberx2",
            "--output",
            GERBER_DIR,
            PCB,
        ]
    )
    # Build the archive OUTSIDE the directory being archived, then move it in.
    #
    # shutil.make_archive(ZIP_BASE, "zip", GERBER_DIR) with ZIP_BASE inside GERBER_DIR
    # makes the zip archive itself: it is created in the tree it is walking, so each
    # block written grows the thing being read. That filled a 330GB disk with a single
    # 4.5GB zip before it was noticed. Any make_archive whose destination is under its
    # root_dir has this bug.
    if os.path.exists(ZIP_BASE + ".zip"):
        os.unlink(ZIP_BASE + ".zip")
    # Only fab files, top level only. make_archive(GERBER_DIR) took everything under it,
    # and pcb_qc.py's review PNGs (then in gerbers/qc/) went to the fab inside the zip
    # (2026-11-09); gerbonara choked on them reading the zip back.
    import zipfile as _zf

    tmp_zip = "/tmp/robot-buddy-reflex-gerbers.zip"
    with _zf.ZipFile(tmp_zip, "w", _zf.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(GERBER_DIR)):
            full = os.path.join(GERBER_DIR, f)
            if os.path.isfile(full) and f.endswith((".gbr", ".drl", ".gbrjob")):
                zf.write(full, f)
    shutil.move(tmp_zip, ZIP_BASE + ".zip")
    return len([f for f in os.listdir(GERBER_DIR) if not f.endswith((".zip", ".md"))])


def export_bom_and_cpl():
    """CPL first — it defines the assembled set; the BOM is filtered to match it."""
    os.makedirs(ASM_DIR, exist_ok=True)
    cpl_raw = "/tmp/reflex-cpl-raw.csv"
    run(
        [
            "kicad-cli",
            "pcb",
            "export",
            "pos",
            "--format",
            "csv",
            "--units",
            "mm",
            "--side",
            "front",
            "--smd-only",
            "--exclude-dnp",
            "--output",
            cpl_raw,
            PCB,
        ]
    )

    with open(cpl_raw, newline="") as fh:
        rows = list(csv.DictReader(fh))
    placed = [r for r in rows if r["Ref"] not in HAND_SOLDERED_MODULES]
    excluded = sorted({r["Ref"] for r in rows} & HAND_SOLDERED_MODULES)

    cpl_path = os.path.join(ASM_DIR, "robot-buddy-reflex-cpl.csv")
    with open(cpl_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in placed:
            w.writerow(
                [
                    r["Ref"],
                    r["PosX"],
                    r["PosY"],
                    "Top" if r["Side"] == "top" else "Bottom",
                    r["Rot"],
                ]
            )

    # BOM from the schematic, restricted to exactly the designators in the CPL
    bom_raw = "/tmp/reflex-bom-raw.csv"
    run(
        [
            "kicad-cli",
            "sch",
            "export",
            "bom",
            "--fields",
            "Reference,Value,Footprint",
            "--labels",
            "Ref,Value,Footprint",
            "--group-by",
            "Value",
            "--output",
            bom_raw,
            SCH,
        ]
    )

    placed_refs = {r["Ref"] for r in placed}
    by_key, missing = {}, []
    with open(bom_raw, newline="") as fh:
        for row in csv.DictReader(fh):
            fp = row["Footprint"].split(":", 1)[-1]
            for ref in expand_refs(row["Ref"]):
                if ref not in placed_refs:
                    continue
                by_key.setdefault((row["Value"], fp), []).append(ref)

    bom_path = os.path.join(ASM_DIR, "robot-buddy-reflex-bom.csv")
    with open(bom_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "JLCPCB Part # (LCSC)"])
        for (val, fp), refs in sorted(by_key.items()):
            part = LCSC.get((val, fp), "")
            if not part:
                missing.append(f"{val} ({fp}): {','.join(sorted(refs))}")
            w.writerow([val, ",".join(sorted(refs)), fp, part])

    bom_refs = {r for refs in by_key.values() for r in refs}
    if bom_refs != placed_refs:
        sys.exit(
            f"BOM/CPL disagree: only in CPL {placed_refs - bom_refs}, "
            f"only in BOM {bom_refs - placed_refs}"
        )

    return len(placed), len(by_key), missing, excluded


def expand_refs(field):
    """'R1,R2,R12-R15' -> individual designators."""
    out = []
    for part in field.split(","):
        part = part.strip()
        if "-" in part[1:]:
            lo, hi = part.rsplit("-", 1)
            prefix = "".join(c for c in lo if not c.isdigit())
            a = int(lo[len(prefix) :])
            b = int("".join(c for c in hi if c.isdigit()))
            out += [f"{prefix}{i}" for i in range(a, b + 1)]
        elif part:
            out.append(part)
    return out


def write_readme(n_placed, n_lines, missing, excluded, gated):
    hand = sorted(excluded) + [
        "U2",
        "C3",
        "C6",
        "J1",
        "J2",
        "J6",
        "J7",
        "J9",
    ]  # J10 deleted 2026-11-09
    banner = (
        ""
        if gated
        else ("> ⚠ **GENERATED WITH --force — GATES NOT CHECKED. NOT ORDERABLE.**\n\n")
    )
    miss = "\n".join(f"- {m}" for m in missing) or "- none"
    with open(os.path.join(ASM_DIR, "README.md"), "w") as fh:
        fh.write(f"""# JLCPCB assembly package — robot-buddy-reflex

{banner}Generated by `hardware/kicad/make_fab.py`. **Do not hand-edit** — regenerate.
The BOM is derived from the CPL, so the two cannot drift apart (register O1).

## Files
- `robot-buddy-reflex-bom.csv` — {n_lines} lines covering {n_placed} placed parts
- `robot-buddy-reflex-cpl.csv` — pick-and-place, all top side
- Gerbers: `../gerbers/robot-buddy-reflex-gerbers.zip`

## 🔴 Parts still needing an LCSC number
{miss}

Leave these unset in the cart and let JLC match them, then **verify the package** on
every one. JLC's matcher will silently return the right value in the wrong package.

## What YOU hand-solder (not in the CPL)
{", ".join(hand)} — through-hole parts and the two plug-in modules.
`U1` carries castellated SMD pads so `--smd-only` lists it, but it is a Waveshare
module, not an LCSC line item; `make_fab.py` removes it explicitly.

## Upload order at cart.jlcpcb.com
1. Upload the gerber zip, set qty (min 5), assemble on 2 or 5.
2. Turn ON "PCB Assembly", side = Top, upload BOM + CPL.
3. Verify every auto-matched LCSC number, package included.
4. Check rotations in the 3D preview for **U4 (TSSOP-16)** and **J5 (Qwiic)** —
   JLC's orientation reference can differ from KiCad by 90/180° on 3+ pin parts.
   2-terminal R/C are symmetric and do not matter.
5. Leave everything not listed unpopulated (DNP).
""")


def main():
    force = "--force" in sys.argv
    gated = True
    if force:
        print("--force: skipping gates\n")
        gated = False
    elif not check_gates():
        sys.exit(
            "\nREFUSING to generate a fab package from a board that does not "
            "pass. Fix the board, or pass --force for inspection only."
        )

    print("\nExporting gerbers + drill ...")
    n_files = export_gerbers()
    print(f"          {n_files} files -> {GERBER_DIR}")

    # Verify the PLOTTED output, not the board file. layout_pcb.py's DFM pass keeps
    # the design free of mask-without-copper, but a plot setting or a missing export
    # flag could reintroduce it downstream, and the gerbers are what the fab builds.
    print("Checking mask openings against copper ...")
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(REPO, "tools", "check_gerber_mask.py"),
            GERBER_DIR,
        ],
        capture_output=True,
        text=True,
    )
    for line in r.stdout.splitlines():
        if line.strip():
            print(f"  {line.strip()}")
    if r.returncode != 0 and gated:
        sys.exit("REFUSING: the plotted gerbers offer bare laminate as solderable.")

    print("Exporting BOM + CPL ...")
    n_placed, n_lines, missing, excluded = export_bom_and_cpl()
    print(f"          {n_placed} placed parts, {n_lines} BOM lines")
    if excluded:
        print(f"          excluded as modules: {', '.join(excluded)}")

    write_readme(n_placed, n_lines, missing, excluded, gated)

    stale = os.path.join(GERBER_DIR, "DO-NOT-FABRICATE.md")
    if gated and os.path.exists(stale):
        os.unlink(stale)
        print("          removed stale DO-NOT-FABRICATE.md")

    if missing:
        print(f"\n⚠ {len(missing)} BOM line(s) have no LCSC part number:")
        for m in missing:
            print(f"    {m}")
    print("\nDone.")


if __name__ == "__main__":
    main()
