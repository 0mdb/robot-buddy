# Reflex MCU Wiring Diagram

## ESP32-S3 WROOM Breakout — Finalized Pin Map

> **Source of truth**: `esp32-reflex/main/pin_map.h`
> This document mirrors the firmware. If they disagree, the firmware wins.

### Reserved Pins (DO NOT USE)

| GPIO | Function | Rule |
|------|----------|------|
| 0 | Boot strap | No runtime logic |
| 19, 20 | USB D+/D- | Leave alone |
| 35, 36, 37 | PSRAM (octal) | Leave alone |
| 43, 44 | UART0 TX/RX | Leave alone (console) |
| 45 | VSPI | Fine but unused |
| 48 | WS2812 onboard LED | Avoid unless intentional |


> ⚠ **Partially updated for the v2 board (2026-08-06).** The e-stop, battery-sense
> and passive-BOM sections below are current. Other sections still describe v1 —
> notably the direction pins, which moved from GPIO13/15/16 to the **TCA9554A
> expander (U4)**. The authoritative sources are the schematic and
> `docs/v2-defect-register.md`; treat anything here that contradicts them as stale.

---

### Wiring Diagram

```
                    ESP32-S3 WROOM BREAKOUT
                    ┌────────────────────┐
                    │                    │
              3V3 ──┤ 3V3          GND  ├── GND (common)
                    │                    │
   [VBAT ÷] ─────── ┤ GPIO1   ADC1_CH0  ├                    ← Battery sense (future)
   [Echo ÷] ─────── ┤ GPIO2   ADC1_CH1  ├                    ← Ultrasonic echo (5V÷3.3V)
                    │                    │
   TB6612 PWMA ──── ┤ GPIO4    LEDC_CH0 ├ ←── 100k pulldown  ← Left motor PWM
   TB6612 PWMB ──── ┤ GPIO5    LEDC_CH1 ├ ←── 100k pulldown  ← Right motor PWM
   TB6612 AIN1 ──── ┤ GPIO6             ├                    ← Left fwd direction
   TB6612 AIN2 ──── ┤ GPIO7             ├                    ← Left rev direction
   TB6612 STBY ──── ┤ GPIO8             ├ ←── 100k pulldown  ← Motor enable (active HIGH)
                    │                    │
   Enc Left A ───── ┤ GPIO9             ├                    ← Left encoder ch A
   Enc Left B ───── ┤ GPIO10            ├                    ← Left encoder ch B
   Enc Right A ──── ┤ GPIO11            ├                    ← Right encoder ch A
   Enc Right B ──── ┤ GPIO12            ├                    ← Right encoder ch B
                    │                    │
   E-Stop (J7.2) ── ┤ GPIO13            ├ ←── 10k pull-DOWN  ← LOW = stopped (fail-safe)
   E-Stop loop ──── ┤ GPIO6             ├ ←── 10k pull-DOWN  ← LOW = cable missing
                    │                    │
   TB6612 BIN1 ──── ┤ GPIO15            ├                    ← Right fwd direction
   TB6612 BIN2 ──── ┤ GPIO16            ├                    ← Right rev direction
                    │                    │
   BMI270 SDA ───── ┤ GPIO17  I2C1_SDA  ├                    ← Qwiic (2.2k on breakout)
   BMI270 SCL ───── ┤ GPIO18  I2C1_SCL  ├                    ← Qwiic (2.2k on breakout)
                    │                    │
   Range TRIG ───── ┤ GPIO21            ├                    ← Ultrasonic trigger (10µs)
                    │                    │
                    │       USB-C        │
                    │    (GPIO19/20)     │
                    └────────┬───────────┘
                             │
                         To Pi / PC
```

---

### Motor Driver — TB6612FNG

