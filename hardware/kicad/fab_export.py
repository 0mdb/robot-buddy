#!/usr/bin/env python3
"""Fab outputs for robot-buddy-reflex: gerbers + drills + job file, zipped, plus BOM/CPL.

    python3 hardware/kicad/fab_export.py          # then: python3 hardware/kicad/pcb_qc.py

Writes robot-buddy-reflex/gerbers/ (cleared first) and robot-buddy-reflex-gerbers.zip in it.
Choices (2026-11-09, after the first order's silk/mask and footprint problems):
- Protel extensions (.gtl/.gbl/.g1/.g2/...): what JLCPCB/PCBWay auto-identify.
- Silkscreen minus soldermask: no silk ink on pads.
- Separate PTH and NPTH Excellon files: a merged MixedPlating file lets a fab plate the M3 holes.
- Job file (.gbrjob) in the zip: layer order and count for the fab's importer.
- BOM + CPL beside the zip (not in it). jlc-bom.csv / jlc-cpl.csv: JLCPCB PCBA, top-side SMD
  only (the 0402s + U3). U1 (flat-mount module, hot plate/air), U2 (female headers) and the
  THT connectors/caps are fitted by hand. LCSC numbers are left for JLC's BOM matcher to fill
  from the descriptions; check U3's pin-1 dot in JLC's placement preview.
"""

import csv

import shutil
import subprocess
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE / "robot-buddy-reflex"
PCB = PROJ / "robot-buddy-reflex.kicad_pcb"
SCH = PROJ / "robot-buddy-reflex.kicad_sch"
OUT = PROJ / "gerbers"
ZIP = OUT / "robot-buddy-reflex-gerbers.zip"

LAYERS = [
    "F.Cu",
    "In1.Cu",
    "In2.Cu",
    "B.Cu",
    "F.Mask",
    "B.Mask",
    "F.Paste",
    "B.Paste",
    "F.Silkscreen",
    "B.Silkscreen",
    "Edge.Cuts",
]


def run(*args: str) -> None:
    subprocess.run(["kicad-cli", *args], check=True, capture_output=True, text=True)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    run(
        "pcb",
        "export",
        "gerbers",
        "--layers",
        ",".join(LAYERS),
        "--subtract-soldermask",
        "-o",
        f"{OUT}/",
        str(PCB),
    )
    run(
        "pcb",
        "export",
        "drill",
        "--format",
        "excellon",
        "--excellon-units",
        "mm",
        "--excellon-zeros-format",
        "decimal",
        "--excellon-separate-th",
        "--generate-map",
        "--map-format",
        "pdf",
        "-o",
        f"{OUT}/",
        str(PCB),
    )
    run(
        "pcb",
        "export",
        "pos",
        "--format",
        "csv",
        "--units",
        "mm",
        "--side",
        "both",
        "--smd-only",
        "-o",
        str(OUT / "robot-buddy-reflex-cpl.csv"),
        str(PCB),
    )
    run(
        "sch",
        "export",
        "bom",
        "--fields",
        "Reference,Value,Footprint,${QUANTITY}",
        "--group-by",
        "Value,Footprint",
        "-o",
        str(OUT / "robot-buddy-reflex-bom.csv"),
        str(SCH),
    )

    write_jlc()
    fab = sorted(
        p
        for p in OUT.iterdir()
        if p.suffix.lower()
        in {
            ".gtl",
            ".gbl",
            ".g1",
            ".g2",
            ".gts",
            ".gbs",
            ".gtp",
            ".gbp",
            ".gto",
            ".gbo",
            ".gm1",
            ".drl",
            ".gbrjob",
        }
    )
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in fab:
            z.write(p, p.name)
    print(f"{len(fab)} files -> {ZIP.relative_to(HERE.parent.parent)}")
    for p in fab:
        print("  ", p.name)


# value -> JLC description (what the BOM matcher searches on)
JLC_DESC = {
    "100n": "100nF 16V X7R 0402",
    "100k": "100k 1% 0402",
    "47k": "47k 1% 0402",
    "20k": "20k 1% 0402",
    "10k": "10k 1% 0402",
    "330": "330R 1% 0402",
    "100": "100R 1% 0402",
    "74AHCT1G125": "74AHCT1G125 SOT-23-5 (SN74AHCT1G125DBVR or equivalent)",
}
HAND_FIT = {"U1"}  # SMD but not fab-placed


def write_jlc() -> None:
    pos = OUT / "robot-buddy-reflex-cpl.csv"
    rows = [r for r in csv.DictReader(open(pos)) if r["Side"] == "top"]
    smd = [r for r in rows if r["Ref"] not in HAND_FIT and r["Val"] in JLC_DESC]
    missing = [
        r["Ref"]
        for r in rows
        if r["Ref"] not in HAND_FIT
        and r["Val"] not in JLC_DESC
        and r["Package"].startswith(("R_", "C_", "SOT"))
    ]
    if missing:
        raise SystemExit(f"SMD parts with no JLC description: {missing}")
    with open(OUT / "jlc-cpl.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in smd:
            w.writerow(
                [
                    r["Ref"],
                    f"{float(r['PosX']):.3f}mm",
                    f"{float(r['PosY']):.3f}mm",
                    "Top",
                    f"{float(r['Rot']):g}",
                ]
            )
    groups: dict[tuple[str, str], list[str]] = {}
    for r in smd:
        groups.setdefault((r["Val"], r["Package"]), []).append(r["Ref"])
    with open(OUT / "jlc-bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, pkg), refs in sorted(groups.items()):
            refs.sort(
                key=lambda x: (x[0], int("".join(c for c in x if c.isdigit()) or 0))
            )
            w.writerow([JLC_DESC[val], ",".join(refs), pkg, ""])
    print(
        f"JLC PCBA: {len(smd)} placements, {len(groups)} BOM lines (jlc-bom.csv, jlc-cpl.csv)"
    )


if __name__ == "__main__":
    main()
