//! Phase 0 gate: DRV8876 current sense -> COMP1 -> TIM1 break stall cutoff, on the NUCLEO-G431RB
//! with a Pololu 4036 DRV8876 carrier and a TT motor. Wiring and procedure: README.md.
//!
//! The hardware path (no firmware in it): CS pin -> COMP1 non-inverting input (PA1), threshold
//! from VREFINT -> TIM1 break -> EN PWM (PA8, TIM1_CH1) forced to its idle level (low = brake).
//! Firmware only logs, re-arms and decides what a trip means.
//!
//! B1 (blue button) steps through the modes; each starts the motor with a soft-start ramp:
//!   0 MEASURE  break off. Logs CS current (ADC) and the COMP output, to size the threshold.
//!   1 LATCH    break on, latched (AOE=0): a trip stops the motor until firmware re-arms it 2 s
//!              later. Shows whether start-up inrush trips, and how fast a hand stall is cut.
//!   2 CYCLE    break on, automatic re-enable (AOE=1): each trip ends that PWM cycle only, so the
//!              break acts as a cycle-by-cycle current limit. Firmware counts trips per window and
//!              latches off once they persist (a stall rather than an inrush spike).
//!   3 IDLE     motor off.
#![no_std]
#![no_main]

use defmt::{info, warn};
use embassy_executor::Spawner;
use embassy_stm32::adc::{Adc, AdcChannel, SampleTime};
use embassy_stm32::comp::{self, Comp, Hysteresis, InvertingInput};
use embassy_stm32::gpio::{Input, Level, Output, OutputType, Pull, Speed};
use embassy_stm32::time::khz;
use embassy_stm32::timer::complementary_pwm::ComplementaryPwm;
use embassy_stm32::timer::low_level::{CountingMode, FilterValue};
use embassy_stm32::timer::simple_pwm::PwmPin;
use embassy_stm32::timer::Channel;
use embassy_stm32::timer::complementary_pwm::{BreakComparatorPolarity, BreakInputPolarity, Ossi};
use embassy_stm32::{bind_interrupts, pac, peripherals};
use embassy_time::{Duration, Instant, Ticker, Timer};
use {defmt_rtt as _, panic_probe as _};

bind_interrupts!(struct Irqs {
    COMP1_2_3 => comp::InterruptHandler<peripherals::COMP1>;
});

/// Pololu 4036: CS has 2.49 kOhm to GND, so about 2.5 V/A (DRV8876 IPROPI gain 1000 uA/A).
const CS_MV_PER_A: u32 = 2490;
/// Trip threshold. VREFINT is 1.212 V typ; 3/4 of it = 0.909 V = about 365 mA.
/// TT on the bench (TODO 2026-11-20): running about 0.4 V (160 mA), stall 1.2-1.7 V.
const THRESHOLD: InvertingInput = InvertingInput::ThreeQuarterVref;
const THRESHOLD_MV: u32 = 909;
/// Run duty, percent. The bench supply is 5 V like the robot's motor rail.
const RUN_DUTY_PCT: u32 = 60;
const SOFT_START_MS: u32 = 200;
const PWM_KHZ: u32 = 20;
/// Sampling loop period and log window.
const TICK_US: u64 = 500;
const WINDOW_TICKS: u32 = 40; // 20 ms
/// CYCLE mode: a window counts as "limiting" if it saw any trip; this many in a row = stall.
const STALL_WINDOWS: u32 = 15; // 300 ms
const LATCH_REARM_MS: u64 = 2000;

#[derive(Clone, Copy, PartialEq, Eq, defmt::Format)]
enum Mode {
    Measure,
    Latch,
    Cycle,
    Idle,
}

impl Mode {
    fn next(self) -> Self {
        match self {
            Mode::Measure => Mode::Latch,
            Mode::Latch => Mode::Cycle,
            Mode::Cycle => Mode::Idle,
            Mode::Idle => Mode::Measure,
        }
    }
}

