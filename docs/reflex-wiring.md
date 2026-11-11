# Reflex MCU Wiring Diagram

## Waveshare ESP32-S3-Zero on robot-buddy-reflex v2: pin map

> **Source of truth**: `esp32-reflex/main/pin_map.h` and the schematic. `hardware/kicad/pcb_qc.py`
> §3 checks every `PIN_*` (and the expander bits/address) against the netlist. This page
> mirrors them (rewritten 2026-11-09 for v2, register M13). If they disagree, the code
> and the schematic win.

The module is soldered flat with its **perimeter pads only** (no underside cluster), so
GPIO14-18 and GPIO38-42/45 are not available. Pads 1-9 run along one long side, 18-26
along the other; the USB-C (the Pi link, USB-Serial-JTAG) is flush with the board's rear edge.

| U1 pad | GPIO | Net | Use |
|---|---|---|---|
| 1 | 5V | +5V | module supply (from J9) |
| 2 | GND | GND | |
| 3 | 3V3 | +3V3 | module LDO out: U2 VCC, U4, encoders, J5, J7 |
| 4 | GPIO1 | — | free |
| 5 | GPIO2 | ECHO_DIV | HC-SR04 echo via R5/R6 divider + R7 |
| 6 | GPIO3 | TRIG | HC-SR04 trigger |
| 7 | GPIO4 | PWMA | left motor PWM (R1 100k pull-down) |
| 8 | GPIO5 | PWMB | right motor PWM (R2 100k pull-down) |
| 9 | GPIO6 | ESTOP_LOOP | e-stop cable detect (R18 pull-down) |
| 18 | GPIO43 | UART_TX | J9 pin 3 → Pi RX |
| 19 | GPIO44 | UART_RX | J9 pin 4 ← Pi TX |
| 20 | GPIO13 | ESTOP | e-stop sense, HIGH = run (R4 pull-down); also TB6612 STBY |
| 21 | GPIO12 | ENC_RB | right encoder B |
| 22 | GPIO11 | ENC_RA | right encoder A |
| 23 | GPIO10 | ENC_LB | left encoder B |
| 24 | GPIO9 | ENC_LA | left encoder A |
| 25 | GPIO8 | SCL | shared I²C (R17 4.7k pull-up) |
| 26 | GPIO7 | SDA | shared I²C (R16 4.7k pull-up) |

**I²C bus (I2C_NUM_1, 400 kHz, `i2c_bus.cpp`):** BMI270 at 0x68 (via Qwiic J5) and the
TCA9554A at 0x38 (U4). One owner; recovery resets the bus without deleting either device.

---

### Motor driver: TB6612FNG module (U2) + TCA9554A expander (U4)

```
   ESP32 GPIO4 ─────────────→ PWMA            AO1/AO2 ──→ J1 MOTOR L (pins 1, 2)
   ESP32 GPIO5 ─────────────→ PWMB            BO1/BO2 ──→ J2 MOTOR R (pins 1, 2)
   U4 P0 ───────────────────→ AIN1
   U4 P1 ───────────────────→ AIN2            VM  ←── +5V (In2 plane; C3 1000 µF at the pin)
   U4 P2 ───────────────────→ BIN1            VCC ←── +3V3
   U4 P3 ───────────────────→ BIN2
   /ESTOP (J7 NC switch) ───→ STBY            (hardware kill: no firmware in the path)

   U4 = TCA9554APWR, A2..A0 = GND (0x38). P0-P3 have R12-R15 100k pull-downs: the expander
   powers up with every port an input, so all four lines sit LOW until firmware drives them.
```

Direction truth table: IN1=1 IN2=0 forward, IN1=0 IN2=1 reverse, IN1=IN2=1 short brake,
IN1=IN2=0 off. PWM low = short brake.

**Direction changes are sequenced** (`motor.cpp`): that side's PWM → 0 (short brake), write
the expander, read the INPUT port back, then restore the duty. The write is an I²C
transaction (~0.1 ms), and VM has only 0.5 V of margin, so flipping with PWM live is a
brownout risk. A failed readback holds the side at PWM 0 and raises `Fault::MOTOR_DRV`
(bit 7). Brake is PWM-only and never waits on the bus.

Footprint: the module is plugged in chip-up on 2×8 female headers. The footprint was a
mirror image until 2026-11-09 (register M1); seating a module on a v1 board shorts the supply.

### Motor harness: encoder TT socket → J1 / J2 (XH 6-pin)

The motor's 6-pin socket and the board's XH header use **different orders**, so the harness
is not straight-through. Motor socket pinout from the vendor sheet (13-line metal TT, 1:45,
Hall AB encoder, 3.3–5 V, outputs pulled up on the encoder board; 2026-11-10):

| Motor socket pin | Function | → J1/J2 XH pin | Board net (J1 / J2) |
|---:|---|---:|---|
| 5 | Motor + | 1 | AO1 / BO1 |
| 6 | Motor − | 2 | AO2 / BO2 |
| 4 | Encoder power | 3 | +3V3 |
| 1 | Encoder ground | 4 | GND |
| 2 | Encoder A | 5 | ENC_LA / ENC_RA |
| 3 | Encoder B | 6 | ENC_LB / ENC_RB |

