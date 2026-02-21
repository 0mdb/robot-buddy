---
name: calibrate
description: Reference for tuning motor PID gains, IMU settings, encoder calibration, range sensor, and safety thresholds. Use when adjusting robot performance or diagnosing control issues.
argument-hint: "[pid|imu|encoder|range|safety]"
allowed-tools: Bash(python:*), Bash(idf.py monitor:*), Read, Grep, Glob
---

Calibration reference for the Reflex MCU. Focus on `$ARGUMENTS` area if specified.

## Key source files

- `esp32-reflex/main/config.h` — all tunable parameters with defaults
- `esp32-reflex/main/config.cpp` — `config_apply()` runtime parameter setter
- `esp32-reflex/main/control.cpp` — FF+PI controller, rate limiting, yaw damping
- `esp32-reflex/main/imu.cpp` — BMI270 init, I2C read, sensitivity tables
- `esp32-reflex/main/encoder.cpp` — PCNT quadrature, delta-to-speed conversion
- `esp32-reflex/main/safety.cpp` — fault detection (tilt, stall, range)

## Runtime tuning via SET_CONFIG

Parameters can be changed at runtime from the supervisor without reflashing.
Send `SET_CONFIG` command (0x15): `param_id(u8) + value(4 bytes, little-endian)`.

## PID tuning (pid)

### Current defaults
```
kV       = 1.0    # feedforward: duty per (mm/s)
kS       = 0.0    # static friction offset
Kp       = 2.0    # proportional gain
Ki       = 0.5    # integral gain
min_pwm  = 80     # deadband compensation (duty units)
max_pwm  = 1023   # max duty (10-bit)
```

### SET_CONFIG param IDs
| Param   | ID   | Type  |
|---------|------|-------|
| KV      | 0x01 | float |
| KS      | 0x02 | float |
| KP      | 0x03 | float |
| KI      | 0x04 | float |
| MIN_PWM | 0x05 | u16   |
| MAX_PWM | 0x06 | u16   |

### Tuning procedure
1. **Characterize motors** — find min_pwm where wheels just start moving
2. **Set kV** — feedforward: measure steady-state duty at known speed, compute duty/speed
3. **Set kS** — static friction: the duty offset needed to overcome stiction
4. **Tune Kp** — increase until responsive but not oscillating
5. **Tune Ki** — small value to eliminate steady-state error; watch for windup
6. **Anti-windup** is built in — integrator bleeds when output saturates

### What to watch
- Telemetry: `speed_l_mm_s`, `speed_r_mm_s` vs commanded speed
- Oscillation → Kp too high
- Slow response → Kp too low, or kV wrong
- Drift at rest → Ki accumulating, check deadband

## Rate limits

### Current defaults
```
max_v_mm_s    = 500      # max linear speed
max_a_mm_s2   = 1000     # max linear accel
max_w_mrad_s  = 2000     # max angular rate (~115 deg/s)
max_aw_mrad_s2 = 4000    # max angular accel
```

### SET_CONFIG param IDs
| Param          | ID   | Type |
|----------------|------|------|
| MAX_V_MM_S     | 0x10 | i16  |
| MAX_A_MM_S2    | 0x11 | i16  |
| MAX_W_MRAD_S   | 0x12 | i16  |
| MAX_AW_MRAD_S2 | 0x13 | i16  |

## IMU calibration (imu)

### BMI270 configuration
```
imu_odr_hz         = 400    # 400 Hz sample rate (headroom over 100 Hz control)
imu_gyro_range_dps = 500    # ±500 dps
imu_accel_range_g  = 2      # ±2g (best resolution for tilt detection)
```

### SET_CONFIG param IDs (boot-only — requires restart)
| Param              | ID   | Type |
|--------------------|------|------|
| IMU_ODR_HZ         | 0x50 | u16  |
| IMU_GYRO_RANGE_DPS | 0x51 | u16  |
| IMU_ACCEL_RANGE_G  | 0x52 | u8   |

### Sensitivity lookup
**Accel:** 16384 (±2g), 8192 (±4g), 4096 (±8g), 2048 (±16g) LSB/g
**Gyro:** 262.1 (±125), 131.1 (±250), 65.5 (±500), 32.8 (±1000), 16.4 (±2000) LSB/dps

### Yaw damping
```
K_yaw = 0.1    # gyro correction gain (conservative)
```
Increase for tighter straight-line tracking. Too high → oscillation on turns.

## Encoder calibration (encoder)

### Physical constants
```
wheelbase_mm      = 150.0   # distance between wheel centers
wheel_diameter_mm = 65.0    # wheel diameter
counts_per_rev    = 1440    # encoder ticks per revolution (post-gearbox)
```

### Speed conversion
```
mm_per_count = (wheel_diameter_mm * pi) / counts_per_rev
speed_mm_s   = (delta_counts * mm_per_count) / dt_s
```

### Verification
- Manually push robot a known distance, check encoder counts match
- `mm_per_count` should be ~0.1418 mm with current defaults
- 1440 counts = one full wheel rotation = ~204 mm travel

## Range sensor (range)

### Current defaults
```
range_stop_mm    = 250     # soft stop trigger
range_release_mm = 350     # release hysteresis
range_timeout_us = 25000   # echo timeout (~4.3m max)
range_hz         = 20      # measurement rate
```

### SET_CONFIG param IDs
| Param          | ID   | Type |
|----------------|------|------|
| RANGE_STOP_MM  | 0x40 | u16  |
| RANGE_RELEASE_MM| 0x41 | u16  |

### Supervisor safety layer (additional caps)
```
< 300mm → 25% speed cap
< 500mm → 50% speed cap
MCU hard stop at 250mm
```

## Safety thresholds (safety)

### Current defaults
```
cmd_timeout_ms    = 400    # command watchdog
soft_stop_ramp_ms = 500    # ramp-to-zero duration
tilt_thresh_deg   = 45.0   # tilt angle for hard stop
tilt_hold_ms      = 200    # persistence before fault
stall_thresh_ms   = 500    # stall detection window
stall_speed_thresh = 20    # mm/s threshold
```

### SET_CONFIG param IDs
| Param              | ID   | Type  |
|--------------------|------|-------|
| CMD_TIMEOUT_MS     | 0x30 | u32   |
| SOFT_STOP_RAMP_MS  | 0x31 | u32   |
| TILT_THRESH_DEG    | 0x32 | float |
| TILT_HOLD_MS       | 0x33 | u32   |
| STALL_THRESH_MS    | 0x34 | u32   |
| STALL_SPEED_THRESH | 0x35 | i16   |
