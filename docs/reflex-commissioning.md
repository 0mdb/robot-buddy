# Reflex MCU Commissioning & Testing Plan

Phased bring-up for the ESP32-S3 reflex MCU. Each phase adds one subsystem,
validates it independently, then locks it down before moving on.

**Approach**: Start bare, add sensors one at a time, verify each in isolation.
Never debug two new things at once.

**Prerequisites**:
- ESP-IDF environment sourced (`source ~/esp/esp-idf/export.sh`)
- USB-C cable from ESP32 to dev machine (or Pi)
- `idf.py monitor` (or `just monitor-reflex`) for log output

---

## Phase 0: Bare ESP32 — Boot & Serial

**Goal**: Confirm the ESP32 boots, USB serial works, and you can see logs.

**Wiring**: Nothing connected. Just the ESP32 breakout powered via USB-C.

**Steps**:

1. Flash the firmware:
   ```bash
   just build-reflex && just flash-reflex
   ```

2. Open serial monitor:
   ```bash
   idf.py monitor
   ```

3. Verify you see:
   ```
   I (xxx) reflex: Reflex MCU booting...
   I (xxx) reflex: Hardware init complete.
   I (xxx) reflex: All tasks started.
   ```

4. You should also see the IMU and range sensor init fail (expected — nothing connected):
   ```
   E (xxx) imu: i2c_new_master_bus failed: ...
   E (xxx) reflex: IMU init FAILED — continuing without gyro
   W (xxx) reflex: Range sensor init failed — continuing without range
   ```

**Pass criteria**: Boot log visible, no crash/reboot loop, fault flags show `IMU_FAIL`.

---

## Phase 1: IMU (BMI270) — I2C Validation

**Goal**: Get the BMI270 talking over I2C and reading live gyro/accel data.

**Wiring**: Connect ONLY the SparkFun Qwiic BMI270 breakout to the ESP32:
- Qwiic cable: GND→GND, 3V3→3V3, SDA→GPIO17, SCL→GPIO18
- No motors, no encoders, no ultrasonic

### Step 1.1: I2C Bus Scan

Before flashing, run an I2C scan to verify the BMI270 is electrically present
at the expected address. Use the ESP-IDF `i2c_tools` example or a minimal
scan sketch.

**Quick scan (add temporarily to app_main before imu_init)**:
```cpp
// Temporary I2C scan — remove after commissioning
#include "driver/i2c_master.h"
ESP_LOGI(TAG, "I2C scan on GPIO17 (SDA), GPIO18 (SCL)...");
i2c_master_bus_config_t scan_bus_cfg = {};
scan_bus_cfg.i2c_port = I2C_NUM_1;
scan_bus_cfg.sda_io_num = GPIO_NUM_17;
scan_bus_cfg.scl_io_num = GPIO_NUM_18;
scan_bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
scan_bus_cfg.glitch_ignore_cnt = 7;
scan_bus_cfg.flags.enable_internal_pullup = true;

i2c_master_bus_handle_t scan_bus;
i2c_new_master_bus(&scan_bus_cfg, &scan_bus);

for (uint8_t addr = 0x08; addr < 0x78; addr++) {
    esp_err_t ret = i2c_master_probe(scan_bus, addr, 50);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "  Found device at 0x%02X", addr);
    }
}
i2c_del_master_bus(scan_bus);
```

**Expected output**:
```
I (xxx) reflex: I2C scan on GPIO17 (SDA), GPIO18 (SCL)...
I (xxx) reflex:   Found device at 0x68
```

**If you see `0x69` instead of `0x68`**: The SDO/SA0 jumper on the SparkFun
board is set to VDDIO. Either:
- (a) Cut the jumper trace and bridge SDO to GND, or
- (b) Change `BMI270_ADDR` in `imu.cpp` line 21 from `0x68` to `0x69`

**If you see nothing**: Check wiring, check Qwiic cable orientation (keyed
connector should click in), verify 3.3V is present at the breakout board VCC.

### Step 1.2: BMI270 Init

Remove the I2C scan code and flash the normal firmware. Watch for:

```
I (xxx) imu: BMI270 detected (CHIP_ID=0x24)
I (xxx) imu: config file loaded OK (INTERNAL_STATUS=0x01)
I (xxx) imu: BMI270 configured: ODR 400 Hz, gyro ±500 dps, accel ±2 g
I (xxx) reflex: IMU initialized OK
```

**Common failures**:

| Log message | Cause | Fix |
|---|---|---|
| `CHIP_ID failed: got 0x00` | I2C address wrong or bus not connected | Run I2C scan (Step 1.1) |
| `CHIP_ID failed: got 0xFF` | SDA/SCL shorted or bus stuck | Check wiring, power cycle |
| `config file upload failed` | I2C bus noisy or too fast | Add 4.7k external pullups, or slow to 100kHz |
| `INTERNAL_STATUS = 0x00` | Config blob corrupted or wrong chip | Verify bmi270_config.h matches chip revision |

### Step 1.3: Live Data Validation

