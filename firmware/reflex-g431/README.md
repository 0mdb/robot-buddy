# reflex-g431

Reflex MCU firmware on the STM32G431: the port of `esp32-reflex`. Logic (protocol v2, control,
safety, IMU conversion) is in `../reflex-core` and host-tested; this crate is the hardware and
the tasks (control 100 Hz with the IMU read, safety 50 Hz, sonar 20 Hz, host link + STATE 20 Hz).

```sh
cargo run --release --features no-imu-fault                 # Nucleo bench (default board)
cargo build --release --no-default-features --features board-v3 --target-dir target/v3   # v3 board
python3 firmware/reflex-g431/bench_check.py /dev/ttyACM0    # from the repo root, Nucleo running
```

`bench_check.py` drives the firmware with the real supervisor client on a bare Nucleo (13/13 on
2026-11-27): v2 handshake, 20 Hz STATE, sonar TIMEOUT, time sync, a twist with no wheels ending
in STALL at ~0.66 s, seq echo, CLEAR_FAULTS, ESTOP, command timeout.

## Pins

| Signal | v3 (G431CBU6, pin plan) | Nucleo (G431RB) | |
|---|---|---|---|
| Host link | USART1 PA9 TX / PA10 RX | USART2 PA2/PA3 (ST-LINK VCP) | 115200 8N1 |
| EN left / right | PA8 TIM1_CH1 / PB0 TIM1_CH2N | same (D7 / A3) | 20 kHz |
| PH left / right | PA2 / PA7 | **PA10 (D2) / PC7 (D9)** | |
| IPROPI left / right | PA1 COMP1 / PA3 COMP2 | PA1 (A1) / **PA7 (D11) COMP2** | ¾ VREFINT ≈ 365 mA |
| nFAULT (both) | PC4 | PC4 | pull-up, → MOTOR_DRV |
| ESTOP_N | PA6 TIM1_BKIN | PA6 (D12), internal pull-up | low = break + ESTOP |
| Encoder L A/B | PA5 / PB3 TIM2 | same (PA5 is also LD2) | QEI |
| Encoder R A/B | PB4 / PA4 TIM3 | same | QEI |
| IMU SPI2 | PB13 SCK, PB14 MISO, PB15 MOSI, PB12 CS | same | LSM6DSV16X, mode 3, 8 MHz |
| Sonar echo F / R | PA11 TIM4_CH1 / PB9 TIM4_CH4 | same | 1 MHz capture |
| Sonar trig F / R | PC10 / PC11 | same | |
| Status LED | PC6 | PC6 (none on the board) | steady = OK, blink = fault |

On the bench, tie the DRV8876 carrier's PMODE to GND and SLEEP to 3V3 (on v3 nSLEEP is
ESTOP_N).

## Differences from the ESP32 (decided or minor fixes)

- Protocol v2 only (`supervisor/PROTOCOL.md` §3.2, amended 2026-11-27).
- DRV8876 PH/EN replaces TB6612 + direction expander; MOTOR_DRV = driver nFAULT.
- Overcurrent: COMP → TIM1 break with automatic output enable (cycle-by-cycle limit); 300 ms
  of continuous limiting reports STALL (Ben 2026-11-27). TIM1 has one break, so a trip on one
  side ends that PWM cycle on both; per-channel OCREF_CLR would separate them.
- E-stop line reported as ESTOP (the ESP32 only cut the driver).
- Rear sonar: local reverse guard only, not reported (Ben 2026-11-27).
- IMU: LSM6DSV16X (v3 core) instead of the BMI270; untested until the v3 board (Ben
  2026-11-27). Axes as the chip reports them: check yaw sign and gravity on Z on the first board.
- Control / safety fixes: see the module headers in `../reflex-core/src/{control,safety}.rs`.
- The ESP32 build on the robot has `BRINGUP_OPEN_LOOP_TEST 1` (control and safety tasks not
  started); this firmware always runs them. A bring-up binary is still to port.
- Not ported (out of scope for now): cliff ToF (VL53L4CD), V5_SENSE, IMU ODR trigger (TIM16).