fn clocks() -> embassy_stm32::Config {
    use embassy_stm32::rcc::*;
    let mut config = embassy_stm32::Config::default();
    // HSI 16 MHz / 4 * 85 / 2 = 170 MHz, boost mode. ADC12 on SYSCLK (the default mux is off).
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

fn cs_ma(raw: u16) -> u32 {
    // 12-bit, VDDA = 3.3 V on the Nucleo.
    let mv = raw as u32 * 3300 / 4095;
    mv * 1000 / CS_MV_PER_A
}

/// TIM1 status/BDTR bits the Embassy wrapper does not expose: break flag (BIF) and MOE.
fn break_flag() -> bool {
    pac::TIM1.sr().read().bif(0)
}
fn clear_break_flag() {
    // SR bits are rc_w0: write 0 to the one to clear, 1 elsewhere.
    pac::TIM1.sr().write(|w| {
        w.0 = !0;
        w.set_bif(0, false);
    });
}

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let mut p = embassy_stm32::init(clocks());

    let idcode = pac::DBGMCU.idcode().read();
    info!("stall gate: DEV_ID {:#05x} REV_ID {:#06x}", idcode.dev_id() & 0x0fff, idcode.rev_id());

    let mut led = Output::new(p.PA5, Level::Low, Speed::Low);
    let button = Input::new(p.PC13, Pull::None); // B1, external pull on the Nucleo
    let button_idle = button.is_high();

    // DRV8876 control. PMODE must be wired to GND (PH/EN mode); the carrier leaves it floating,
    // which selects independent half-bridge mode.
    let mut sleep_n = Output::new(p.PB5, Level::Low, Speed::Low); // D4 -> SLEEP (also feeds VREF)
    let mut ph = Output::new(p.PA10, Level::Low, Speed::Low); // D2 -> PH/IN2
    let fault_n = Input::new(p.PB3, Pull::Up); // D3 <- FAULT (open drain)

    // COMP1: + = PA1 (A1, the CS pin), - = VREFINT fraction. Output high = over threshold.
    let mut comp = Comp::new(
        p.COMP1,
        p.PA1.reborrow(),
        Irqs,
        comp::Config {
            inverting_input: THRESHOLD,
            hysteresis: Hysteresis::Hyst20M,
            ..Default::default()
        },
    );
    comp.enable();

    // Same pin on the ADC for the measured current.
    let mut adc = Adc::new(p.ADC1, Default::default());
    let mut cs_ch = p.PA1.degrade_adc();

    // TIM1 CH1 on PA8 (D7) -> EN/IN1. Idle (after a break) = low = DRV8876 brake.
    let en_pin = PwmPin::new(p.PA8, OutputType::PushPull);
    let mut pwm = ComplementaryPwm::new(
        p.TIM1,
        Some(en_pin),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        khz(PWM_KHZ),
        CountingMode::EdgeAlignedUp,
    );
    let max = pwm.get_max_duty();
    pwm.set_duty(Channel::Ch1, 0);
    // OSSI=1: outputs stay driven at their idle level (low) when MOE drops, instead of Hi-Z.
    pwm.set_off_state_selection_idle(Ossi::IDLE_LEVEL);
    pac::TIM1.cr2().modify(|w| w.set_ois(0, false));
    // Break source: COMP1 only. BKIN pin off (its enable bit resets to 1 on the G4).
    pwm.set_break_input_pin_enable(false);
    pwm.set_break_comparator_enable(0, true);
    pwm.set_break_comparator_polarity(0, BreakComparatorPolarity::NOT_INVERTED);
    pwm.set_break_polarity(BreakInputPolarity::ACTIVE_HIGH);
    // About 1 us of filter at 170 MHz: rejects switching spikes, not a stall.
    pwm.set_break_filter(FilterValue::FDTS_DIV32_N8);
    pwm.enable(Channel::Ch1);

    sleep_n.set_high();
    Timer::after_millis(2).await; // DRV8876 wake time ~1 ms
    info!(
        "threshold {} mV = {} mA; run duty {}%, {} kHz; FAULT {}",
        THRESHOLD_MV,
        THRESHOLD_MV * 1000 / CS_MV_PER_A,
        RUN_DUTY_PCT,
        PWM_KHZ,
        if fault_n.is_low() { "LOW" } else { "ok" }
    );
    info!("B1 steps MEASURE -> LATCH -> CYCLE -> IDLE");

    let mut mode = Mode::Idle;
    let mut ticker = Ticker::every(Duration::from_micros(TICK_US));
    let mut started = Instant::now();
    let mut btn_last = button_idle;
    let mut btn_since = Instant::now();
    let mut btn_handled = true;

    // Window stats.
    let (mut sum, mut peak, mut n, mut comp_hi, mut trips) = (0u32, 0u32, 0u32, 0u32, 0u32);
    let mut limiting_windows = 0u32;
    let mut latched_at: Option<Instant> = None;
    let mut total_trips = 0u32;

    loop {
        ticker.next().await;
        let now = Instant::now();

        // Button: debounced press = level away from idle for 30 ms.
        let b = button.is_high();
        if b != btn_last {
            btn_last = b;
            btn_since = now;
            btn_handled = false;
        } else if !btn_handled && b != button_idle && now - btn_since >= Duration::from_millis(30) {
            btn_handled = true;
            mode = mode.next();
            pwm.set_break_enable(false);
            pwm.set_automatic_output_enable(false);
            pwm.set_duty(Channel::Ch1, 0);
            clear_break_flag();
            pwm.set_master_output_enable(true);
            match mode {
                Mode::Latch | Mode::Cycle => {
                    pwm.set_automatic_output_enable(mode == Mode::Cycle);
                    pwm.set_break_enable(true);
                }
                _ => {}
            }
            started = now;
            latched_at = None;
            limiting_windows = 0;
            total_trips = 0;
            led.set_level(if mode == Mode::Idle { Level::Low } else { Level::High });
            info!("== mode {} ==", mode);
        }

        // Duty: soft-start ramp, then hold.
        if mode != Mode::Idle && latched_at.is_none() {
            let ms = (now - started).as_millis() as u32;
            let pct = if ms >= SOFT_START_MS { RUN_DUTY_PCT } else { RUN_DUTY_PCT * ms / SOFT_START_MS };
            ph.set_low();
            pwm.set_duty(Channel::Ch1, max * pct / 100);
        }

        // Sample.
        let raw = adc.blocking_read(&mut cs_ch, SampleTime::CYCLES47_5);
        let ma = cs_ma(raw);
        sum += ma;
        peak = peak.max(ma);
        n += 1;
        if comp.output_level() {
            comp_hi += 1;
        }
        if break_flag() {
            trips += 1;
            total_trips += 1;
            clear_break_flag();
            if mode == Mode::Latch && latched_at.is_none() {
                latched_at = Some(now);
                pwm.set_duty(Channel::Ch1, 0);
                warn!(
                    "TRIP (latched) at {} ms after start, CS {} mA",
                    (now - started).as_millis(),
                    ma
                );
            }
        }

        // LATCH: re-arm after a pause.
        if let Some(t) = latched_at {
            if now - t >= Duration::from_millis(LATCH_REARM_MS) {
                info!("re-arm, soft start");
                clear_break_flag();
                pwm.set_master_output_enable(true);
                latched_at = None;
                started = now;
            }
        }

        if n == WINDOW_TICKS {
            // CYCLE: persistent limiting = stall -> latch off for good (until the next mode).
            if mode == Mode::Cycle {
                if trips > 0 {
                    limiting_windows += 1;
                } else {
                    limiting_windows = 0;
                }
                if limiting_windows == STALL_WINDOWS {
                    pwm.set_automatic_output_enable(false);
                    pwm.set_master_output_enable(false);
                    pwm.set_duty(Channel::Ch1, 0);
                    warn!(
                        "STALL: limiting for {} ms, {} trips since start -> off (B1 to continue)",
                        STALL_WINDOWS * WINDOW_TICKS * TICK_US as u32 / 1000,
                        total_trips
                    );
                }
            }
            if mode != Mode::Idle {
                info!(
                    "t {} ms  CS avg {} mA  peak {} mA  comp_hi {}/{}  trips {}  MOE {}  FAULT {}",
                    (now - started).as_millis(),
                    sum / n,
                    peak,
                    comp_hi,
                    n,
                    trips,
                    pac::TIM1.bdtr().read().moe() as u8,
                    if fault_n.is_low() { "LOW" } else { "ok" }
                );
            }
            (sum, peak, n, comp_hi, trips) = (0, 0, 0, 0, 0);
        }
    }
}