Wire colours vary by batch: identify each bare wire by continuity to its socket-pin position,
not by colour. Pins 4 and 1 swapped reverse-power the encoder; a motor or A/B swap only
inverts direction / count sign (firmware). J1 = MOTOR L, J2 = MOTOR R (identical headers,
silk only). The encoder's pull-ups go to its own supply, so at 3V3 A/B are 3.3 V logic.

---

### IMU: SparkFun Qwiic BMI270 (via J5)

```
   J5 (JST-SH, Qwiic):  1 GND   2 +3V3   3 SDA (GPIO7)   4 SCL (GPIO8)
   ADR jumper default = 0x68. Shares the bus with U4 (0x38).
   Pull-ups: R16/R17 4.7k on the reflex board (the breakout's own 2.2k are in parallel).
```

---

### Ultrasonic range sensor: HC-SR04 (J6)

```
   J6:  1 +5V   2 TRIG (GPIO3, 3.3 V drive is enough for the sensor)   3 ECHO_IN   4 GND

   ECHO_IN ── R5 10k ──┬── R7 100R ── GPIO2 (ECHO_DIV)
                       R6 15k
                       GND
   Divider output: 5 V × 15k / 25k = 3.0 V.
```

---

### E-Stop — fail-safe, de-energise to stop (v2, register E3)

```
   J7 pin1  +3V3 ─────────────┐          harness ties pin3 to pin1
                              │          AT THE SWITCH END
                 ┌── NC contact┘
                 │            └────────────────────┐
   J7 pin2 ESTOP ┴──┬── ESP32 GPIO13   (sense)     │
                    ├── TB6612 STBY    (hardware kill, no firmware)
                    ├── C1 100nF ── GND (debounce)
                    └── R4 10k   ── GND (pull-DOWN)
                                                   │
   J7 pin3 ESTOP_LOOP ─┬── ESP32 GPIO6  (detect) ──┘
                       └── R18 10k ── GND (pull-DOWN)

   loop  estop   meaning
   ────  ─────   ────────────────────────────────
   HIGH  HIGH    connected, not pressed  -> run
   HIGH  LOW     connected, PRESSED      -> stopped
   LOW   LOW     CABLE MISSING           -> stopped
```

Pressed, unplugged, broken wire and failed crimp **all** pull ESTOP low, and low
drives STBY low — the driver is disabled in hardware with no firmware in the path.
The loop only lets firmware report *which* of the two happened; both stop the motors.

⚠ **The switch must be NORMALLY CLOSED.** A normally-open switch here leaves the
motors disabled permanently. This replaced a normally-open, press-to-GND design
whose unplugged state was indistinguishable from "not pressed" — see register E3.

### Battery sense — DELETED in v2

`/BAT_SENSE`, its 100k/47k divider, C2 and the J8 pack input are all gone
(register A3). The reflex board is fed 5 V from the Pi HAT through J9 and never
sees cell voltage; battery telemetry comes from the HAT's INA219 on the Pi's
`i2c-1`. See `docs/power.md`.


### Passive Component BOM

| Component | Location | Purpose |
|-----------|----------|---------|
| 2x 100k (R1,R2) | PWMA→GND, PWMB→GND | PWM boot safety pull-downs |
| 4x 100k (R12-R15) | expander AIN1/AIN2/BIN1/BIN2 → GND | direction-pin pull-downs (A2) |
| 1x 10k (R4) | ESTOP → GND | e-stop **pull-DOWN** (fail-safe, E3) |
| 1x 10k (R18) | ESTOP_LOOP → GND | e-stop cable-detect pull-down (E3) |
| 1x 10k (R5) | HC-SR04 ECHO → divider node | echo divider (top) |
| 1x 15k (R6) | divider node → GND | echo divider (bottom) — was 20k, see X5 |
| 1x 100R (R7) | divider node → GPIO2 | ESD series protection |
| 2x 4.7k (R16,R17) | SDA→+3V3, SCL→+3V3 | I²C pull-ups (X1) |
| 1x 100nF (C1) | ESTOP → GND | e-stop debounce |
| 4x 100nF (C4,C5,C7,C8) | rail / U4 decoupling | |
| 1x 10µF (C9) | +3V3 → GND | +3V3 bulk (X3) |
| 1x 1000µF (C3) | +5V → GND, at U2 pad 9 | TB6612 VM bulk |
| 1x 100µF (C6) | +5V → GND | +5V bulk |

---

### Power Distribution (v2, register A3)

```
   Pi UPS HAT 5 V ──→ J9 pin 1 (+5V), pin 2 GND (JST-VH)
                        │
                        ├── In2.Cu +5V plane ──→ TB6612 VM (C3 1000 µF at the pin), C6 100 µF
                        ├── U1 5V pad ──→ module LDO ──→ +3V3: TB6612 VCC, U4, encoders,
                        │                                       J5 (BMI270), J7 e-stop loop
                        └── J6 HC-SR04 VCC
   GND: In1.Cu + B.Cu planes.  No pack input, no battery sense (battery telemetry is the
   HAT's INA219 on the Pi, docs/power.md).
```
