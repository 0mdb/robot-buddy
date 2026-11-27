//! LSM6DSV16X on SPI2 (mode 3), blocking: a 13-byte transfer at 8 MHz takes ~15 µs, read once
//! per control tick. Registers and conversion: `reflex_core::imu`.

use embassy_stm32::gpio::Output;
use embassy_stm32::mode::Blocking;
use embassy_stm32::spi::Spi;
use embassy_time::{Duration, block_for};
use reflex_core::config::Config;
use reflex_core::imu::{self, ImuSample};

pub struct Imu {
    spi: Spi<'static, Blocking, embassy_stm32::spi::mode::Master>,
    cs: Output<'static>,
}

impl Imu {
    pub fn new(spi: Spi<'static, Blocking, embassy_stm32::spi::mode::Master>, cs: Output<'static>) -> Self {
        Self { spi, cs }
    }

    fn write(&mut self, reg: u8, val: u8) -> bool {
        self.cs.set_low();
        let ok = self.spi.blocking_write(&[reg & 0x7F, val]).is_ok();
        self.cs.set_high();
        ok
    }

    fn read(&mut self, reg: u8, out: &mut [u8]) -> bool {
        let mut buf = [0u8; 13];
        let n = out.len() + 1;
        buf[0] = reg | imu::SPI_READ;
        self.cs.set_low();
        let ok = self.spi.blocking_transfer_in_place(&mut buf[..n]).is_ok();
        self.cs.set_high();
        out.copy_from_slice(&buf[1..n]);
        ok
    }

    /// Reset and configure from `cfg`. False if the chip does not answer WHO_AM_I or a
    /// register does not read back.
    pub fn init(&mut self, cfg: &Config) -> bool {
        let mut id = [0u8];
        if !self.read(imu::WHO_AM_I, &mut id) || id[0] != imu::WHO_AM_I_VALUE {
            defmt::warn!("imu: WHO_AM_I {:#04x}, expected {:#04x}", id[0], imu::WHO_AM_I_VALUE);
            return false;
        }
        self.write(imu::CTRL3, imu::CTRL3_SW_RESET);
        block_for(Duration::from_millis(2));
        for (reg, val) in imu::init_writes(cfg) {
            let mut back = [0u8];
            if !self.write(reg, val) || !self.read(reg, &mut back) || back[0] != val {
                defmt::warn!("imu: reg {:#04x} wrote {:#04x} read {:#04x}", reg, val, back[0]);
                return false;
            }
        }
        true
    }

    pub fn sample(&mut self, cfg: &Config) -> Option<ImuSample> {
        let mut raw = [0u8; 12];
        self.read(imu::OUTX_L_G, &mut raw).then(|| imu::convert(cfg, &raw))
    }
}
