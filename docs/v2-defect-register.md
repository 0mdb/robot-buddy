# robot-buddy-reflex — v2 defect register

**Status: all v1 boards SCRAP.** Do not power a v1 board with U2 (TB6612) seated — see E1.

Consolidated list of every v1 defect plus the v2 architecture change, with a
pre-fab sign-off gate at the end. Mirrors `robot-scout/docs/v2-defect-register.md`.

Verified 2026-08-06 against `hardware/kicad/robot-buddy-reflex/robot-buddy-reflex.kicad_pcb`,
`docs/ref/SparkFun_Motor_Driver-TB6612FNG_v11c.{sch,brd}`, and the Waveshare
ESP32-S3-Zero STEP.

---

## E — Electrical (fatal)

### E1. TB6612 JP1 net misassignment — direct battery short — **FIXED 2026-08-06**

Fixed at source, in all three places the error lived:
1. `~/kicad-libs/symbols/robot-projects.kicad_sym` — `SparkFun_TB6612FNG_v2` symbol
   pins 11/12/13/16 renamed and re-typed: `AO1→GND2 (power_in)`, `AO2→AO1`,
   `GND2→AO2 (output)`, `VM2→GND3`. This was the origin; the error propagated
   symbol → schematic → PCB.
2. `hardware/kicad/populate_schematic.py` — `U2P` right-column map corrected, and
   the `+BATT` power symbol on pin 16 replaced with `GND`.
3. `robot-buddy-reflex.kicad_sch` / `.kicad_pcb` — regenerated from the above.

Verified: exported netlist and PCB both show all 16 U2 pins matching the Eagle
schematic, with `+BATT` on pin 9 only.

The as-built v1 board is preserved at
`hardware/kicad/robot-buddy-reflex/v1-asbuilt/` as the record of the physical
scrapped boards. **The live PCB is now unrouted** — `route_pcb.py` needs
`freerouting-2.0.jar`, which is not installed, and the v2 layout supersedes it
anyway (cluster deleted, expander added, J8 connector family changed).

Original defect, for the record:
Right row (JP1) nets are wrong. Authoritative JP1 order from the SparkFun Eagle
schematic is pin1→8: `GND, BO1, BO2, AO2, AO1, GND, VCC, VM` — note **two** GNDs
(pin 1 and pin 6). Dropping the pin-6 GND shifted everything by one.

Our footprint is Eagle rotated 180°, so the right row low→high y = JP1 pin8→pin1.

| pad | board has | must be | |
|---|---|---|---|
| 9  | `+BATT` | VM | ok |
| 10 | `+3V3` | VCC | ok |
| 11 | `/AO1` | **GND** | off-by-one |
| 12 | `/AO2` | **/AO1** | off-by-one |
| 13 | `GND` | **/AO2** | off-by-one |
| 14 | `/BO2` | BO2 | ok |
| 15 | `/BO1` | BO1 | ok |
| 16 | **`+BATT`** | **GND** | **pack short** |

Pad 16 puts `+BATT` on the module's GND pin — a dead short across the 2S pack the
moment U2 is seated. The left row (JP2: `PWMA, AIN2, AIN1, STBY, BIN1, BIN2, PWMB,
GND`) is **correct** and is what pins the 180° mapping down.

**This lives in buddy's `.kicad_pcb`, not the shared library — a footprint respin
will not touch it.** Must be fixed here.

---

### E2. C3 was placed on top of U2's pad column — **FIXED 2026-08-06 (2nd pass)**
C3 (1000 µF, `CP_Elec_10x10.5`) sat at **(53.62, 25.0)** — the same X as U2 pad 9, but
5.9 mm *below* it. The 10 mm can therefore covered **U2 pads 9–13**. Unbuildable: the
module cannot be seated and the pads cannot be soldered.

The intent was right — "C3 must sit at pad 9, VM has only 0.5 V of margin" — and the
X coordinate was right. Only the side was wrong, and the placement comment reads
correctly, which is why it survived review. DRC said only *"courtyards overlap"* + 5 ×
*"PTH inside courtyard"*, which reads like a nuisance warning, not "this cannot exist".

**Watch for this class:** a courtyard overlap between a tall part and a pad column is
not cosmetic. Any `pth_inside_courtyard` naming a component body should be treated as
an assembly blocker until proven otherwise.

Now at **(53.62, 10.75) rot 90**, above the module:
- pad 1 (+) at (53.62, 14.95) → **4.16 mm straight down to U2 pad 9**, no dogleg
- gaps: MH2 0.49 mm left, J1 0.10 mm right, U2 0.10 mm below
- only possible because F4 corrected U2's courtyard top from 14.96 → 17.55, **and**
  because MH2 vacated (55, 11)

**Mounting pattern reworked** (holes confirmed free to move — the chassis is built to the
board, not the reverse):

| Hole | Position | Note |
|---|---|---|
| MH1 | (4, 11) | unchanged |
| MH2 | (55,11) → **(44.5, 4)** | it owned the only approach to pad 9 from above; with it there the best C3 could reach was an 8.8 mm dogleg |
| MH3 | (4, 56) | unchanged |
| MH4 | (55, 56) | unchanged |
| **MH5** | **(60.5, 24.5)** — new | right edge, between J1 and J2 |

**MH5 is the one that matters mechanically.** The right edge carries both motor
connectors and both take cable pull, and with four corner holes the nearest support to
J1 was ~25 mm away. **J2 moved y 42 → 46.5** to open the slot: the J1/J2 courtyard gap
had been 6.5 mm, which fits the 6.19 mm keepout but *not a driver* — an M3 head is ~6 mm
across and would have sat in a 6.5 mm slot between two ~11 mm-tall housings. At 11 mm
there is 1.4 mm to J1 and 3.4 mm to J2 around the head.

MH5 sits in the U2→J1/J2 motor corridor, which is only routable because R3a fixed the
DSN keepouts — before that the router drove `/AO1` straight through the hole.

---

## F — Footprint geometry

### F1. ESP32-S3-Zero rear cluster is fabricated geometry (fatal)
`Waveshare_ESP32-S3-Zero_FlatMount` places 8 cluster pads as 2 columns of 4 at
x=4.87/13.22, y=14.84/16.43/18.02/19.61 (1.59 mm pitch). The real module does not
have this topology.

Root cause: the STEP contains **exactly two** Φ1.40 mm board-frame cylinders —
(4.870, 14.839) and (13.220, 14.839) — and nothing else in that region at any
radius. The 2026-06-26 pass validated those two points and **extrapolated the other
six**. Topology was assumed, not measured, which is why a coordinate-level
correction could not catch it.

**The STEP cannot resolve the cluster.** Pads are not modelled as cylinders; the
z=−0.010 geometry is a sub-part in its own local frame (x spans −0.5…0.87).
Recovering it would need physical measurement or a Waveshare dimension drawing.

**v2 resolution: buddy deletes the cluster (see A1). No measurement needed.**

Signal order, if ever needed: `GP45 · 42 · 41 · 40 · 39 · 38 · 18 · 17` from the
USB-C end. Record positions in the module **front** frame —
`x_front = 18.00 − x_from_back_left_edge`; the back view is mirrored, and that is
the trap.

### F2. Perimeter footprint — VERIFIED GOOD, do not re-derive
18 holes at x=1.389/16.629 → **15.240 mm** row spacing, 2.54 pitch, y=1.59–21.91,
18 × 23.5 body, 1.59 mm first-pad offset, R1.00 corners. Confirmed independently
from the STEP and vendor-verified on both axes by scout.

### F3. `Waveshare_ESP32-S3-Zero-M_Socket` stale (shared library)
Pads at ±7.75 → 15.500 mm; must be ±7.62 → 15.240 mm. Harmless in SMD, fatal in
THT. Only blocks buddy if v2 sockets the module rather than flat-mounting.

### F4. `SparkFun_TB6612FNG_v2` body extents — **RESOLVED 2026-08-06 (2nd pass)**
The footprint claimed a **23.0 × 23.0 mm body / 26.1 × 26.1 mm courtyard**. The real
module is **20.32 × 20.32 mm** — 2.89 mm of phantom courtyard per side.

Settled from the vendor Eagle file already sitting in `docs/ref/`
(`SparkFun_Motor_Driver-TB6612FNG_v11c.brd`), not from a caliper:

| Evidence | Value |
|---|---|
| Layer 20 (Dimension) | four wires forming a `0,0 → 20.32,20.32` square |
| JP1 | `(2.54, 1.27)` R90 → pad column at x=2.54, pads y 1.27–19.05 |
| JP2 | `(17.78, 19.05)` R270 → pad column at x=17.78, same y span |
| Derived | body extends **2.54 mm beyond each pad column in X**, **1.27 mm beyond the end pads in Y** |

