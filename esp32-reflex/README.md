# esp32-reflex

ESP32-S3 (Reflex MCU) firmware: owns motors, encoders, and safety.

Design goal: **deterministic motion control** with reliable feedback, smooth starts/stops, and hard safety guarantees. Supervisor (Raspberry Pi 5) sends high-level velocity targets; MCU owns PWM, PID, and stop behavior.

---

## Framework
- ESP-IDF (FreeRTOS)
- Motors: LEDC PWM + GPIO direction into TB6612FNG
- Encoders: PCNT (quadrature) for each wheel
- Control loop: 100–200 Hz speed PID (closed-loop)
- Transport: USB serial (binary protocol)

---

## Hardware
- Differential drive (left/right motors)
- TT gear motors with integrated quadrature encoders
- Motor driver TB6612FNG
- 2S battery pack
- BMI270 IMU (gyro + accelerometer, 400 Hz ODR)
- Ultrasonic range sensor

---

## Control Philosophy
### Reflexes stay local
- The MCU is responsible for **stable motion** regardless of supervisor load.
- No real-time PWM from supervisor. Ever.

### Interfaces are narrow and stable
- Supervisor commands *intent*: `SET_TWIST(v, w)`, `STOP()`
- MCU returns *truth*: wheel speed, gyro, battery, faults

---

## Motion Stack (v1)
1) **Command layer**
- `SET_TWIST(v_mm_s, w_mrad_s)` target
- Convert to wheel speed targets using wheelbase & wheel radius

2) **Rate limiting**
- Acceleration / jerk limiting on wheel targets
- Prevents brownouts, reduces stalls, kid-safe motion

3) **Speed PID (per wheel)**
- Inputs: encoder counts over dt
- Output: PWM duty (signed)
- Anti-windup + output saturation
- Deadband compensation (optional)

4) **Safety**
- Command timeout -> controlled stop (ramp down)
- Watchdog
- Fault flags -> forced stop

---

## Advanced Features (only if they earn their keep)
### A) Slip / traction heuristics (low-cost, optional)
Without an IMU, "traction control" is limited. What we *can* do:
- Detect wheel-speed mismatch under commanded straight motion
- Detect stall (commanded speed high, measured ~0 for N ms)
- Apply corrective action:
  - reduce accel
  - clamp max PWM
  - pulse-retry pattern
This is practical and improves robustness, but it’s not true traction control.

### B) IMU-assisted yaw damping (implemented)
BMI270 IMU is integrated. Current implementation:
- Gyro-Z feedback for yaw damping in the control loop
- 400 Hz ODR, ±500 dps gyro range, ±4g accel range

### C) Battery-aware torque limiting (high leverage)
- Monitor battery voltage
- If sag detected: reduce accel / max PWM to avoid Pi 5 brownouts
This is *very* useful in kid scenarios (stalls, carpet, low battery).

### D) Odometry (recommended once encoders are stable)
- Integrate wheel distances -> (x, y, theta)
- Provide odom to Pi 5 for higher-level behavior
Note: odom on tracks drifts; still valuable.

---

## Protocol (Supervisor ↔ Reflex MCU)
Binary packets, fixed-size, no JSON.

### Commands
- `SET_TWIST(v_mm_s: i16, w_mrad_s: i16)`
- `STOP(reason: u8)`
- `SET_MODE(mode: u8)` (future: safe/normal/turbo)
- `SET_LIMITS(max_v, max_a, max_pwm)` (optional)

### Telemetry
- wheel_speed_l/r (i16)
- encoder_counts_l/r (i32)
- battery_mv (u16) (optional but recommended)
- fault_flags (u16)
- (future) odom x/y/theta

---

## Tasks / Timing (suggested)
- `usb_serial_task`: parse commands, publish targets
- `control_task` @ 100–200 Hz:
  - read encoders (PCNT snapshot)
  - compute wheel speeds
  - apply rate limit
  - run PID
  - write PWM + direction
- `safety_task` @ 10–50 Hz:
  - command timeout
  - battery checks
  - fault handling
- optional `telemetry_task` @ 10–20 Hz

No blocking in the control loop.

---

## Fault Model (v1)
- `FAULT_CMD_TIMEOUT`
- `FAULT_ENCODER_MISSING`
- `FAULT_STALL_LEFT / FAULT_STALL_RIGHT`
- `FAULT_BATT_LOW` (if battery sense)
- `FAULT_ESTOP`

Faults force stop or limit mode depending on severity.

---

## Completed
- [x] Motor driver pinout + open-loop control (LEDC PWM + GPIO direction into TB6612FNG)
- [x] Encoders with PCNT (quadrature, per wheel) + wheel speed measurement
- [x] Per-wheel FF+PI speed control @ 100 Hz
- [x] Acceleration limiting / ramping (kid-safe, power-safe)
- [x] Stall detection + safe recovery
- [x] STOP behavior (ramped stop, brake/coast)
- [x] Command timeout → safe stop
- [x] Watchdog integration (esp_task_wdt)
- [x] E-stop + fault flags → forced stop
- [x] USB serial binary protocol (COBS + CRC16) to supervisor
- [x] Telemetry packets (STATE: speeds, gyro, battery, faults, range)
- [x] BMI270 IMU integration (gyro-Z yaw damping)

## TODO

See [docs/TODO.md](../docs/TODO.md) for the full backlog. Key remaining items for reflex:
- Battery voltage sense (ADC) + sag-aware limiting
- Odometry integration (x, y, theta)
- Full IMU heading hold PID (currently gyro damping only)
- Hardware commissioning (Phases 1-5)
