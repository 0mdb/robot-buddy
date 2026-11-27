//! Safety state machine, ported from `esp32-reflex/main/safety.cpp` (50 Hz): command timeout,
//! e-stop, tilt, stall, obstacle latch with hysteresis and blind release, stop state, recovery.
//! Owns the fault flags. Returns what the motor layer must do; it never touches hardware.
//!
//! Deliberate changes from the ESP32 (minor bugs):
//! - **Stall** compares the control loop's per-track targets with the measured speeds. The
//!   ESP32 looked only at `|v_cmd|`, so a stalled spin in place (v = 0, w != 0) never tripped.
//! - **CLEAR_FAULTS with OBSTACLE** also drops the obstacle latch, so the next tick re-checks
//!   the range. On the ESP32 a clear during the stop ramp left the latch set and the flag clear:
//!   the robot could drive at the wall until the ramp ended.
//! - **Physical e-stop**: the e-stop line (ESTOP_N, also TIM1 BKIN in hardware) raises ESTOP.
//!   The ESP32 cut the driver in hardware but never reported it.
//! - Honest comment: "soft stop" does not ramp the motors. Any fault zeroes the control output
//!   at once (control.rs fault gate); the ramp state only times when the bridge is braked.

use crate::config::Config;
use crate::protocol::{fault, range_status};

/// Latest ultrasonic sample.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub struct RangeSample {
    pub mm: u16,
    pub status: u8,
}

