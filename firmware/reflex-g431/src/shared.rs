//! State shared between tasks (the ESP32's `shared_state.h` seqlocks and atomics), behind one
//! critical-section mutex. Every access is short: copy in, copy out.

use core::cell::RefCell;

use embassy_sync::blocking_mutex::Mutex;
use embassy_sync::blocking_mutex::raw::CriticalSectionRawMutex;
use embassy_time::Instant;
use reflex_core::config::Config;
use reflex_core::imu::ImuSample;
use reflex_core::protocol::range_status;
use reflex_core::safety::{MotorAction, RangeSample, RearGuard, Safety};

/// Latest command (`g_cmd`).
#[derive(Clone, Copy, Default)]
pub struct Cmd {
    pub v_mm_s: i16,
    pub w_mrad_s: i16,
    pub seq: u32,
}

pub struct Shared {
    pub cfg: Config,
    pub safety: Safety,
    pub cmd: Cmd,
    /// When the last reflex command arrived (`g_cmd.last_cmd_us`), None before the first.
    pub last_cmd_us: Option<u32>,
    /// Seq of the last reflex command received (`g_cmd_seq_last`).
    pub cmd_seq_last: u32,
    /// Motor action from the safety task, applied by the control task (which owns the motors).
    pub pending_action: MotorAction,
    // Written by the control task.
    pub speed_l: f32,
    pub speed_r: f32,
    pub target_l: f32,
    pub target_r: f32,
    pub pos_l_mm: f32,
    pub pos_r_mm: f32,
    pub imu: Option<ImuSample>,
    pub cmd_seq_applied: u32,
    pub t_cmd_applied_us: u32,
    // Written by the sonar task.
    pub range_front: RangeSample,
    pub range_rear: RangeSample,
    pub rear: RearGuard,
}

impl Shared {
    const fn new() -> Self {
        Self {
            cfg: Config::DEFAULTS,
            safety: Safety::new(),
            cmd: Cmd { v_mm_s: 0, w_mrad_s: 0, seq: 0 },
            last_cmd_us: None,
            cmd_seq_last: 0,
            pending_action: MotorAction::None,
            speed_l: 0.0,
            speed_r: 0.0,
            target_l: 0.0,
            target_r: 0.0,
            pos_l_mm: 0.0,
            pos_r_mm: 0.0,
            imu: None,
            cmd_seq_applied: 0,
            t_cmd_applied_us: 0,
            range_front: RangeSample { mm: 0, status: range_status::NOT_READY },
            range_rear: RangeSample { mm: 0, status: range_status::NOT_READY },
            rear: RearGuard::new(),
        }
    }
}

pub static SHARED: Mutex<CriticalSectionRawMutex, RefCell<Shared>> = Mutex::new(RefCell::new(Shared::new()));

pub fn with<R>(f: impl FnOnce(&mut Shared) -> R) -> R {
    SHARED.lock(|s| f(&mut s.borrow_mut()))
}

/// Monotonic µs as u32, wrapping (the ESP32's `esp_timer_get_time()` truncated).
pub fn now_us() -> u32 {
    Instant::now().as_micros() as u32
}

/// Merge a new motor action with one not yet applied: a hard kill is never downgraded.
pub fn post_action(s: &mut Shared, a: MotorAction) {
    s.pending_action = match (s.pending_action, a) {
        (_, MotorAction::None) => s.pending_action,
        (MotorAction::HardKill, MotorAction::Brake) => MotorAction::HardKill,
        (_, a) => a,
    };
}
