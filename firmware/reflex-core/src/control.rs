//! Speed control, ported from `esp32-reflex/main/control.cpp`: twist -> per-track targets,
//! obstacle escape, per-track rate limit, gyro yaw damping, feedforward + PI with anti-windup,
//! deadband compensation, fault gate. Output is a signed duty in the ESP32's 10-bit units
//! (`Config::max_pwm`, default 1023), so gains tuned on the ESP32 carry over; the motor layer
//! scales it to its own timer.
//!
//! Deliberate changes from the ESP32 (minor bugs):
//! - `max_w_mrad_s` is applied to the commanded turn rate. The ESP32 accepted it over SET_CONFIG
//!   and never used it, so a large `w` was limited only by the per-track speed clamp.
//! - The anti-windup back-calculation guards `Ki == 0` by skipping (the ESP32 divided by 1.0
//!   instead, bleeding an integrator that does not contribute).

use crate::config::Config;
use crate::kinematics::twist_to_wheels;
use crate::protocol::fault;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
struct WheelPi {
    integral: f32,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Input {
    /// Seconds since the last step (the ESP32 measured it; nominal 1 / control_hz).
    pub dt_s: f32,
    /// Measured track speeds from the encoders, mm/s.
    pub v_meas_l: f32,
    pub v_meas_r: f32,
    /// Latest command.
    pub v_cmd_mm_s: f32,
    pub w_cmd_mrad_s: f32,
    /// Gyro yaw rate, rad/s.
    pub gyro_z_rad_s: f32,
    /// Active fault flags.
    pub faults: u16,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Output {
    /// Signed duty, + forward, in `Config::max_pwm` units.
    pub u_l: f32,
    pub u_r: f32,
    /// Rate-limited track targets after yaw damping, mm/s (for stall detection and logging).
    pub target_l: f32,
    pub target_r: f32,
    /// True when the obstacle escape (reverse-only, capped) is active.
    pub escape: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Controller {
    pi_l: WheelPi,
    pi_r: WheelPi,
    rl_l: f32,
    rl_r: f32,
}

fn rate_limit(current: f32, setpoint: f32, max_accel: f32, dt: f32) -> f32 {
    let max_delta = max_accel * dt;
    current + (setpoint - current).clamp(-max_delta, max_delta)
}

fn ff_pi(cfg: &Config, st: &mut WheelPi, v_target: f32, v_meas: f32, dt: f32) -> f32 {
    let mut ff = cfg.k_v * v_target;
    if v_target != 0.0 {
        ff += if v_target > 0.0 { cfg.k_s } else { -cfg.k_s };
    }
    let error = v_target - v_meas;
    st.integral += error * dt;
    let u = ff + cfg.k_p * error + cfg.k_i * st.integral;
    let max_u = cfg.max_pwm as f32;
    let u_clamped = u.clamp(-max_u, max_u);
    if u != u_clamped && cfg.k_i > 0.0 {
        // Back-calculate: remove half the excess from the integrator.
        st.integral -= (u - u_clamped) / cfg.k_i * 0.5;
    }
    u_clamped
}

fn deadband_comp(cfg: &Config, u: f32, v_target: f32) -> f32 {
    if v_target == 0.0 {
        return u;
    }
    let min = cfg.min_pwm as f32;
    let u = if u > 0.0 {
        u + min
    } else if u < 0.0 {
        u - min
    } else if v_target > 0.0 {
        min // PI output exactly zero with a non-zero target: kick-start
    } else {
        -min
    };
    let max_u = cfg.max_pwm as f32;
    u.clamp(-max_u, max_u)
}

impl Controller {
    pub const fn new() -> Self {
        Self { pi_l: WheelPi { integral: 0.0 }, pi_r: WheelPi { integral: 0.0 }, rl_l: 0.0, rl_r: 0.0 }
    }

    pub fn reset(&mut self) {
        *self = Self::new();
    }

    pub fn step(&mut self, cfg: &Config, i: &Input) -> Output {
        let dt = i.dt_s;
        let max_w = cfg.max_w_mrad_s as f32;
        let w_cmd_mrad = i.w_cmd_mrad_s.clamp(-max_w, max_w);
        let w_cmd = w_cmd_mrad / 1000.0;

        // 3. Twist -> per-track targets, clamped to max speed.
        let (tl, tr) = twist_to_wheels(cfg, i.v_cmd_mm_s, w_cmd_mrad);
        let max_v = cfg.max_v_mm_s as f32;
        let (mut tl, mut tr) = (tl.clamp(-max_v, max_v), tr.clamp(-max_v, max_v));

        // 3b. Obstacle escape: with OBSTACLE the only fault, a command reversing *both* tracks
        // may run, capped. Forward motion and spinning in place stay blocked.
        let escape = i.faults == fault::OBSTACLE && tl < 0.0 && tr < 0.0;
        if escape {
            let cap = cfg.range_escape_max_mm_s as f32;
            tl = tl.clamp(-cap, 0.0);
            tr = tr.clamp(-cap, 0.0);
            // Never carry forward motion into an escape.
            self.rl_l = self.rl_l.min(0.0);
            self.rl_r = self.rl_r.min(0.0);
        }

        // 4. Rate limit.
        let max_a = cfg.max_a_mm_s2 as f32;
        self.rl_l = rate_limit(self.rl_l, tl, max_a, dt);
        self.rl_r = rate_limit(self.rl_r, tr, max_a, dt);

        // 5. Yaw damping.
        let delta_v = cfg.k_yaw * (w_cmd - i.gyro_z_rad_s);
        let rl_l = self.rl_l - delta_v;
        let rl_r = self.rl_r + delta_v;

        // 6-7. FF + PI, deadband.
        let mut u_l = deadband_comp(cfg, ff_pi(cfg, &mut self.pi_l, rl_l, i.v_meas_l, dt), rl_l);
        let mut u_r = deadband_comp(cfg, ff_pi(cfg, &mut self.pi_r, rl_r, i.v_meas_r, dt), rl_r);

        // 8. Fault gate. Any fault zeroes the output at once (the safety state machine decides
        // brake vs. coast); an escape may only drive backwards.
        if escape {
            u_l = u_l.min(0.0);
            u_r = u_r.min(0.0);
        } else if i.faults != 0 {
            u_l = 0.0;
            u_r = 0.0;
            self.reset();
        }
        Output { u_l, u_r, target_l: rl_l, target_r: rl_r, escape }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const DT: f32 = 0.01;

    fn cfg() -> Config {
        Config::DEFAULTS
    }

    fn run(c: &mut Controller, cfg: &Config, i: Input, n: usize) -> Output {
        let mut o = Output::default();
        for _ in 0..n {
            o = c.step(cfg, &i);
        }
        o
    }

    #[test]
    fn rate_limited_ramp() {
        let cfg = cfg();
        let mut c = Controller::new();
        let i = Input { dt_s: DT, v_cmd_mm_s: 400.0, ..Default::default() };
        // 1000 mm/s^2 * 10 ms = 10 mm/s per step.
        let o = c.step(&cfg, &i);
        assert!((o.target_l - 10.0).abs() < 1e-3 && (o.target_r - 10.0).abs() < 1e-3);
        let o = run(&mut c, &cfg, i, 9);
        assert!((o.target_l - 100.0).abs() < 1e-2);
        let o = run(&mut c, &cfg, i, 100);
        assert!((o.target_l - 400.0).abs() < 1e-2);
    }

    #[test]
    fn feedforward_and_deadband_signs() {
        let cfg = cfg();
        let mut c = Controller::new();
        // Steady state at target: measured = target, integral small -> u ~ kV*v + min_pwm.
        let i = Input { dt_s: DT, v_cmd_mm_s: -200.0, v_meas_l: -200.0, v_meas_r: -200.0, ..Default::default() };
        let o = run(&mut c, &cfg, i, 50);
        assert!(o.u_l < -(cfg.min_pwm as f32) && o.u_r < 0.0, "{o:?}");
        // Zero command: no deadband kick.
        let mut c = Controller::new();
        let o = c.step(&cfg, &Input { dt_s: DT, ..Default::default() });
        assert_eq!((o.u_l, o.u_r), (0.0, 0.0));
    }

    #[test]
    fn output_saturates_and_integrator_bleeds() {
        let cfg = cfg();
        let mut c = Controller::new();
        // Stalled wheel at full command: output pinned at max_pwm, integrator bounded.
        let i = Input { dt_s: DT, v_cmd_mm_s: 500.0, ..Default::default() };
        let o = run(&mut c, &cfg, i, 500);
        assert_eq!(o.u_l, cfg.max_pwm as f32);
        assert!(c.pi_l.integral.abs() < 2000.0, "integral {}", c.pi_l.integral);
    }

    #[test]
    fn any_fault_zeroes_and_resets() {
        let cfg = cfg();
        let mut c = Controller::new();
        run(&mut c, &cfg, Input { dt_s: DT, v_cmd_mm_s: 300.0, ..Default::default() }, 20);
        let o = c.step(&cfg, &Input { dt_s: DT, v_cmd_mm_s: 300.0, faults: fault::CMD_TIMEOUT, ..Default::default() });
        assert_eq!((o.u_l, o.u_r), (0.0, 0.0));
        assert_eq!(c, Controller::new());
    }

    #[test]
    fn obstacle_escape_reverse_only_capped() {
        let cfg = cfg();
        let mut c = Controller::new();
        // Forward with OBSTACLE: blocked.
        let f = Input { dt_s: DT, v_cmd_mm_s: 200.0, faults: fault::OBSTACLE, ..Default::default() };
        let o = c.step(&cfg, &f);
        assert!(!o.escape && o.u_l == 0.0);
        // Spin in place with OBSTACLE: blocked (one track forward).
        let s = Input { w_cmd_mrad_s: 1000.0, v_cmd_mm_s: 0.0, ..f };
        assert!(!c.step(&cfg, &s).escape);
        // Straight back: escape, capped at range_escape_max_mm_s, never positive.
        let b = Input { v_cmd_mm_s: -400.0, ..f };
        let o = run(&mut c, &cfg, b, 200);
        assert!(o.escape);
        assert!((o.target_l + cfg.range_escape_max_mm_s as f32).abs() < 1.0, "{o:?}");
        assert!(o.u_l <= 0.0 && o.u_r <= 0.0);
        // OBSTACLE plus another fault: no escape.
        let o = c.step(&cfg, &Input { faults: fault::OBSTACLE | fault::TILT, ..b });
        assert!(!o.escape && o.u_l == 0.0);
    }

    #[test]
    fn escape_never_carries_forward_ramp() {
        let cfg = cfg();
        let mut c = Controller::new();
        run(&mut c, &cfg, Input { dt_s: DT, v_cmd_mm_s: 300.0, ..Default::default() }, 50);
        let o = c.step(&cfg, &Input { dt_s: DT, v_cmd_mm_s: -100.0, faults: fault::OBSTACLE, ..Default::default() });
        assert!(o.escape && o.target_l <= 0.0, "{o:?}");
    }

    #[test]
    fn yaw_damping_steers_toward_command() {
        let cfg = cfg();
        let mut c = Controller::new();
        // Commanded straight, gyro says turning left (+): right track slowed, left sped up.
        let o = c.step(&cfg, &Input { dt_s: DT, v_cmd_mm_s: 0.0, gyro_z_rad_s: 1.0, ..Default::default() });
        assert!(o.target_l > 0.0 && o.target_r < 0.0, "{o:?}");
    }

    #[test]
    fn max_w_is_applied() {
        let mut cfg = cfg();
        cfg.max_w_mrad_s = 100;
        let mut c = Controller::new();
        let i = Input { dt_s: DT, w_cmd_mrad_s: 2000.0, ..Default::default() };
        let o = run(&mut c, &cfg, i, 200);
        // 0.1 rad/s * 75 mm = 7.5 mm/s per track (yaw damping adds K_yaw * (0.1 - 0)).
        assert!((o.target_r - (7.5 + cfg.k_yaw * 0.1)).abs() < 0.01, "{o:?}");
    }
}
