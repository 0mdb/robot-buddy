#!/usr/bin/env python3
"""robot-buddy reflex v3: the shared STM32G431 core (kicad-libs g4core) + buddy's motor stage.

    python3 hardware/kicad/reflex_v3.py            # schematic + placed PCB
    python3 hardware/kicad/reflex_v3.py --route    # + freerouting, DRC, parity, gates

Writes hardware/kicad/robot-buddy-reflex-v3/ (v2 in robot-buddy-reflex/ stays as the I/O
reference and is what is being built now). Built on ~/kicad-libs/tools/g4board.py. Pins:
~/kicad-libs/docs/g431-pin-plan.md (buddy-reflex). Plan: shared-mcu-core.md (Ben 2026-11-21:
draft v3 now; the phase-0 stall test and v2 bring-up still feed it before any order).

Motor stage: 2x DRV8876PWPR (C575551; TI SLVSDS7B, in ~/kicad-libs/docs/ref/parts), one per
TT motor, VM = the board's +5V (as v2's TB6612):
- PH/EN mode: PMODE to GND (sec. 7.3.2). EN = TIM1 CHxN PWM, PH = GPIO direction.
- IMODE to GND (Table 6, quad-level 1): fixed off-time chopping, auto retry, nFAULT on
  overcurrent only (chopping alone does not raise a fault).
- IPROPI 2.49 k to GND (= the Pololu 4036 carrier used for the phase-0 stall test, 2.49 V/A
  with AIPROPI 1000 uA/A) into the G431 (ADC + COMP -> TIM1 break). VREF 3.3 k / 10 k from
  +3V3 = 2.48 V, so ITRIP = 2.48 V / 2.49 k / 1000 uA/A = 1.0 A (eq. 3): caps the 1.5 A
  direction-flip surge noted in TODO; TT stall ~0.5-0.7 A stays below it, for the MCU to see.
- nSLEEP of both = ESTOP_N: the e-stop loop puts the drivers to sleep in hardware (v2: TB6612
  STBY). nFAULT open-drain, wired-OR, 10 k up = M_FAULT_N.
- Per driver: VM 0.1 uF + 10 uF, VCP 100 nF to VM, CPH-CPL 22 nF 50 V. Plus v2's 1000 uF bulk.
Host: the Pi's UART + 5 V on a JST-VH 4 (v2 J9 pinout) and its two GPIOs for NRST/BOOT0 on a
JST-XH 2 (the core's host_ctl circuit, Pi GPIOs idle low).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "kicad-libs" / "tools"))

from g4board import C, Board, Part, R, conn, mounting_holes  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
NAME = "robot-buddy-reflex-v3"
W, H = 72.0, 52.0

XH2 = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
XH3 = "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"
XH6 = "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical"
VH4 = "Connector_JST:JST_VH_B4P-VH_1x04_P3.96mm_Vertical"
SH4 = "Connector_JST:JST_SH_BM04B-SRSS-TB_1x04-1MP_P1.00mm_Vertical"
SH5 = "Connector_JST:JST_SH_BM05B-SRSS-TB_1x05-1MP_P1.00mm_Vertical"
HDR4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
DRV = "robot-projects:DRV8876PWPR"
DRV_FP = "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask3x3mm_ThermalVias"
C0805 = "Capacitor_SMD:C_0805_2012Metric"


def driver(u, side, r_ipropi, c0) -> list[Part]:
    s = side
    cvcp, cfly, cvm, cbulk = (f"C{c0 + i}" for i in range(4))
    return [
        Part(
            u,
            DRV,
            "DRV8876PWPR",
            DRV_FP,
            "C575551",
            {
                "1": f"M_{s}_EN",
                "2": f"M_{s}_PH",
                "3": "ESTOP_N",
                "4": "M_FAULT_N",
                "5": "M_VREF",
                "6": f"M_ISENSE_{s}",
                "7": "GND",
                "8": f"M_{s}_OUT1",
                "9": "GND",
                "10": f"M_{s}_OUT2",
                "11": "+5V",
                "12": f"{u}_VCP",
                "13": f"{u}_CPH",
                "14": f"{u}_CPL",
                "15": "GND",
                "16": "GND",
                "17": "GND",
            },
            "board",
            f"motor {s}: PMODE=GND (PH/EN), IMODE=GND (fixed off-time, retry)",
        ),
        Part(
            cvcp,
            "Device:C",
            "100n",
            "Capacitor_SMD:C_0402_1005Metric",
            "C1525",
            {"1": f"{u}_VCP", "2": "+5V"},
            "board",
            "VCP to VM, 16 V X7R (pin table)",
        ),
        Part(
            cfly,
            "Device:C",
            "22n",
            "Capacitor_SMD:C_0402_1005Metric",
            "C337699",
            {"1": f"{u}_CPH", "2": f"{u}_CPL"},
            "board",
            "CPH-CPL, 50 V X7R (VM-rated)",
        ),
        C(cvm, "100n", "+5V", note="VM bypass at the pin"),
        Part(
            cbulk,
            "Device:C",
            "10uF",
            C0805,
            "C15850",
            {"1": "+5V", "2": "GND"},
            "board",
            "VM local bulk, 25 V X5R",
        ),
        R(
            r_ipropi,
            "2.49k",
            f"M_ISENSE_{s}",
            "GND",
            "RIPROPI: 2.49 V/A (Pololu 4036 value, phase-0 bench)",
        ),
    ]


def parts() -> list[Part]:
    return [
        conn(
            "J10",
            4,
            "HOST 5V UART",
            VH4,
            "",
            ["+5V", "GND", "HOST_TX", "HOST_RX"],
            "Pi: 5 V in + UART (v2 J9 pinout, MCU TX on 3)",
        ),
        conn(
            "J11",
            2,
            "PI CTL",
            XH2,
            "C265283",
            ["HOST_NRST_CTL", "HOST_BOOT0_CTL"],
            "Pi GPIOs (idle low) -> the core's NRST NPN / BOOT0 series R",
        ),
        *driver("U10", "L", "R20", 20),
        *driver("U11", "R", "R21", 24),
        R("R22", "3.3k", "+3V3", "M_VREF", "VREF top: 2.48 V -> ITRIP 1.0 A"),
        R("R23", "10k", "M_VREF", "GND"),
        C("C28", "100n", "M_VREF"),
        R("R24", "10k", "M_FAULT_N", "+3V3", "nFAULT pull-up (both, wired-OR)"),
        Part(
            "C29",
            "Device:C_Polarized",
            "1000uF",
            "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
            "",
            {"1": "+5V", "2": "GND"},
            "board",
            "+5V bulk, hand-soldered (v2 C3: 10ZLH 10x12.5)",
        ),
        conn(
            "J12",
            6,
            "MOTOR L",
            XH6,
            "C265366",
            ["M_L_OUT1", "M_L_OUT2", "+3V3", "GND", "ENC_L_A", "ENC_L_B"],
            "v2 J1 pinout: motor, encoder 3V3/GND/A/B",
        ),
        conn(
            "J13",
            6,
            "MOTOR R",
            XH6,
            "C265366",
            ["M_R_OUT1", "M_R_OUT2", "+3V3", "GND", "ENC_R_A", "ENC_R_B"],
            "v2 J2 pinout",
        ),
        # E-stop: v2 J7 pinout, NC loop from +3V3; both lines pulled down (open = stop)
        conn(
            "J14",
            3,
            "E-STOP NC",
            XH3,
            "C144394",
            ["+3V3", "ESTOP_N", "ESTOP_LOOP"],
            "1 +3V3, 2 switch return (ESTOP_N), 3 cable-present loop",
        ),
        R(
            "R25",
            "10k",
            "ESTOP_N",
            "GND",
            "open loop = low = drivers asleep + TIM1 break",
        ),
        C("C30", "100n", "ESTOP_N", note="as v2 C1"),
        R("R26", "10k", "ESTOP_LOOP", "GND", "cable detect (v2 R18)"),
        # Cliff ToF (VL53L4CD boards): Qwiic order + XSHUT on pin 5; the fourth has no XSHUT
        *[
            conn(
                f"J{15 + i}",
                5,
                f"TOF {i + 1}",
                SH5,
                "C54582900",
                ["GND", "+3V3", "I2C_SDA", "I2C_SCL", f"TOF_XSHUT{i + 1}"],
                "VL53L4CD board: 1 GND, 2 3V3, 3 SDA, 4 SCL, 5 XSHUT",
            )
            for i in range(3)
        ],
        conn(
            "J18",
            4,
            "TOF 4",
            SH4,
            "C160390",
            ["GND", "+3V3", "I2C_SDA", "I2C_SCL"],
            "fourth ToF (re-addressed first, no XSHUT)",
        ),
        R("R27", "4.7k", "I2C_SDA", "+3V3"),
        R("R28", "4.7k", "I2C_SCL", "+3V3"),
        # Sonars: v2 J6 pinout; echo 5 V straight into FT pins (PA11, PB9) through 1 k
        conn(
            "J19",
            4,
            "SONAR FRONT",
            HDR4,
            "",
            ["+5V", "SONAR_F_TRIG", "SONAR_F_ECHO_J", "GND"],
        ),
        R("R29", "1k", "SONAR_F_ECHO_J", "SONAR_F_ECHO", "series into an FT pin"),
        conn(
            "J20",
            4,
            "SONAR REAR",
            HDR4,
            "",
            ["+5V", "SONAR_R_TRIG", "SONAR_R_ECHO_J", "GND"],
        ),
        R("R30", "1k", "SONAR_R_ECHO_J", "SONAR_R_ECHO"),
        # 5 V sense: 15 k / 10 k = 0.4 (5 V -> 2.0 V; a 7.8 V hot-plug spike -> 3.1 V)
        R("R31", "15k", "+5V", "V5_SENSE"),
        R("R32", "10k", "V5_SENSE", "GND"),
        C("C31", "100n", "V5_SENSE"),
        *mounting_holes(),
    ]


SCH_FRAMES = [
    (
        "Motor drivers DRV8876 (PH/EN, IPROPI 2.49 k, ITRIP 1.0 A, nSLEEP = ESTOP_N)",
        (15.24, 434.34),
        (414.02, 523.24),
    ),
    ("Host (Pi), e-stop, 5 V sense", (424.18, 434.34), (650.24, 523.24)),
    ("Cliff ToF, sonars, motors", (15.24, 533.4), (414.02, 584.2)),
    ("Power, mounting", (424.18, 533.4), (650.24, 584.2)),
]


def sch_place() -> dict:
    p = {
        "U10": (60.96, 469.9, 0),
        "U11": (238.76, 469.9, 0),
        "R22": (360.68, 452.12, 90),
        "R23": (360.68, 477.52, 90),
        "C28": (381.0, 477.52, 0),
        "R24": (360.68, 500.38, 90),
        "J10": (447.04, 459.74, 0),
        "J11": (447.04, 485.14, 0),
        "J14": (518.16, 459.74, 0),
        "R25": (553.72, 469.9, 0),
        "C30": (571.5, 469.9, 0),
        "R26": (586.74, 469.9, 0),
        "R31": (604.52, 452.12, 90),
        "R32": (604.52, 477.52, 90),
        "C31": (624.84, 477.52, 0),
        "J15": (38.1, 558.8, 0),
        "J16": (76.2, 558.8, 0),
        "J17": (114.3, 558.8, 0),
        "J18": (152.4, 558.8, 0),
        "R27": (180.34, 553.72, 0),
        "R28": (195.58, 553.72, 0),
        "J19": (228.6, 558.8, 0),
        "R29": (259.08, 558.8, 90),
        "J20": (284.48, 558.8, 0),
        "R30": (314.96, 558.8, 90),
        "J12": (345.44, 558.8, 0),
        "J13": (381.0, 558.8, 0),
        "C29": (452.12, 558.8, 0),
        "MH1": (500.38, 558.8, 0),
        "MH2": (515.62, 558.8, 0),
        "MH3": (530.86, 558.8, 0),
        "MH4": (546.1, 558.8, 0),
        "#FLG91": (472.44, 548.64, 0),
        "#FLG92": (485.14, 548.64, 0),
    }
    for base, u, r, c0 in ((60.96, "U10", "R20", 20), (238.76, "U11", "R21", 24)):
        p[f"C{c0}"] = (base + 38.1, 452.12, 0)
        p[f"C{c0 + 1}"] = (base + 50.8, 452.12, 0)
        p[f"C{c0 + 2}"] = (base + 38.1, 492.76, 0)
        p[f"C{c0 + 3}"] = (base + 50.8, 492.76, 0)
        p[r] = (base - 25.4, 497.84, 0)
    return p


PCB_PLACE: dict[str, tuple] = {
    "MH1": (3.5, 3.5, 0),
    "MH2": (W - 3.5, 3.5, 0),
    "MH3": (3.5, H - 3.5, 0),
    "MH4": (W - 3.5, H - 3.5, 0),
    # top edge: cliff ToF x4, front sonar
    "J15": (14.0, 3.5, 0),
    "J16": (24.0, 3.5, 0),
    "J17": (34.0, 3.5, 0),
    "J18": (43.0, 3.5, 0),
    "R27": (46.5, 8.4, 0),
    "R28": (46.5, 9.8, 0),
    "J19": (50.0, 3.0, 90),
    "R29": (51.0, 7.4, 0),
    # motor stage, right
    "U10": (54.0, 14.0, 0),
    "U11": (54.0, 33.0, 0),
    "R20": (48.8, 15.6, 90),
    "C20": (60.6, 12.3, 0),
    "C21": (60.6, 11.0, 0),
    "C22": (60.6, 14.3, 0),
    "C23": (60.8, 16.2, 0),
    "R21": (48.8, 34.6, 90),
    "C24": (60.6, 31.3, 0),
    "C25": (60.6, 30.0, 0),
    "C26": (60.6, 33.3, 0),
    "C27": (60.8, 35.2, 0),
    "R22": (49.0, 23.0, 90),
    "R23": (50.5, 23.0, 90),
    "C28": (52.0, 23.0, 90),
    "R24": (55.0, 23.0, 90),
    "J12": (W - 3.5, 10.5, 270),
    "J13": (W - 3.5, 29.0, 270),
    "C29": (55.5, 45.0, 0),
    # left edge: host power/UART, Pi control
    "J10": (4.0, 22.0, 90),
    "J11": (3.5, 31.0, 90),
    "R31": (11.0, 14.0, 90),
    "R32": (12.5, 14.0, 90),
    "C31": (14.0, 14.0, 90),
    # bottom edge: e-stop, rear sonar
    "J14": (20.0, H - 3.0, 180),
    "R25": (8.6, 37.0, 90),
    "C30": (8.6, 39.6, 90),
    "R26": (8.6, 42.2, 90),
    "J20": (40.0, H - 2.5, 90),
    "R30": (37.0, 46.2, 0),
}


def board() -> Board:
    return Board(
        name=NAME,
        out=REPO / "hardware" / "kicad" / NAME,
        title="robot-buddy reflex v3 (shared STM32G431 core, 2x DRV8876)",
        pro_template=REPO
        / "hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pro",
        plan="buddy-reflex",
        size=(W, H),
        core_at=(28.0, 20.0, 0.0),
        io_offset=(-3.0, 15.0, 0.0),
        parts=parts(),
        sch_place=sch_place(),
        sch_frames=SCH_FRAMES,
        pcb_place=PCB_PLACE,
        core_flags={},
        netclass={
            "+5V": "Motor",
            "M_L_OUT1": "Motor",
            "M_L_OUT2": "Motor",
            "M_R_OUT1": "Motor",
            "M_R_OUT2": "Motor",
        },
        # 0.5 mm is the widest track that enters the DRV8876's 0.65 mm-pitch pins at 0.15 mm
        # clearance (0.8 left 5 nets unrouted, 2026-11-22). IPC, 1 oz outer: 1.44 A at 10 C,
        # 1.95 A at 20 C. OUT nets see <= ITRIP 1.0 A; +5V sees both at ITRIP only in surges.
        class_width={"Motor": 0.5},
        label_at={
            "J19": (56.0, 6.6, 0),
            "J20": (44.0, 46.6, 0),
            "J14": (28.8, 47.0, 0),
        },
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--route", action="store_true")
    ap.add_argument("--tries", type=int, default=8)
    ap.add_argument("--seconds", type=int, default=120)
    a = ap.parse_args(argv)
    return board().build(route=a.route, tries=a.tries, seconds=a.seconds)


if __name__ == "__main__":
    sys.exit(main())
