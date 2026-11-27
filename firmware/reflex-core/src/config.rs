//! Runtime config, mirroring `esp32-reflex/main/config.{h,cpp}`: the same defaults and the same
//! SET_CONFIG parameter IDs and value encodings, so the supervisor's tuning code is unchanged.
//! Hardware fields that differ on the G431 (PWM resolution, IMU) are kept for wire compatibility.

#[derive(Clone, Copy, Debug, PartialEq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub struct Config {
    // Kinematics
    pub wheelbase_mm: f32,
    pub wheel_diameter_mm: f32,
    pub counts_per_rev: u16,
    // Control loop
    pub control_hz: u16,
    pub pwm_freq_hz: u16,
    pub max_pwm: u16,
    // FF + PI (duty units of a 10-bit PWM, as on the ESP32; the G431 port scales to its ARR)
    pub k_v: f32,
    pub k_s: f32,
    pub k_p: f32,
    pub k_i: f32,
    pub min_pwm: u16,
    // Rate limits
    pub max_v_mm_s: i16,
    pub max_a_mm_s2: i16,
    pub max_w_mrad_s: i16,
    pub max_aw_mrad_s2: i16,
    // IMU (boot-only)
    pub imu_odr_hz: u16,
    pub imu_gyro_range_dps: u16,
    pub imu_accel_range_g: u8,
    // Yaw damping
    pub k_yaw: f32,
    // Safety
    pub cmd_timeout_ms: u32,
    pub soft_stop_ramp_ms: u32,
    pub tilt_thresh_deg: f32,
    pub tilt_hold_ms: u32,
    pub stall_thresh_ms: u32,
    pub stall_speed_thresh: i16,
    // Range sensor
    pub range_stop_mm: u16,
    pub range_release_mm: u16,
    pub range_escape_max_mm_s: u16,
    pub range_blind_release_ms: u16,
    pub range_blind_release_mm: u16,
    pub range_timeout_us: u32,
    pub range_hz: u16,
}

/// 10-bit duty scale the gains and `min_pwm` / `max_pwm` are expressed in.
pub const PWM_MAX_DUTY: u16 = 1023;

impl Config {
    /// `CFG_DEFAULTS` in `config.h`.
    pub const DEFAULTS: Config = Config {
        wheelbase_mm: 150.0,
        wheel_diameter_mm: 65.0,
        counts_per_rev: 1440,
        control_hz: 100,
        pwm_freq_hz: 20000,
        max_pwm: PWM_MAX_DUTY,
        k_v: 1.0,
        k_s: 0.0,
        k_p: 2.0,
        k_i: 0.5,
        min_pwm: 80,
        max_v_mm_s: 500,
        max_a_mm_s2: 1000,
        max_w_mrad_s: 2000,
        max_aw_mrad_s2: 4000,
        imu_odr_hz: 400,
        imu_gyro_range_dps: 500,
        imu_accel_range_g: 2,
        k_yaw: 0.1,
        cmd_timeout_ms: 400,
        soft_stop_ramp_ms: 500,
        tilt_thresh_deg: 45.0,
        tilt_hold_ms: 200,
        stall_thresh_ms: 500,
        stall_speed_thresh: 20,
        range_stop_mm: 250,
        range_release_mm: 350,
        range_escape_max_mm_s: 100,
        range_blind_release_ms: 1000,
        range_blind_release_mm: 100,
        range_timeout_us: 25000,
        range_hz: 20,
    };

