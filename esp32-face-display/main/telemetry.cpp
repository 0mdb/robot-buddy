#include "telemetry.h"
#include "protocol.h"
#include "config.h"
#include "shared_state.h"
#include "usb_composite.h"
#include "audio.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include <cstring>

static const char* TAG = "telemetry";
static constexpr int64_t HEARTBEAT_PERIOD_US = 1000 * 1000;

void telemetry_task(void* arg)
{
    ESP_LOGI(TAG, "telemetry_task started (%d Hz)", TELEMETRY_HZ);

    uint8_t tx_buf[128];
    uint8_t seq = 0;
    uint32_t status_tx_count = 0;
    uint32_t touch_tx_count = 0;
    uint32_t last_mic_probe_seq_sent = 0;
    int64_t last_heartbeat_us = 0;

    const TickType_t period = pdMS_TO_TICKS(1000 / TELEMETRY_HZ);

    while (true) {
        const MicProbeStats mic = audio_get_mic_probe_stats();

        // Build FACE_STATUS payload
        FaceStatusPayload status;
        status.mood_id = g_current_mood.load(std::memory_order_relaxed);
        status.active_gesture = g_active_gesture.load(std::memory_order_relaxed);
        status.system_mode = g_system_mode.load(std::memory_order_relaxed);
        status.flags = 0;
        if (g_touch_active.load(std::memory_order_relaxed)) {
            status.flags |= 0x01;
        }
        if (audio_is_playing()) {
            status.flags |= 0x02;
        }
        if (audio_mic_activity_detected()) {
            status.flags |= 0x04;
        }

        size_t len = packet_build(
            static_cast<uint8_t>(FaceTelId::FACE_STATUS),
            seq++,
            reinterpret_cast<const uint8_t*>(&status),
            sizeof(status),
            tx_buf, sizeof(tx_buf));

        if (len > 0) {
            usb_cdc_write(tx_buf, len);
            status_tx_count++;
        }

        // Check for pending touch events
        const TouchSample* touch = g_touch.read();
        if (touch->event_type != 0xFF) {
            TouchEventPayload tev;
            tev.event_type = touch->event_type;
            tev.x = touch->x;
            tev.y = touch->y;

            size_t tlen = packet_build(
                static_cast<uint8_t>(FaceTelId::TOUCH_EVENT),
                seq++,
                reinterpret_cast<const uint8_t*>(&tev),
                sizeof(tev),
                tx_buf, sizeof(tx_buf));

            if (tlen > 0) {
                usb_cdc_write(tx_buf, tlen);
                touch_tx_count++;
            }

            // Clear the event so we don't re-send
            TouchSample* slot = g_touch.write_slot();
            slot->event_type = 0xFF;
            g_touch.publish();
        }

        if (mic.probe_seq != 0 && mic.probe_seq != last_mic_probe_seq_sent) {
            auto clamp_u16 = [](uint32_t v) -> uint16_t {
                return (v > 0xFFFFu) ? 0xFFFFu : static_cast<uint16_t>(v);
            };
            auto clamp_i16 = [](int32_t v) -> int16_t {
                if (v > 32767) return 32767;
                if (v < -32768) return -32768;
                return static_cast<int16_t>(v);
            };

            FaceMicProbePayload mp = {};
            mp.probe_seq = mic.probe_seq;
            mp.duration_ms = mic.duration_ms;
            mp.sample_count = mic.sample_count;
            mp.read_timeouts = clamp_u16(mic.read_timeouts);
            mp.read_errors = clamp_u16(mic.read_errors);
            mp.selected_rms_x10 = clamp_u16(mic.selected_rms_x10);
            mp.selected_peak = clamp_u16(mic.selected_peak);
            mp.selected_dbfs_x10 = clamp_i16(mic.selected_dbfs_x10);
            mp.selected_channel = mic.selected_channel;
            mp.active = mic.active ? 1 : 0;

            size_t mlen = packet_build(
                static_cast<uint8_t>(FaceTelId::MIC_PROBE),
                seq++,
                reinterpret_cast<const uint8_t*>(&mp),
                sizeof(mp),
                tx_buf,
                sizeof(tx_buf));

            if (mlen > 0) {
                usb_cdc_write(tx_buf, mlen);
                last_mic_probe_seq_sent = mic.probe_seq;
            }
        }

        const int64_t now_us = esp_timer_get_time();
        if (last_heartbeat_us == 0 || (now_us - last_heartbeat_us) >= HEARTBEAT_PERIOD_US) {
            FaceHeartbeatPayload hb = {};
            hb.uptime_ms = static_cast<uint32_t>(now_us / 1000);
            hb.status_tx_count = status_tx_count;
            hb.touch_tx_count = touch_tx_count;
            hb.mic_probe_seq = mic.probe_seq;
            hb.mic_activity = audio_mic_activity_detected() ? 1 : 0;
            const UsbCdcDiagSnapshot usb_diag = usb_cdc_diag_snapshot();
            hb.usb_tx_calls = usb_diag.tx_calls;
            hb.usb_tx_bytes_requested = usb_diag.tx_bytes_requested;
            hb.usb_tx_bytes_queued = usb_diag.tx_bytes_queued;
            hb.usb_tx_short_writes = usb_diag.tx_short_writes;
            hb.usb_tx_flush_ok = usb_diag.tx_flush_ok;
            hb.usb_tx_flush_not_finished = usb_diag.tx_flush_not_finished;
            hb.usb_tx_flush_timeout = usb_diag.tx_flush_timeout;
            hb.usb_tx_flush_error = usb_diag.tx_flush_error;
            hb.usb_rx_calls = usb_diag.rx_calls;
            hb.usb_rx_bytes = usb_diag.rx_bytes;
            hb.usb_rx_errors = usb_diag.rx_errors;
            hb.usb_line_state_events = usb_diag.line_state_events;
            hb.usb_dtr = usb_diag.dtr;
            hb.usb_rts = usb_diag.rts;

            size_t hlen = packet_build(
                static_cast<uint8_t>(FaceTelId::HEARTBEAT),
                seq++,
                reinterpret_cast<const uint8_t*>(&hb),
                sizeof(hb),
                tx_buf,
                sizeof(tx_buf));

            if (hlen > 0) {
                usb_cdc_write(tx_buf, hlen);
                last_heartbeat_us = now_us;
            }
        }

        vTaskDelay(period);
    }
}
