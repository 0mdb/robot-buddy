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

static constexpr size_t MAX_FRAME = 768;

void usb_rx_task(void* arg)
{
    ESP_LOGI(TAG, "usb_rx_task started");

    uint8_t frame_buf[MAX_FRAME];
    size_t  frame_pos = 0;
    bool    discard = false;

    uint8_t          decode_buf[MAX_FRAME];
    const TickType_t idle_delay_ticks = (pdMS_TO_TICKS(1) > 0) ? pdMS_TO_TICKS(1) : 1;

    while (true) {
        uint8_t rx_buf[64];
        int     n = usb_cdc_read(rx_buf, sizeof(rx_buf), 50);
        if (n <= 0) {
            // Prevent starvation on low tick-rate configs (e.g. 100 Hz where 1 ms -> 0 ticks).
            vTaskDelay(idle_delay_ticks);
            continue;
        }

        for (int i = 0; i < n; i++) {
            uint8_t rx_byte = rx_buf[i];

            if (rx_byte == 0x00) {
                if (frame_pos > 0 && !discard) {
                    ParsedPacket pkt = packet_parse(frame_buf, frame_pos, decode_buf, sizeof(decode_buf));
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

// ---- Common protocol handlers (v2 handshake / time sync) ----

static void handle_common_cmd(const ParsedPacket& pkt)
{
    uint8_t tx_buf[64];

    switch (static_cast<CommonCmdId>(pkt.type)) {

    case CommonCmdId::SET_PROTOCOL_VERSION: {
        if (pkt.data_len >= 1 && pkt.data[0] == 2) {
            g_protocol_version.store(2, std::memory_order_release);
            ProtocolVersionPayload ack = {.version = 2};
            const uint64_t         now_us = static_cast<uint64_t>(esp_timer_get_time());
            const size_t           len =
                packet_build_v2(static_cast<uint8_t>(CommonTelId::PROTOCOL_VERSION_ACK), next_seq(), now_us,
                                reinterpret_cast<const uint8_t*>(&ack), sizeof(ack), tx_buf, sizeof(tx_buf));
            if (len > 0) {
                usb_cdc_write(tx_buf, len);
            }
            ESP_LOGI(TAG, "protocol version set to 2");
        } else if (pkt.data_len >= 1 && pkt.data[0] == 1) {
            g_protocol_version.store(1, std::memory_order_release);
            ProtocolVersionPayload ack = {.version = 1};
            const size_t           len =
                packet_build(static_cast<uint8_t>(CommonTelId::PROTOCOL_VERSION_ACK), static_cast<uint8_t>(next_seq()),
                             reinterpret_cast<const uint8_t*>(&ack), sizeof(ack), tx_buf, sizeof(tx_buf));
            if (len > 0) {
                usb_cdc_write(tx_buf, len);
            }
            ESP_LOGI(TAG, "protocol version set to 1");
        }
        break;
    }

    case CommonCmdId::TIME_SYNC_REQ: {
        if (pkt.data_len >= 8) {
            uint32_t ping_seq;
            memcpy(&ping_seq, pkt.data, 4);
            // Respond immediately — minimize latency (per PROTOCOL.md §2.6)
            const uint64_t      now_us = static_cast<uint64_t>(esp_timer_get_time());
            TimeSyncRespPayload resp;
            resp.ping_seq = ping_seq;
            resp.t_src_us = now_us;
            const size_t len =
                packet_build_v2(static_cast<uint8_t>(CommonTelId::TIME_SYNC_RESP), next_seq(), now_us,
                                reinterpret_cast<const uint8_t*>(&resp), sizeof(resp), tx_buf, sizeof(tx_buf));
            if (len > 0) {
                usb_cdc_write(tx_buf, len);
            }
        }
        break;
    }

    default:
        break;
    }
}

// ---- Command dispatch ----

static void handle_packet(const ParsedPacket& pkt)
{
    // Handle common protocol commands first (v2 handshake, time sync)
    if (pkt.type == static_cast<uint8_t>(CommonCmdId::SET_PROTOCOL_VERSION) ||
        pkt.type == static_cast<uint8_t>(CommonCmdId::TIME_SYNC_REQ)) {
        handle_common_cmd(pkt);
        return;
    }

    // Track last command seq for v2 causality (written by usb_rx, read by telemetry)
    g_cmd_seq_last.store(pkt.seq, std::memory_order_release);

    switch (static_cast<FaceCmdId>(pkt.type)) {

    case FaceCmdId::SET_STATE: {
        if (pkt.data_len < sizeof(FaceSetStatePayload)) {
            break;
        }
        FaceSetStatePayload sp;
        memcpy(&sp, pkt.data, sizeof(sp));
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        g_cmd_state_mood.store(sp.mood_id, std::memory_order_relaxed);
        g_cmd_state_intensity.store(sp.intensity, std::memory_order_relaxed);
        g_cmd_state_gaze_x.store(sp.gaze_x, std::memory_order_relaxed);
        g_cmd_state_gaze_y.store(sp.gaze_y, std::memory_order_relaxed);
        g_cmd_state_brightness.store(sp.brightness, std::memory_order_relaxed);
        g_cmd_state_us.store(now_us, std::memory_order_release);
        break;
    }

    case FaceCmdId::GESTURE: {
        if (pkt.data_len < sizeof(FaceGesturePayload)) {
            break;
        }
        FaceGesturePayload gp;
        memcpy(&gp, pkt.data, sizeof(gp));
        GestureEvent ev = {};
        ev.gesture_id = gp.gesture_id;
        ev.duration_ms = gp.duration_ms;
        ev.timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
        if (!g_gesture_queue.push(ev)) {
            // Drop oldest so latest gesture still lands.
            g_gesture_queue.pop(nullptr);
            if (!g_gesture_queue.push(ev)) {
                ESP_LOGW(TAG, "gesture queue saturated; dropped gesture id=%u", gp.gesture_id);
            }
        }
        break;
    }

    case FaceCmdId::SET_SYSTEM: {
        if (pkt.data_len < sizeof(FaceSetSystemPayload)) {
            break;
        }
        FaceSetSystemPayload sysp;
        memcpy(&sysp, pkt.data, sizeof(sysp));
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        g_cmd_system_mode.store(sysp.mode, std::memory_order_relaxed);
        g_cmd_system_param.store(sysp.param, std::memory_order_relaxed);
        g_cmd_system_us.store(now_us, std::memory_order_release);
        break;
    }

    case FaceCmdId::SET_TALKING: {
        if (pkt.data_len < sizeof(FaceSetTalkingPayload)) {
            ESP_LOGW(TAG, "SET_TALKING payload too short: %u", static_cast<unsigned>(pkt.data_len));
            break;
        }
        FaceSetTalkingPayload tp;
        memcpy(&tp, pkt.data, sizeof(tp));
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        g_cmd_talking.store(tp.talking ? 1 : 0, std::memory_order_relaxed);
        g_cmd_talking_energy.store(tp.energy, std::memory_order_relaxed);
        g_cmd_talking_us.store(now_us, std::memory_order_release);
        break;
    }

    case FaceCmdId::SET_FLAGS: {
        if (pkt.data_len < sizeof(FaceSetFlagsPayload)) {
            ESP_LOGW(TAG, "SET_FLAGS payload too short: %u", static_cast<unsigned>(pkt.data_len));
            break;
        }
        FaceSetFlagsPayload fp;
        memcpy(&fp, pkt.data, sizeof(fp));
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        g_cmd_flags.store(static_cast<uint8_t>(fp.flags & FACE_FLAGS_ALL), std::memory_order_relaxed);
        g_cmd_flags_us.store(now_us, std::memory_order_release);
        break;
    }

    default:
        ESP_LOGD(TAG, "unknown cmd type 0x%02X", pkt.type);
        break;
    }
}
