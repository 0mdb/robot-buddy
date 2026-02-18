#include "telemetry.h"
#include "protocol.h"
#include "config.h"
#include "shared_state.h"
#include "usb_composite.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char* TAG = "telemetry";
static constexpr int64_t HEARTBEAT_PERIOD_US = 1000 * 1000;
static constexpr uint32_t TELEMETRY_LOOP_MS = 10;

void telemetry_task(void* arg)
{
    ESP_LOGI(TAG, "telemetry_task started (%d Hz)", TELEMETRY_HZ);

    uint8_t tx_buf[256];
    uint8_t seq = 0;
    uint32_t status_tx_count = 0;
    uint32_t touch_tx_count = 0;
    uint32_t button_tx_count = 0;
    int64_t last_status_us = 0;
    int64_t last_heartbeat_us = 0;

    const TickType_t period = (pdMS_TO_TICKS(TELEMETRY_LOOP_MS) > 0)
        ? pdMS_TO_TICKS(TELEMETRY_LOOP_MS)
        : 1;
    const int64_t status_period_us = (TELEMETRY_HZ > 0)
        ? (1000 * 1000 / TELEMETRY_HZ)
        : (1000 * 1000);

    while (true) {
        const int64_t now_us = esp_timer_get_time();

        if (last_status_us == 0 || (now_us - last_status_us) >= status_period_us) {
            FaceStatusPayload status = {};
            status.mood_id = g_current_mood.load(std::memory_order_relaxed);
            status.active_gesture = g_active_gesture.load(std::memory_order_relaxed);
            status.system_mode = g_system_mode.load(std::memory_order_relaxed);
            if (g_touch_active.load(std::memory_order_relaxed)) {
                status.flags |= 0x01;
            }
            if (g_talking_active.load(std::memory_order_relaxed)) {
                status.flags |= 0x02;
            }
            if (g_ptt_listening.load(std::memory_order_relaxed)) {
                status.flags |= 0x04;
            }

            const size_t len = packet_build(
                static_cast<uint8_t>(FaceTelId::FACE_STATUS),
                seq++,
                reinterpret_cast<const uint8_t*>(&status),
                sizeof(status),
                tx_buf,
                sizeof(tx_buf));
            if (len > 0) {
                usb_cdc_write(tx_buf, len);
                status_tx_count++;
            }

            const TouchSample* touch = g_touch.read();
            if (touch->event_type != 0xFF) {
                TouchEventPayload tev = {};
                tev.event_type = touch->event_type;
                tev.x = touch->x;
                tev.y = touch->y;

                const size_t tlen = packet_build(
                    static_cast<uint8_t>(FaceTelId::TOUCH_EVENT),
                    seq++,
                    reinterpret_cast<const uint8_t*>(&tev),
                    sizeof(tev),
                    tx_buf,
                    sizeof(tx_buf));
                if (tlen > 0) {
                    usb_cdc_write(tx_buf, tlen);
                    touch_tx_count++;

                    TouchSample* slot = g_touch.write_slot();
                    slot->event_type = 0xFF;
                    g_touch.publish();
                }
            }

            const ButtonEventSample* btn = g_button.read();
            if (btn->event_type != 0xFF && btn->button_id != 0xFF) {
                FaceButtonEventPayload bp = {};
                bp.button_id = btn->button_id;
                bp.event_type = btn->event_type;
                bp.state = btn->state;

                const size_t blen = packet_build(
                    static_cast<uint8_t>(FaceTelId::BUTTON_EVENT),
                    seq++,
                    reinterpret_cast<const uint8_t*>(&bp),
                    sizeof(bp),
                    tx_buf,
                    sizeof(tx_buf));
                if (blen > 0) {
                    usb_cdc_write(tx_buf, blen);
                    button_tx_count++;

                    ButtonEventSample* slot = g_button.write_slot();
                    slot->button_id = 0xFF;
                    slot->event_type = 0xFF;
                    slot->state = 0;
                    g_button.publish();
                }
            }

            last_status_us = now_us;
        }

        if (last_heartbeat_us == 0 || (now_us - last_heartbeat_us) >= HEARTBEAT_PERIOD_US) {
            FaceHeartbeatPayload hb = {};
            hb.uptime_ms = static_cast<uint32_t>(now_us / 1000);
            hb.status_tx_count = status_tx_count;
            hb.touch_tx_count = touch_tx_count;
            hb.button_tx_count = button_tx_count;

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
            hb.ptt_listening = g_ptt_listening.load(std::memory_order_relaxed) ? 1 : 0;
            hb.reserved = 0;

            const size_t hlen = packet_build(
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
