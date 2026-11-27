//! Two HC-SR04 on TIM4 input capture at 1 MHz (front echo CH1, rear echo CH4), measured one
//! after the other (`range_ultrasonic.cpp` used the ESP32 RMT on one sonar). Echo is 5 V: the
//! echo pins are FT. Front feeds STATE and the OBSTACLE latch; rear only the local reverse
//! guard (Ben 2026-11-27).

use embassy_futures::select::{Either, select};
use embassy_stm32::gpio::Output;
use embassy_stm32::peripherals::TIM4;
use embassy_stm32::timer::Channel;
use embassy_stm32::timer::input_capture::InputCapture;
use embassy_time::{Duration, Timer, block_for};
use reflex_core::safety::{RangeSample, range_from_echo};

pub struct Sonar {
    ic: InputCapture<'static, TIM4>,
    trig_front: Output<'static>,
    trig_rear: Output<'static>,
}

#[derive(Clone, Copy, PartialEq, Eq, defmt::Format)]
pub enum Which {
    Front,
    Rear,
}

impl Sonar {
    pub fn new(mut ic: InputCapture<'static, TIM4>, trig_front: Output<'static>, trig_rear: Output<'static>) -> Self {
        ic.enable(Channel::Ch1);
        ic.enable(Channel::Ch4);
        Self { ic, trig_front, trig_rear }
    }

    /// One ping: 10 µs trigger, then time the echo pulse (rising -> falling) on the capture
    /// channel, giving up after `timeout_us` (+ the ~0.5 ms the module waits before echoing).
    pub async fn measure(&mut self, which: Which, timeout_us: u32) -> RangeSample {
        let (trig, ch) = match which {
            Which::Front => (&mut self.trig_front, Channel::Ch1),
            Which::Rear => (&mut self.trig_rear, Channel::Ch4),
        };
        trig.set_high();
        block_for(Duration::from_micros(10));
        trig.set_low();
        let deadline = Timer::after(Duration::from_micros(timeout_us as u64 + 1_000));
        let ic = &mut self.ic;
        let echo = async {
            let rise = ic.wait_for_rising_edge(ch).await;
            let fall = ic.wait_for_falling_edge(ch).await;
            fall.wrapping_sub(rise) as u32 // 16-bit counter at 1 MHz: < 65 ms, fine for 25 ms
        };
        match select(echo, deadline).await {
            Either::First(us) => range_from_echo(Some(us), timeout_us),
            Either::Second(()) => range_from_echo(None, timeout_us),
        }
    }
}
