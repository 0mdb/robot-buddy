#include "telemetry.h"
#include "protocol.h"
#include "config.h"
#include "shared_state.h"
#include "usb_composite.h"
#include "audio.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include <cstring>

static const char* TAG = "telemetry";

void telemetry_task(void* arg)
{
    ESP_LOGI(TAG, "telemetry_task started (%d Hz)", TELEMETRY_HZ);

    uint8_t tx_buf[64];
    uint8_t seq = 0;

    const TickType_t period = pdMS_TO_TICKS(1000 / TELEMETRY_HZ);

    while (true) {
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
            }

            // Clear the event so we don't re-send
            TouchSample* slot = g_touch.write_slot();
            slot->event_type = 0xFF;
            g_touch.publish();
        }

        vTaskDelay(period);
    }
}
