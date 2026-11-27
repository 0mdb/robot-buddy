//! Control (100 Hz) + safety (50 Hz) together against a simple track model, as the firmware
//! wires them (`firmware/reflex-g431/src/main.rs`). Plant per track: first-order lag (tau 80 ms)
//! to a steady speed of (|duty| - 60) mm/s per duty unit above a 60-duty deadband, which is what
//! the default gains assume (kV = 1 duty per mm/s, min_pwm = 80). Checks system behaviour, not
//! tuning: the gains are still the ESP32 placeholders.

use reflex_core::config::Config;
use reflex_core::control::{self, Controller};
use reflex_core::protocol::{fault, range_status};
use reflex_core::safety::{self, MotorAction, RangeSample, Safety};

const DT_US: u32 = 10_000;

#[derive(Default)]
struct Track {
    v: f32,
    pos: f32,
    jammed: bool,
}

impl Track {
    fn step(&mut self, duty: f32, dt: f32) {
        let mag = (duty.abs() - 60.0).max(0.0) * duty.signum();
        let target = if self.jammed { 0.0 } else { mag };
        self.v += (target - self.v) * (dt / 0.08);
        if self.jammed {
            self.v = 0.0;
        }
        self.pos += self.v * dt;
    }
}

struct Sim {
    cfg: Config,
    ctl: Controller,
    safety: Safety,
    l: Track,
    r: Track,
    t_us: u32,
    enabled: bool,
    out: control::Output,
    /// Distance from the front sonar to a wall, mm (None = nothing in range).
    wall_mm: Option<f32>,
    last_cmd_us: Option<u32>,
}

impl Sim {
    fn new() -> Self {
        Self {
            cfg: Config::DEFAULTS,
            ctl: Controller::new(),
            safety: Safety::new(),
            l: Track::default(),
            r: Track::default(),
            t_us: 0,
            enabled: true,
            out: control::Output::default(),
            wall_mm: None,
            last_cmd_us: None,
        }
    }

    fn range(&self) -> RangeSample {
        match self.wall_mm {
            Some(d) if d < 4000.0 => RangeSample { mm: d.max(0.0) as u16, status: range_status::OK },
            _ => RangeSample { mm: 0, status: range_status::TIMEOUT },
        }
    }

    /// Run for `ms`, commanding (v, w) when `cmd` is Some (refreshing the command timestamp).
    fn run(&mut self, ms: u32, cmd: Option<(f32, f32)>) {
        let (v, w) = cmd.unwrap_or((0.0, 0.0));
        for _ in 0..ms * 1000 / DT_US {
            self.t_us = self.t_us.wrapping_add(DT_US);
            if cmd.is_some() {
                self.last_cmd_us = Some(self.t_us);
            }
            let dt = DT_US as f32 / 1e6;
            let i = control::Input {
                dt_s: dt,
                v_meas_l: self.l.v,
                v_meas_r: self.r.v,
                v_cmd_mm_s: v,
                w_cmd_mrad_s: w,
                gyro_z_rad_s: (self.r.v - self.l.v) / self.cfg.wheelbase_mm,
                faults: self.safety.faults(),
                rear_blocked: false,
            };
            self.out = self.ctl.step(&self.cfg, &i);
            if self.t_us % 20_000 == 0 {
                let si = safety::Inputs {
                    now_us: self.t_us,
                    last_cmd_us: self.last_cmd_us,
                    accel_g: Some([0.0, 0.0, 1.0]),
                    speed_l: self.l.v,
                    speed_r: self.r.v,
                    target_l: self.out.target_l,
                    target_r: self.out.target_r,
                    range: self.range(),
                    pos_l_mm: self.l.pos,
                    pos_r_mm: self.r.pos,
                    estop_ok: true,
                };
                match self.safety.step(&self.cfg, &si) {
                    MotorAction::HardKill => self.enabled = false,
                    MotorAction::Enable => self.enabled = true,
                    _ => {}
                }
            }
            let (ul, ur) = if self.enabled { (self.out.u_l, self.out.u_r) } else { (0.0, 0.0) };
            let before = (self.l.pos + self.r.pos) / 2.0;
            self.l.step(ul, dt);
            self.r.step(ur, dt);
            if let Some(d) = self.wall_mm.as_mut() {
                *d -= (self.l.pos + self.r.pos) / 2.0 - before;
            }
        }
    }
}

#[test]
fn tracks_speed_command() {
    let mut s = Sim::new();
    s.run(1500, Some((300.0, 0.0)));
    assert_eq!(s.safety.faults(), 0);
    assert!((s.l.v - 300.0).abs() < 15.0 && (s.r.v - 300.0).abs() < 15.0, "L {} R {}", s.l.v, s.r.v);
}

#[test]
fn turns_in_place() {
    let mut s = Sim::new();
    s.run(1500, Some((0.0, 1000.0)));
    assert_eq!(s.safety.faults(), 0);
    // 1 rad/s * 75 mm = 75 mm/s per track, opposite signs.
    assert!((s.r.v - 75.0).abs() < 10.0 && (s.l.v + 75.0).abs() < 10.0, "L {} R {}", s.l.v, s.r.v);
}

#[test]
fn jammed_track_stalls_and_hard_stops() {
    let mut s = Sim::new();
    s.run(500, Some((200.0, 0.0)));
    s.l.jammed = true;
    s.r.jammed = true;
    s.run(1000, Some((200.0, 0.0)));
    assert_ne!(s.safety.faults() & fault::STALL, 0);
    assert!(!s.enabled);
}

#[test]
fn stops_at_wall_then_escapes_backwards() {
    let mut s = Sim::new();
    s.wall_mm = Some(800.0);
    s.run(4000, Some((200.0, 0.0)));
    assert_eq!(s.safety.faults(), fault::OBSTACLE);
    let d = s.wall_mm.unwrap();
    // Stopped short of the wall: latched below 250 mm, minus the stopping distance.
    assert!(d > 150.0 && d < 250.0, "stopped at {d} mm");
    assert!(s.l.v.abs() < 1.0, "still moving {}", s.l.v);
    // Forward is still blocked.
    s.run(1000, Some((200.0, 0.0)));
    assert!(s.wall_mm.unwrap() >= d - 1.0);
    // Reverse escape: capped at range_escape_max_mm_s, releases past range_release_mm.
    s.run(500, Some((-300.0, 0.0)));
    // The cap is on the target (as on the ESP32); the PI loop overshoots it a little.
    assert!(s.l.v >= -(s.cfg.range_escape_max_mm_s as f32) * 1.1, "escape speed {}", s.l.v);
    s.run(3000, Some((-300.0, 0.0)));
    assert_eq!(s.safety.faults(), 0, "released once past {} mm", s.cfg.range_release_mm);
    assert!(s.wall_mm.unwrap() > s.cfg.range_release_mm as f32);
}

#[test]
fn command_loss_stops_the_robot() {
    let mut s = Sim::new();
    s.run(1000, Some((300.0, 0.0)));
    s.run(1500, None);
    assert_eq!(s.safety.faults(), fault::CMD_TIMEOUT);
    assert!(s.l.v.abs() < 1.0 && s.r.v.abs() < 1.0);
}
