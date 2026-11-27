//! Two DRV8876 in PH/EN mode on TIM1 (replaces the ESP32's TB6612 + TCA9554A direction
//! expander, `motor.cpp`). EN = PWM (left TIM1_CH1, right TIM1_CH2N), PH = direction GPIO.
//! EN low = brake (low-side slow decay). The DRV8876 takes a direction change on PH directly,
//! so the ESP32's PWM-0 / expander write / readback sequence is gone, and with it MOTOR_DRV
//! for a missing expander; MOTOR_DRV now means a driver nFAULT.
//!
//! Hardware stop paths (no firmware in them), as in the phase 0 stall gate:
//! - IPROPI L/R -> COMP1 / COMP2 (threshold from VREFINT) -> TIM1 break, automatic output enable:
//!   a trip ends that PWM cycle (cycle-by-cycle current limit). Note: TIM1 has one break, so a
//!   trip on either side ends the cycle for both. Per-channel OCREF_CLR would separate them.
//! - ESTOP_N -> TIM1 BKIN (active low): outputs forced to idle (low) while the loop is open.
//!   On v3 ESTOP_N also drives both nSLEEP, so the bridges are off whatever the MCU does.
//!
//! Duty arrives in the ESP32's 10-bit units (`Config::max_pwm`) and is scaled to the timer.

use embassy_stm32::gpio::{Input, Output};
use embassy_stm32::pac;
use embassy_stm32::peripherals::TIM1;
use embassy_stm32::timer::Channel;
use embassy_stm32::timer::complementary_pwm::{BreakComparatorPolarity, BreakInputPolarity, ComplementaryPwm, Ossi};
use embassy_stm32::timer::low_level::FilterValue;
use reflex_core::config::PWM_MAX_DUTY;

#[derive(Clone, Copy, PartialEq, Eq, defmt::Format)]
pub enum Side {
    Left,
    Right,
}

pub struct Motors {
    pwm: ComplementaryPwm<'static, TIM1>,
    ph_l: Output<'static>,
    ph_r: Output<'static>,
    fault_n: Input<'static>,
    enabled: bool,
}

/// Right-side output is CH2N; left is CH1.
fn channel(side: Side) -> Channel {
    match side {
        Side::Left => Channel::Ch1,
        Side::Right => Channel::Ch2,
    }
}

impl Motors {
    /// `pwm` must be built with CH1 (left EN) and CH2N (right EN) pins only.
    pub fn new(
        mut pwm: ComplementaryPwm<'static, TIM1>,
        ph_l: Output<'static>,
        ph_r: Output<'static>,
        fault_n: Input<'static>,
    ) -> Self {
        pwm.set_duty(Channel::Ch1, 0);
        pwm.set_duty(Channel::Ch2, 0);
        // Outputs: CH1 main only, CH2 complementary only (OC2N = OC2REF when CC2E = 0).
        // ComplementaryPwm::enable() would set both and invert CH2N.
        pac::TIM1.ccer().modify(|w| {
            w.set_cce(0, true);
            w.set_ccne(0, false);
            w.set_cce(1, false);
            w.set_ccne(1, true);
        });
        // Break (MOE = 0): outputs driven at their idle level, low = EN low = brake.
        pwm.set_off_state_selection_idle(Ossi::IDLE_LEVEL);
        pac::TIM1.cr2().modify(|w| {
            w.set_ois(0, false);
            w.set_oisn(1, false);
        });
        // Break sources: COMP1 + COMP2 (high = overcurrent), BKIN (ESTOP_N, low = open loop).
        pwm.set_break_comparator_enable(0, true);
        pwm.set_break_comparator_enable(1, true);
        pwm.set_break_comparator_polarity(0, BreakComparatorPolarity::NOT_INVERTED);
        pwm.set_break_comparator_polarity(1, BreakComparatorPolarity::NOT_INVERTED);
        pwm.set_break_input_pin_enable(true);
        pac::TIM1.af1().modify(|w| w.set_bkinp(BreakComparatorPolarity::INVERTED)); // invert BKIN: low pin = break
        pwm.set_break_polarity(BreakInputPolarity::ACTIVE_HIGH);
        pwm.set_break_filter(FilterValue::FDTS_DIV32_N8); // ~1.5 µs: switching spikes, not a stall
        pwm.set_automatic_output_enable(true);
        pwm.set_break_enable(true);
        clear_break_flag();
        pwm.set_master_output_enable(true);
        Self { pwm, ph_l, ph_r, fault_n, enabled: false }
    }

    pub fn enable(&mut self) {
        self.enabled = true;
        clear_break_flag();
        self.pwm.set_master_output_enable(true);
    }

    /// Signed duty in `Config::max_pwm` units (+ forward). Ignored while disabled.
    pub fn set(&mut self, side: Side, u: f32, max_pwm: u16) {
        if !self.enabled {
            return;
        }
        let forward = u >= 0.0;
        let mag = if forward { u } else { -u };
        let mag = mag.min(max_pwm as f32);
        let max = self.pwm.get_max_duty();
        let duty = ((mag * max as f32) / PWM_MAX_DUTY as f32) as u32;
        let ph = match side {
            Side::Left => &mut self.ph_l,
            Side::Right => &mut self.ph_r,
        };
        // PH high = OUT1 -> OUT2 ("forward"); swap the motor leads, not this, if a side runs
        // backwards.
        if forward {
            ph.set_high();
        } else {
            ph.set_low();
        }
        self.pwm.set_duty(channel(side), duty.min(max));
    }

    /// Duty 0 on both: EN low = brake.
    pub fn brake(&mut self) {
        self.pwm.set_duty(Channel::Ch1, 0);
        self.pwm.set_duty(Channel::Ch2, 0);
    }

    /// Brake and disable until `enable()`.
    pub fn hard_kill(&mut self) {
        self.enabled = false;
        self.brake();
    }

    /// A DRV8876 reports a fault (nFAULT wired-OR, low = fault).
    pub fn driver_fault(&self) -> bool {
        self.fault_n.is_low()
    }

    /// Did the break trip since the last call (overcurrent or e-stop)? Clears the flag.
    pub fn take_break(&mut self) -> bool {
        let tripped = pac::TIM1.sr().read().bif(0);
        if tripped {
            clear_break_flag();
        }
        tripped
    }
}

fn clear_break_flag() {
    // SR bits are rc_w0: write 0 to the one to clear, 1 elsewhere.
    pac::TIM1.sr().write(|w| {
        w.0 = !0;
        w.set_bif(0, false);
    });
}