Fixed at source in `~/kicad-libs/.../SparkFun_TB6612FNG_v2.kicad_mod` (body, courtyard,
pin-1 marker, ref/value positions), with the derivation written into its `descr` so it
is not re-derived by eye. **This unblocked the C3 placement** — see E2.

Lesson to carry: **the vendor's own CAD was in the repo the whole time.** Before
reaching for calipers on a module footprint, check `docs/ref/` and the vendor's
Eagle/KiCad download — the Dimension layer is authoritative and takes a minute.

Scout's error class still stands for parts with no vendor CAD: pins are the constrained
feature, never assume the body is symmetric about them.

### F5. Stock-footprint variant check (carried from scout)
Scout's AMASS lesson — XT30U-F (cable) vs XT30UPB-F (board-mount), 2.7 vs 1.8 mm
drill — generalises. **Check every stock KiCad footprint against the actual part
variant in stock, not just the custom ones.** Applies to all JST-XH/SH parts here.

---

## C — Connector mateability

Method: list every connector and ask "can any two be swapped, and what happens?"
Every footprint below is individually correct. The defect only appears across the set.

### C1. Three identical JST-XH 2-pin, one at pack voltage (CRITICAL)

| ref | value | pin 1 | pin 2 |
|---|---|---|---|
| J7 | E-Stop | `/ESTOP` | GND |
| J8 | PWR In | **`+BATT`** | GND |
| J10 | LED | `/LED_A` | GND |

All three are `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` — freely interchangeable.

- **Pack cable → J7:** 8.4 V lands on `/ESTOP`, which goes straight to U1 pad 20
  (GPIO) and back-feeds +3V3 through R4. Destroys the MCU.
- **E-stop cable → J8:** the switch now bridges `+BATT` to GND. Pressing e-stop is a
  dead short across a 2S 18650 pack. Worst case here — fire risk.
- **LED cable → J8:** indicator LED directly across the pack.

**Fix:** move J8 to a different connector family (not JST-XH), or a distinct pin
count with a blocked position. Colour/labelling alone is not sufficient.

### C2. J1/J2 identical 6-pin (MEDIUM)
Both `JST_XH_B6B-XH-A_1x06`, same pin functions (`AO1/AO2` vs `BO1/BO2`, both
`+5V`, `GND`, encoder A/B). Swapping is non-destructive but reverses left/right
drive **and** encoders together — so each PID still closes correctly per channel
and the robot simply steers backwards. Consistent-but-wrong is the hard kind to
diagnose. Key or label distinctly.

### C3. Safe by construction — record so v2 doesn't regress
- J5 Qwiic — JST-SH 1 mm, unique on the board.
- J6 HC-SR04 — 2.54 mm pin header; an XH housing cannot mate with it.
- J9 UART/Pi — only 4-pin XH.
- J11 NeoPixel — only 3-pin XH.

---

## L — Labelling and silkscreen

### L1. All 34 Value fields are on F.Fab (same as scout)
Nothing about function or voltage is printed on the physical board. Given C1, this
is the difference between a labelled hazard and an unlabelled one. Move
function/voltage text to F.SilkS for v2.

### L2. J8 "PWR In" does not state voltage
Worst offender given C1. Should read `VBAT 7.4V` or similar.

### L3. J9 "UART/Pi" TX/RX direction ambiguous
`/UART_TX` and `/UART_RX` — whose TX? Ambiguous on a crossover link. Name from the
reflex board's perspective and say so on silk.

### L4. J1/J2 "Motor A"/"Motor B" don't map to left/right
Nets say A = Left (`ENC_LA/LB`) and B = Right (`ENC_RA/RB`), but the labels don't.
Relabel "Motor L"/"Motor R".

### L5. Net-vs-label pass — no lying labels found
Every connector's Value string matches the nets actually on it. Buddy has no
equivalent of scout's J17 "ServoBus" defect. J11 `/NEO_DIN` vs U1 `/NEO_DATA` is a
genuine level-shift boundary (see V1), not a mislabel.

---

## A — Architecture change for v2

### A0. v2 BASELINE — decided 2026-08-06. **Expander, no inverter.**

Supersedes A1/A2 below, which are kept for the reasoning. Requirement that settled it:
**no loss of any motor-control capability.**

| # | Decision | Frees | Note |
|---|---|---|---|
| 1 | **Drop `/BAT_SENSE`** (A3) | 1 | No pack input; HAT reports telemetry over the Pi's i2c-1. |
| 2 | **Tie STBY to the `/ESTOP` net** | 1 | Hardware e-stop, no firmware in the path. Keep even though pins allow otherwise. |
| 3 | **`AIN1/AIN2/BIN1/BIN2` → I²C expander** (TCA9554APWR, LCSC C2863976) | 4 | Preserves full per-channel control. |
| 4 | **Cut the NeoPixels entirely** | 1 | Removes J11, U3 74LVC1G125, R11. |

**19 signals → 13, against 15 perimeter pads. 2 spare.**

#### Why the dual inverter was rejected
`AIN2 = !AIN1` makes `IN1 = IN2` unreachable, so per-channel **coast** (`IN1=IN2=L`,
outputs high-Z) is lost. Reachable states collapse to forward / reverse / short brake.

The proposed mitigation — driving the STBY net low via an open-drain GPIO on `/ESTOP` — was
**wrong**: STBY is a **chip-wide** signal, so it coasts *both* motors together. Coasting one
track while driving the other is unreachable with the inverter under any firmware trick.
That is a genuine loss of motor-control capability, so the inverter is out.

It also mattered that decisions 2 and 3 interacted: tying STBY to `/ESTOP` removes the only
other route to high-Z, so the inverter plus that tie would have eliminated coast entirely.

#### What the expander costs, stated plainly
- Motor direction sits **behind the I²C bus**. Safety is unaffected — PWM stays on hardware
  GPIO (so PWM=0 → short brake always works) and `/ESTOP` → STBY gives hardware high-Z
  independent of the bus.
- Sequence a direction change as PWM=0 → write direction → restore PWM. An I²C byte at
  400 kHz is ~60 µs, about one PWM period; the zero-PWM window is good practice anyway.
- 🔴 **X1 returns to blocker status.** With an on-board I²C device the bus must work with J5
  empty, so the 4.7 kΩ pull-ups are mandatory, not good practice.
- Expander shares the bus with the BMI270 (0x68/0x69 vs 0x38–0x3F — no clash). Bandwidth is
  ample, but the IMU feeds the **tilt hard-stop** (`esp32-reflex/main/safety.h`), so keep
  bus utilisation low enough that IMU polling is never starved.
- TCA9554A powers up with all I/O as inputs — fit **pull-downs on all four direction lines**
  so the driver has a defined state before firmware configures it.

**Full state coverage achieved:** per channel — forward, reverse, short brake, **coast**;
chip-wide — hardware standby via e-stop. Nothing unreachable.

⚠ Note the earlier "move the BMI270 to the Pi's i2c-1 for spare pins" idea is **dead**:
`safety.h` uses the IMU for a tilt hard-stop, and that input must stay local to the safety
MCU rather than round-tripping through the Pi.

**Why STBY → `/ESTOP` is a gain, not a compromise.** `/ESTOP` is active-low (R4 pull-up,
switch to GND); TB6612 STBY is active-high-enable. Wiring them together means **pressing
e-stop disables the motor driver in hardware**, with no firmware in the path. `/ESTOP` still
reaches a GPIO for software awareness. Boot state becomes driver-enabled with PWM held low
by R1/R2 → short brake, so the motors resist motion rather than spinning or coasting.

**Why no expander.** It is not the ~$1.09: keeping the four direction pins on hardware GPIO
means **motor direction never depends on the I²C bus**. It also means buddy adds *no*
on-board I²C devices, which demotes **X1 (pull-ups) from blocker to good practice** — still
fit 4.7 kΩ, but the bus is no longer load-bearing for motor control.
Fallback if a future signal forces the expander back: **TCA9554APWR, LCSC C2863976**,
TSSOP-16, Extended, ~$1.09@10, 152 in stock (verify at order time; confirm the match review
shows TSSOP-16). MCP23008-E/SO C92253 is the alternate but is a 300-mil SOIC-18.

**Consequences of cutting the NeoPixels:**
- Delete J11, U3, R11, and the `/NEO_DATA` `/NEO_BUF` `/NEO_DIN` nets.
- **Keep C6 100 µF and C7 100 nF** — they were annotated as NeoPixel decoupling but are the
  `+5V` rail's bulk and HF bypass, which the rail still needs (X8, and the cable-fed-rail rule).
