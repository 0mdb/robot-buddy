#include "safety.h"
#include "config.h"
#include "motor.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include <cmath>

static const char* TAG = "safety";

// Safety task rate: 50 Hz
static constexpr TickType_t SAFETY_PERIOD = pdMS_TO_TICKS(20);

// ---- Soft stop ramp state ----
// When a soft stop is triggered, we ramp commanded speed to zero over
// soft_stop_ramp_ms, then brake and disable motors.

enum class StopState {
    RUNNING,      // normal operation
    RAMPING_DOWN, // soft stop in progress
    STOPPED,      // motors disabled, waiting for fault clear
};

static StopState s_stop_state = StopState::RUNNING;
static uint32_t  s_ramp_start_us = 0;

// ---- Tilt detection state ----
static uint32_t s_tilt_since_us = 0;
static bool     s_tilt_active = false;

// ---- Stall detection state ----
static uint32_t s_stall_since_us = 0;
static bool     s_stall_active = false;

// ---- Obstacle detection state (hysteresis) ----
static bool s_obstacle_active = false;

// ---- Helpers ----

static uint32_t now_us()
{
    return static_cast<uint32_t>(esp_timer_get_time());
}

static uint32_t elapsed_ms(uint32_t from_us, uint32_t to_us)
{
    return (to_us - from_us) / 1000;
}

static void do_hard_stop()
{
    motor_hard_kill();
    s_stop_state = StopState::STOPPED;
    ESP_LOGW(TAG, "HARD STOP executed");
}

static void begin_soft_stop()
{
    if (s_stop_state == StopState::RUNNING) {
        s_stop_state = StopState::RAMPING_DOWN;
        s_ramp_start_us = now_us();
        ESP_LOGI(TAG, "soft stop: ramping down over %lu ms", (unsigned long)g_cfg.soft_stop_ramp_ms);
    }
}

// ---- Fault checks ----

static void check_cmd_timeout(uint32_t now)
{
    uint32_t last_cmd = g_cmd.last_cmd_us.load(std::memory_order_acquire);

    // If we've never received a command, don't trigger timeout yet
    // (control_task will just drive zero anyway)
    if (last_cmd == 0) return;

    uint32_t age_ms = elapsed_ms(last_cmd, now);
    if (age_ms > g_cfg.cmd_timeout_ms) {
        uint16_t flags = g_fault_flags.load(std::memory_order_relaxed);
        if (!(flags & Fault::CMD_TIMEOUT)) {
            g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::CMD_TIMEOUT), std::memory_order_relaxed);
            ESP_LOGW(TAG, "command timeout (%lu ms)", (unsigned long)age_ms);
            begin_soft_stop();
        }
    }
}

static void check_estop()
{
    uint16_t flags = g_fault_flags.load(std::memory_order_relaxed);
    if (flags & Fault::ESTOP) {
        if (s_stop_state != StopState::STOPPED) {
            ESP_LOGW(TAG, "ESTOP fault active");
            do_hard_stop();
        }
    }
}

static void check_tilt(uint32_t now)
{
    const ImuSample* imu = g_imu.read();

    // Compute tilt angle from gravity vector.
    // When upright, accel_z ≈ 1g. Tilt angle ≈ acos(az / |a|).
    // Simplified: if az < cos(threshold), we're tilted.
    float ax = imu->accel_x_g;
    float ay = imu->accel_y_g;
    float az = imu->accel_z_g;
    float a_mag = std::sqrt(ax * ax + ay * ay + az * az);

    if (a_mag < 0.1f) return; // no valid reading (freefall or IMU dead)

    float cos_tilt = std::fabs(az) / a_mag;
    float tilt_deg = std::acos(cos_tilt) * (180.0f / M_PI);

    if (tilt_deg > g_cfg.tilt_thresh_deg) {
        if (!s_tilt_active) {
            s_tilt_active = true;
            s_tilt_since_us = now;
        } else if (elapsed_ms(s_tilt_since_us, now) > g_cfg.tilt_hold_ms) {
            uint16_t flags = g_fault_flags.load(std::memory_order_relaxed);
            if (!(flags & Fault::TILT)) {
                g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::TILT), std::memory_order_relaxed);
                ESP_LOGW(TAG, "TILT fault (%.1f deg for %lu ms)", tilt_deg, (unsigned long)g_cfg.tilt_hold_ms);
                do_hard_stop();
            }
        }
    } else {
        s_tilt_active = false;
    }
}

