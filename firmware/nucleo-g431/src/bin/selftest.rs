//! Stall-cutoff self-test with no driver or motor: one jumper from A2 (PA4, DAC1_OUT1) to A1
//! (PA1, COMP1_INP) stands in for the DRV8876 CS pin. Proves the hardware half of the phase 0 gate
//! (COMP1 -> TIM1 break -> EN forced low) on the bench before the carrier is wired.
//!
//! For each VREFINT fraction the comparator can use (1/4, 1/2, 3/4, 1):
//!   1. sweep the DAC up in ~1.6 mV steps until COMP1 trips: trip voltage (ADC-measured) vs the
//!      expected fraction of the measured VREFINT;
//!   2. check the break fired: BIF set, MOE cleared, PA8 (TIM1_CH1, PWM at 100 %) reads low;
//!   3. sweep back down to the release voltage (hysteresis);
//!   4. latency: PWM held high, DAC stepped from 0 V to threshold + 100 mV, DWT cycles until PA8
//!      reads low. An upper bound: it includes DAC settling (~3 us, DS12589) and the break filter.
//! Ends with PASS/FAIL per threshold. Wiring: README.md.
#![no_std]
#![no_main]

use cortex_m::peripheral::DWT;
use defmt::{error, info, warn};
use embassy_executor::Spawner;
use embassy_stm32::adc::{Adc, AdcChannel, SampleTime};
use embassy_stm32::comp::{self, Comp, Hysteresis, InvertingInput};
use embassy_stm32::dac::{DacChannel, Value};
use embassy_stm32::gpio::OutputType;
use embassy_stm32::time::khz;
use embassy_stm32::timer::Channel;
use embassy_stm32::timer::complementary_pwm::{BreakComparatorPolarity, BreakInputPolarity, ComplementaryPwm, Ossi};
use embassy_stm32::timer::low_level::{CountingMode, FilterValue};
use embassy_stm32::timer::simple_pwm::PwmPin;
use embassy_stm32::{bind_interrupts, pac, peripherals};
use embassy_time::{Duration, Timer};
use {defmt_rtt as _, panic_probe as _};

bind_interrupts!(struct Irqs {
    COMP1_2_3 => comp::InterruptHandler<peripherals::COMP1>;
});

const SYSCLK_HZ: u32 = 170_000_000;
/// VREFINT_CAL: raw 12-bit VREFINT reading taken at VDDA = 3.0 V, 30 C (DS12589 Table 6).
const VREFINT_CAL_ADDR: *const u16 = 0x1FFF_75AA as *const u16;
/// Trip must land within this of the expected fraction of VREFINT. COMP offset is +-20 mV max on
/// a good part (rev Z/Y have an erratum); the VREFINT scaler adds a little.
const TOLERANCE_MV: i32 = 25;
const DAC_STEP: u16 = 2; // LSB, ~1.6 mV at 3.3 V

fn clocks() -> embassy_stm32::Config {
    use embassy_stm32::rcc::*;
    let mut config = embassy_stm32::Config::default();
    config.rcc.pll = Some(Pll {
        source: PllSource::HSI,
        prediv: PllPreDiv::DIV4,
        mul: PllMul::MUL85,
        divp: None,
        divq: None,
        divr: Some(PllRDiv::DIV2),
    });
    config.rcc.sys = Sysclk::PLL1_R;
    config.rcc.boost = true;
    config.rcc.mux.adc12sel = mux::Adcsel::SYS;
    config
}

