//! Reflex MCU firmware on the STM32G431: the port of `esp32-reflex` (motors, encoders, IMU,
//! sonar, safety, host link). Logic lives in `reflex-core` (host-tested); this crate is the
//! hardware and the tasks:
//!
//! | ESP32 task (core, prio)   | here                         | rate     |
//! |---------------------------|------------------------------|----------|
//! | control_task (0, 10)      | `control_task` (+ IMU read)  | 100 Hz   |
//! | safety_task (0, 6)        | `safety_task`                | 50 Hz    |
//! | imu_task (0, 8)           | read in `control_task`       | 100 Hz   |
//! | range_task (1, 4)         | `sonar_task` (front + rear)  | 20 Hz    |
//! | usb_rx + telemetry (1)    | `link_task`                  | 20 Hz TX |
//!
//! Boards (Cargo feature): `board-nucleo` (default, bench) or `board-v3`. Pins:
//! `~/kicad-libs/docs/g431-pin-plan.md` (v3); the Nucleo moves three of them off the ST-LINK
//! VCP (USART2 on PA2/PA3), see README.md.
#![no_std]
#![no_main]
#![cfg_attr(feature = "bringup", allow(dead_code))]

mod imu;
mod motor;
mod shared;
mod sonar;

use defmt::{info, warn};
use embassy_executor::Spawner;
use embassy_futures::select::{Either3, select3};
use embassy_sync::blocking_mutex::raw::CriticalSectionRawMutex;
use embassy_sync::channel::Channel;
use embassy_stm32::comp::{self, Comp, Hysteresis, InvertingInput};
use embassy_stm32::gpio::{Input, Level, Output, OutputType, Pull, Speed};
use embassy_stm32::peripherals::{TIM2, TIM3};
use embassy_stm32::spi::{self, Spi};
use embassy_stm32::time::{hz, mhz};
use embassy_stm32::timer::complementary_pwm::{ComplementaryPwm, ComplementaryPwmPin};
use embassy_stm32::timer::input_capture::{CapturePin, InputCapture};
use embassy_stm32::timer::low_level::{CountingMode, FilterValue};
use embassy_stm32::timer::qei::Qei;
use embassy_stm32::timer::simple_pwm::PwmPin;
use embassy_stm32::usart::{self, BufferedUart};
use embassy_stm32::{bind_interrupts, pac, peripherals, timer};
use embassy_time::{Duration, Ticker};
use embedded_io_async::{Read, Write};
use reflex_core::control::{self, Controller};
use reflex_core::kinematics::{clamp_i16, counts_to_mm, delta_to_mm_s};
use reflex_core::link::{Link, MAX_TX_FRAME};
use reflex_core::protocol::{BringupDiag, Command, State, fault};
use reflex_core::safety::{self, MotorAction, OvercurrentMonitor};
use shared::{now_us, post_action, with};
use {defmt_rtt as _, panic_probe as _};

#[cfg(all(feature = "board-nucleo", feature = "board-v3"))]
compile_error!("pick one board: board-nucleo or board-v3");

#[cfg(feature = "board-nucleo")]
bind_interrupts!(struct Irqs {
    USART2 => usart::BufferedInterruptHandler<peripherals::USART2>;
    COMP1_2_3 => comp::InterruptHandler<peripherals::COMP1>, comp::InterruptHandler<peripherals::COMP2>;
    TIM4 => timer::CaptureCompareInterruptHandler<peripherals::TIM4>;
});

#[cfg(feature = "board-v3")]
bind_interrupts!(struct Irqs {
    USART1 => usart::BufferedInterruptHandler<peripherals::USART1>;
    COMP1_2_3 => comp::InterruptHandler<peripherals::COMP1>, comp::InterruptHandler<peripherals::COMP2>;
    TIM4 => timer::CaptureCompareInterruptHandler<peripherals::TIM4>;
});

