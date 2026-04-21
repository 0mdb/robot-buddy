# Power

## Goal

Run the Pi 5 + 2× ESP32-S3 + TFT face + 2× Yahboom TT gearmotors from a single
18650 pack with UPS function (seamless AC ↔ battery switchover) and software-
readable battery telemetry.

## Topology (single-rail, 5 V)

```
  USB-C (AC) ─┐
              ├─► Waveshare UPS HAT (B) ─► 5 V / 5 A ─┬─► Pi 5
  2× 18650 ───┘                                       │     └─► USB 5 V ─► ESP32-face + ESP32-reflex
                (2S, 7.4 V nominal)                   │
                                                      └─► TB6612 VM ─► TT motors
```

Everything downstream of the HAT lives on a shared 5 V rail. The HAT owns
charging, undervoltage cutoff, UPS switchover, and reports pack voltage +
current over I²C (INA219-class). Pi PMIC monitors its own 5 V rail
independently as a second opinion via `vcgencmd get_throttled` and sysfs
hwmon (the supervisor's `PiPMICMonitor`).

### Why a single rail is OK here

The "dirty rail / clean rail" split in the old version of this doc was sized
for unknown motors. The actual motors — Yahboom TT gearmotors, 1440
counts/rev, TT-family spec — draw ~150 mA per motor continuous and
~500–700 mA stall. Two motors = ~300 mA continuous, ~1.5 A peak during a
direction flip. That's inside the 5 A HAT budget with the Pi pulling
2–2.5 A on top.

TB6612 VM is spec'd 4.5–13.5 V. A 1000 µF bulk cap on VM input absorbs
motor-surge sag so the rail stays above the 4.5 V floor during direction
flips. No dedicated motor supply needed at this scale.

## Battery

- **2× 18650 in series** in the Waveshare UPS HAT (B) Pi 5 pogo-pin variant.
- Cells: start with whatever's on hand. For real runtime (≥1 hr) replace with
  Samsung 30Q / LG HG2 / Molicel P26A from a reputable US source.
- Charger: the UPS HAT charges via its USB-C input; no external 18650
  charger needed during normal use. A dedicated 18650 charger (the one
  already on hand) stays useful for capacity tests + cell rotation.

## Telemetry chain

- HAT INA219 → `/dev/i2c-1` → supervisor `WaveshareUpsBMonitor` (Phase 2).
- Pi 5 PMIC → `/sys/class/hwmon/*` + `vcgencmd get_throttled` → supervisor
  `PiPMICMonitor` (Phase 1, shipping now).
- Both flow into `RobotState.power` (`PowerState` dataclass) and broadcast as
  the nested `power` field on the telemetry WebSocket.
- Dashboard `PowerPanel` renders source + voltage + SoC (when available) +
  PMIC undervoltage pill.
- Planner `WorldState.power` carries the same structure; speech_policy owns
  the low-battery announcement at `soc_pct < power.soc_warn_pct` and
  `soc_pct < power.soc_critical_pct` thresholds, plus any PMIC
  undervoltage event.

## Camera-ribbon interaction (physical)

Pi 5 CSI connectors (CAM0 / CAM1) are on the side edge. Pogo-pin HATs sit
flat over GPIO only and don't block them, but the Pi 5 camera ribbons ship
short — if the HAT's height makes the ribbon tight, swap to a longer
(15 cm+) Pi 5 CSI ribbon.

## Safety notes

- UPS HAT (B) has built-in 2.5 V/cell undervoltage cutoff. Do not bypass.
- Avoid no-name "9900 mAh" 18650s for sustained use — typical real capacity
  is a fraction of the claim and some cells have inadequate protection.
- Always charge through the HAT or a dedicated charger — never plug a bare
  18650 straight to USB.

## Firmware note

`esp32-reflex/main/pin_map.h` historically reserved `GPIO_NUM_1` as
`PIN_VBAT_SENSE` for an on-MCU ADC battery read. That path is obsolete in
this topology (the ESP32 only sees USB 5 V, not pack voltage) and the pin
will be freed in a follow-up cleanup after the HAT is commissioned.