fn bif() -> bool {
    pac::TIM1.sr().read().bif(0)
}
fn clear_bif() {
    pac::TIM1.sr().write(|w| {
        w.0 = !0;
        w.set_bif(0, false);
    });
}
fn moe() -> bool {
    pac::TIM1.bdtr().read().moe()
}
fn pa8_high() -> bool {
    pac::GPIOA.idr().read().idr(8) == pac::gpio::vals::Idr::HIGH
}

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let mut p = embassy_stm32::init(clocks());
    let mut cp = cortex_m::Peripherals::take().unwrap();
    cp.DCB.enable_trace();
    cp.DWT.enable_cycle_counter();

    let idcode = pac::DBGMCU.idcode().read();
    info!("selftest: DEV_ID {:#05x} REV_ID {:#06x}", idcode.dev_id() & 0x0fff, idcode.rev_id());
    info!("needs a jumper A2 (PA4) -> A1 (PA1); nothing else on A1");

    // ADC: measure VREFINT to get VDDA and the real comparator thresholds.
    let mut adc = Adc::new(p.ADC1, Default::default());
    let mut vrefint = adc.enable_vrefint();
    Timer::after_micros(20).await;
    let mut acc = 0u32;
    for _ in 0..16 {
        acc += adc.blocking_read(&mut vrefint, SampleTime::CYCLES640_5) as u32;
    }
    let vref_raw = acc / 16;
    let cal = unsafe { core::ptr::read_volatile(VREFINT_CAL_ADDR) } as u32;
    let vdda_mv = 3000 * cal / vref_raw;
    let vrefint_mv = (cal * 3000 / 4095) as i32; // VREFINT itself, from the factory calibration
    info!("VREFINT_CAL {} raw {} -> VDDA {} mV, VREFINT {} mV", cal, vref_raw, vdda_mv, vrefint_mv);
    let to_mv = |raw: u16| (raw as u32 * vdda_mv / 4095) as i32;

    let mut dac = DacChannel::new_blocking(p.DAC1, p.PA4);
    dac.set(Value::Bit12Right(0));

    // TIM1 CH1 on PA8, 100 % duty so the pin sits high until the break forces it to idle (low).
    let mut pwm = ComplementaryPwm::new(
        p.TIM1,
        Some(PwmPin::new(p.PA8, OutputType::PushPull)),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        khz(20),
        CountingMode::EdgeAlignedUp,
    );
    let max = pwm.get_max_duty();
    pwm.set_duty(Channel::Ch1, max); // max = 100 % in Embassy: output always active
    pwm.set_off_state_selection_idle(Ossi::IDLE_LEVEL);
    pac::TIM1.cr2().modify(|w| w.set_ois(0, false));
    pwm.set_break_input_pin_enable(false);
    pwm.set_break_comparator_enable(0, true);
    pwm.set_break_comparator_polarity(0, BreakComparatorPolarity::NOT_INVERTED);
    pwm.set_break_polarity(BreakInputPolarity::ACTIVE_HIGH);
    pwm.set_break_filter(FilterValue::FDTS_DIV32_N8);
    pwm.enable(Channel::Ch1);

    let cases = [
        ("1/4 VREFINT", InvertingInput::OneQuarterVref, 1, 4),
        ("1/2 VREFINT", InvertingInput::HalfVref, 1, 2),
        ("3/4 VREFINT", InvertingInput::ThreeQuarterVref, 3, 4),
        ("VREFINT", InvertingInput::Vref, 1, 1),
    ];
    let mut all = true;

    for (name, inm, num, den) in cases {
        let expected_mv = vrefint_mv * num / den;
        let mut comp = Comp::new(
            p.COMP1.reborrow(),
            p.PA1.reborrow(),
            Irqs,
            comp::Config { inverting_input: inm, hysteresis: Hysteresis::Hyst20M, ..Default::default() },
        );
        comp.enable();
        // Same pin on the ADC (analog mode serves both).
        let mut sense = p.PA1.reborrow().degrade_adc();
        // Arm: DAC low, break off, flags clear, outputs on.
        dac.set(Value::Bit12Right(0));
        Timer::after_millis(2).await;
        pwm.set_break_enable(false);
        clear_bif();
        pwm.set_master_output_enable(true);
        pwm.set_break_enable(true);
        clear_bif();
        Timer::after_micros(100).await;
        if !moe() || !pa8_high() {
            error!("{}: could not arm (MOE {}, PA8 high {}): A1 above threshold at 0 V?", name, moe(), pa8_high());
        }

        // 1. Sweep up.
        let mut code: u16 = 0;
        let mut trip_mv = -1;
        while code < 4095 - DAC_STEP {
            code += DAC_STEP;
            dac.set(Value::Bit12Right(code));
            Timer::after_micros(50).await;
            if comp.output_level() || bif() {
                trip_mv = to_mv(adc.blocking_read(&mut sense, SampleTime::CYCLES247_5));
                break;
            }
        }
        // 2. Break effect.
        let break_ok = trip_mv >= 0 && bif() && !moe() && !pa8_high();
        // 3. Sweep down to release (break stays latched: AOE is off).
        let mut release_mv = -1;
        while code > DAC_STEP {
            code -= DAC_STEP;
            dac.set(Value::Bit12Right(code));
            Timer::after_micros(50).await;
            if !comp.output_level() {
                release_mv = to_mv(adc.blocking_read(&mut sense, SampleTime::CYCLES247_5));
                break;
            }
        }

        // 4. Latency: re-arm at 0 V, step to threshold + 100 mV, time PA8 going low.
        dac.set(Value::Bit12Right(0));
        Timer::after_millis(2).await;
        clear_bif();
        pwm.set_master_output_enable(true);
        Timer::after_micros(100).await;
        let step_code = (((expected_mv + 100) as u32 * 4095) / vdda_mv).min(4095) as u16;
        let mut latency_ns = u32::MAX;
        if pa8_high() {
            let t0 = DWT::cycle_count();
            dac.set(Value::Bit12Right(step_code));
            let mut t1 = t0;
            for _ in 0..100_000 {
                if !pa8_high() {
                    t1 = DWT::cycle_count();
                    break;
                }
            }
            if t1 != t0 {
                latency_ns = ((t1.wrapping_sub(t0)) as u64 * 1_000_000_000 / SYSCLK_HZ as u64) as u32;
            }
        }

        info!(
            "{}: expect {} mV, trip {} mV, release {} mV (hyst {} mV), break {}, latency {} ns",
            name,
            expected_mv,
            trip_mv,
            release_mv,
            trip_mv - release_mv,
            if break_ok { "ok" } else { "MISSING" },
            latency_ns
        );
        let pass = trip_mv >= 0
            && (trip_mv - expected_mv).abs() <= TOLERANCE_MV
            && release_mv >= 0
            && release_mv < trip_mv
            && break_ok
            && latency_ns < 10_000;
        all &= pass;
        if pass {
            info!("PASS {}", name);
        } else {
            warn!("FAIL {}", name);
        }

        pwm.set_break_enable(false);
        dac.set(Value::Bit12Right(0));
        drop(comp);
    }

    if all {
        info!("SELFTEST PASS: COMP1 -> TIM1 break works at all four thresholds");
    } else {
        error!("SELFTEST FAIL (jumper A2 -> A1 in place?)");
    }
    loop {
        Timer::after(Duration::from_secs(3600)).await;
    }
}
