#include "usb_rx.h"
#include "protocol.h"
#include "usb_composite.h"
#include "shared_state.h"
#include "audio.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include <cstring>

static const char* TAG = "usb_rx";

static void handle_packet(const ParsedPacket& pkt);

static constexpr size_t MAX_FRAME = 768;

void usb_rx_task(void* arg)
{
    ESP_LOGI(TAG, "usb_rx_task started");

    uint8_t frame_buf[MAX_FRAME];
    size_t  frame_pos = 0;
    bool    discard = false;

    uint8_t decode_buf[MAX_FRAME];
    const TickType_t idle_delay_ticks = (pdMS_TO_TICKS(1) > 0) ? pdMS_TO_TICKS(1) : 1;

    while (true) {
        uint8_t rx_buf[64];
        int n = usb_cdc_read(rx_buf, sizeof(rx_buf), 50);
        if (n <= 0) {
            // Prevent starvation on low tick-rate configs (e.g. 100 Hz where 1 ms -> 0 ticks).
            vTaskDelay(idle_delay_ticks);
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
        if (pkt.data_len < sizeof(FaceSetStatePayload)) {
            break;
        }
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
        slot->has_talking = false;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case FaceCmdId::GESTURE: {
        if (pkt.data_len < sizeof(FaceGesturePayload)) {
            break;
        }
        FaceGesturePayload gp;
        memcpy(&gp, pkt.data, sizeof(gp));

        FaceCommand* slot = g_face_cmd.write_slot();
        slot->has_state    = false;
        slot->has_gesture  = true;
        slot->gesture_id   = gp.gesture_id;
        slot->gesture_dur  = gp.duration_ms;
        slot->has_system   = false;
        slot->has_talking  = false;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case FaceCmdId::SET_SYSTEM: {
        if (pkt.data_len < sizeof(FaceSetSystemPayload)) {
            break;
        }
        FaceSetSystemPayload sysp;
        memcpy(&sysp, pkt.data, sizeof(sysp));

        FaceCommand* slot = g_face_cmd.write_slot();
        slot->has_state    = false;
        slot->has_gesture  = false;
        slot->has_system   = true;
        slot->system_mode  = sysp.mode;
        slot->system_param = sysp.param;
        slot->has_talking  = false;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case FaceCmdId::SET_TALKING: {
        if (pkt.data_len < sizeof(FaceSetTalkingPayload)) {
            ESP_LOGW(TAG, "SET_TALKING payload too short: %u", static_cast<unsigned>(pkt.data_len));
            break;
        }
        FaceSetTalkingPayload tp;
        memcpy(&tp, pkt.data, sizeof(tp));

        FaceCommand* slot = g_face_cmd.write_slot();
        slot->has_state = false;
        slot->has_gesture = false;
        slot->has_system = false;
        slot->has_talking = true;
        slot->talking = (tp.talking != 0);
        slot->talking_energy = tp.energy;
        g_face_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case FaceCmdId::AUDIO_DATA: {
        if (pkt.data_len < sizeof(FaceAudioDataPayload)) {
            ESP_LOGW(TAG, "AUDIO_DATA payload too short: %u", static_cast<unsigned>(pkt.data_len));
            break;
        }
        FaceAudioDataPayload ap = {};
        memcpy(&ap, pkt.data, sizeof(ap));
        if (ap.chunk_len == 0 || ap.chunk_len > AUDIO_STREAM_PCM_BYTES) {
            ESP_LOGW(TAG, "AUDIO_DATA invalid chunk_len=%u", static_cast<unsigned>(ap.chunk_len));
            break;
        }
        const size_t payload_len = sizeof(FaceAudioDataPayload) + static_cast<size_t>(ap.chunk_len);
        if (pkt.data_len != payload_len) {
            ESP_LOGW(TAG,
                     "AUDIO_DATA size mismatch: pkt=%u expected=%u",
                     static_cast<unsigned>(pkt.data_len),
                     static_cast<unsigned>(payload_len));
            break;
        }
        const uint8_t* pcm = pkt.data + sizeof(FaceAudioDataPayload);
        if (!audio_stream_enqueue_pcm(pcm, ap.chunk_len)) {
            ESP_LOGW(TAG, "AUDIO_DATA enqueue failed (chunk_len=%u)", static_cast<unsigned>(ap.chunk_len));
        }
        break;
    }

    case FaceCmdId::SET_CONFIG: {
        if (pkt.data_len < sizeof(FaceSetConfigPayload)) {
            break;
        }
        FaceSetConfigPayload cfg;
        memcpy(&cfg, pkt.data, sizeof(cfg));

        const uint32_t value =
            (static_cast<uint32_t>(cfg.value[0]) << 0) |
            (static_cast<uint32_t>(cfg.value[1]) << 8) |
            (static_cast<uint32_t>(cfg.value[2]) << 16) |
            (static_cast<uint32_t>(cfg.value[3]) << 24);

        switch (static_cast<FaceCfgId>(cfg.param_id)) {
        case FaceCfgId::AUDIO_TEST_TONE_MS:
            audio_play_test_tone(value > 0 ? value : 1000);
            break;
        case FaceCfgId::AUDIO_MIC_PROBE_MS:
            audio_run_mic_probe(value > 0 ? value : 2000);
            break;
        case FaceCfgId::AUDIO_REG_DUMP:
            audio_dump_codec_regs();
            break;
        case FaceCfgId::AUDIO_MIC_STREAM_ENABLE:
            audio_set_mic_stream_enabled(value != 0);
            break;
        default:
            ESP_LOGW(TAG, "unknown face config param_id=0x%02X", cfg.param_id);
            break;
        }
        break;
    }

    default:
        ESP_LOGD(TAG, "unknown cmd type 0x%02X", pkt.type);
        break;
    }
}