- J10 + R10 (the separate always-on power LED) are unaffected.

### A0d-v2. 🔴 The no-fuse safety case must be re-derived — the trace it cited is gone

A0d closed X2 (inverted overcurrent coordination) by widening `+5V` to 1.5 mm and
moving J9 to JST-VH, giving `HAT ~5 A < trace 5.26 A < connector 10 A`. **`RAIL_W` is
now 0.4 mm** (it was narrowed to clear 14 clearance violations, §R2), so that chain no
longer holds as written: at 1 oz a 0.4 mm trace carries ~2.0 A, at 2 oz ~3.3 A — in both
cases **below** the ~5 A source. On paper the coordination is inverted again.

**The board itself is very likely fine, and for a different reason than the one
documented.** The 5 A path never touches a surface trace:

| `+5V` node | Pad | Path |
|---|---|---|
| J9.1 (power in) | PTH | barrel straight onto the In2.Cu plane |
| U2.9 (VM, the motor current) | PTH | barrel straight off the plane |
| C3.1 (1000 µF bulk) | PTH | barrel straight onto the plane |
| J1.3 / J2.3 (motor connectors) | PTH | barrel onto the plane |
| J6.1 (HC-SR04, ~15 mA) | PTH | barrel onto the plane |
| C4.1, C7.1, R10.1, U1.1 | SMD | surface stub + via — decoupling and ~250 mA of logic |

Zone pad connection is **`ZONE_CONNECTION_FULL`** on all three planes (verified — note
that in pcbnew 10.0.5 `FULL == 2` and `THERMAL == 1`, which reads backwards if you
assume the usual ordering), so those barrels get solid copper, not thermal spokes.

To close this, the safety case has to be rewritten in terms of the plane and the
barrels rather than the surface trace, **and** the copper weight has to be declared —
see A0e.

### A0e. 🔴 No copper weight is declared anywhere
The board has **no stackup** in either `.kicad_pcb` or `.kicad_pro`. `check_pcb_ampacity.py`
defaults to **2 oz outer**, which is an assumption the board does not state, and JLC's
default for 4-layer is **1 oz outer / 0.5 oz inner**. Every ampacity number in this
register therefore rests on a parameter nobody has chosen. Decide it, declare it in the
board stackup, and order to it — a 2 oz assumption silently built at 1 oz halves the
outer-copper margin.

### A0d. (original) Fuse part verification — the PTC conflicts with the VM margin