/// Host link baud: the supervisor's SerialTransport default.
const HOST_BAUD: u32 = 115_200;
/// Overcurrent trip threshold: 3/4 VREFINT = 0.91 V on IPROPI = ~365 mA at 2.49 kΩ (phase 0
/// value; set from the stall-gate bench results).
const OC_THRESHOLD: InvertingInput = InvertingInput::ThreeQuarterVref;
/// Consecutive 10 ms control ticks with break trips before reporting STALL.
const OC_STALL_TICKS: u16 = 30;
const TEL_PERIOD_MS: u64 = 50;
const SAFETY_PERIOD_MS: u64 = 20;
const SONAR_PERIOD_MS: u64 = 50;

/// BRINGUP_DIAG samples from the bring-up task to the link task.
static DIAG: Channel<CriticalSectionRawMutex, BringupDiag, 4> = Channel::new();

fn clocks() -> embassy_stm32::Config {
    use embassy_stm32::rcc::*;
    let mut config = embassy_stm32::Config::default();
    // HSI 16 MHz / 4 * 85 / 2 = 170 MHz, boost. (v3 has an 8 MHz crystal for FDCAN, unused here.)
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

/// ESTOP_N (PA6) closed loop = high. The pin is in AF mode for TIM1 BKIN; IDR still reads it.
fn estop_ok() -> bool {
    pac::GPIOA.idr().read().idr(6) == pac::gpio::vals::Idr::HIGH
}

/// PA6 -> TIM1_BKIN (AF6). Embassy checks the BreakInputPin trait but has no constructor for it.
fn route_bkin() {
    let pull = if cfg!(feature = "board-nucleo") {
        pac::gpio::vals::Pupdr::PULL_UP // nothing wired on the bench: loop "closed"
    } else {
        pac::gpio::vals::Pupdr::FLOATING // v3: external pull-down, NC loop to 3V3
    };
    pac::GPIOA.pupdr().modify(|w| w.set_pupdr(6, pull));
    pac::GPIOA.afr(0).modify(|w| w.set_afr(6, 6));
    pac::GPIOA.moder().modify(|w| w.set_moder(6, pac::gpio::vals::Moder::ALTERNATE));
}

#[embassy_executor::main]
async fn main(spawner: Spawner) {
    let p = embassy_stm32::init(clocks());
    let id = pac::DBGMCU.idcode().read();
    info!(
        "reflex-g431 ({}) DEV_ID {:#05x} REV_ID {:#06x}",
        if cfg!(feature = "board-v3") { "v3" } else { "nucleo" },
        id.dev_id() & 0x0fff,
        id.rev_id()
    );
    let cfg = with(|s| s.cfg);

    // ---- Board-specific pins ----
    #[cfg(feature = "board-nucleo")]
    let (uart, ph_l, ph_r, isense_l, isense_r) = {
        let mut ucfg = usart::Config::default();
        ucfg.baudrate = HOST_BAUD;
        static mut TX: [u8; 256] = [0; 256];
        static mut RX: [u8; 256] = [0; 256];
        #[allow(static_mut_refs)]
        let uart = unsafe { BufferedUart::new(p.USART2, p.PA3, p.PA2, &mut TX, &mut RX, Irqs, ucfg) }.unwrap();
        (uart, p.PA10, p.PC7, p.PA1, p.PA7)
    };
    #[cfg(feature = "board-v3")]
    let (uart, ph_l, ph_r, isense_l, isense_r) = {
        let mut ucfg = usart::Config::default();
        ucfg.baudrate = HOST_BAUD;
        static mut TX: [u8; 256] = [0; 256];
        static mut RX: [u8; 256] = [0; 256];
        #[allow(static_mut_refs)]
        let uart = unsafe { BufferedUart::new(p.USART1, p.PA10, p.PA9, &mut TX, &mut RX, Irqs, ucfg) }.unwrap();
        (uart, p.PA2, p.PA7, p.PA1, p.PA3)
    };

    // ---- Motors: TIM1 CH1 (PA8) left EN, CH2N (PB0) right EN; COMP1/2 + BKIN -> break ----
    let ccfg = comp::Config { inverting_input: OC_THRESHOLD, hysteresis: Hysteresis::Hyst20M, ..Default::default() };
    let mut comp_l = Comp::new(p.COMP1, isense_l, Irqs, ccfg);
    let mut comp_r = Comp::new(p.COMP2, isense_r, Irqs, ccfg);
    comp_l.enable();
    comp_r.enable();
    // Dropping a Comp disables it; these run for the life of the firmware.
    core::mem::forget(comp_l);
    core::mem::forget(comp_r);
    route_bkin();
    let pwm = ComplementaryPwm::new(
        p.TIM1,
        Some(PwmPin::new(p.PA8, OutputType::PushPull)),
        None,
        None,
        Some(ComplementaryPwmPin::new(p.PB0, OutputType::PushPull)),
        None,
        None,
        None,
        None,
        hz(cfg.pwm_freq_hz as u32),
        CountingMode::EdgeAlignedUp,
    );
    let motors = motor::Motors::new(
        pwm,
        Output::new(ph_l, Level::Low, Speed::Low),
        Output::new(ph_r, Level::Low, Speed::Low),
        Input::new(p.PC4, Pull::Up),
    );

    // ---- Encoders: TIM2 (PA5/PB3) left, TIM3 (PB4/PA4) right ----
    // Internal pull-ups as well as the encoder board's: a missing encoder reads still, not noise.
    let qcfg = {
        let mut c = embassy_stm32::timer::qei::Config::default();
        c.ch1_pull = Pull::Up;
        c.ch2_pull = Pull::Up;
        c
    };
    let qei_l = Qei::new(p.TIM2, p.PA5, p.PB3, qcfg);
    let qei_r = Qei::new(p.TIM3, p.PB4, p.PA4, qcfg);
    // Input filter fDTS/16, N = 8: ~750 ns at 170 MHz (the ESP32 PCNT used a 1 µs glitch filter).
    for tim in [pac::TIM2.ccmr_input(0), pac::TIM3.ccmr_input(0)] {
        tim.modify(|w| {
            w.set_icf(0, FilterValue::FDTS_DIV16_N8);
            w.set_icf(1, FilterValue::FDTS_DIV16_N8);
        });
    }

    // ---- IMU: LSM6DSV16X on SPI2 (PB13 SCK, PB15 MOSI, PB14 MISO, PB12 CS) ----
    let mut scfg = spi::Config::default();
    scfg.mode = spi::MODE_3;
    scfg.frequency = mhz(8);
    let spi = Spi::new_blocking(p.SPI2, p.PB13, p.PB15, p.PB14, scfg);
    let mut imu = imu::Imu::new(spi, Output::new(p.PB12, Level::High, Speed::VeryHigh));
    let imu = if imu.init(&cfg) {
        info!("imu: LSM6DSV16X up");
        Some(imu)
    } else {
        warn!("imu: init failed");
        if !cfg!(feature = "no-imu-fault") {
            with(|s| s.safety.raise(fault::IMU_FAIL));
        }
        None
    };

    // ---- Sonars: TIM4 capture at 1 MHz, front echo PA11 (CH1), rear PB9 (CH4) ----
    let ic = InputCapture::new(
        p.TIM4,
        Some(CapturePin::new(p.PA11, Pull::None)),
        None,
        None,
        Some(CapturePin::new(p.PB9, Pull::None)),
        Irqs,
        mhz(1),
        CountingMode::EdgeAlignedUp,
    );
    let sonar = sonar::Sonar::new(
        ic,
        Output::new(p.PC10, Level::Low, Speed::Low),
        Output::new(p.PC11, Level::Low, Speed::Low),
    );

    let led = Output::new(p.PC6, Level::Low, Speed::Low);

    // Motors are enabled at boot; the safety task gates them on faults (app_main.cpp).
    let mut motors = motors;
    motors.enable();

    #[cfg(not(feature = "bringup"))]
    {
        spawner.spawn(control_task(motors, qei_l, qei_r, imu).unwrap());
        spawner.spawn(safety_task(led).unwrap());
    }
    #[cfg(feature = "bringup")]
    {
        let _ = (imu, led);
        spawner.spawn(bringup_task(motors, qei_l, qei_r).unwrap());
    }
    spawner.spawn(sonar_task(sonar).unwrap());
    spawner.spawn(link_task(uart).unwrap());
}

#[embassy_executor::task]
async fn control_task(
    mut motors: motor::Motors,
    qei_l: Qei<'static, TIM2>,
    qei_r: Qei<'static, TIM3>,
    mut imu: Option<imu::Imu>,
) {
    let hz = with(|s| s.cfg.control_hz).max(1) as u64;
    let mut ticker = Ticker::every(Duration::from_micros(1_000_000 / hz));
    let mut ctl = Controller::new();
    let mut oc = OvercurrentMonitor::new();
    let (mut prev_l, mut prev_r) = (qei_l.count(), qei_r.count());
    let (mut acc_l, mut acc_r) = (0i32, 0i32);
    let mut prev_t = now_us();
    info!("control @ {} Hz", hz);
    loop {
        ticker.next().await;
        let now = now_us();
        let dt_us = now.wrapping_sub(prev_t).max(1);
        prev_t = now;

        // Encoders: 16-bit hardware counters, extended by wrapping deltas.
        let (cl, cr) = (qei_l.count(), qei_r.count());
        let (dl, dr) = (cl.wrapping_sub(prev_l) as i16 as i32, cr.wrapping_sub(prev_r) as i16 as i32);
        (prev_l, prev_r) = (cl, cr);
        acc_l = acc_l.wrapping_add(dl);
        acc_r = acc_r.wrapping_add(dr);

        // Motor action requested by the safety task.
        match with(|s| core::mem::replace(&mut s.pending_action, MotorAction::None)) {
            MotorAction::HardKill => motors.hard_kill(),
            MotorAction::Brake => motors.brake(),
            MotorAction::Enable => motors.enable(),
            MotorAction::None => {}
        }

        let cfg = with(|s| s.cfg);
        let sample = imu.as_mut().and_then(|i| i.sample(&cfg));
        // Break trips while the e-stop loop is closed are overcurrent; with it open, BKIN.
        let tripped = motors.take_break() && estop_ok();
        let drv_fault = motors.driver_fault();

        let out = with(|s| {
            if oc.update(tripped, OC_STALL_TICKS) && s.safety.faults() & fault::STALL == 0 {
                warn!("overcurrent limiting for {} ms: STALL", OC_STALL_TICKS as u32 * 10);
                s.safety.raise(fault::STALL);
            }
            if drv_fault && s.safety.faults() & fault::MOTOR_DRV == 0 {
                warn!("DRV8876 nFAULT: MOTOR_DRV");
                s.safety.raise(fault::MOTOR_DRV);
            }
            let v_l = delta_to_mm_s(&cfg, dl, dt_us);
            let v_r = delta_to_mm_s(&cfg, dr, dt_us);
            if sample.is_some() {
                s.imu = sample;
            }
            let gyro_z = s.imu.map_or(0.0, |m| m.gyro_rad_s[2]);
            let input = control::Input {
                dt_s: dt_us as f32 / 1_000_000.0,
                v_meas_l: v_l,
                v_meas_r: v_r,
                v_cmd_mm_s: s.cmd.v_mm_s as f32,
                w_cmd_mrad_s: s.cmd.w_mrad_s as f32,
                gyro_z_rad_s: gyro_z,
                faults: s.safety.faults(),
                rear_blocked: s.rear.blocked(),
            };
            let out = ctl.step(&cfg, &input);
            s.speed_l = v_l;
            s.speed_r = v_r;
            s.target_l = out.target_l;
            s.target_r = out.target_r;
            s.pos_l_mm = counts_to_mm(&cfg, acc_l);
            s.pos_r_mm = counts_to_mm(&cfg, acc_r);
            s.cmd_seq_applied = s.cmd.seq;
            s.t_cmd_applied_us = now;
            out
        });
        motors.set(motor::Side::Left, out.u_l, cfg.max_pwm);
        motors.set(motor::Side::Right, out.u_r, cfg.max_pwm);
    }
}

/// Open-loop bring-up (`app_main.cpp::open_loop_test_task`): 2 s wait, then each motor forward
/// and reverse at max_pwm/4 for 1.5 s, BRINGUP_DIAG every 100 ms, brake + 0.5 s + an IDLE
/// sample between phases, hard kill at the end. Raw counts are 16-bit QEI extended to i32.
#[cfg(feature = "bringup")]
#[embassy_executor::task]
async fn bringup_task(mut motors: motor::Motors, qei_l: Qei<'static, TIM2>, qei_r: Qei<'static, TIM3>) {
    use embassy_time::Timer;
    let cfg = with(|s| s.cfg);
    let duty = (cfg.max_pwm / 4) as f32;
    let (mut prev_l, mut prev_r) = (qei_l.count(), qei_r.count());
    let (mut raw_l, mut raw_r) = (0i32, 0i32);
    let mut counts = || {
        let (cl, cr) = (qei_l.count(), qei_r.count());
        raw_l = raw_l.wrapping_add(cl.wrapping_sub(prev_l) as i16 as i32);
        raw_r = raw_r.wrapping_add(cr.wrapping_sub(prev_r) as i16 as i32);
        (prev_l, prev_r) = (cl, cr);
        (raw_l, raw_r)
    };
    Timer::after_millis(2000).await;
    motors.enable();
    let phases = [
        (1u8, motor::Side::Left, true),
        (2, motor::Side::Left, false),
        (3, motor::Side::Right, true),
        (4, motor::Side::Right, false),
    ];
    for (phase, side, forward) in phases {
        info!("bringup phase {} {} {}", phase, side, if forward { "fwd" } else { "rev" });
        let (start_l, start_r) = counts();
        motors.set(side, if forward { duty } else { -duty }, cfg.max_pwm);
        for _ in 0..15 {
            Timer::after_millis(100).await;
            let (l, r) = counts();
            DIAG.send(BringupDiag {
                phase,
                side: (side == motor::Side::Right) as u8,
                forward,
                pwm_duty: duty as u16,
                raw_l: l,
                raw_r: r,
            })
            .await;
        }
        let (l, r) = counts();
        info!("  delta L {} R {}", l - start_l, r - start_r);
        motors.set(side, 0.0, cfg.max_pwm);
        motors.brake();
        Timer::after_millis(500).await;
        let (l, r) = counts();
        let side_u8 = (side == motor::Side::Right) as u8;
        DIAG.send(BringupDiag { phase: 0, side: side_u8, forward, pwm_duty: 0, raw_l: l, raw_r: r }).await;
    }
    motors.hard_kill();
    info!("bringup done");
}

#[embassy_executor::task]
async fn safety_task(mut led: Output<'static>) {
    let mut ticker = Ticker::every(Duration::from_millis(SAFETY_PERIOD_MS));
    let mut n: u32 = 0;
    let mut last_faults = 0u16;
    loop {
        ticker.next().await;
        let estop = estop_ok();
        let faults = with(|s| {
            let inputs = safety::Inputs {
                now_us: now_us(),
                last_cmd_us: s.last_cmd_us,
                accel_g: s.imu.map(|m| m.accel_g),
                speed_l: s.speed_l,
                speed_r: s.speed_r,
                target_l: s.target_l,
                target_r: s.target_r,
                range: s.range_front,
                pos_l_mm: s.pos_l_mm,
                pos_r_mm: s.pos_r_mm,
                estop_ok: estop,
            };
            let cfg = s.cfg;
            let action = s.safety.step(&cfg, &inputs);
            post_action(s, action);
            s.safety.faults()
        });
        if faults != last_faults {
            info!("faults {:#06x} -> {:#06x}", last_faults, faults);
            last_faults = faults;
        }
        // LED: steady with no faults, fast blink with any.
        n = n.wrapping_add(1);
        led.set_level(if faults == 0 || n % 10 < 5 { Level::High } else { Level::Low });
    }
}

#[embassy_executor::task]
async fn sonar_task(mut sonar: sonar::Sonar) {
    let mut ticker = Ticker::every(Duration::from_millis(SONAR_PERIOD_MS));
    loop {
        ticker.next().await;
        let timeout = with(|s| s.cfg.range_timeout_us);
        let front = sonar.measure(sonar::Which::Front, timeout).await;
        let rear = sonar.measure(sonar::Which::Rear, timeout).await;
        with(|s| {
            s.range_front = front;
            s.range_rear = rear;
            let cfg = s.cfg;
            s.rear.update(&cfg, rear, now_us());
        });
    }
}

#[embassy_executor::task]
async fn link_task(uart: BufferedUart<'static>) {
    let (mut tx, mut rx) = uart.split();
    let mut link = Link::new();
    let mut ticker = Ticker::every(Duration::from_millis(TEL_PERIOD_MS));
    let mut buf = [0u8; 64];
    let mut out = [0u8; MAX_TX_FRAME];
    loop {
        match select3(rx.read(&mut buf), ticker.next(), DIAG.receive()).await {
            Either3::Third(d) => {
                if let Some(n) = link.bringup_frame(&d, embassy_time::Instant::now().as_micros(), &mut out) {
                    let _ = tx.write_all(&out[..n]).await;
                }
            }
            Either3::First(Ok(n)) => {
                let mut replies: [([u8; MAX_TX_FRAME], usize); 4] = [([0; MAX_TX_FRAME], 0); 4];
                let mut nrep = 0;
                let now = now_us();
                link.feed(
                    &buf[..n],
                    embassy_time::Instant::now().as_micros(),
                    |f| {
                        if nrep < replies.len() {
                            replies[nrep].0[..f.len()].copy_from_slice(f);
                            replies[nrep].1 = f.len();
                            nrep += 1;
                        }
                    },
                    |c, seq| handle_command(c, seq, now),
                );
                for (f, len) in &replies[..nrep] {
                    let _ = tx.write_all(&f[..*len]).await;
                }
            }
            Either3::First(Err(e)) => warn!("uart rx error {}", e),
            Either3::Second(()) => {
                let s = with(|s| {
                    let imu = s.imu.unwrap_or_default();
                    State {
                        speed_l_mm_s: clamp_i16(s.speed_l),
                        speed_r_mm_s: clamp_i16(s.speed_r),
                        gyro_z_mrad_s: clamp_i16(imu.gyro_rad_s[2] * 1000.0),
                        accel_x_mg: clamp_i16(imu.accel_g[0] * 1000.0),
                        accel_y_mg: clamp_i16(imu.accel_g[1] * 1000.0),
                        accel_z_mg: clamp_i16(imu.accel_g[2] * 1000.0),
                        fault_flags: s.safety.faults(),
                        range_mm: s.range_front.mm,
                        range_status: s.range_front.status,
                        cmd_seq_last_applied: s.cmd_seq_applied,
                        t_cmd_applied_us: s.t_cmd_applied_us,
                    }
                });
                if let Some(n) = link.state_frame(&s, embassy_time::Instant::now().as_micros(), &mut out) {
                    let _ = tx.write_all(&out[..n]).await;
                }
            }
        }
    }
}

/// `usb_rx.cpp::handle_packet` for the reflex commands.
fn handle_command(c: Command, seq: u32, now: u32) {
    with(|s| {
        s.cmd_seq_last = seq;
        match c {
            Command::SetTwist { v_mm_s, w_mrad_s } => {
                s.cmd = shared::Cmd { v_mm_s, w_mrad_s, seq };
                s.last_cmd_us = Some(now);
            }
            Command::Stop { .. } => {
                s.cmd = shared::Cmd { v_mm_s: 0, w_mrad_s: 0, seq };
                s.last_cmd_us = Some(now);
            }
            Command::Estop => s.safety.estop(),
            Command::ClearFaults { mask } => s.safety.clear(mask),
            Command::SetConfig { param_id, value } => {
                if !s.cfg.apply(param_id, value) {
                    warn!("SET_CONFIG {:#04x} unknown", param_id);
                }
            }
            _ => {}
        }
    });
}
