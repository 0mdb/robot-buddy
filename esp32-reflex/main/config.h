#pragma once
// Configuration for Reflex MCU.
// Defaults are set at compile time. Runtime-tunable fields can be updated
// via the SET_CONFIG command from the supervisor.

#include <cstdint>

struct ReflexConfig {
    // -- Kinematics --
    float    wheelbase_mm;
    float    wheel_diameter_mm;
    uint16_t counts_per_rev; // encoder counts per wheel revolution (post-gearbox)

    // -- Control loop --
    uint16_t control_hz;  // control task frequency
    uint16_t pwm_freq_hz; // LEDC PWM frequency
    uint16_t max_pwm;     // max duty value (LEDC resolution dependent)

    // -- FF + PI gains (per wheel) --
    float    kV;      // feedforward velocity gain: duty per (mm/s)
    float    kS;      // feedforward static friction offset (duty units)
    float    Kp;      // proportional gain
    float    Ki;      // integral gain
    uint16_t min_pwm; // deadband / stiction compensation (duty units)

    // -- Rate limits --
    int16_t max_v_mm_s;     // max linear speed
    int16_t max_a_mm_s2;    // max linear accel
    int16_t max_w_mrad_s;   // max angular rate
    int16_t max_aw_mrad_s2; // max angular accel

    // -- IMU (BMI270) --
    uint16_t imu_odr_hz;         // accel + gyro output data rate (25–1600)
    uint16_t imu_gyro_range_dps; // gyro full-scale: 125, 250, 500, 1000, 2000
    uint8_t  imu_accel_range_g;  // accel full-scale: 2, 4, 8, 16

    // -- Yaw damping --
    float K_yaw; // gyro yaw correction gain

    // -- Safety --
    uint32_t cmd_timeout_ms;     // host must send commands faster than this
    uint32_t soft_stop_ramp_ms;  // ramp-to-zero duration on soft stop
    float    tilt_thresh_deg;    // tilt angle for hard stop
    uint32_t tilt_hold_ms;       // how long tilt must persist before fault
    uint32_t stall_thresh_ms;    // stall detection window
    int16_t  stall_speed_thresh; // speed below this + target above → stall (mm/s)

    // -- Range sensor --
    uint16_t range_stop_mm;    // trigger soft stop when range < this
    uint16_t range_release_mm; // release stop when range > this (hysteresis)
    uint32_t range_timeout_us; // max echo wait (limits max measurable range)
    uint16_t range_hz;         // measurement rate
};

// PWM resolution: 10-bit → max duty = 1023
constexpr uint8_t  PWM_RESOLUTION_BITS = 10;
constexpr uint16_t PWM_MAX_DUTY = (1 << PWM_RESOLUTION_BITS) - 1;

// Default configuration. Copied to the mutable g_cfg at boot.
constexpr ReflexConfig CFG_DEFAULTS = {
    // Kinematics — adjust for your chassis
    .wheelbase_mm = 150.0f,
    .wheel_diameter_mm = 65.0f,
    .counts_per_rev = 1440, // typical for TT motor + encoder disc

    // Control loop
    .control_hz = 100,
    .pwm_freq_hz = 20000, // 20 kHz — above audible, good for small motors
    .max_pwm = PWM_MAX_DUTY,

    // FF + PI — conservative starting point, needs tuning
    .kV = 1.0f,    // placeholder
    .kS = 0.0f,    // placeholder
    .Kp = 2.0f,    // placeholder
    .Ki = 0.5f,    // placeholder
    .min_pwm = 80, // placeholder — tune to overcome stiction

    // Rate limits
    .max_v_mm_s = 500,
    .max_a_mm_s2 = 1000,
    .max_w_mrad_s = 2000, // ~115 deg/s
    .max_aw_mrad_s2 = 4000,

    // IMU (BMI270)
    .imu_odr_hz = 400,         // 400 Hz — headroom above 100 Hz control loop
    .imu_gyro_range_dps = 500, // ±500 dps — good for wheeled robot yaw rates
    .imu_accel_range_g = 2,    // ±2g — max resolution for tilt detection

    // Yaw damping
    .K_yaw = 0.1f, // conservative, tune up

    // Safety
    .cmd_timeout_ms = 400,
    .soft_stop_ramp_ms = 500,
    .tilt_thresh_deg = 45.0f,
    .tilt_hold_ms = 200,
    .stall_thresh_ms = 500,
    .stall_speed_thresh = 20, // mm/s

    // Range sensor
    .range_stop_mm = 250,      // soft stop when obstacle closer than this
    .range_release_mm = 350,   // release when obstacle farther than this
    .range_timeout_us = 25000, // ~4.3 m max range (25 ms echo timeout)
    .range_hz = 20,            // 20 Hz measurement rate (50 ms period)
};

// ---- Runtime-mutable config ----
// Defined in app_main.cpp. Tasks read from this (not CFG_DEFAULTS).
extern ReflexConfig g_cfg;

// ---- Config parameter IDs for SET_CONFIG command ----
// Each ID maps to a field in ReflexConfig.
// Payload: [param_id:u8] [value:4 bytes] — float or u32 (LE).

enum class ConfigParam : uint8_t {
    // FF + PI gains (float)
    KV = 0x01,
    KS = 0x02,
    KP = 0x03,
    KI = 0x04,
    MIN_PWM = 0x05, // u16 (sent as u32, truncated)
    MAX_PWM = 0x06, // u16

    // Rate limits (i16 sent as i32)
    MAX_V_MM_S = 0x10,
    MAX_A_MM_S2 = 0x11,
    MAX_W_MRAD_S = 0x12,
    MAX_AW_MRAD_S2 = 0x13,

    // IMU (boot_only — requires reinit, sent as u32)
    IMU_ODR_HZ = 0x50,         // u16 as u32
    IMU_GYRO_RANGE_DPS = 0x51, // u16 as u32
    IMU_ACCEL_RANGE_G = 0x52,  // u8 as u32

    // Yaw damping (float)
    K_YAW = 0x20,

    // Safety (mixed types)
    CMD_TIMEOUT_MS = 0x30,     // u32
    SOFT_STOP_RAMP_MS = 0x31,  // u32
    TILT_THRESH_DEG = 0x32,    // float
    TILT_HOLD_MS = 0x33,       // u32
    STALL_THRESH_MS = 0x34,    // u32
    STALL_SPEED_THRESH = 0x35, // i16 as i32

    // Range sensor (u16 sent as u32)
    RANGE_STOP_MM = 0x40,
    RANGE_RELEASE_MM = 0x41,
};

// Apply a SET_CONFIG parameter. Returns true if the param_id was recognized.
// `value_bytes` points to 4 bytes (little-endian).
bool config_apply(uint8_t param_id, const uint8_t* value_bytes);