Verified against the [Bourns MF-MSMF datasheet](https://www.bourns.com/docs/product-datasheets/mf-msmf.pdf)
before layout, 2026-08-06. Three findings:

**1. PTC coordination is on I_trip, NOT I_hold.** The obvious "2 A fuse"
(SMD1206P200TF, LCSC C545216) holds 2.0 A but **trips at 3.50 A** — above the 3 A
JST-XH rating. That is scout's 3 A-fuse-on-3 A-connector defect wearing a different
hat. The part that actually coordinates is the 1.6 A-hold one, tripping at 2.80 A.

**2. `MF-MSMF160-2` is not a datasheet part number** — the variant trap again
(cf. AMASS XT30U-F vs XT30UPB-F, F5). Real designators are voltage-suffixed:

| Model | V_max | I_hold | I_trip | R_1max | AEC-Q200 |
|---|---|---|---|---|---|
| MF-MSMF160/8X | 8 V | 1.60 A | 2.80 A | 0.100 Ω | — |
| MF-MSMF160/12X | 12 V | 1.60 A | 2.80 A | 0.100 Ω | — |
| MF-MSMF160/16X | 16 V | 1.60 A | 2.80 A | 0.100 Ω | ✓ |
| MF-MSMF160/24X | 24 V | 1.60 A | 3.20 A | 0.100 Ω | ✓ |

The `-2` seen at distributors is a packaging suffix. The datasheet also flags several
models "not recommended for new designs" (⚠ on MF-MSMF150/12 among others); the /160
variants are clean.

**3. 🔴 But R_1max = 0.100 Ω eats the VM margin.** At the 1.75 A peak that is 175 mV,
plus ~43 mV trace and ~18 mV connector:

```
5.00 V − 0.236 V ≈ 4.76 V at U2 VM      (TB6612 floor 4.50 V)
```

**~47 % of the entire 0.5 V VM budget**, before PTC self-heating raises R further or
the HAT sags under the step. Adding a fuse to protect the copper would undermine what
the copper feeds.

**Recommended instead — no series element at all:** widen `+5V` to **1.5 mm**
(5.26 A at 1 oz) and move J9 to **JST-VH** (10 A). The HAT's own ~5 A limit becomes the
protection:

```
HAT ~5 A  <  trace 5.26 A  <  connector 10 A     coordinated, zero series resistance
```

No added drop, no extra part, and the JST-VH change also resolves C1/C2 keying — the
same move scout made. **This supersedes A0b's "2 A slow-blow" and X2 if adopted.**

### A0c. v2 PIN MAP — 13 signals + 3 power on 18 perimeter pads, 2 spare

Uses `Waveshare_ESP32-S3-Zero_FlatMount_NoCluster` (pad numbering unchanged from the
clustered variant: 1–9 left, 18–26 right).

| Pad | GPIO | v2 signal | vs v1 |
|-----|------|-----------|-------|
| 1 | — | `+5V` | — |
| 2 | — | `GND` | — |
| 3 | — | `+3V3` | — |
| 4 | 1 | *spare* (ADC1_CH0) | was `/BAT_SENSE` — deleted |
| 5 | 2 | `/ECHO_DIV` | unchanged |
| 6 | 3 | `/TRIG` | unchanged |
| 7 | 4 | `/PWMA` | unchanged |
| 8 | 5 | `/PWMB` | unchanged |
| 9 | 6 | *spare* | was `/AIN1` — moved to expander |
| 18 | 43 | `/UART_TX` | unchanged |
| 19 | 44 | `/UART_RX` | unchanged |
| 20 | 13 | `/ESTOP` | unchanged — **also drives the STBY net** |
| 21 | 12 | `/ENC_RB` | unchanged |
| 22 | 11 | `/ENC_RA` | unchanged |
| 23 | 10 | `/ENC_LB` | unchanged |
| 24 | 9 | `/ENC_LA` | unchanged |
| 25 | 8 | `/SCL` | **moved** from cluster GPIO18; GPIO8 freed by STBY→`/ESTOP` |
| 26 | 7 | `/SDA` | **moved** from cluster GPIO17; GPIO7 freed by AIN2→expander |

Expander U4 (TCA9554APWR) P0–P3 = `/AIN1`, `/AIN2`, `/BIN1`, `/BIN2`.

**Only SDA/SCL actually move**; everything else either stays put or moves to the expander.
They land adjacent on pads 25/26 so the I²C bus, J5 and U4 can share one side of the board.

**Firmware delta for `esp32-reflex/main/pin_map.h`:**
- `PIN_IMU_SDA` 17 → **7**, `PIN_IMU_SCL` 18 → **8**
- `PIN_AIN1/AIN2/BIN1/BIN2` become expander bits P0–P3, not GPIOs
- `PIN_STBY` (GPIO8) removed — STBY is hardware-tied to `/ESTOP`
- `PIN_VBAT_SENSE` (GPIO1) removed; GPIO1 and GPIO6 are the two spares
- Everything else unchanged.

### A0b. 🔴 `POWER_W` is sized on an assumption A3 invalidated
`route_pcb.py:35` sets `POWER_W = 0.40 mm`, narrowed from 0.50 "to clear NeoPixel cluster;
**adequate for <500 mA 5V rail**". A3 puts the motors on `+5V`, so that premise is gone.
0.40 mm at 1 oz rates **2.02 A**; the post-A3 peak is ~1.75 A (1.5 A motors + 0.25 A logic)
= 87 % of rating, ΔT ≈ 22 °C. It had been 99 % before the NeoPixels were cut.

Same class of defect as scout's fuse-vs-trace: a number justified under conditions that
later changed, with nothing re-checking it.

- [ ] **Widen `+5V` to 0.8 mm** (3.34 A, ΔT ≈ 7 °C). The NeoPixel cluster it was dodging is
      now gone, so the original reason for 0.40 mm no longer applies either.
- [ ] **Fuse `+5V` at 2 A slow-blow.** Coordination rule is *fuse < min(conductor,
      connector)*: 2 A < 3.34 A trace and 2 A < 3 A JST-XH ✅. Continuous load is ~0.55 A, so
      a 2 A slow-blow rides the 1.75 A motor transients without nuisance tripping.
      This supersedes X2's "2 A on `+BATT` and `+5V`" — there is only one rail now.

### A1. (superseded by A0) I²C expander removes the cluster dependency entirely

Buddy's budget: 18 perimeter pads − 3 power (`+5V`, `GND`, `+3V3`) = **15 signal
pads**, all consumed, **plus 5 cluster nets** (`/NEO_DATA`, `/BIN2`, `/BIN1`,
`/SCL`, `/SDA`) = 20 signals needed. Deficit of 5 — same shape as scout's.

Scout's I²C-ADC relief was assessed as not transferring to buddy because `/SDA` and
`/SCL` sit on the cluster and an I²C bus can't move onto an I²C device. That's
correct but narrower than it looks: it rules out moving SDA/SCL, not out moving
everything else off the cluster.

| must stay on GPIO | can move to I²C |
|---|---|
| PWMA, PWMB (hardware PWM) | AIN1, AIN2, BIN1, BIN2 (direction) |
| ENC_LA/LB/RA/RB (edge interrupts) | STBY (static enable) |
| ECHO_DIV, TRIG (µs timing) | BAT_SENSE (analog, slow) |
| NEO_DATA (800 kHz WS2812) | |
| ESTOP (interrupt) | |
| UART_TX/RX, SDA, SCL | |

The four direction pins are the unlock — they change at command rate (tens of Hz),
while PWM stays on hardware GPIO. A 400 kHz I²C byte is ~50 µs.

**Move AIN1/AIN2/BIN1/BIN2 + BAT_SENSE → 15 vs 15. Exactly fits, cluster deleted,
zero features lost.** Add STBY → 14 vs 15, 1 spare — the same landing as scout.

Buddy then uses the perimeter-only `_NoCluster` variant, and **buddy's rear-pad
caliper session is cancelled too.**

### A2. Expander power-up state is a safety property
If STBY moves to the expander, do **not** use PCF8574 — it powers up with all pins
weakly high, which would *enable* the motor driver at boot. Use **MCP23008 or
TCA9554A** (power up as inputs) with external pull-downs on STBY and the four
direction pins, matching the existing R1/R2/R3 pattern.

The fail-safe survives an I²C wedge either way, since PWM stays on GPIO and PWM=0
puts the TB6612 into short-brake regardless of the IN pins. This is about boot
state, not runaway.

Addresses are clear: the reflex bus carries only the Qwiic BMI270 (0x68/0x69). The
INA219 at 0x40–0x45 is on the Pi's i2c-1, a separate bus. Expander → 0x20,
ADS1115 → 0x48. Both need the JLC package check (see F5 and the wrong-package trap).

### A3. RESOLVED 2026-08-06 — **drop `/BAT_SENSE`; there is no pack input**

Decision: **buddy is powered solely from the Pi HAT in this version; the direct 2S pack
connection is gone.** So `docs/power.md`'s single-rail topology was right and the board was
wrong — the separate `+BATT` input was the divergence, not the doc.

Consequences for v2 capture:

| Change | Detail |
|---|---|
| Remove `/BAT_SENSE` | Delete R8 100k, R9 47k, C2 100nF. Frees a GPIO. Pack telemetry already comes from the HAT's INA219 over the Pi's i2c-1. |
| Eliminate the `+BATT` net | TB6612 `VM` (pad 9) ties to `+5V`. |
| Remove J8 | The board no longer has a second power input. |
| In2.Cu plane | Was `+BATT`; re-purpose to `+5V` (or GND — decide at layout). |
| 🔴 **VM margin collapses to 0.5 V** | TB6612 floor is 4.5 V and the supply is now 5 V. This promotes **X4 from 🟡 to 🔴**: C3 1000 µF must sit **at pad 9**, not 31.8 mm away. |
| 🟡 One shared rail | Motor transients now sag the rail the Pi runs on. Peak ≈ 4.99 A against the HAT's 5 A (see X6). |
| ✅ **C1 largely dissolves** | With J8 gone, the JST-XH 2-pin group is J7 (E-Stop) and J10 (LED) — both signal-only, same domain, no destructive swap. Still key them, but the pack-into-GPIO hazard is designed out rather than mitigated. |
| ⚠ Revises X2 | See the fuse re-sizing below — a single 5 V input now carries the motors too. |

⚠ Still to confirm: whether the HAT itself is still the 2S 18650 UPS HAT (B). That does not
change the reflex board, but `docs/power.md`'s Battery section may need updating.

### A3-old. (superseded) — is BAT_SENSE needed at all?
`docs/power.md:78-81` states the reflex ESP32 "only sees USB 5 V, not pack voltage"
and that `PIN_VBAT_SENSE` is obsolete and "will be freed in a follow-up cleanup."
But the board implements a pack divider (R8 100k / R9 47k → `/BAT_SENSE` → U1 pad 4).
The board and the doc disagree.

Board supply is consistent with the doc — `+5V` comes from the Pi via J9, and `+BATT`
via J8 feeds only the TB6612 VM stage plus this divider. So the divider is an
addition made against the documented topology, and the Pi/HAT already reports pack
voltage and SoC via the INA219.

Two ways to close it:
- **Keep** — an independent local undervoltage check on the safety/motor MCU that
  doesn't depend on the Pi. Needs the ADS1115.
- **Drop** — Pi already monitors; frees a GPIO for free, drops a part, and matches
  the documented topology. Then only the expander is needed, and moving the four
  direction pins alone gets to 15 vs 15.

**Decide before layout — it changes the v2 BOM.** Whichever way, update
`docs/power.md` so board and doc agree.

---

## O — Ordering / assembly split (decided 2026-08-06)

**JLC order is SMT-only.** No through-hole assembly step: it would have needed wave
soldering with a fixture, an extra build day, and JLC-purchased parts "cannot be shipped
separately" — no fallback if the step is declined. VH headers are easier to hand-solder
than the XH already being done by hand, so there was nothing to gain.

| JLC (SMT, 21 parts) | Hand-solder |
|---|---|
| 0402 R/C, U4 TSSOP-16, J5 Qwiic JST-SH | J1, J2, J6, J7, J9, J10 |
| **C3 1000 µF + C6 100 µF — SMD electrolytic** | U1 Waveshare module, U2 TB6612 breakout |

**C3 and C6 were moved from THT radial to SMD** (`CP_Elec_10x10.5` / `CP_Elec_6.3x5.4`)
specifically so C3 is machine-placed: VM has only 0.5 V of margin post-A3, so its position
at U2 pad 9 is an electrical requirement, not tidiness. Achieved **7.23 mm** (was 31.8 mm).
At that distance ESL is ~7 nH = 0.0009 Ω at 20 kHz, against C3's ~0.08 Ω ESR — the ripple
path is unspoiled. It cannot go closer: U2 is header-mounted and a 10.5 mm can will not fit
beneath it.

**C3 ripple verified** against C3445233 (KNSCHA, 1000 µF 16 V, D10×10.5, Extended):
20 kHz PWM, chopped supply current, worst case D=0.5 → **150 mA RMS continuous**
(2×150 mA motors) vs a 300 mA rating, ~270 mA derated for 20 kHz = **56 % of rating**.
C3 carries the majority of it (|Z| 0.080 Ω vs the breakout tantalum's 0.94 Ω). The
direction-flip transient reaches 750 mA RMS but lasts milliseconds and ripple ratings are
thermal. ESR heating 1.8 mW.

**Part-number traps caught while ordering:**
- **ROB-14450 is the with-headers TB6612 breakout, NOT ROB-14451** (14451 is the bare "1A"
  board). Our footprint needs the headers.
- `MF-MSMF160-2` is not a datasheet part number — Bourns uses voltage suffixes
  (`/8X /12X /16X /24X`). Moot now that the fuse was dropped (A0d), but the pattern isn't.
- `B4P-VH` vs `B4P-VH-B` / `-FB-B` / `-R` are different orderable parts; the first two share
  an identical KiCad land pattern (diffed), the others were not checked.
- SVH-21T-P1.1 is AWG **#22–#18**, not #16 as one distributor listing claimed. AWG #16
  needs SVH-41T-P1.1.

**All footprints are on F.Cu** — nothing bottom-side, confirmed, which is what would have
made wave soldering viable had we taken that route.

### O1. 🔴 `jlcpcb-assembly/robot-buddy-reflex-bom.csv` is the **v1** BOM — do not order from it
Nine rows, and it describes a board that no longer exists:

| Problem | Detail |
|---|---|
| Parts deleted in v2 still listed | `U3` 74LVC1G125 and `R11` — both removed with the NeoPixel circuit (A0) |
| v2 parts absent | `U4` TCA9554APWR (C2863976), `R12`–`R17` expander pull-downs |
| Values disagree with the schematic | BOM says `R6` = 20k; the schematic says 15k |
| **C3 and C6 have no LCSC part at all** | Neither electrolytic is in the BOM, despite C3 being the part the §O ripple analysis is built on |

C3's part *is* settled — **C3445233**, KNSCHA 1000 µF **16 V**, D10×10.5, an SMD V-chip,
which is exactly what `Capacitor_SMD:CP_Elec_10x10.5` lands. C6 (100 µF, `CP_Elec_6.3x5.4`)
has no part number recorded anywhere. Both need to reach the BOM before ordering.

**C3 and C6 are SMD, not through-hole, and that is deliberate** — this order is SMT-only,
so a radial can would have to be hand-soldered. `layout_pcb.py` used to describe C3 as
"polarized THT, 10mm dia, 5mm lead pitch", a radial part this board has never carried;
the schematic and footprint always said SMD. Comment fixed. Worth a conscious call before
ordering: a 10 mm can on SMD pads is the heaviest part on a machine that vibrates, and
gluing it or moving to a leaded part are the alternatives if that is judged a risk.

- [x] BOM and CPL regenerated from the v2 schematic by `make_fab.py` (P8)
- [ ] Assign LCSC parts for C3 and C6 (neither is fab-placed, but both need ordering)

### O2. 🔴 C3 and C6 were silently swapped from radial THT to SMD — **REVERTED**
Caught by asking a simple question of the BOM: *if C3 is SMD, is it coming with the
board?* It is not. `jlcpcb-assembly/README.md` says, and has always said:

> **What YOU hand-solder (excluded — all THT / modules)**
> — C3 1000 µF, C6 100 µF (radial electrolytics)

But `layout_pcb.py` and `populate_schematic.py` had them as
`Capacitor_SMD:CP_Elec_10x10.5` / `CP_Elec_6.3x5.4` — surface pads, no drill. A radial
cap has two wire leads and cannot be fitted to them.

**`git log -S` on both footprint strings returns nothing.** The SMD names appear in *no
commit*; they existed only in the uncommitted working tree, while every committed
artefact — both scripts and the assembly README — said radial THT. So this was never a
recorded decision, and it would have shipped a board the parts on hand do not fit.

Restored to `Capacitor_THT:CP_Radial_D10.0mm_P5.00mm` and `CP_Radial_D5.0mm_P2.00mm`.
THT is also the better answer electrically: the pad barrels pass through In2.Cu, so C3's
`+5V` terminal lands **on the +5V plane** and its GND terminal on the In1/B.Cu GND
planes. The plane is the connection; the 4.51 mm run to U2 pad 9 is a secondary path.

⚠ Two consequences to check before ordering:
- The §O ripple analysis was done against **C3445233** (KNSCHA 1000 µF 16 V, D10×10.5),
  which is an **SMD V-chip**. The 150 mA RMS / 300 mA rating result should carry to an
  equivalent radial 1000 µF 16 V, but **the part number in that analysis is for the
  wrong package** and needs re-picking.
- `CP_Radial_D10.0mm_P5.00mm`'s origin is **pad 1, not the body centre** (courtyard runs
  y−7.79 … y+2.79). Placement arithmetic that assumes a centred origin will be wrong.
- 🟡 **C6's footprint may be undersized.** `CP_Radial_D5.0mm_P2.00mm` is the committed
  value and was restored as-is, but a 5 mm-diameter radial can is roughly 100 µF at
  6.3 V or 47 µF at 16 V. C6 sits on the 5 V rail, so 6.3 V leaves almost no derating
  margin — a 100 µF 16 V part is typically 6.3 × 11 mm and would need
  `CP_Radial_D6.3mm_P2.50mm`. **Measure the cap actually in hand before fab.**

**Generalise this.** F5 already says to check stock footprints against the actual part
*variant*. This is the same class one level up: check the footprint against **how the
part is being sourced and assembled**. "Is this coming with the board?" is a question
worth asking of every part, and the assembly README is the authority, not the footprint.

---

## R — Route status (2026-08-06)

**Routed, fully connected, DRC not yet clean.** Do not export gerbers.

| Check | Result |
|---|---|
| Routing gate | ✅ 475 tracks, 46 vias, every net has copper |
| Design review gate | ✅ mateability / label-vs-net / silk / placement |
| DRC unconnected | ✅ **0** |
| DRC schematic parity | ✅ 0 |
| DRC violations | ⚠ **194** (from 268) |

### Fixed
| Was | Now | How |
|---|---|---|
| 17 shorts, 18 mask bridges | **0** | `RAIL_W` 1.5 → 0.8 mm. In2.Cu is a solid `+5V` plane and freerouting's vias are through-hole, so the plane carries the ampacity — the surface trace only needs to reach pads and vias. Supersedes A0b's 1.5 mm. |
| 86 clearance | **32** | Clearance set to **0.2 mm uniformly**. 0.25/0.3 was sized when `+BATT` carried pack voltage; A3 removed that rail, so nothing exceeds 5 V. IPC-2221 creepage below 15 V is negligible and JLC 4-layer capability is well under 0.2 mm — this is a correction, not a relaxation. |
| netclasses hardcoded twice | single source | `layout_pcb.py` writes them to `.kicad_pro`; `route_pcb.py` reads them back for both DSN classes and the width fixup. They had drifted. |
| 9 stale `+3V3` patch tracks | removed | Hand-tuned to v1 geometry (referenced a via at 22.10,22.04; ran to x=53.62 where C3 now sits) and applied unconditionally. **Verified obsolete** — 0 unconnected without it. |
| C6 ↔ U1 pad collision | fixed | Rotated 90°; its pads span 9.1 mm against a 9.0 mm gap. |

### Two things I got wrong, recorded so they aren't retried
- **Aligning per-class DSN clearances did nothing** (72 → 76). Freerouting plans most pairs
  against the *structure-level* rule, not the per-class ones.
- **Raising the structure clearance to 300 µm made it worse** (72 → 86): it demanded room
  the board does not have. Lowering to a uniform 0.2 mm is what actually worked.
- Run-to-run variance is only ±1 violation, so these deltas were real, not noise.

### Remaining 194 — needs a manual KiCad pass, not more autorouter tuning
Freerouting's score converged (971.37, plateaued by pass 8); more passes will not help.

| Count | Type | Disposition |
|---|---|---|
| 109 | silk_over_copper / silk_overlap / text_height / silk_edge | Text is legible at 1.0 mm but positions need moving. Manual. |
| 32 | `clearance` | 22 Pad↔Track, actuals 0.05–0.19 mm. Freerouting is not honouring the 200 µm it was given for these pairs. Interactive-router cleanup, or more board area. |
| 30 | `lib_footprint_mismatch` | **Expected** — the DFM pass edits pads after placement by design. Accept or exclude. |
| 13 | `track_dangling` | Stubs carrying no current. KiCad's *Cleanup Tracks & Vias* clears them; not scripted because zone-terminated tracks are easy to remove wrongly. |
| 10 | courtyard / edge clearance | Small, mostly pre-existing. |

**The "manual KiCad pass" above was not needed and was NOT done.** All of it was
scripted instead — see §R2. That mattered: a hand pass in the GUI is exactly the P1
failure mode, and the board was regenerated ~6 more times afterwards.

## R2 — Route status (2026-08-06, 2nd pass) — **194 → 25, 0 errors**

| Check | Result |
|---|---|
| Routing gate | ✅ 379 tracks, 46 vias, every net has copper |
| Design review gate | ✅ mateability / label-vs-net / silk / placement |
| DRC unconnected | ✅ **0** |
| DRC **errors** | ✅ **0** |
| DRC warnings | ⚠ **25**, all silkscreen — dispositioned below |

Everything below is encoded in `layout_pcb.py` / the new `hardware/kicad/finish_pcb.py`,
which `route_pcb.py` invokes as Step 6.5. Nothing was clicked in KiCad.

| Was | Now | How |
|---|---|---|
| 30 `lib_footprint_mismatch` | **0** | Severity → `ignore` in `.kicad_pro`, written by `layout_pcb.py`. Expected by design — the DFM pass edits pads after placement. Silenced rather than per-instance excluded: an exclusion list goes stale the moment a footprint moves and would then hide a genuinely swapped part. |
| 20 `text_height` | **0** | The bump pass matched the literal `(size 0.7 0.7)` and silently missed the 0.6 mm pin labels inside U1 and U2. Now matches **any** font below the 0.8 mm minimum. ⚠ The regex **must** stay anchored on `(font` — pads carry `(size x y)` too, and an unanchored match shrink-wraps every 0402 pad up to 1.0 mm. |
| 13 `track_dangling` | **0** | Deleted exactly what `kicad-cli pcb drc` names, iterating until it reports none. |
| 5 `pth_inside_courtyard` + 1 `courtyards_overlap` | **0** | E2 — C3 moved off U2's pad column. |
| 4 `copper_edge_clearance` | **0** | J9 x 1.5 → 2.0 (2.7 mm pads left only 0.15 mm to the edge against a 0.5 mm rule). R5/R6/R7 moved 6.5 → 7.7 to stay clear of it. |
| 32 `clearance` | **0** | Two independent causes, below. |
| 109 silk | **25** | Four passes, below. |

### The clearance fix was two separate things
1. **`Rail` width 0.8 → 0.4 mm** killed 14 of the 16 unique violations. The surface
   `+5V` trace carries almost nothing: In2.Cu is a **single filled island spanning the
   whole board** (verified), and every high-current `+5V` node — J9.1 (power in), U2.9
   (VM), J1.3, J2.3, J6.1 — is a **through-hole pad sitting inside it**, so it reaches
   the plane through its own barrel. Width is set by the plane and the barrels, not by
   the surface run. 0.8 mm was just freerouting threading fat copper between 0402 pads.
2. **One segment was simply off-centre.** The `+3V3` run under U1 had a 1.04 mm channel
   between pad 19 (bottom y=20.88) and pad 20 (top y=21.92); a 0.4 mm track with 0.2 mm
   either side needs 0.80 mm, leaving a 0.24 mm legal band for the centreline — and the
   router had put it 0.13 mm above that band. `finish_pcb.py` now **slides** such a
   segment perpendicular into the legal window, dragging coincident endpoints so
   neighbours stay connected, with **DRC as the judge** — each candidate offset is
   applied, re-checked, and kept only if the count drops.

### 🔴 The 16 "clearance violations" were really 1 — duplicate copper
`layout_pcb.py` deliberately preserves `traceItems` as freerouting seeds, and
`route_pcb.py`'s SES import **adds** the router's own copy on top. **Every run left
another duplicate behind: 71 exact duplicates in 450 segments**, including 8 stacked
copies of the same 13.9 mm `+3V3` run.

DRC reports a violation **once per copy**, so a single geometric problem presented as
16 and looked far worse than it was. `finish_pcb.py` now dedupes (same net/layer/width/
endpoints) as pass 0, which also cleans the seeds for the next run so the count cannot
creep. **Worth checking on scout — same seed-preservation pattern.**

### 🔴 The text_height fix caused 17 of the silk violations
Promoting sub-minimum silk to **1.0 mm** made U1's 18 pin labels 25 % wider than the
rule requires and pushed them into the passives packed around the module. Now promotes
to exactly **0.8 mm**. General lesson: a fix that changes geometry to satisfy one rule
can manufacture violations of another — re-measure the whole report, not the rule you
were fixing.

### Silk: 109 → 25
| Pass | Effect |
|---|---|
| Reference/Value auto-placement | Tries a ring of candidate positions around each footprint, scoring against copper, other silk, and the board outline; hides a field only if nothing fits. **37 relocated, 3 hidden.** |
| Clip silk to the board outline | Edge-mount connectors (J1/J2/J9/J10) legitimately overhang. Rectangles are expanded to their four sides so each clips independently. **20 graphics clipped → 18 segments kept.** |
| U2 pin labels | Were anchored at the exact centres of pads 1 and 9 — ink on the solderable holes — and invisible anyway once the breakout is seated. Now short `1` / `9` marks *outside* the body, where they can actually be read. |
| `subtractmaskfromsilk` no → **yes** | Plot-time knockout of mask openings from silk. |

### Silk went 25 → 0 by making room instead of dispositioning
An earlier draft of this section argued the residual 25 were acceptable because
`subtractmaskfromsilk` would keep ink off the pads at plot time. **That reasoning was
wrong twice over** and is recorded so it is not reused:
- The board-level `subtractmaskfromsilk` flag is **not honoured by `kicad-cli pcb
  export gerbers`** — a silk gerber plotted with it on and off came back byte-identical.
  The CLI needs an explicit `--subtract-soldermask` flag. Any claim about what the
  gerbers contain must be checked against a plotted gerber, not the board setting.
- It was treating a space problem as a documentation problem. There was room.

What actually cleared them:

| Fix | Effect |
|---|---|
| U1 pin labels `GPn` → `n` in the footprint | 4-char `GP13` → 2-char `13`, roughly halving the widest labels. The module's own silk still reads `GP13`, so nothing is lost. |
| C6 moved out of the left strip | It was at (4.5, 25) occupying the only clear channel for U1's left-hand labels. The strip is 9 mm and had to hold J9's courtyard (6.25 mm), C6 (7.19 mm) *and* the labels — it never fitted, it just was not DRC-visible. Moved to the empty block below U1. |
| R5/R6/R7 moved to under J6 | They had been pushed to x=7.7 by the J9 edge fix, directly onto the same labels. Under J6 is the better home regardless: R7 is the series ESD resistor on the incoming echo line and now sits ~5 mm from the connector instead of 34 mm. |
| C3/C6 back to radial THT (O2) | Their SMD outlines crossed their own pads; the radial footprints do not. |

- [x] ~~Manual pass in KiCad~~ — scripted instead, see above
- [x] **DRC 0 violations, 0 unconnected, 0 schematic-parity; both gates pass**
- [x] Verified reproducible: two independent full `layout → route` runs both land on 0
- [x] Gerbers/BOM/CPL regenerated by `make_fab.py`, which gates on DRC + both gates (P8)
- [ ] Fill the 3 missing LCSC numbers: `10u` C9, `15k` R6, `4.7k` R16/R17

## R3 — Four latent pipeline bugs found by the last round of changes

Each was present in every prior run and invisible until something moved.

### R3a. 🔴 freerouting never saw ANY mounting hole
`ERROR Package.read_scope: could not read keepout area of package 'MountingHole...'`
printed on every run and had been treated as noise. It is not: freerouting rejects the
**entire package** when a keepout fails to parse, so all five holes were invisible and it
routed straight through them. Two independent causes, both needed fixing:
1. KiCad emits `(circle F.Cu 3700)` — diameter only. The Specctra grammar lets the
   centre default to `0 0`; freerouting does not. Now rewritten to `(circle F.Cu 3700 0 0)`.
2. Four keepouts are emitted per hole, one per copper layer, and `route_pcb.py` strips
   In1/In2 from the DSN — so two keepouts pointed at layers that no longer existed and
   took the F.Cu/B.Cu ones down with them. **Exactly 2 errors per run for 4 keepouts is
   what identified it.** Now dropped alongside the layers.

### R3b. 🔴 Plane zones carved at 0.1 mm while DRC demanded 0.2 mm
All three zones (In1 GND, In2 +5V, B.Cu GND) had a hardcoded 0.1 mm local clearance. A
plane carves around foreign-net copper at *its* clearance, so every foreign track
crossing one was a clearance error. Hidden while B.Cu carried almost no signal routing;
it appeared the moment two nets were re-routed there, and a from-scratch route produced
**121** of them. Both scripts now take the value from the Default netclass.

### R3c. Stale seeds, third variant: shorts
`layout_pcb.py` preserves `traceItems` as freerouting seeds, and a seed survives changes
to the thing it was routed around. Restoring C3/C6 to through-hole took their pads from
F.Cu-only to spanning every layer, and B.Cu tracks that had legally passed beneath them
became **dead shorts** — `/SDA` and `/ENC_LB` onto `+5V`. New pre-route pass
(`finish_pcb.py unshort`) deletes shorting seeds *before* the DSN export so the router
lays those nets again against the geometry that now exists.

That is three distinct failures from one mechanism: duplicates, stubs pointing at moved
pads, and now shorts. **Any pad geometry change invalidates the seeds over it.**

### R3d. Routing from bare copper is much worse, for a different reason than recorded
The note in `layout_pcb.py` says clearing seeds makes freerouting "hang indefinitely".
Tested: it now completes in **1.44 s, fully routed** — that note is stale, from the v1
board with the rear cluster. But the result was far worse (**194 errors**), because
freerouting puts many more signals on B.Cu where they fight the GND plane. **Keep the
seeds — but for routing quality, not for termination.**

## P — Process defects

### P1. The v1 DFM fixes were never in the generation pipeline — **FIXED 2026-08-06**
Found while regenerating the board for E1. Both 2026-07-20 mask-opening fixes
(`keep_end_layers`, NPTH `*.Mask`) had been applied by hand *after* the last
`layout_pcb.py` run and lived nowhere in the scripts. The regeneration silently
reintroduced **all 37 defects** — 33 `keep_end_layers no` and 4 NPTH pads with
`*.Mask` — in a board that would otherwise have looked ready to fab.

This is the failure mode the sign-off gate exists for: a fix verified once, on a
file that a later regeneration overwrites. Anything checked by hand and not
encoded in the pipeline should be assumed reverted after any regeneration.

Now applied automatically at the end of `layout_pcb.py`, which reports
`DFM pass : keep_end_layers no→yes ×33, np_thru_hole *.Mask stripped ×4` on every
run. Re-verified clean afterwards.

**Audit the other three boards for the same gap** — scout's v1 DFM fixes were made
in the same session and may also sit outside its layout scripts.

### P2. Orphaned netless copper survived regeneration — **FIXED 2026-08-06**
`layout_pcb.py` deliberately preserves `traceItems` as freerouting seeds. When E1
changed U2's pad nets, the old tracks survived with **no net at all** — 23 segments of
dead copper, invisible to the netlist but still physically on the board. That is exactly
how a corrected schematic can still fabricate a short. Found by the routing gate, not by
DRC. `layout_pcb.py` now drops netless tracks after net regeneration.

### P3. Router could report success for routing that didn't happen — **FIXED 2026-08-06**
Buddy has no equivalent of scout's retry-loop bug, but had the same failure class by a
different route: `route_pcb.py` never checked freerouting's exit code, and `SES` lives at
a fixed `/tmp` path, so a **stale SES from a previous run** would satisfy the existence
check and be imported as if fresh. Fixed by deleting the SES before invoking, checking
`returncode`, and adding a **Step 7** that runs the shared routing gate and exits non-zero
if the board is not fully routed.

### P4. Two parallel copies of the review gates — **FIXED 2026-08-06**
The gates were briefly forked into buddy's `tools/`, immediately diverging (buddy's
mateability rule gained a fix scout's lacked). Now a **single canonical copy** lives in
`~/kicad-libs/tools/`, symlinked into both repos' `tools/`. Board discovery walks up from
the invocation path, so each symlink checks its own repo. **Do not fork these files.**

`~/kicad-libs/` is now a **git repository** covering footprints, symbols, 3D models and
both gates, with a README carrying the shared design rules. Local only, no remote yet.
Shared-library edits are now versioned and reviewable — the ad-hoc backup-before-editing
workaround used earlier in this session is obsolete. **A defect there is a two-project
defect**, so commit those edits deliberately.

### P6. Post-route finishing now exists as a pipeline stage — `hardware/kicad/finish_pcb.py`
Everything that can only be decided once the copper is final — dedupe, dangling,
clearance repair, silk placement, silk clipping — lives here, and `route_pcb.py` runs
it as **Step 6.5**. It is idempotent: a second run reports 0/0/0 and leaves the board
unchanged, which is what makes it safe inside a pipeline that regenerates constantly.

Two hard-won implementation notes, both of which cost real time:

- **`pcbnew`'s Python bindings degrade after a mutation.** Calling `fp.Remove()`
  invalidates *other* SWIG container proxies on the same board — `board.GetDrawings()`
  starts returning a bare `SwigPyObject`, then the `BOARD` proxy itself loses its
  methods. Reloading inside the same interpreter does **not** clear it. Each pass
  therefore runs in **its own subprocess**. Separately, `BOX2I` return values are not
  reliably wrapped (every call warns `memory leak of type BOX2<VECTOR2<int>>*`), so all
  geometry here uses plain `(l,t,r,b)` integer tuples converted at the boundary.
- **`LoadBoard` intermittently returns an unusable proxy.** pcbnew 10.0.5 emits
  `property.h(607): assert "m_choices.GetCount() > 0" failed in PROPERTY_ENUM()` during
  static init; when that fires the property manager is half-registered and SWIG cannot
  build the `BOARD` proxy. Same script, same board file, succeeds or fails run to run.
  `load_board()` detects it and the driver retries in a fresh interpreter.

### P7. Don't hand-roll a rule KiCad already implements
The first dangling-track pass was a geometric test — "does either endpoint touch
same-net copper?" It found **0 of the 14** segments KiCad reports, because it counted a
point lying anywhere along another track's width as connected, which is more permissive
than KiCad's connectivity graph. Every stub looked attached to the track it stubbed off.

It ran clean and fixed nothing — the worst possible outcome, and it would have been
believed. Both that pass and the clearance repair now use **`kicad-cli pcb drc` as the
oracle**: DRC names the offending item, the script acts on exactly that, and re-runs DRC
to confirm the count dropped. Slower, and correct.

### P8. Fab outputs are now generated, gated, and self-consistent — `hardware/kicad/make_fab.py`
Replaces hand-made gerbers/BOM/CPL. Three properties, each fixing a defect above:

1. **It refuses to emit anything unless DRC is clean (0 violations / 0 unconnected /
   0 parity) and both gates pass.** P5 existed because scrap gerbers could sit in the
   repo looking ordinary; a package that cannot be generated from a failing board
   cannot become scrap. `--force` exists for inspection and stamps the README
   "NOT ORDERABLE".
2. **The BOM is derived from the CPL**, and it exits non-zero if the two ever disagree.
   O1 happened because they were maintained separately.
3. **It passes `--subtract-soldermask`.** Verified to matter: F.Silkscreen plots to
   88,156 bytes with the flag and 82,624 without, while the board-level
   `(subtractmaskfromsilk yes)` alone changes nothing.

`--smd-only` is not sufficient on its own to decide what the fab places: **U1 has
castellated SMD pads**, so the tool lists it, but it is a Waveshare module and not an
LCSC line item. `HAND_SOLDERED_MODULES` removes it explicitly.

🔴 **Three BOM lines still have no LCSC part number** — `10u` (C9), `15k` (R6),
`4.7k` (R16/R17), all new in v2. The script prints them on every run. The v1 BOM's
`C25765` is **20k, not 15k** — do not reuse it.

### P9. `shutil.make_archive` into its own root_dir filled a 330 GB disk
`make_fab.py` first wrote the gerber zip to `gerbers/…​.zip` while archiving `gerbers/`.
The archive was created inside the tree it was walking, so every block written grew the
input — one 4.5 GB zip, disk at 100 %, and the next subprocess died on ENOSPC with its
output lost. Now built in `/tmp` and moved into place. **Any `make_archive` whose
destination is under its `root_dir` has this bug.**

### P5. ✅ Stale gerbers — **RESOLVED 2026-08-06.** Regenerated by `make_fab.py` from the
### clean v2 board; `DO-NOT-FABRICATE.md` removed. Original note follows.
`gerbers/` and `jlcpcb-assembly/*.zip` predate the E1 fix and would fabricate the battery
short. They **pass** the routing gate, because it checks whether copper exists, not
whether the netlist was right. Flagged with `gerbers/DO-NOT-FABRICATE.md`; regenerate
before any v2 order.

---

## X — Electrical calculation pass

Full worked numbers in **`docs/electrical-design-calcs.md`** (2026-08-06). New defects it
found that are not listed elsewhere in this register:

### X1. 🔴 No I²C pull-ups anywhere on the board — blocks the A1 expander plan
All eleven resistors accounted for; none touch `/SDA` or `/SCL`. The bus works today only
because the external Qwiic BMI270 breakout carries its own. **A1 puts the four motor-direction
pins on an on-board I²C expander, so the bus must work with J5 empty — and it will not.**
Fix: 4.7 kΩ to `+3V3` on-board (219 ns rise at 55 pF; 2.2 mA sink even in parallel with a
2.2 kΩ Qwiic device).

### X2. 🔴 No overcurrent protection, and the coordination is inverted
Source ~5 A > connector 3 A > trace 2.37 A (0.5 mm, 1 oz), with no fuse. The copper is the
weakest element in the chain. Fix: 2 A slow-blow on `+BATT` and `+5V` — gives
fuse 2 A < trace 2.37 A < connector 3 A.

### X3. 🔴 No bulk capacitance on `+3V3`
Derived from the module's onboard LDO and leaves the board over the J5 cable with only a
100 nF. Add 10 µF. Gets worse in v2 when the expander/ADC become on-board 3V3 loads.

### X4. 🟡 Bulk capacitors are tens of mm from what they serve
C3 (1000 µF) is 31.8 mm from U2 `VM` and 53.7 mm from J8. `docs/power.md:34` relies on C3 to
hold VM above its 4.5 V floor during direction flips. Measured impact is modest (~47 mV IR +
~48 mV L·di/dt at 1.5 A) and the breakout's onboard caps cover HF, so this is sloppy rather
than fatal — but **the E1 fix made it worse**: pad 16 was wrongly `+BATT` at 15.2 mm from C3,
and pad 9 (the real VM) is at 31.8 mm. The v2 placement must put C3 next to pad 9.

### X5. 🟡 Echo divider has only 100 mV of absolute-maximum margin
R5/R6 = 10 k/20 k gives 3.50 V at a 5.25 V HC-SR04 supply against a 3.6 V absolute maximum,
while the logic threshold is only 2.475 V. Change R6 to 15 kΩ → 3.15 V worst case. Supersedes
the LOW-severity note in V6.

### X6. 🟡 5 V rail peak is within ~0.25 A of the HAT's 5 A before NeoPixels
Pi + face + reflex + a 1.5 A motor direction flip ≈ 4.75 A. Eight NeoPixels at full white push
it to 5.23 A. Cap brightness in firmware, keep N ≤ 4, or accept the transient — but decide.

### X7. ℹ️ Two things that are correct and must not be "cleaned up"
- **C2 (100 nF) is load-bearing** — it is the charge reservoir that lets a 32 kΩ divider source
  drive an ESP32 SAR ADC that wants ≤ 10 kΩ.
- **R10 is fed from `+5V`, not `+3V3`** — which is why 330 Ω works for every LED colour. The
  same resistor from 3.3 V with a blue LED passes 0.30 mA and is invisible.
- **The battery divider is 2S-only.** A 3S pack puts 4.03 V on the ADC pin, over the 3.6 V
  absolute maximum. Record this beside the battery spec.

### X8. ✅ Capacitance and trace current are genuinely fine
Unlike scout, buddy has 7 caps including bulk on both cable-fed rails. C3's ESR overdamps the
hot-plug loop by 4–6× (ζ ≈ 4.5–5.8), so there is no ring — the failure mode that would put
~15.8 V on a 15 V-absmax TB6612 does not apply here. All traces pass at 1 oz with ≤ 10.6 °C
rise, so the copper-weight unknown does not swing any verdict.

---

## V — Verified good (record so v2 doesn't regress)

- **V1. NeoPixel level shift is correct.** U3 74LVC1G125: pin1 OE→GND (enabled),
  pin2 A=`/NEO_DATA`, pin3 GND, pin4 Y=`/NEO_BUF`, pin5 VCC=`+5V`. VIH is 2.0 V at
  VCC=4.5–5.5 V, so 3.3 V drive is valid. R11 330 Ω series on the data line.
- **V2. Boot fail-safe present.** R1/R2/R3 100k pull-downs on `/PWMA`, `/PWMB`,
  `/STBY` — driver disabled before GPIO config. Keep this pattern for the expander.
- **V3. E-stop** — R4 10k pull-up to +3V3, C1 100n debounce, active-low. Correct.
- **V4. Qwiic pin order** — J5 = GND, +3V3, SDA, SCL. Standard.
- **V5. Battery divider safe for 2S** — 100k/47k → ×0.3197; 8.4 V max → 2.69 V.
  (Would be 4.03 V and destructive on 3S — do not reuse this divider if the pack
  ever changes.)
- **V6. Echo divider** — R5 10k / R6 20k → 3.33 V from a 5.0 V echo, R7 100 Ω
  series. Within the 3.6 V absolute max but with no margin (3.5 V at a 5.25 V
  supply). Consider 10k/15k → 3.0 V in v2. LOW severity.

---

## Pre-fab sign-off gate

No gerbers are generated until every line is checked and initialled.

### Electrical
- [x] E1 — TB6612 JP1 nets corrected; pad 16 = GND, pads 11/12/13 = GND/AO1/AO2
- [x] U2 pad→net map re-verified against the Eagle `.sch` after the fix
- [x] A3 decided — drop `/BAT_SENSE`; no pack input; VM ties to `+5V`
- [x] A0 — v2 baseline agreed: expander (TCA9554APWR C2863976); STBY→`/ESTOP`; NeoPixels cut
- [x] Pull-downs on all four direction lines — R12–R15 100k
- [ ] Direction-change sequencing in firmware: PWM=0 → write → restore PWM
- [x] X6 — NeoPixels cut entirely, so the 5 A budget question is closed
- [ ] `docs/power.md` updated so board and doc agree (firmware note + Battery section)
- [~] A0b — `+5V` is its own DSN class, but `RAIL_W` is now **0.4 mm**, not 1.5 mm.
      See the A0d re-derivation below before ticking this.
- [x] In2.Cu plane re-homed `+BATT` → `+5V`; `POWER_NETS` updated
- [x] STBY net tied to `/ESTOP`; R3 deleted (its pull-down role is gone)
- [x] J11 / U3 / R11 and the `/NEO_*` nets deleted; C6 + C7 retained as `+5V` bulk/bypass
- [x] X1 — 4.7 kΩ I²C pull-ups added (R16/R17)
- [x] X3 — 10 µF bulk on `+3V3` (C9); C8 100n decouples U4
- [x] X5 — R6 changed 20 kΩ → 15 kΩ
- [ ] Remaining unverified inputs in `electrical-design-calcs.md` §7 resolved or accepted

### Schematic capture (v2, 2026-08-06)
- [x] `_NoCluster` footprint in use; cluster pins 10–17 no-connect
- [x] Pin map A0c implemented — SDA/SCL on pads 26/25, 2 spares (GPIO1, GPIO6)
- [x] `+BATT` eliminated, VM on `+5V`, `/BAT_SENSE` + R8/R9/C2 deleted, J8 deleted
- [x] U4 TCA9554APWR drives AIN1/AIN2/BIN1/BIN2; netlist verified, no orphan nets
- [ ] 🔴 Protection **without a fuse** (A0d) — the argument as written is stale.
      It reads "HAT ~5 A < trace 5.26 A < connector 10 A", but 5.26 A was 1.5 mm at
      1 oz and `RAIL_W` is now 0.4 mm. Re-derive against the plane. See A0d-v2.
- [x] `_NoCluster` **schematic symbol** derived in the shared library; U1 now has
      exactly pins 1–9 and 18–26, matching the footprint pad-for-pad

### Footprints
- [x] F1 — cluster deleted; `_NoCluster` perimeter-only variant in use
- [x] F3 — n/a: v2 flat-mounts U1, so `M_Socket` is not used
- [x] F4 — body is **20.32×20.32mm**, from the vendor Eagle `.brd` layer 20; footprint
      corrected from its claimed 23mm and the derivation written into its `descr`
- [ ] F5 — every stock footprint checked against the actual part variant in stock
- [ ] All new/changed footprints have vendor mounting holes and pin-name silk

### Connectors
- [x] C1 — **designed out**: J8 deleted entirely, J9 moved to JST-VH. The review gate
      no longer reports a mateability failure. Only J7/J10 share a footprint and both
      are signal-only.
- [~] C2 — J1/J2 carry silk `MOTOR L` / `MOTOR R`. **Not keyed**: identical 6-pin XH
      with the same net *types* (+5V, GND, 2 motor, 2 encoder), so a swap reverses both
      tracks rather than damaging anything. Decide whether silk alone is enough.
- [x] Full mateability re-run — `check_board_review.py` passes. Only J1/J2 (see C2) and
      J7/J10 share footprints; J7 `/ESTOP`+GND vs J10 `/LED_A`+GND are both signal-level,
      so a swap misbehaves but cannot damage anything. No power-into-signal pair exists.
- [x] Full net-vs-label re-run — every connector Value matches the nets on it

### Silkscreen
- [x] L1 — all 7 connector Value fields moved to F.SilkS by `layout_pcb.py`
- [x] L2 — moot, J8 deleted; J9 reads `5V+UART Pi` so the inlet states its voltage
- [x] L4 — J1 `MOTOR L`, J2 `MOTOR R`
- [ ] L3 — 🔴 **J9 still does not state TX/RX direction.** `5V+UART Pi` does not say
      whether pin 3 is the Pi's TX or the board's. One silk edit.

### DFM (carried from v1 — these were fixed, reverted once, and must stay fixed)
- [x] P1 — DFM pass encoded in `layout_pcb.py`, not applied by hand
- [x] All THT pads `(keep_end_layers yes)` — **28 yes / 0 no** (28 not 33: the v1 count
      predates the cluster deletion and the NeoPixel circuit removal)
- [x] No `np_thru_hole` pad carries `*.Mask` — **0**
- [x] Both re-checked **after** the final regeneration, not before
- [ ] Mask ⊆ copper verified by parsing D03 flash coords on both outer layers
- [ ] JLC BOM match review: every line shows the intended **Package**, not just a
      valid C-number (the wrong-package auto-match is silent)

### Final
- [x] DRC clean — 0 violations, 0 unconnected, 0 schematic-parity; all three gates pass
- [ ] 3D placement preview reviewed, rotations checked on all 3+ pin parts
- [ ] This register has no unchecked box
