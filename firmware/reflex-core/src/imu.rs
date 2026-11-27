//! LSM6DSV16X register settings and sample conversion (datasheet DS13510 Rev 4, local copy in
//! `~/kicad-libs/docs/ref/stm32g4/ds13510-lsm6dsv16x.pdf`). Pure: the SPI transfers live in the
//! firmware. Replaces the ESP32's BMI270 (`imu.cpp`); the core IMU on v3 is on SPI2, mode 3.
//!
//! Axes are used as the chip reports them, as the ESP32 did with the BMI270. The v3 board's
//! IMU orientation is not fixed yet: verify yaw sign and gravity on Z on the first v3 board.

use crate::config::Config;

pub const WHO_AM_I: u8 = 0x0F;
pub const WHO_AM_I_VALUE: u8 = 0x70;
pub const CTRL1: u8 = 0x10; // accel: OP_MODE_XL[6:4] | ODR_XL[3:0]
pub const CTRL2: u8 = 0x11; // gyro: OP_MODE_G[6:4] | ODR_G[3:0]
pub const CTRL3: u8 = 0x12; // BOOT | BDU(6) | IF_INC(2) | SW_RESET(0); default 0x44
pub const CTRL6: u8 = 0x15; // LPF1_G_BW[6:4] | FS_G[3:0]
pub const CTRL8: u8 = 0x17; // HP_LPF2_XL_BW[7:5] | XL_DualC_EN(3) | FS_XL[1:0]
pub const STATUS_REG: u8 = 0x1E;
/// OUTX_L_G: gyro X/Y/Z then (0x28) accel X/Y/Z, 12 bytes little-endian with IF_INC.
pub const OUTX_L_G: u8 = 0x22;
/// SPI: MSB of the address byte set = read.
pub const SPI_READ: u8 = 0x80;

pub const CTRL3_SW_RESET: u8 = 0x01;
/// BDU + IF_INC (the reset default, written explicitly).
pub const CTRL3_RUN: u8 = 0x44;

/// High-performance ODR code (CTRL1/CTRL2 table 52) for the first rate >= `hz`, capped at 7.68 kHz.
pub fn odr_code(hz: u16) -> u8 {
    const RATES: [(u16, u8); 11] = [
        (8, 0x2),
        (15, 0x3),
        (30, 0x4),
        (60, 0x5),
        (120, 0x6),
        (240, 0x7),
        (480, 0x8),
        (960, 0x9),
        (1920, 0xA),
        (3840, 0xB),
        (7680, 0xC),
    ];
    RATES.iter().find(|(r, _)| *r >= hz).map_or(0xC, |(_, c)| *c)
}

/// FS_G code and sensitivity (mdps/LSB) for a gyro range in dps (first range >= request).
pub fn gyro_fs(dps: u16) -> (u8, f32) {
    match dps {
        0..=125 => (0b0000, 4.375),
        126..=250 => (0b0001, 8.75),
        251..=500 => (0b0010, 17.5),
        501..=1000 => (0b0011, 35.0),
        1001..=2000 => (0b0100, 70.0),
        _ => (0b1100, 140.0),
    }
}

/// FS_XL code and sensitivity (mg/LSB) for an accel range in g (first range >= request).
pub fn accel_fs(g: u8) -> (u8, f32) {
    match g {
        0..=2 => (0b00, 0.061),
        3..=4 => (0b01, 0.122),
        5..=8 => (0b10, 0.244),
        _ => (0b11, 0.488),
    }
}

/// Register writes to configure the IMU from `Config` (after a SW reset).
pub fn init_writes(cfg: &Config) -> [(u8, u8); 5] {
    let odr = odr_code(cfg.imu_odr_hz);
    [
        (CTRL3, CTRL3_RUN),
        (CTRL6, gyro_fs(cfg.imu_gyro_range_dps).0),
        (CTRL8, accel_fs(cfg.imu_accel_range_g).0),
        (CTRL1, odr), // high-performance mode (OP_MODE 000)
        (CTRL2, odr),
    ]
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub struct ImuSample {
    pub gyro_rad_s: [f32; 3],
    pub accel_g: [f32; 3],
}

/// Convert the 12 bytes read from OUTX_L_G.
pub fn convert(cfg: &Config, raw: &[u8; 12]) -> ImuSample {
    let v = |i: usize| i16::from_le_bytes([raw[2 * i], raw[2 * i + 1]]) as f32;
    let g_sens = gyro_fs(cfg.imu_gyro_range_dps).1 / 1000.0 * core::f32::consts::PI / 180.0; // rad/s per LSB
    let a_sens = accel_fs(cfg.imu_accel_range_g).1 / 1000.0; // g per LSB
    ImuSample {
        gyro_rad_s: [v(0) * g_sens, v(1) * g_sens, v(2) * g_sens],
        accel_g: [v(3) * a_sens, v(4) * a_sens, v(5) * a_sens],
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_from_defaults() {
        let w = init_writes(&Config::DEFAULTS); // 400 Hz, 500 dps, 2 g
        assert_eq!(w, [(CTRL3, 0x44), (CTRL6, 0b0010), (CTRL8, 0b00), (CTRL1, 0x8), (CTRL2, 0x8)]);
        assert_eq!(odr_code(100), 0x6);
        assert_eq!(odr_code(9999), 0xC);
    }

    #[test]
    fn conversion() {
        let cfg = Config::DEFAULTS;
        let mut raw = [0u8; 12];
        // 1 g on Z at ±2 g: 1000 / 0.061 = 16393 LSB.
        raw[10..12].copy_from_slice(&16393i16.to_le_bytes());
        // 100 dps on Z at ±500 dps: 100000 / 17.5 = 5714 LSB.
        raw[4..6].copy_from_slice(&5714i16.to_le_bytes());
        let s = convert(&cfg, &raw);
        assert!((s.accel_g[2] - 1.0).abs() < 1e-3, "{s:?}");
        assert!((s.gyro_rad_s[2] - 100f32.to_radians()).abs() < 1e-3, "{s:?}");
    }
}
