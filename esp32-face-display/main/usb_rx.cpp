#include "usb_rx.h"
#include "protocol.h"
#include "usb_composite.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include <cstring>

static const char* TAG = "usb_rx";

static void handle_packet(const ParsedPacket& pkt);

static constexpr size_t MAX_FRAME = 64;

void usb_rx_task(void* arg)
{
    ESP_LOGI(TAG, "usb_rx_task started");

    uint8_t frame_buf[MAX_FRAME];
    size_t  frame_pos = 0;
    bool    discard = false;

    uint8_t decode_buf[MAX_FRAME];

    while (true) {
        uint8_t rx_buf[64];
        int n = usb_cdc_read(rx_buf, sizeof(rx_buf), 50);
        if (n <= 0) {
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }

        for (int i = 0; i < n; i++) {
            uint8_t rx_byte = rx_buf[i];

            if (rx_byte == 0x00) {
                if (frame_pos > 0 && !discard) {
                    ParsedPacket pkt = packet_parse(frame_buf, frame_pos,
                                                    decode_buf, sizeof(decode_buf));
                    if (pkt.valid) {
                        handle_packet(pkt);
                    } else {
                        ESP_LOGD(TAG, "dropped invalid packet (len=%u)", (unsigned)frame_pos);
                    }
                }
                frame_pos = 0;
                discard = false;
            } else {
                if (discard) continue;
                if (frame_pos < MAX_FRAME) {
                    frame_buf[frame_pos++] = rx_byte;
                } else {
                    ESP_LOGW(TAG, "frame overflow, discarding until delimiter");
                    discard = true;
                }
            }
        }
    }
}

// ---- Command dispatch ----

static void handle_packet(const ParsedPacket& pkt)
{
    switch (static_cast<FaceCmdId>(pkt.type)) {

    case FaceCmdId::SET_STATE: {
        if (pkt.data_len < sizeof(FaceSetStatePayload)) break;
        FaceSetStatePayload sp;
        memcpy(&sp, pkt.data, sizeof(sp));

        FaceCommand* slot = g_face_cmd.write_slot();
        slot->has_state  = true;
        slot->mood_id    = sp.mood_id;
        slot->intensity  = sp.intensity;
        slot->gaze_x     = sp.gaze_x;
        slot->gaze_y     = sp.gaze_y;
        slot->brightness = sp.brightness;
        slot->has_gesture = false;
        slot->has_system  = false;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case FaceCmdId::GESTURE: {
        if (pkt.data_len < sizeof(FaceGesturePayload)) break;
        FaceGesturePayload gp;
        memcpy(&gp, pkt.data, sizeof(gp));

        FaceCommand* slot = g_face_cmd.write_slot();
        slot->has_state    = false;
        slot->has_gesture  = true;
        slot->gesture_id   = gp.gesture_id;
        slot->gesture_dur  = gp.duration_ms;
        slot->has_system   = false;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case FaceCmdId::SET_SYSTEM: {
        if (pkt.data_len < sizeof(FaceSetSystemPayload)) break;
        FaceSetSystemPayload sysp;
        memcpy(&sysp, pkt.data, sizeof(sysp));

        FaceCommand* slot = g_face_cmd.write_slot();
        slot->has_state    = false;
        slot->has_gesture  = false;
        slot->has_system   = true;
        slot->system_mode  = sysp.mode;
        slot->system_param = sysp.param;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    default:
        ESP_LOGD(TAG, "unknown cmd type 0x%02X", pkt.type);
        break;
    }
}
