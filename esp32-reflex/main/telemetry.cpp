#include "telemetry.h"
#include "protocol.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "driver/usb_serial_jtag.h"

#include <cstring>

static const char* TAG = "telemetry";

// Telemetry rate: ~20 Hz
static constexpr TickType_t TEL_PERIOD = pdMS_TO_TICKS(50);

// Read g_telemetry using seqlock pattern. Returns true if a consistent read
// was obtained, false if the writer was mid-update (caller should skip).
static bool read_telemetry(TelemetryState& out)
{
    for (int attempts = 0; attempts < 3; attempts++) {
        uint32_t seq1 = g_telemetry.seq.load(std::memory_order_acquire);
        if (seq1 & 1) continue; // writer is mid-update

        // Copy the data fields
        out.speed_l_mm_s = g_telemetry.speed_l_mm_s;
        out.speed_r_mm_s = g_telemetry.speed_r_mm_s;
        out.gyro_z_mrad_s = g_telemetry.gyro_z_mrad_s;
        out.accel_x_mg = g_telemetry.accel_x_mg;
        out.accel_y_mg = g_telemetry.accel_y_mg;
        out.accel_z_mg = g_telemetry.accel_z_mg;
        out.battery_mv = g_telemetry.battery_mv;
        out.fault_flags = g_telemetry.fault_flags;
        out.timestamp_us = g_telemetry.timestamp_us;
        out.cmd_seq_last_applied = g_telemetry.cmd_seq_last_applied;
        out.t_cmd_applied_us = g_telemetry.t_cmd_applied_us;

        uint32_t seq2 = g_telemetry.seq.load(std::memory_order_acquire);
        if (seq1 == seq2) return true; // consistent read
    }
    return false; // couldn't get a clean read, skip this cycle
}

void telemetry_task(void* arg)
{
    ESP_LOGI(TAG, "telemetry_task started @ ~20 Hz");

    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, TEL_PERIOD);

        TelemetryState snap;
        if (!read_telemetry(snap)) continue;

        // Read latest range sample (separate from seqlock — double-buffered)
        const RangeSample* range = g_range.read();

        // Capture timestamp for v2 envelope
        const uint64_t t_src = static_cast<uint64_t>(esp_timer_get_time());

        // Build wire packet (conditional v1/v2 payload)
        uint8_t wire_buf[64];
        size_t  wire_len = 0;

        if (g_protocol_version.load(std::memory_order_acquire) == 2) {
            // v2: extended payload with cmd causality
            StatePayloadV2 sp2;
            sp2.speed_l_mm_s = snap.speed_l_mm_s;
            sp2.speed_r_mm_s = snap.speed_r_mm_s;
            sp2.gyro_z_mrad_s = snap.gyro_z_mrad_s;
            sp2.accel_x_mg = snap.accel_x_mg;
            sp2.accel_y_mg = snap.accel_y_mg;
            sp2.accel_z_mg = snap.accel_z_mg;
            sp2.battery_mv = snap.battery_mv;
            sp2.fault_flags = snap.fault_flags;
            sp2.range_mm = range->range_mm;
            sp2.range_status = static_cast<uint8_t>(range->status);
            sp2.cmd_seq_last_applied = snap.cmd_seq_last_applied;
            sp2.t_cmd_applied_us = snap.t_cmd_applied_us;

            wire_len = packet_build_v2(static_cast<uint8_t>(TelId::STATE), next_seq(), t_src,
                                       reinterpret_cast<const uint8_t*>(&sp2), sizeof(sp2), wire_buf, sizeof(wire_buf));
        } else {
            // v1: original 13-byte payload
            StatePayload sp;
            sp.speed_l_mm_s = snap.speed_l_mm_s;
            sp.speed_r_mm_s = snap.speed_r_mm_s;
            sp.gyro_z_mrad_s = snap.gyro_z_mrad_s;
            sp.accel_x_mg = snap.accel_x_mg;
            sp.accel_y_mg = snap.accel_y_mg;
            sp.accel_z_mg = snap.accel_z_mg;
            sp.battery_mv = snap.battery_mv;
            sp.fault_flags = snap.fault_flags;
            sp.range_mm = range->range_mm;
            sp.range_status = static_cast<uint8_t>(range->status);

            wire_len = packet_build_v2(static_cast<uint8_t>(TelId::STATE), next_seq(), t_src,
                                       reinterpret_cast<const uint8_t*>(&sp), sizeof(sp), wire_buf, sizeof(wire_buf));
        }

        if (wire_len == 0) continue;

        // Best-effort send: write with zero timeout — drop if TX buffer is full
        int written = usb_serial_jtag_write_bytes(reinterpret_cast<const char*>(wire_buf), wire_len, 0);
        if (written < static_cast<int>(wire_len)) {
            // Backpressured or disconnected — silently drop
        }
    }
}
