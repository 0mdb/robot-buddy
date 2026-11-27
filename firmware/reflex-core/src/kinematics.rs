//! Encoder counts <-> distance and speed (`encoder.cpp::encoder_delta_to_mm_s`).

use crate::config::Config;

/// Millimetres of track per encoder count.
pub fn mm_per_count(cfg: &Config) -> f32 {
    cfg.wheel_diameter_mm * core::f32::consts::PI / cfg.counts_per_rev as f32
}

/// Speed from a count delta over `dt_us`. 0 for `dt_us == 0`.
pub fn delta_to_mm_s(cfg: &Config, delta_counts: i32, dt_us: u32) -> f32 {
    if dt_us == 0 {
        return 0.0;
    }
    delta_counts as f32 * mm_per_count(cfg) / (dt_us as f32 / 1_000_000.0)
}

/// Distance for a count delta.
pub fn counts_to_mm(cfg: &Config, counts: i32) -> f32 {
    counts as f32 * mm_per_count(cfg)
}

/// Twist (mm/s, mrad/s) -> (left, right) track speeds in mm/s.
pub fn twist_to_wheels(cfg: &Config, v_mm_s: f32, w_mrad_s: f32) -> (f32, f32) {
    let half_wb = cfg.wheelbase_mm / 2.0;
    let w = w_mrad_s / 1000.0;
    (v_mm_s - w * half_wb, v_mm_s + w * half_wb)
}

/// Saturating f32 -> i16 (`control.cpp::clamp_i16`; NaN -> 0).
pub fn clamp_i16(v: f32) -> i16 {
    if v.is_nan() {
        0
    } else {
        v.clamp(-32768.0, 32767.0) as i16
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_rev_per_second() {
        let c = Config::DEFAULTS;
        let v = delta_to_mm_s(&c, c.counts_per_rev as i32, 1_000_000);
        assert!((v - 65.0 * core::f32::consts::PI).abs() < 0.01);
        assert_eq!(delta_to_mm_s(&c, 100, 0), 0.0);
    }

    #[test]
    fn spin_in_place() {
        let (l, r) = twist_to_wheels(&Config::DEFAULTS, 0.0, 1000.0);
        assert_eq!((l, r), (-75.0, 75.0));
    }

    #[test]
    fn clamp() {
        assert_eq!(clamp_i16(1e9), 32767);
        assert_eq!(clamp_i16(-1e9), -32768);
        assert_eq!(clamp_i16(f32::NAN), 0);
    }
}
