# esp32-reflex

ESP32-S3 (Reflex MCU) firmware: owns motors, encoders, and safety.

Design goal: **deterministic motion control** with reliable feedback, smooth starts/stops, and hard safety guarantees. Jetson sends high-level velocity targets; MCU owns PWM, PID, and stop behavior.

---

## Framework
- ESP-IDF (FreeRTOS)
- Motors: LEDC PWM + GPIO direction into TB6612FNG
- Encoders: PCNT (quadrature) for each wheel
- Control loop: 100–200 Hz speed PID (closed-loop)
- Transport: USB serial (binary protocol)

---

## Hardware Assumptions
- Differential drive (left/right motors)
- TT gear motors with integrated quadrature encoders
- Motor driver TB6612FNG
- 2S battery pack
- Optional inputs (future): e-stop switch, battery sense ADC, IMU

---

## Control Philosophy
### Reflexes stay local
- The MCU is responsible for **stable motion** regardless of Jetson load.
- No real-time PWM from Jetson. Ever.

### Interfaces are narrow and stable
- Jetson commands *intent*: `SET_TWIST(v, w)`, `STOP()`
- MCU returns *truth*: wheel speed, odom, battery, faults

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

### B) IMU-assisted heading hold (worth it if you add IMU)
If you add an IMU (later), you can implement:
- yaw-rate or heading PID to maintain straight travel
- better slip detection
This is the point where "traction control" becomes real.

### C) Battery-aware torque limiting (high leverage)
- Monitor battery voltage
- If sag detected: reduce accel / max PWM to avoid Jetson brownouts
This is *very* useful in kid scenarios (stalls, carpet, low battery).

### D) Odometry (recommended once encoders are stable)
- Integrate wheel distances -> (x, y, theta)
- Provide odom to Jetson for higher-level behavior
Note: odom on tracks drifts; still valuable.

---

## Protocol (Jetson ↔ Reflex MCU)
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

## TODO
### Bring-up
- [ ] Finalize motor driver pinout (AIN1/AIN2/PWMA/STBY etc.)
- [ ] Implement open-loop motor control (direction + PWM)
- [ ] Bring up encoders with PCNT (A/B per wheel) + verify counts
- [ ] Implement wheel speed measurement (counts/dt) and telemetry

### Control
- [ ] Implement per-wheel PID speed control @ 100–200 Hz
- [ ] Add accel limiting / ramping (kid-safe, power-safe)
- [ ] Add stall detection + safe recovery (optional)
- [ ] Implement STOP behavior (ramped stop, then brake/coast mode)

### Safety
- [ ] Command timeout -> safe stop
- [ ] Watchdog integration
- [ ] E-stop input (if added)
- [ ] Fault flags + forced stop behavior

### Protocol
- [ ] Implement USB serial binary protocol to Jetson
- [ ] Add telemetry packets + versioning

### Future
- [ ] Battery voltage sense (ADC) + sag-aware limiting
- [ ] Odometry integration (x, y, theta)
- [ ] Optional IMU support (heading hold)