static void check_stall(uint32_t now)
{
    // Read telemetry speeds (written by control_task on same core)
    // Use a relaxed read since we're on the same core.
    int16_t speed_l = g_telemetry.speed_l_mm_s;
    int16_t speed_r = g_telemetry.speed_r_mm_s;
    float   avg_speed = (std::abs(speed_l) + std::abs(speed_r)) / 2.0f;

    // Read commanded target
    const Command* cmd = g_cmd.read();
    float          cmd_speed = std::fabs(static_cast<float>(cmd->v_mm_s));

    // Stall: commanding significant speed but wheels aren't moving
    bool stalled = (cmd_speed > static_cast<float>(g_cfg.stall_speed_thresh) * 2.0f) &&
                   (avg_speed < static_cast<float>(g_cfg.stall_speed_thresh));

    if (stalled) {
        if (!s_stall_active) {
            s_stall_active = true;
            s_stall_since_us = now;
        } else if (elapsed_ms(s_stall_since_us, now) > g_cfg.stall_thresh_ms) {
            uint16_t flags = g_fault_flags.load(std::memory_order_relaxed);
            if (!(flags & Fault::STALL)) {
                g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::STALL), std::memory_order_relaxed);
                ESP_LOGW(TAG, "STALL fault (cmd=%.0f mm/s, meas=%.0f mm/s for %lu ms)", cmd_speed, avg_speed,
                         (unsigned long)g_cfg.stall_thresh_ms);
                do_hard_stop();
            }
        }
    } else {
        s_stall_active = false;
    }
}

static void check_obstacle()
{
    const RangeSample* range = g_range.read();

    // Only act on valid readings
    if (range->status != RangeStatus::OK) return;

    if (!s_obstacle_active) {
        // Not currently stopped — check if obstacle is too close
        if (range->range_mm < g_cfg.range_stop_mm) {
            s_obstacle_active = true;
            uint16_t flags = g_fault_flags.load(std::memory_order_relaxed);
            if (!(flags & Fault::OBSTACLE)) {
                g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::OBSTACLE), std::memory_order_relaxed);
                ESP_LOGW(TAG, "OBSTACLE fault (%u mm < %u mm threshold)", range->range_mm, g_cfg.range_stop_mm);
                begin_soft_stop();
            }
        }
    } else {
        // Currently stopped — release only when obstacle is far enough (hysteresis)
        if (range->range_mm > g_cfg.range_release_mm) {
            s_obstacle_active = false;
            g_fault_flags.fetch_and(~static_cast<uint16_t>(Fault::OBSTACLE), std::memory_order_relaxed);
            ESP_LOGI(TAG, "obstacle cleared (%u mm > %u mm release)", range->range_mm, g_cfg.range_release_mm);
        }
    }
}

// ---- Soft stop ramp management ----

static void update_soft_stop_ramp(uint32_t now)
{
    if (s_stop_state != StopState::RAMPING_DOWN) return;

    uint32_t elapsed = elapsed_ms(s_ramp_start_us, now);
    if (elapsed >= g_cfg.soft_stop_ramp_ms) {
        // Ramp complete — brake and disable
        motor_brake();
        if (motor_is_enabled()) {
            // Keep STBY high but braked (gearbox-friendly).
            // hard_kill only on hard stop or power-off.
        }
        s_stop_state = StopState::STOPPED;
        ESP_LOGI(TAG, "soft stop complete — motors braked");
    }
    // During ramp: control_task sees fault flags and zeros its output,
    // which naturally ramps down via rate limiting.
}

// ---- Fault recovery ----

static void check_fault_cleared()
{
    uint16_t flags = g_fault_flags.load(std::memory_order_relaxed);
    if (flags == 0 && s_stop_state == StopState::STOPPED) {
        // All faults cleared — re-enable motors
        s_stop_state = StopState::RUNNING;
        s_tilt_active = false;
        s_stall_active = false;
        s_obstacle_active = false;
        motor_enable();
        ESP_LOGI(TAG, "faults cleared — motors re-enabled");
    }
}

// ---- Safety task ----

void safety_task(void* arg)
{
    ESP_LOGI(TAG, "safety_task started @ 50 Hz");

    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, SAFETY_PERIOD);

        uint32_t now = now_us();

        check_cmd_timeout(now);
        check_estop();
        check_tilt(now);
        check_stall(now);
        check_obstacle();
        update_soft_stop_ramp(now);
        check_fault_cleared();
    }
}