Add temporary logging to `imu_task` (or use the telemetry stream) to print
raw accel/gyro values. Verify:

1. **Board flat on desk**: accel_z ~= 1.0g (±0.05), accel_x/y ~= 0.0
2. **Rotate by hand around Z**: gyro_z shows positive/negative deflection
3. **Tilt 45 degrees**: accel_x or accel_y shifts toward ±0.7g
4. **Data rate**: Confirm samples arrive at ~400 Hz (2.5 ms intervals)

**Pass criteria**: CHIP_ID = 0x24, INTERNAL_STATUS = 0x01, sensible accel/gyro
values, no IMU_FAIL fault flag, no I2C recovery attempts in first 60 seconds.

---

## Phase 2: Motors + Encoders — Open-Loop Test

**Goal**: Verify motor spin direction matches encoder count direction.

**Wiring**: Add the TB6612FNG motor driver and both encoder motors.
Keep the BMI270 connected from Phase 1.

- Motor driver: GPIO4/5 (PWM), GPIO6/7 (left dir), GPIO15/16 (right dir), GPIO8 (STBY)
- Install 100k pulldowns on GPIO4, GPIO5, GPIO8
- Encoders: GPIO9/10 (left A/B), GPIO11/12 (right A/B)
- Connect motor power (VM) to battery or bench supply (6-8.4V)

### Step 2.1: Enable Open-Loop Test Mode

In `app_main.cpp`, set:
```cpp
#define BRINGUP_OPEN_LOOP_TEST 1
```

This disables the PID control loop and safety task, and runs a simple
motor ramp test instead. It exercises each motor forward/reverse at 25% duty
and prints encoder deltas.

Flash and monitor:
```bash
just build-reflex && just flash-reflex
idf.py monitor
```

### Step 2.2: Verify Motor Direction

Watch the log output:
```
I (xxx) reflex: === OPEN-LOOP BRING-UP TEST ===
I (xxx) reflex: --- LEFT FORWARD ---
I (xxx) reflex:   enc L=xxx  R=xxx  (dL=+xxx dR=0)
I (xxx) reflex: --- LEFT REVERSE ---
I (xxx) reflex:   enc L=xxx  R=xxx  (dL=-xxx dR=0)
I (xxx) reflex: --- RIGHT FORWARD ---
...
```

**Expected**:
- Left forward → dL positive, dR ~zero
- Left reverse → dL negative, dR ~zero
- Right forward → dR positive, dL ~zero
- Right reverse → dR negative, dL ~zero

**If motor direction is backwards**: Swap AIN1/AIN2 (or BIN1/BIN2) wires,
OR swap the motor's power leads, OR swap encoder A/B for that motor.

**If encoder direction is wrong but motor is right**: Swap encoder A/B wires
for that side in pin_map.h (e.g., swap `PIN_ENC_L_A` and `PIN_ENC_L_B`).

### Step 2.3: Verify Encoder Counts

For a TT motor with 1440 counts/rev and 65mm wheels:
- One full wheel rotation = 1440 counts
- 25% duty for 1.5s should produce a measurable delta
- Lift wheels off the ground for consistent results

**Pass criteria**: Both motors spin in the correct direction, encoder deltas
are positive for forward and negative for reverse, counts are roughly symmetric
between left and right.

### Step 2.4: Disable Open-Loop Test

```cpp
#define BRINGUP_OPEN_LOOP_TEST 0
```

Flash again. The full control loop, safety task, and IMU task will now all run.
Motors should remain stopped (no commands being sent = CMD_TIMEOUT fault after
400ms, which is correct and expected).

---

## Phase 3: Ultrasonic Range Sensor

**Goal**: Verify range readings at known distances.

**Wiring**: Add the HC-SR04. Keep everything from Phase 1-2 connected.

- TRIG → GPIO21
- ECHO → voltage divider → GPIO2
- VCC → 5V, GND → common GND
- **Important**: The 5V→3.3V divider on ECHO is required (10k top, 20k bottom)

> **Note**: After updating `pin_map.h` (TRIG from GPIO1→GPIO21), flash again.

### Step 3.1: Static Distance Test

Place the sensor facing a flat wall at known distances. Watch telemetry or
add temporary logging to `range_task`:

| Actual distance | Expected `range_mm` | Tolerance |
|---|---|---|
| 100 mm | ~100 | ±15 mm |
| 300 mm | ~300 | ±20 mm |
| 1000 mm | ~1000 | ±30 mm |
| 3000 mm | ~3000 | ±50 mm |
| No obstacle (aim at ceiling) | TIMEOUT or OUT_OF_RANGE | — |

### Step 3.2: Obstacle Safety Test

With closed-loop control disabled (CMD_TIMEOUT fault active), verify the
range sensor reads and publishes. Then test the safety path:

1. Start sending SET_TWIST commands from the supervisor (low speed: 100 mm/s)
2. Move your hand in front of the sensor at <250 mm
3. Verify OBSTACLE fault is set and motors soft-stop
4. Move hand away (>350 mm)
5. Verify OBSTACLE fault clears and motors resume