    /// Apply one SET_CONFIG parameter (`value` is 4 LE bytes: f32, u32 or i32 by parameter,
    /// narrowed with C cast semantics). Returns false for an unknown ID, which is left unapplied.
    pub fn apply(&mut self, param_id: u8, value: [u8; 4]) -> bool {
        let f = f32::from_le_bytes(value);
        let u = u32::from_le_bytes(value);
        let i = i32::from_le_bytes(value);
        match param_id {
            param::KV => self.k_v = f,
            param::KS => self.k_s = f,
            param::KP => self.k_p = f,
            param::KI => self.k_i = f,
            param::MIN_PWM => self.min_pwm = u as u16,
            param::MAX_PWM => self.max_pwm = u as u16,
            param::MAX_V_MM_S => self.max_v_mm_s = i as i16,
            param::MAX_A_MM_S2 => self.max_a_mm_s2 = i as i16,
            param::MAX_W_MRAD_S => self.max_w_mrad_s = i as i16,
            param::MAX_AW_MRAD_S2 => self.max_aw_mrad_s2 = i as i16,
            param::IMU_ODR_HZ => self.imu_odr_hz = u as u16,
            param::IMU_GYRO_RANGE_DPS => self.imu_gyro_range_dps = u as u16,
            param::IMU_ACCEL_RANGE_G => self.imu_accel_range_g = u as u8,
            param::K_YAW => self.k_yaw = f,
            param::CMD_TIMEOUT_MS => self.cmd_timeout_ms = u,
            param::SOFT_STOP_RAMP_MS => self.soft_stop_ramp_ms = u,
            param::TILT_THRESH_DEG => self.tilt_thresh_deg = f,
            param::TILT_HOLD_MS => self.tilt_hold_ms = u,
            param::STALL_THRESH_MS => self.stall_thresh_ms = u,
            param::STALL_SPEED_THRESH => self.stall_speed_thresh = i as i16,
            param::RANGE_STOP_MM => self.range_stop_mm = u as u16,
            param::RANGE_RELEASE_MM => self.range_release_mm = u as u16,
            _ => return false,
        }
        true
    }
}

impl Default for Config {
    fn default() -> Self {
        Self::DEFAULTS
    }
}

/// SET_CONFIG parameter IDs (`config.h::ConfigParam`).
pub mod param {
    pub const KV: u8 = 0x01;
    pub const KS: u8 = 0x02;
    pub const KP: u8 = 0x03;
    pub const KI: u8 = 0x04;
    pub const MIN_PWM: u8 = 0x05;
    pub const MAX_PWM: u8 = 0x06;
    pub const MAX_V_MM_S: u8 = 0x10;
    pub const MAX_A_MM_S2: u8 = 0x11;
    pub const MAX_W_MRAD_S: u8 = 0x12;
    pub const MAX_AW_MRAD_S2: u8 = 0x13;
    pub const K_YAW: u8 = 0x20;
    pub const CMD_TIMEOUT_MS: u8 = 0x30;
    pub const SOFT_STOP_RAMP_MS: u8 = 0x31;
    pub const TILT_THRESH_DEG: u8 = 0x32;
    pub const TILT_HOLD_MS: u8 = 0x33;
    pub const STALL_THRESH_MS: u8 = 0x34;
    pub const STALL_SPEED_THRESH: u8 = 0x35;
    pub const RANGE_STOP_MM: u8 = 0x40;
    pub const RANGE_RELEASE_MM: u8 = 0x41;
    pub const IMU_ODR_HZ: u8 = 0x50;
    pub const IMU_GYRO_RANGE_DPS: u8 = 0x51;
    pub const IMU_ACCEL_RANGE_G: u8 = 0x52;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apply_types() {
        let mut c = Config::DEFAULTS;
        assert!(c.apply(param::KP, 3.5f32.to_le_bytes()));
        assert_eq!(c.k_p, 3.5);
        assert!(c.apply(param::MAX_V_MM_S, (-300i32).to_le_bytes()));
        assert_eq!(c.max_v_mm_s, -300);
        assert!(c.apply(param::CMD_TIMEOUT_MS, 1234u32.to_le_bytes()));
        assert_eq!(c.cmd_timeout_ms, 1234);
        assert!(c.apply(param::MIN_PWM, 0x0001_0050u32.to_le_bytes())); // truncates like the C cast
        assert_eq!(c.min_pwm, 0x50);
        let before = c;
        assert!(!c.apply(0x99, [1, 2, 3, 4]));
        assert_eq!(c, before);
    }
}
