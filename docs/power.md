# Power

## Goal

Run the Pi 5 + 2× ESP32-S3 + TFT face + 2× Yahboom TT gearmotors from the
Waveshare UPS HAT (B), with UPS function (seamless AC ↔ battery switchover) and
software-readable battery telemetry.

**There is no separate battery pack in this design.** The HAT is the entire
battery subsystem: it owns the cells, the charger, the switchover and the fuel
gauge, and the only thing it presents to the rest of the robot is **5 V**. No
board in this robot sees cell voltage.

## Topology (single-rail, 5 V)

```
  USB-C (AC) ──► Waveshare UPS HAT (B) ──► 5 V / 5 A ─┬─► Pi 5
                 (cells + charger + UPS               │     └─► USB 5 V ─► ESP32-face
                  switchover + fuel gauge,            │     └─► J9 5 V ──► ESP32-reflex board
                  all internal)                       │
                                                      └─► TB6612 VM ─► TT motors
```

5 V is the only rail that leaves the HAT, and it is the only rail on the reflex
board. Nothing carries cell voltage.

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

The HAT is the battery. There is no pack to design around, no pack connector,
and no pack voltage anywhere in the robot's wiring.

- **Waveshare UPS HAT (B), GPIO-header variant** — chosen over the pogo-pin
  version, which had a CSI-ribbon clearance risk. Confirmed by physical fit
  check on the Pi 5, 2026-04-25.
- Cells live inside the HAT. Start with whatever's on hand; for real runtime
  (≥1 hr) replace with Samsung 30Q / LG HG2 / Molicel P26A from a reputable
  US source.
- Charging is the HAT's job, over its own USB-C input. No external charger is
  needed in normal use; a bench 18650 charger stays useful for capacity tests
  and cell rotation.

⚠ **One place cell chemistry still shows through, and it is software.** The
supervisor's `WaveshareUpsBMonitor` derives SoC from a piecewise-linear **2S
18650** curve, and the dashboard voltage thresholds are tuned to it
(8.0 / 7.0 / 6.4 V). That calibration is shipped and tested, so it has not been
touched here. If the HAT's actual cell configuration is not 2S, `_SOC_CURVE`
and those thresholds are both wrong and the low-battery UX will misfire —
worth confirming against the unit before the SoC-curve refinement in
`docs/TODO.md` (Power & Battery follow-ups).

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

**Confirmed 2026-08-06.** The reflex board never sees battery voltage — see the
topology above; it is fed 5 V through J9 like every other consumer.

The reflex v1 board contradicted this page: it had a
separate `+BATT` input (J8), a pack-scaled divider into the ESP32 ADC, and a
`+BATT` inner plane. This page was right and the board was wrong. The v2 reflex
board drops all of it — no pack input, no `/BAT_SENSE`, TB6612 `VM` fed from
`+5V`. Battery telemetry comes solely from the HAT's INA219 over the Pi's
`i2c-1`, as described under *Telemetry chain* above.

Two consequences worth carrying:

- **TB6612 `VM` now has only 0.5 V of margin** (5 V supply against its 4.5 V
  floor). The 1000 µF bulk called for above is not optional, and on v2 it must
  be placed *at the VM pin* — on v1 it sat 31.8 mm away, which is not a VM input
  capacitor in any electrical sense.
- **The 5 V rail is the single critical resource.** Peak is ~4.75 A (Pi 2.5 A +
  face 0.5 A + reflex logic 0.25 A + a 1.5 A motor direction flip) against the
  HAT's 5 A. Motor transients now sag the same rail the Pi runs on.

**Battery section updated 2026-08-06** — no pack, no 2S rail, the HAT only.

Full v2 reasoning: `docs/v2-defect-register.md` §A0/§A3 and
`docs/electrical-design-calcs.md`.
