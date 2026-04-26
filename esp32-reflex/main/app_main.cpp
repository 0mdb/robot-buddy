// Reflex MCU — app_main
// Full system: motor + encoder + IMU + protocol + control loop + safety.

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "config.h"
#include "pin_map.h"
#include "motor.h"
#include "encoder.h"
#include "imu.h"
#include "range_ultrasonic.h"
#include "control.h"
#include "safety.h"
#include "usb_rx.h"
#include "telemetry.h"
#include "shared_state.h"
#include "protocol.h"

#include "driver/usb_serial_jtag.h"
#include <cstring>

static const char* TAG = "reflex";

// ---- Global shared state (owned here, extern'd in shared_state.h) ----
ImuBuffer             g_imu;
CommandBuffer         g_cmd;
RangeBuffer           g_range;
TelemetryState        g_telemetry;
std::atomic<uint16_t> g_fault_flags{0};
std::atomic<uint32_t> g_cmd_seq_last{0};

// ============================================================
// Bring-up test: open-loop motor ramp + encoder readback.
// Set to 0 once closed-loop control is validated.
// When enabled, control_task and safety_task are NOT started.
// ============================================================
#define BRINGUP_OPEN_LOOP_TEST 1

#if BRINGUP_OPEN_LOOP_TEST

// Emit a BRINGUP_DIAG telemetry packet with the current encoder snapshot.
// Best-effort, non-blocking — drop on TX backpressure (matches telemetry_task).
// ESP_LOGI calls in this task are silenced (binary protocol owns USB-Serial-JTAG);
// this packet is the actual data path the supervisor consumes.
static void emit_bringup_diag(BringupPhase phase, MotorSide side, bool forward, uint16_t pwm_duty)
{
    int32_t cur_l, cur_r;
    encoder_snapshot(&cur_l, &cur_r);

    BringupDiagPayload p{};
    p.phase = static_cast<uint8_t>(phase);
    p.side = (side == MotorSide::LEFT) ? 0u : 1u;
    p.forward = forward ? 1u : 0u;
    p.pwm_duty = pwm_duty;
    p.raw_l = cur_l;
    p.raw_r = cur_r;

    uint8_t      wire_buf[64];
    const size_t wire_len = packet_build_v2(
        static_cast<uint8_t>(TelId::BRINGUP_DIAG), next_seq(), static_cast<uint64_t>(esp_timer_get_time()),
        reinterpret_cast<const uint8_t*>(&p), sizeof(p), wire_buf, sizeof(wire_buf));
    if (wire_len == 0) return;
    usb_serial_jtag_write_bytes(reinterpret_cast<const char*>(wire_buf), wire_len, 0);
}

static void open_loop_test_task(void* arg)
{
    ESP_LOGI(TAG, "=== OPEN-LOOP BRING-UP TEST ===");
    ESP_LOGI(TAG, "Will ramp each motor forward then reverse.");
    ESP_LOGI(TAG, "Watch encoder counts — they should increase with positive PWM.");

    vTaskDelay(pdMS_TO_TICKS(2000));

    motor_enable();

    const uint16_t test_duty = g_cfg.max_pwm / 4;
    const uint32_t hold_ms = 1500;
    const uint32_t sample_interval_ms = 100;

    auto run_phase = [&](const char* label, BringupPhase phase, MotorSide side, bool forward) {
        ESP_LOGI(TAG, "--- %s ---", label);

        int32_t start_l, start_r;
        encoder_snapshot(&start_l, &start_r);

        motor_set_output(side, test_duty, forward);
        uint32_t elapsed = 0;
        while (elapsed < hold_ms) {
            vTaskDelay(pdMS_TO_TICKS(sample_interval_ms));
            elapsed += sample_interval_ms;

            int32_t cur_l, cur_r;
            encoder_snapshot(&cur_l, &cur_r);
            ESP_LOGI(TAG, "  enc L=%ld  R=%ld  (dL=%ld dR=%ld)", (long)cur_l, (long)cur_r, (long)(cur_l - start_l),
                     (long)(cur_r - start_r));
            emit_bringup_diag(phase, side, forward, test_duty);
        }

        motor_set_output(side, 0, true);
        motor_brake();
        vTaskDelay(pdMS_TO_TICKS(500));
        emit_bringup_diag(BringupPhase::IDLE, side, forward, 0);
    };

    run_phase("LEFT FORWARD", BringupPhase::LEFT_FWD, MotorSide::LEFT, true);
    run_phase("LEFT REVERSE", BringupPhase::LEFT_REV, MotorSide::LEFT, false);
    run_phase("RIGHT FORWARD", BringupPhase::RIGHT_FWD, MotorSide::RIGHT, true);
    run_phase("RIGHT REVERSE", BringupPhase::RIGHT_REV, MotorSide::RIGHT, false);

    motor_hard_kill();
    ESP_LOGI(TAG, "=== OPEN-LOOP TEST COMPLETE ===");
    ESP_LOGI(TAG, "Check: positive PWM should give positive encoder delta.");
    ESP_LOGI(TAG, "If a motor is backwards, swap its encoder A/B or direction pins in pin_map.h.");

    vTaskDelete(nullptr);
}

#endif // BRINGUP_OPEN_LOOP_TEST

extern "C" void app_main()
{
    // Silence ALL ESP_LOG immediately — USB Serial/JTAG is used exclusively
    // for binary protocol.  Any text output corrupts COBS framing.
    esp_log_level_set("*", ESP_LOG_NONE);

    // ---- Phase 1: hardware init ----
    motor_init();
    encoder_init();

    if (imu_init()) {
        ESP_LOGI(TAG, "IMU initialized OK");
        // imu_task on PRO core (core 0), below control_task priority
        xTaskCreatePinnedToCore(imu_task, "imu", 4096, nullptr, 8, nullptr, 0);
    } else {
        ESP_LOGE(TAG, "IMU init FAILED — continuing without gyro");
        g_fault_flags.store(static_cast<uint16_t>(Fault::IMU_FAIL), std::memory_order_relaxed);
    }

    if (range_init()) {
        ESP_LOGI(TAG, "Range sensor initialized OK");
    } else {
        ESP_LOGW(TAG, "Range sensor init failed — continuing without range");
    }

    // Install USB Serial/JTAG driver before starting tasks that use it.
    usb_serial_jtag_driver_config_t usb_cfg = {};
    usb_cfg.rx_buffer_size = 512;
    usb_cfg.tx_buffer_size = 512;
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb_cfg));

    // ---- Phase 2: APP core tasks (USB protocol + telemetry + range) ----
    xTaskCreatePinnedToCore(usb_rx_task, "usb_rx", 4096, nullptr, 5, nullptr, 1);   // APP core, normal priority
    xTaskCreatePinnedToCore(telemetry_task, "telem", 4096, nullptr, 3, nullptr, 1); // APP core, below-normal
    xTaskCreatePinnedToCore(range_task, "range", 3072, nullptr, 4, nullptr, 1); // APP core, between usb_rx and telem

#if BRINGUP_OPEN_LOOP_TEST
    xTaskCreatePinnedToCore(open_loop_test_task, "ol_test", 4096, nullptr, 5, nullptr, 1);
#else
    // ---- Phase 3: PRO core tasks (control + safety) ----
    // Enable motors — safety_task will gate them on faults.
    motor_enable();

    xTaskCreatePinnedToCore(control_task, "control", 4096, nullptr, 10, nullptr, 0); // PRO core, highest
    xTaskCreatePinnedToCore(safety_task, "safety", 4096, nullptr, 6, nullptr, 0);    // PRO core, above-normal
#endif
}