**Pass criteria**: Range reads within tolerance at known distances, OBSTACLE
fault triggers/clears with hysteresis, no false triggers.

---

## Phase 4: E-Stop & Safety Systems

**Goal**: Verify all fault paths work correctly.

**Wiring**: Add the e-stop switch (NC switch between GPIO13 and GND, 10k pullup
to 3.3V).

### Step 4.1: E-Stop Test

1. Verify GPIO13 reads HIGH (switch closed = normal)
2. Open the switch (press the e-stop button)
3. Verify ESTOP fault is set, motors hard-stop (STBY → LOW)
4. Close the switch, send CLEAR_FAULTS
5. Verify recovery

> **Note**: The firmware currently reads the e-stop pin in `safety_task`.
> If polling isn't implemented yet, this is a TODO item to add.

### Step 4.2: Tilt Detection

1. With IMU running, tilt the robot >45 degrees
2. Hold for >200ms
3. Verify TILT fault is set and motors hard-stop
4. Return to level, verify fault auto-clears

### Step 4.3: Command Timeout

1. Send a SET_TWIST command, verify motors respond
2. Stop sending commands
3. After 400ms, verify CMD_TIMEOUT fault and soft-stop
4. Resume commands, verify recovery

### Step 4.4: Stall Detection

1. Command forward at 200 mm/s
2. Block a wheel (hold it stopped)
3. After ~500ms, verify STALL fault and hard-stop
4. Release wheel, clear faults, verify recovery

**Pass criteria**: All four fault paths (ESTOP, TILT, CMD_TIMEOUT, STALL)
trigger and recover correctly. Hard stops are immediate, soft stops are ramped.

---

## Phase 5: Closed-Loop Integration

**Goal**: Full system operating with PID control.

**Wiring**: Everything connected from all previous phases.

### Step 5.1: PID Tuning Baseline

1. Connect to supervisor (USB serial from Pi)
2. Send low-speed SET_TWIST: `v=100 mm/s, w=0`
3. Watch telemetry: `speed_l_mm_s`, `speed_r_mm_s` should converge to ~100
4. If oscillating: reduce Kp (default 2.0 → try 1.0)
5. If slow to respond: increase kV (default 1.0 → try 1.5)
6. If motors stutter at low speed: increase min_pwm (default 80)

### Step 5.2: Yaw Damping

1. Command straight-line travel: `v=200 mm/s, w=0`
2. Observe gyro_z in telemetry — should stay near 0
3. Gently push robot sideways — gyro correction should resist yaw
4. If yaw correction is too weak: increase K_yaw (0.1 → 0.2)
5. If yaw oscillates: decrease K_yaw (0.1 → 0.05)

### Step 5.3: Full Exercise

Run through the dashboard drive tab or supervisor test commands:

| Test | Command | Expected |
|---|---|---|
| Forward straight | v=300, w=0 | Both wheels ~300 mm/s |
| Reverse straight | v=-300, w=0 | Both wheels ~-300 mm/s |
| Spin left | v=0, w=1000 | Left back, right forward |
| Spin right | v=0, w=-1000 | Left forward, right back |
| Arc left | v=200, w=500 | Left slower than right |
| Stop | v=0, w=0 | Both wheels stop, then brake |
| Accel limit | v=500 (instant) | Ramps up over ~500ms |
| Obstacle stop | Drive toward wall | Soft-stop at <250mm |

**Pass criteria**: PID tracks commanded speed within ±20%, no oscillation,
yaw damping keeps straight lines straight, safety overrides work under load,
telemetry rates are stable (20 Hz STATE packets).

---

## Quick Reference: Expected Log Output (Healthy Boot)

```
I (xxx) reflex: Reflex MCU booting...
I (xxx) imu: BMI270 detected (CHIP_ID=0x24)
I (xxx) imu: config file loaded OK (INTERNAL_STATUS=0x01)
I (xxx) imu: BMI270 configured: ODR 400 Hz, gyro ±500 dps, accel ±2 g
I (xxx) reflex: IMU initialized OK
I (xxx) range: range sensor initialized (TRIG=GPIO21, ECHO=GPIO2)
I (xxx) reflex: Range sensor initialized OK
I (xxx) reflex: Hardware init complete.
I (xxx) reflex: All tasks started.
I (xxx) imu: imu_task started (period=2 ms)
I (xxx) range: range_task started @ 20 Hz
```

---

## Firmware Changes Required

Before starting Phase 1, apply the pin_map.h update:

```diff
- constexpr gpio_num_t PIN_RANGE_TRIG = GPIO_NUM_1;
+ constexpr gpio_num_t PIN_RANGE_TRIG = GPIO_NUM_21;
- constexpr gpio_num_t PIN_VBAT_SENSE = GPIO_NUM_14;
+ constexpr gpio_num_t PIN_VBAT_SENSE = GPIO_NUM_1;
```

This moves TRIG to a clean digital pin (GPIO21) and VBAT to the best ADC pin
(GPIO1 = ADC1_CH0). See `docs/reflex-wiring.md` for full rationale.