impl Default for RangeSample {
    fn default() -> Self {
        Self { mm: 0, status: range_status::NOT_READY }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Inputs {
    /// Monotonic µs, wrapping (as `esp_timer_get_time()` truncated to u32).
    pub now_us: u32,
    /// When the last reflex command arrived; None before the first.
    pub last_cmd_us: Option<u32>,
    /// Accelerometer, g. None when the IMU has no valid sample (no tilt check).
    pub accel_g: Option<[f32; 3]>,
    /// Measured track speeds, mm/s.
    pub speed_l: f32,
    pub speed_r: f32,
    /// Control loop's rate-limited track targets, mm/s.
    pub target_l: f32,
    pub target_r: f32,
    pub range: RangeSample,
    /// Odometry: distance travelled per track since boot, mm.
    pub pos_l_mm: f32,
    pub pos_r_mm: f32,
    /// E-stop loop closed (ESTOP_N high).
    pub estop_ok: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub enum StopState {
    Running,
    RampingDown { since_us: u32 },
    Stopped,
}

/// What the motor layer must do after a safety step.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "defmt", derive(defmt::Format))]
pub enum MotorAction {
    None,
    /// Duty 0, bridge braked, stay enabled (end of a soft stop).
    Brake,
    /// Duty 0, braked, disabled until all faults clear (ESTOP, TILT, STALL).
    HardKill,
    /// All faults cleared after a stop: re-enable.
    Enable,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct ObstacleLatch {
    pos_l_mm: f32,
    pos_r_mm: f32,
    blind_since_us: Option<u32>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Safety {
    faults: u16,
    state: StopState,
    tilt_since_us: Option<u32>,
    stall_since_us: Option<u32>,
    obstacle: Option<ObstacleLatch>,
}

impl Default for Safety {
    fn default() -> Self {
        Self::new()
    }
}

fn elapsed_ms(from_us: u32, to_us: u32) -> u32 {
    to_us.wrapping_sub(from_us) / 1000
}

impl Safety {
    pub const fn new() -> Self {
        Self { faults: 0, state: StopState::Running, tilt_since_us: None, stall_since_us: None, obstacle: None }
    }

    pub fn faults(&self) -> u16 {
        self.faults
    }

    pub fn state(&self) -> StopState {
        self.state
    }

    /// Host ESTOP command.
    pub fn estop(&mut self) {
        self.faults |= fault::ESTOP;
    }

    /// Faults raised by drivers (IMU_FAIL, MOTOR_DRV, BROWNOUT).
    pub fn raise(&mut self, bits: u16) {
        self.faults |= bits;
    }

    /// Host CLEAR_FAULTS. Conditions still present re-raise on the next step.
    pub fn clear(&mut self, mask: u16) {
        self.faults &= !mask;
        if mask & fault::OBSTACLE != 0 {
            self.obstacle = None;
        }
    }

    fn hard_stop(&mut self) -> MotorAction {
        self.state = StopState::Stopped;
        MotorAction::HardKill
    }

    fn begin_soft_stop(&mut self, now_us: u32) {
        if self.state == StopState::Running {
            self.state = StopState::RampingDown { since_us: now_us };
        }
    }

    /// One 50 Hz safety tick. Returns the strongest motor action this tick asked for.
    pub fn step(&mut self, cfg: &Config, i: &Inputs) -> MotorAction {
        let mut action = MotorAction::None;
        let now = i.now_us;

        // Command timeout (only once a command has been seen).
        if let Some(last) = i.last_cmd_us {
            if elapsed_ms(last, now) > cfg.cmd_timeout_ms && self.faults & fault::CMD_TIMEOUT == 0 {
                self.faults |= fault::CMD_TIMEOUT;
                self.begin_soft_stop(now);
            }
        }

        // E-stop: the loop opened, or the host sent ESTOP.
        if !i.estop_ok {
            self.faults |= fault::ESTOP;
        }
        if self.faults & fault::ESTOP != 0 && self.state != StopState::Stopped {
            action = self.hard_stop();
        }

        // Tilt from the gravity vector, held for tilt_hold_ms.
        if let Some([ax, ay, az]) = i.accel_g {
            let mag = libm::sqrtf(ax * ax + ay * ay + az * az);
            if mag >= 0.1 {
                let tilt_deg = libm::acosf((libm::fabsf(az) / mag).min(1.0)).to_degrees();
                if tilt_deg > cfg.tilt_thresh_deg {
                    match self.tilt_since_us {
                        None => self.tilt_since_us = Some(now),
                        Some(t) if elapsed_ms(t, now) > cfg.tilt_hold_ms && self.faults & fault::TILT == 0 => {
                            self.faults |= fault::TILT;
                            action = self.hard_stop();
                        }
                        _ => {}
                    }
                } else {
                    self.tilt_since_us = None;
                }
            }
        }

        // Stall: tracks asked to move, not moving.
        let thr = cfg.stall_speed_thresh as f32;
        let target = libm::fabsf(i.target_l).max(libm::fabsf(i.target_r));
        let meas = (libm::fabsf(i.speed_l) + libm::fabsf(i.speed_r)) / 2.0;
        if target > thr * 2.0 && meas < thr {
            match self.stall_since_us {
                None => self.stall_since_us = Some(now),
                Some(t) if elapsed_ms(t, now) > cfg.stall_thresh_ms && self.faults & fault::STALL == 0 => {
                    self.faults |= fault::STALL;
                    action = self.hard_stop();
                }
                _ => {}
            }
        } else {
            self.stall_since_us = None;
        }

        self.check_obstacle(cfg, i);

        // End of a soft stop: brake.
        if let StopState::RampingDown { since_us } = self.state {
            if elapsed_ms(since_us, now) >= cfg.soft_stop_ramp_ms {
                self.state = StopState::Stopped;
                if action == MotorAction::None {
                    action = MotorAction::Brake;
                }
            }
        }

        // Recovery: everything clear after a stop.
        if self.faults == 0 && self.state == StopState::Stopped {
            self.state = StopState::Running;
            self.tilt_since_us = None;
            self.stall_since_us = None;
            self.obstacle = None;
            action = MotorAction::Enable;
        }
        action
    }

    fn check_obstacle(&mut self, cfg: &Config, i: &Inputs) {
        let r = i.range;
        let Some(latch) = self.obstacle.as_mut() else {
            if r.status == range_status::OK && r.mm < cfg.range_stop_mm {
                self.obstacle = Some(ObstacleLatch { pos_l_mm: i.pos_l_mm, pos_r_mm: i.pos_r_mm, blind_since_us: None });
                if self.faults & fault::OBSTACLE == 0 {
                    self.faults |= fault::OBSTACLE;
                    self.begin_soft_stop(i.now_us);
                }
            }
            return;
        };
        // Latched: release when far enough (hysteresis)...
        if r.status == range_status::OK {
            latch.blind_since_us = None;
            if r.mm > cfg.range_release_mm {
                self.release_obstacle();
            }
            return;
        }
        // ...or when blind (grazing-angle wall: TIMEOUT, never > release) *and* backed off.
        if r.status != range_status::TIMEOUT {
            latch.blind_since_us = None;
            return;
        }
        let since = *latch.blind_since_us.get_or_insert(i.now_us);
        let moved_mm = 0.5 * ((i.pos_l_mm - latch.pos_l_mm) + (i.pos_r_mm - latch.pos_r_mm));
        if elapsed_ms(since, i.now_us) >= cfg.range_blind_release_ms as u32
            && moved_mm <= -(cfg.range_blind_release_mm as f32)
        {
            self.release_obstacle();
        }
    }

    fn release_obstacle(&mut self) {
        self.obstacle = None;
        self.faults &= !fault::OBSTACLE;
    }
}

/// HC-SR04 echo pulse -> sample (`range_ultrasonic.cpp`): 5.83 µs per mm round trip;
/// no echo = TIMEOUT; an echo at or beyond the timeout = OUT_OF_RANGE.
pub fn range_from_echo(echo_us: Option<u32>, timeout_us: u32) -> RangeSample {
    match echo_us {
        None | Some(0) => RangeSample { mm: 0, status: range_status::TIMEOUT },
        Some(us) => {
            let mm = (us as f32 / 5.83).min(u16::MAX as f32) as u16;
            let status = if us >= timeout_us { range_status::OUT_OF_RANGE } else { range_status::OK };
            RangeSample { mm, status }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TICK: u32 = 20_000; // 50 Hz

    fn base(now_us: u32) -> Inputs {
        Inputs {
            now_us,
            accel_g: Some([0.0, 0.0, 1.0]),
            range: RangeSample { mm: 1000, status: range_status::OK },
            estop_ok: true,
            ..Default::default()
        }
    }

    /// Run ticks from `t0` for `ms`, with `f` adjusting each tick's inputs. Returns all actions.
    fn run(s: &mut Safety, cfg: &Config, t0: u32, ms: u32, f: impl Fn(&mut Inputs)) -> std::vec::Vec<MotorAction> {
        let mut out = std::vec::Vec::new();
        for k in 0..ms * 1000 / TICK {
            let mut i = base(t0.wrapping_add(k * TICK));
            f(&mut i);
            out.push(s.step(cfg, &i));
        }
        out
    }

    #[test]
    fn cmd_timeout_soft_stop_then_brake_then_recover() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        // No command yet: no timeout ever.
        run(&mut s, &cfg, 0, 2000, |_| {});
        assert_eq!(s.faults(), 0);
        let acts = run(&mut s, &cfg, 0, 1000, |i| i.last_cmd_us = Some(0));
        assert_eq!(s.faults(), fault::CMD_TIMEOUT);
        assert!(acts.contains(&MotorAction::Brake) && !acts.contains(&MotorAction::HardKill));
        assert_eq!(s.state(), StopState::Stopped);
        s.clear(0xFFFF);
        // Fresh command: recovers and re-enables.
        let acts = run(&mut s, &cfg, 2_000_000, 40, |i| i.last_cmd_us = Some(2_000_000));
        assert_eq!(acts[0], MotorAction::Enable);
        assert_eq!(s.state(), StopState::Running);
    }

    #[test]
    fn estop_command_and_line() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        s.estop();
        assert_eq!(s.step(&cfg, &base(0)), MotorAction::HardKill);
        assert_eq!(s.step(&cfg, &base(TICK)), MotorAction::None); // already stopped
        s.clear(fault::ESTOP);
        assert_eq!(s.step(&cfg, &base(2 * TICK)), MotorAction::Enable);
        // The physical loop opening raises ESTOP; clearing while still open re-raises it.
        let open = Inputs { estop_ok: false, ..base(3 * TICK) };
        assert_eq!(s.step(&cfg, &open), MotorAction::HardKill);
        s.clear(0xFFFF);
        s.step(&cfg, &open);
        assert_eq!(s.faults() & fault::ESTOP, fault::ESTOP);
    }

    #[test]
    fn tilt_needs_hold_time() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        let tilted = |i: &mut Inputs| i.accel_g = Some([0.8, 0.0, 0.5]); // ~58 deg
        run(&mut s, &cfg, 0, 200, tilted);
        assert_eq!(s.faults(), 0, "within tilt_hold_ms");
        let acts = run(&mut s, &cfg, 200_000, 100, tilted);
        assert_eq!(s.faults(), fault::TILT);
        assert!(acts.contains(&MotorAction::HardKill));
        // A brief tilt that recovers never latches.
        let mut s = Safety::new();
        run(&mut s, &cfg, 0, 100, tilted);
        run(&mut s, &cfg, 100_000, 20, |_| {});
        run(&mut s, &cfg, 120_000, 100, tilted);
        assert_eq!(s.faults(), 0);
        // No IMU sample: no tilt check.
        let mut s = Safety::new();
        run(&mut s, &cfg, 0, 1000, |i| i.accel_g = None);
        assert_eq!(s.faults(), 0);
    }

    #[test]
    fn stall_includes_spin_in_place() {
        let cfg = Config::DEFAULTS;
        for (tl, tr) in [(200.0, 200.0), (-75.0, 75.0)] {
            let mut s = Safety::new();
            let acts = run(&mut s, &cfg, 0, 700, |i| {
                i.target_l = tl;
                i.target_r = tr;
            });
            assert_eq!(s.faults(), fault::STALL, "targets {tl} {tr}");
            assert!(acts.contains(&MotorAction::HardKill));
        }
        // Moving as asked: no stall.
        let mut s = Safety::new();
        run(&mut s, &cfg, 0, 2000, |i| {
            i.target_l = 200.0;
            i.target_r = 200.0;
            i.speed_l = 190.0;
            i.speed_r = 195.0;
        });
        assert_eq!(s.faults(), 0);
    }

    #[test]
    fn obstacle_hysteresis() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        let at = |mm| move |i: &mut Inputs| i.range = RangeSample { mm, status: range_status::OK };
        run(&mut s, &cfg, 0, 40, at(200));
        assert_eq!(s.faults(), fault::OBSTACLE);
        run(&mut s, &cfg, 40_000, 200, at(300)); // between stop (250) and release (350)
        assert_eq!(s.faults(), fault::OBSTACLE);
        run(&mut s, &cfg, 240_000, 40, at(400));
        assert_eq!(s.faults(), 0);
    }

    #[test]
    fn obstacle_blind_release_needs_backing_off() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        let mut i = base(0);
        i.range = RangeSample { mm: 200, status: range_status::OK };
        s.step(&cfg, &i);
        assert_eq!(s.faults(), fault::OBSTACLE);
        let blind = |pos: f32| move |i: &mut Inputs| {
            i.range = RangeSample { mm: 0, status: range_status::TIMEOUT };
            i.pos_l_mm = pos;
            i.pos_r_mm = pos;
        };
        run(&mut s, &cfg, TICK, 2000, blind(0.0)); // blind but not moved
        assert_eq!(s.faults(), fault::OBSTACLE);
        run(&mut s, &cfg, 3_000_000, 1100, blind(-120.0)); // reversed 120 mm, blind > 1 s
        assert_eq!(s.faults(), 0);
    }

    #[test]
    fn clear_obstacle_rechecks_at_once() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        let close = |i: &mut Inputs| i.range = RangeSample { mm: 200, status: range_status::OK };
        run(&mut s, &cfg, 0, 100, close); // latched, ramping
        s.clear(fault::OBSTACLE);
        assert_eq!(s.faults(), 0);
        run(&mut s, &cfg, 100_000, 20, close);
        assert_eq!(s.faults(), fault::OBSTACLE, "still close: re-latched on the next tick");
    }

    #[test]
    fn timer_wrap() {
        let cfg = Config::DEFAULTS;
        let mut s = Safety::new();
        let t0 = u32::MAX - 100_000;
        run(&mut s, &cfg, t0, 300, |i| i.last_cmd_us = Some(u32::MAX - 100_000));
        assert_eq!(s.faults(), 0, "300 ms across the wrap is not a timeout");
    }

    #[test]
    fn range_conversion() {
        assert_eq!(range_from_echo(None, 25_000).status, range_status::TIMEOUT);
        let r = range_from_echo(Some(5830), 25_000);
        assert_eq!((r.mm, r.status), (1000, range_status::OK));
        assert_eq!(range_from_echo(Some(25_000), 25_000).status, range_status::OUT_OF_RANGE);
    }
}