```
                         TB6612FNG
                    ┌──────────────────┐
   ESP32 GPIO4 ───→│ PWMA        AOUT1├───→ Left Motor +
   ESP32 GPIO6 ───→│ AIN1        AOUT2├───→ Left Motor -
   ESP32 GPIO7 ───→│ AIN2             │
                    │                  │
   ESP32 GPIO5 ───→│ PWMB        BOUT1├───→ Right Motor +
   ESP32 GPIO15 ──→│ BIN1        BOUT2├───→ Right Motor -
   ESP32 GPIO16 ──→│ BIN2             │
                    │                  │
   ESP32 GPIO8 ───→│ STBY         VCC ├───→ 3.3V (logic)
        GND ──────→│ GND          VM  ├───→ +5V (from the Pi HAT via J9; A3)
                    └──────────────────┘

   Direction truth table:
     IN1=1, IN2=0 → Forward
     IN1=0, IN2=1 → Reverse
     IN1=1, IN2=1 → Short brake
     IN1=0, IN2=0 → Coast

   Boot safety: 100k pulldown on PWMA (GPIO4), PWMB (GPIO5), STBY (GPIO8)
   ensures motors are OFF until firmware explicitly enables them.
```

---

### IMU — SparkFun Qwiic BMI270

```
   SparkFun Qwiic BMI270 Breakout
   ┌────────────────────────────┐
   │  Qwiic connector (JST-SH) │
   │  ┌──────┐                  │
   │  │ BLK  │ GND ─────────── │───→ GND
   │  │ RED  │ 3V3 ─────────── │───→ 3.3V
   │  │ BLU  │ SDA ─────────── │───→ ESP32 GPIO17
   │  │ YEL  │ SCL ─────────── │───→ ESP32 GPIO18
   │  └──────┘                  │
   │                            │
   │  ADR jumper: default = 0x68 (SDO→GND)               │
   │  Cut center + bridge to VDDIO pad for 0x69           │
   │                            │
   │  Onboard: 2.2k pullups on SDA/SCL (no external needed)│
   └────────────────────────────┘

   I2C bus: I2C_NUM_1, 400 kHz fast mode
   Firmware address: 0x68 (verify with I2C scan in Phase 1)
```

---

### Ultrasonic Range Sensor — HC-SR04

```
                    HC-SR04
                ┌──────────────┐
    5V ────────→│ VCC          │
    GND ───────→│ GND          │
                │              │
   ESP32 GPIO21 ←──│ TRIG     │   (direct 3.3V → 5V tolerant input)
                │              │
                │ ECHO ────────│───┐
                └──────────────┘   │
                                   │     5V → 3.3V voltage divider
                             10k   ├──── ┤
                                   │     │
                      ESP32 GPIO2 ←┤     │     Optional: 100-330 ohm
                                   │     │     series resistor before GPIO2
                             20k   ├──── ┤     for ESD protection
                                   │
                                  GND

   Divider output: 5V × 20k/(10k+20k) = 3.33V (safe for ESP32)
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
| 1x 330R (R10) | +5V → LED_A | power LED series |
| 1x 100nF (C1) | ESTOP → GND | e-stop debounce |
| 4x 100nF (C4,C5,C7,C8) | rail / U4 decoupling | |
| 1x 10µF (C9) | +3V3 → GND | +3V3 bulk (X3) |
| 1x 1000µF (C3) | +5V → GND, at U2 pad 9 | TB6612 VM bulk |
| 1x 100µF (C6) | +5V → GND | +5V bulk |

---

### Power Distribution

```
   2S LiPo (6.0–8.4V)
          │
          ├──→ TB6612FNG VM (motor power, direct)
          │
          ├──→ Voltage divider → GPIO1 (battery sense)
          │
          ├──→ 5V Buck Regulator
          │         │
          │         ├──→ HC-SR04 VCC (5V)
          │         │
          │         └──→ 3.3V LDO (or ESP32 breakout onboard regulator)
          │                  │
          │                  ├──→ ESP32-S3 3.3V
          │                  ├──→ TB6612FNG VCC (logic, 3.3V)
          │                  ├──→ SparkFun BMI270 3V3
          │                  └──→ E-stop pullup
          │
          └──→ GND (common ground for everything)
```
