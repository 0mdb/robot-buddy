//! Host link bring-up: the reflex wire protocol (`reflex-core`) over the Nucleo's ST-LINK VCP
//! (USART2, PA2/PA3, 115200 8N1 = the supervisor's `SerialTransport` default), so the real Pi
//! supervisor code can drive the G431 from this PC with no carrier attached.
//!
//! Handles the v2 handshake and time sync, STATE at 20 Hz (as `telemetry.cpp`), ESTOP /
//! CLEAR_FAULTS / SET_CONFIG, and the command timeout fault. No motors: the "wheel speeds" in
//! STATE are the rate-limited twist target, so the supervisor sees motion respond to commands.
//! LD2 lights while the target is non-zero.
#![no_std]
#![no_main]

use defmt::{info, warn};
use embassy_executor::Spawner;
use embassy_futures::select::{Either, select};
use embassy_stm32::gpio::{Level, Output, Speed};
use embassy_stm32::usart::{self, BufferedUart};
use embassy_stm32::{bind_interrupts, peripherals};
use embassy_time::{Duration, Instant, Ticker};
use embedded_io_async::{Read, Write};
use reflex_core::config::Config;
use reflex_core::link::{Link, MAX_TX_FRAME};
use reflex_core::protocol::{Command, State, fault, range_status};
use {defmt_rtt as _, panic_probe as _};

bind_interrupts!(struct Irqs {
    USART2 => usart::BufferedInterruptHandler<peripherals::USART2>;
});

const TEL_PERIOD_MS: u64 = 50;

fn now_us() -> u64 {
    Instant::now().as_micros()
}

/// Step `cur` toward `target` by at most `max_step`.
fn slew(cur: i32, target: i32, max_step: i32) -> i32 {
    cur + (target - cur).clamp(-max_step, max_step)
}

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_stm32::init(Default::default());
    info!("link: reflex protocol on USART2 (ST-LINK VCP), 115200");

    let mut led = Output::new(p.PA5, Level::Low, Speed::Low);

    let mut cfg_uart = usart::Config::default();
    cfg_uart.baudrate = 115_200;
    let mut tx_buf = [0u8; 256];
    let mut rx_buf = [0u8; 256];
    let uart = BufferedUart::new(p.USART2, p.PA3, p.PA2, &mut tx_buf, &mut rx_buf, Irqs, cfg_uart).unwrap();
    let (mut tx, mut rx) = uart.split();

    let mut cfg = Config::DEFAULTS;
    let mut link = Link::new();
    let mut faults: u16 = 0;
    let (mut target_v, mut target_w) = (0i32, 0i32);
    let (mut v, mut w) = (0i32, 0i32);
    let mut last_cmd: Option<Instant> = None;
    let mut t_cmd_applied_us: u32 = 0;

    let mut ticker = Ticker::every(Duration::from_millis(TEL_PERIOD_MS));
    let mut buf = [0u8; 64];
    let mut out = [0u8; MAX_TX_FRAME];

    loop {
        match select(rx.read(&mut buf), ticker.next()).await {
            Either::First(Ok(n)) => {
                // Replies are queued here and written after feed() (it borrows link mutably).
                let mut replies: [([u8; MAX_TX_FRAME], usize); 4] = [([0; MAX_TX_FRAME], 0); 4];
                let mut nrep = 0;
                link.feed(
                    &buf[..n],
                    now_us(),
                    |f| {
                        if nrep < replies.len() {
                            replies[nrep].0[..f.len()].copy_from_slice(f);
                            replies[nrep].1 = f.len();
                            nrep += 1;
                        }
                    },
                    |c, seq| {
                        match c {
                            Command::SetTwist { v_mm_s, w_mrad_s } => {
                                target_v = (v_mm_s as i32).clamp(-cfg.max_v_mm_s as i32, cfg.max_v_mm_s as i32);
                                target_w =
                                    (w_mrad_s as i32).clamp(-cfg.max_w_mrad_s as i32, cfg.max_w_mrad_s as i32);
                                last_cmd = Some(Instant::now());
                                t_cmd_applied_us = now_us() as u32;
                            }
                            Command::Stop { .. } => {
                                (target_v, target_w) = (0, 0);
                                last_cmd = Some(Instant::now());
                            }
                            Command::Estop => {
                                faults |= fault::ESTOP;
                                warn!("ESTOP (seq {})", seq);
                            }
                            Command::ClearFaults { mask } => {
                                faults &= !mask;
                                info!("clear faults {:#06x} -> {:#06x}", mask, faults);
                            }
                            Command::SetConfig { param_id, value } => {
                                let ok = cfg.apply(param_id, value);
                                info!("SET_CONFIG {:#04x} {}", param_id, if ok { "ok" } else { "unknown" });
                            }
                            other => info!("ignored {}", other),
                        }
                    },
                );
                for (f, len) in &replies[..nrep] {
                    let _ = tx.write_all(&f[..*len]).await;
                }
            }
            Either::First(Err(e)) => warn!("uart rx error {}", e),
            Either::Second(()) => {
                // Command timeout (safety.cpp): only once a command has been seen.
                if let Some(t) = last_cmd {
                    if Instant::now() - t > Duration::from_millis(cfg.cmd_timeout_ms as u64) {
                        if faults & fault::CMD_TIMEOUT == 0 {
                            warn!("command timeout");
                        }
                        faults |= fault::CMD_TIMEOUT;
                    }
                }
                if faults != 0 {
                    (target_v, target_w) = (0, 0);
                }
                // Stand-in plant: slew the twist at the configured accel limits.
                let dt_ms = TEL_PERIOD_MS as i32;
                v = slew(v, target_v, cfg.max_a_mm_s2 as i32 * dt_ms / 1000);
                w = slew(w, target_w, cfg.max_aw_mrad_s2 as i32 * dt_ms / 1000);
                let half_track_w = (w as f32 * cfg.wheelbase_mm / 2000.0) as i32; // mrad/s * mm -> mm/s
                led.set_level(if v != 0 || w != 0 { Level::High } else { Level::Low });

                let s = State {
                    speed_l_mm_s: (v - half_track_w) as i16,
                    speed_r_mm_s: (v + half_track_w) as i16,
                    accel_z_mg: 1000,
                    fault_flags: faults,
                    range_mm: 0,
                    range_status: range_status::NOT_READY,
                    cmd_seq_last_applied: link.cmd_seq_last,
                    t_cmd_applied_us,
                    ..Default::default()
                };
                if let Some(n) = link.state_frame(&s, now_us(), &mut out) {
                    let _ = tx.write_all(&out[..n]).await;
                }
            }
        }
    }
}
