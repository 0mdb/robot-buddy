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
   E-Stop SW ────── ┤ GPIO13            ├ ←── 10k pullup 3V3 ← Active-low, NC to GND
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
        GND ──────→│ GND          VM  ├───→ VBAT (motor power, 2S LiPo)
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

### E-Stop & Battery Sense

```
   E-Stop (GPIO13):                    Battery Sense (GPIO1):
   ┌─────────────────────┐             ┌─────────────────────┐
   │                     │             │                     │
   │  3V3 ──── 10k ─┬── │             │  VBAT ── 100k ─┬── │
   │                 │   │             │                 │   │
   │  ESP32 GPIO13 ──┘   │             │  ESP32 GPIO1 ──┘   │
   │                 │   │             │                 │   │
   │  E-Stop SW ─── GND  │             │            47k ┤   │
   │  (NC = HIGH = OK)   │             │                 │   │
   │  (pressed = LOW      │             │   0.1µF cap ── GND  │
   │   = ESTOP active)   │             │                     │
   │                     │             │  Divider: VBAT × 47k/(100k+47k) │
   │  Optional: 0.1µF    │             │  @ 8.4V (2S full): 2.68V (safe) │
   │  cap GPIO13→GND     │             │  @ 6.0V (2S low):  1.92V        │
   │  for debounce       │             │                     │
   └─────────────────────┘             └─────────────────────┘
```

---

### Passive Component BOM

| Component | Location | Purpose |
|-----------|----------|---------|
| 3x 100k resistor | GPIO4→GND, GPIO5→GND, GPIO8→GND | Motor boot safety pulldowns |
| 1x 10k resistor | 3V3→GPIO13 | E-stop pullup |
| 1x 10k resistor | HC-SR04 ECHO → divider node | Echo voltage divider (top) |
| 1x 20k resistor | Divider node → GND | Echo voltage divider (bottom) |
| 1x 100-330 ohm | Divider node → GPIO2 (optional) | ESD series protection |
| 1x 100k resistor | VBAT → divider node | Battery sense (top, future) |
| 1x 47k resistor | Divider node → GND | Battery sense (bottom, future) |
| 1x 0.1uF cap | GPIO13 → GND (optional) | E-stop debounce |
| 1x 0.1uF cap | Battery ADC node → GND | ADC noise filter |

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
