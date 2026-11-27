//! Bench bring-up on the NUCLEO-G431RB: blink LD2 (PA5) and log over defmt/RTT.
//! Proves the build → flash → log loop before the phase 0 stall-cutoff gate.
#![no_std]
#![no_main]

use defmt::info;
use embassy_executor::Spawner;
use embassy_stm32::gpio::{Level, Output, Speed};
use embassy_time::Timer;
use {defmt_rtt as _, panic_probe as _};

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_stm32::init(Default::default());

    let idcode = embassy_stm32::pac::DBGMCU.idcode().read();
    info!(
        "NUCLEO-G431RB up: DEV_ID {:#05x}, REV_ID {:#06x}",
        idcode.dev_id() & 0x0fff, // DEV_ID is bits 11:0; the PAC field is wider
        idcode.rev_id()
    );

    let mut led = Output::new(p.PA5, Level::Low, Speed::Low);
    let mut n: u32 = 0;
    loop {
        led.toggle();
        n = n.wrapping_add(1);
        info!("tick {}", n);
        Timer::after_millis(500).await;
    }
}
