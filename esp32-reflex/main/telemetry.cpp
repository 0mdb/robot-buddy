#include "telemetry.h"
#include "protocol.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

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
        if (seq1 & 1) continue;  // writer is mid-update

        // Copy the data fields
        out.speed_l_mm_s  = g_telemetry.speed_l_mm_s;
        out.speed_r_mm_s  = g_telemetry.speed_r_mm_s;
        out.gyro_z_mrad_s = g_telemetry.gyro_z_mrad_s;
        out.battery_mv    = g_telemetry.battery_mv;
        out.fault_flags   = g_telemetry.fault_flags;
        out.timestamp_us  = g_telemetry.timestamp_us;

        uint32_t seq2 = g_telemetry.seq.load(std::memory_order_acquire);
        if (seq1 == seq2) return true;  // consistent read
    }
    return false;  // couldn't get a clean read, skip this cycle
}

void telemetry_task(void* arg)
{
    ESP_LOGI(TAG, "telemetry_task started @ ~20 Hz");

    uint8_t seq_counter = 0;
    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, TEL_PERIOD);

        TelemetryState snap;
        if (!read_telemetry(snap)) continue;

        // Read latest range sample (separate from seqlock — double-buffered)
        const RangeSample* range = g_range.read();

        // Build STATE payload
        StatePayload sp;
        sp.speed_l_mm_s  = snap.speed_l_mm_s;
        sp.speed_r_mm_s  = snap.speed_r_mm_s;
        sp.gyro_z_mrad_s = snap.gyro_z_mrad_s;
        sp.battery_mv    = snap.battery_mv;
        sp.fault_flags   = snap.fault_flags;
        sp.range_mm      = range->range_mm;
        sp.range_status  = static_cast<uint8_t>(range->status);

        // Build wire packet
        uint8_t wire_buf[32];
        size_t wire_len = packet_build(
            static_cast<uint8_t>(TelId::STATE), seq_counter++,
            reinterpret_cast<const uint8_t*>(&sp), sizeof(sp),
            wire_buf, sizeof(wire_buf));

        if (wire_len == 0) continue;

        // Best-effort send: write with zero timeout — drop if TX buffer is full
        int written = usb_serial_jtag_write_bytes(wire_buf, wire_len, 0);
        if (written < static_cast<int>(wire_len)) {
            // Backpressured or disconnected — silently drop
        }
    }
}
