#include "control.h"
#include "config.h"
#include "motor.h"
#include "encoder.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_task_wdt.h"

#include <cmath>

static const char* TAG = "control";

// ---- Per-wheel PI controller state ----

struct WheelPI {
    float integral = 0.0f;
    float prev_target = 0.0f; // for rate limiting (mm/s)

    void reset()
    {
        integral = 0.0f;
        prev_target = 0.0f;
    }
};

// ---- Helpers ----

static float clampf(float val, float lo, float hi)
{
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

// Rate-limit a target towards a setpoint, respecting max accel.
// Returns the new rate-limited target.
static float rate_limit(float current, float setpoint, float max_accel, float dt)
{
    float max_delta = max_accel * dt;
    float delta = setpoint - current;
    delta = clampf(delta, -max_delta, max_delta);
    return current + delta;
}

// Feedforward + PI controller. Returns PWM duty (signed: + = forward, - = reverse).
static float ff_pi(WheelPI& state, float v_target, float v_meas, float dt)
{
    // Feedforward
    float ff = g_cfg.kV * v_target;
    if (v_target != 0.0f) {
        ff += (v_target > 0.0f) ? g_cfg.kS : -g_cfg.kS;
    }

    // PI error
    float error = v_target - v_meas;
    state.integral += error * dt;

    // Compute output
    float u = ff + g_cfg.Kp * error + g_cfg.Ki * state.integral;

    // Clamp
    float max_u = static_cast<float>(g_cfg.max_pwm);
    float u_clamped = clampf(u, -max_u, max_u);

    // Anti-windup: if output is saturated, bleed integrator
    if (u != u_clamped) {
        // Back-calculate: remove the excess from the integrator
        state.integral -= (u - u_clamped) / (g_cfg.Ki > 0.0f ? g_cfg.Ki : 1.0f) * 0.5f;
    }

    return u_clamped;
}

// Deadband / stiction compensation.
// Shifts the entire output curve by min_pwm so duty never lands in the
// motor's dead zone when a nonzero speed is commanded.
static float deadband_comp(float u, float v_target)
{
    if (v_target == 0.0f) return u;

    float min = static_cast<float>(g_cfg.min_pwm);
    if (u > 0.0f) {
        u += min;
    } else if (u < 0.0f) {
        u -= min;
    } else {
        // PI output is exactly zero but target is nonzero — kick-start
        u = (v_target > 0.0f) ? min : -min;
    }

    float max_u = static_cast<float>(g_cfg.max_pwm);
    return clampf(u, -max_u, max_u);
}

// Apply motor output from a signed duty value.
static void apply_motor(MotorSide side, float u)
{
    if (u >= 0.0f) {
        motor_set_output(side, static_cast<uint16_t>(u), true);
    } else {
        motor_set_output(side, static_cast<uint16_t>(-u), false);
    }
}

// Clamp float to int16_t range before cast (avoids UB on overflow).
static int16_t clamp_i16(float v)
{
    if (v > 32767.0f) return 32767;
    if (v < -32768.0f) return -32768;
    return static_cast<int16_t>(v);
}

// Write telemetry using seqlock pattern.
// acquire fence after first increment prevents data writes from reordering before it.
// release fence on second increment prevents data writes from reordering after it.
static void publish_telemetry(float speed_l, float speed_r, float gyro_z_mrad,
                              uint32_t now_us, uint32_t cmd_seq_applied)
{
    // Increment to odd (writing) — acquire prevents subsequent stores
    // from being reordered before this point.
    g_telemetry.seq.fetch_add(1, std::memory_order_acquire);

    g_telemetry.speed_l_mm_s = clamp_i16(speed_l);
    g_telemetry.speed_r_mm_s = clamp_i16(speed_r);
    g_telemetry.gyro_z_mrad_s = clamp_i16(gyro_z_mrad);
    g_telemetry.fault_flags = g_fault_flags.load(std::memory_order_relaxed);
    g_telemetry.timestamp_us = now_us;
    g_telemetry.cmd_seq_last_applied = cmd_seq_applied;
    g_telemetry.t_cmd_applied_us = now_us;

    // Increment to even (done) — release prevents preceding stores
    // from being reordered after this point.
    g_telemetry.seq.fetch_add(1, std::memory_order_release);
}

// ---- Control task ----

void control_task(void* arg)
{
    ESP_LOGI(TAG, "control_task started @ %u Hz", g_cfg.control_hz);

    // Register with Task Watchdog
    ESP_ERROR_CHECK(esp_task_wdt_add(nullptr));

    const TickType_t period = pdMS_TO_TICKS(1000 / g_cfg.control_hz);
    const float      dt = 1.0f / static_cast<float>(g_cfg.control_hz);

    WheelPI pi_left;
    WheelPI pi_right;

    // Encoder state for delta computation
    int32_t prev_enc_l = 0, prev_enc_r = 0;
    encoder_snapshot(&prev_enc_l, &prev_enc_r);
    uint32_t prev_time_us = static_cast<uint32_t>(esp_timer_get_time());

    // Rate-limited targets (start at zero)
    float rl_target_l = 0.0f;
    float rl_target_r = 0.0f;

    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, period);
        esp_task_wdt_reset();

        uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        uint32_t dt_us = now_us - prev_time_us;
        float    dt_actual = static_cast<float>(dt_us) / 1'000'000.0f;
        if (dt_actual <= 0.0f) dt_actual = dt; // guard against timer wrap edge
        prev_time_us = now_us;

        // ---- 1. Encoder snapshot → wheel speeds ----
        int32_t enc_l, enc_r;
        encoder_snapshot(&enc_l, &enc_r);

        int32_t delta_l = enc_l - prev_enc_l;
        int32_t delta_r = enc_r - prev_enc_r;
        prev_enc_l = enc_l;
        prev_enc_r = enc_r;

        float v_meas_l = encoder_delta_to_mm_s(delta_l, dt_us);
        float v_meas_r = encoder_delta_to_mm_s(delta_r, dt_us);

        // ---- 2. Read latest command ----
        const Command* cmd = g_cmd.read();
        float          v_cmd = static_cast<float>(cmd->v_mm_s);
        float          w_cmd = static_cast<float>(cmd->w_mrad_s) / 1000.0f; // mrad/s → rad/s
        uint32_t       cmd_seq = cmd->cmd_seq; // v2 causality tracking

        // ---- 3. Differential drive: twist → per-wheel targets ----
        float half_wb = g_cfg.wheelbase_mm / 2.0f;
        float v_target_l = v_cmd - w_cmd * half_wb;
        float v_target_r = v_cmd + w_cmd * half_wb;

        // Clamp to max speed
        float max_v = static_cast<float>(g_cfg.max_v_mm_s);
        v_target_l = clampf(v_target_l, -max_v, max_v);
        v_target_r = clampf(v_target_r, -max_v, max_v);

        // ---- 4. Rate limiting ----
        float max_a = static_cast<float>(g_cfg.max_a_mm_s2);
        rl_target_l = rate_limit(rl_target_l, v_target_l, max_a, dt_actual);
        rl_target_r = rate_limit(rl_target_r, v_target_r, max_a, dt_actual);

        // ---- 5. Yaw damping (gyro correction) ----
        const ImuSample* imu = g_imu.read();
        float            gyro_z = imu->gyro_z_rad_s;

        float w_error = w_cmd - gyro_z;
        float delta_v = g_cfg.K_yaw * w_error;
        float rl_l = rl_target_l - delta_v;
        float rl_r = rl_target_r + delta_v;

        // ---- 6. FF + PI per wheel ----
        float u_l = ff_pi(pi_left, rl_l, v_meas_l, dt_actual);
        float u_r = ff_pi(pi_right, rl_r, v_meas_r, dt_actual);

        // ---- 7. Deadband compensation ----
        u_l = deadband_comp(u_l, rl_l);
        u_r = deadband_comp(u_r, rl_r);

        // ---- 8. Fault gate: if any faults active, don't drive motors ----
        uint16_t faults = g_fault_flags.load(std::memory_order_relaxed);
        if (faults != 0) {
            // Safety task owns the stop behavior; we just zero our output
            u_l = 0.0f;
            u_r = 0.0f;
            pi_left.reset();
            pi_right.reset();
            rl_target_l = 0.0f;
            rl_target_r = 0.0f;
        }

        // ---- 9. Apply to motors ----
        apply_motor(MotorSide::LEFT, u_l);
        apply_motor(MotorSide::RIGHT, u_r);

        // ---- 10. Publish telemetry ----
        publish_telemetry(v_meas_l, v_meas_r,
                          gyro_z * 1000.0f, // rad/s → mrad/s
                          now_us, cmd_seq);
    }
}
