#include "usb_rx.h"
#include "protocol.h"
#include "config.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "driver/usb_serial_jtag.h"

#include <cstring>

static const char* TAG = "usb_rx";

static void handle_packet(const ParsedPacket& pkt);

// Max raw frame size between 0x00 delimiters (before COBS decode).
// Largest expected command: type(1) + seq(1) + TwistPayload(4) + crc(2) = 8,
// plus COBS overhead. 64 bytes is generous.
static constexpr size_t MAX_FRAME = 64;

void usb_rx_task(void* arg)
{
    ESP_LOGI(TAG, "usb_rx_task started");

    // NOTE: USB Serial/JTAG driver is installed in app_main before tasks start.
    // Both usb_rx_task and telemetry_task share the driver.

    uint8_t frame_buf[MAX_FRAME];
    size_t  frame_pos = 0;
    bool    discard = false; // true = skip bytes until next 0x00 delimiter

    uint8_t decode_buf[MAX_FRAME];

    while (true) {
        // Read available bytes (block up to 50ms if nothing available)
        uint8_t rx_byte;
        int     n = usb_serial_jtag_read_bytes(&rx_byte, 1, pdMS_TO_TICKS(50));
        if (n <= 0) continue;

        if (rx_byte == 0x00) {
            // End of COBS frame
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

// ---- Command dispatch ----

static void handle_packet(const ParsedPacket& pkt)
{
    switch (static_cast<CmdId>(pkt.type)) {

    case CmdId::SET_TWIST: {
        if (pkt.data_len < sizeof(TwistPayload)) break;
        TwistPayload tw;
        memcpy(&tw, pkt.data, sizeof(tw));

        Command* slot = g_cmd.write_slot();
        slot->v_mm_s = tw.v_mm_s;
        slot->w_mrad_s = tw.w_mrad_s;
        g_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case CmdId::STOP: {
        // Soft stop: zero the command
        Command* slot = g_cmd.write_slot();
        slot->v_mm_s = 0;
        slot->w_mrad_s = 0;
        g_cmd.publish(static_cast<uint32_t>(esp_timer_get_time()));
        break;
    }

    case CmdId::ESTOP: {
        // Hard stop: set fault flag, safety_task will handle the kill
        g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::ESTOP), std::memory_order_relaxed);
        break;
    }

    case CmdId::CLEAR_FAULTS: {
        if (pkt.data_len < sizeof(ClearFaultsPayload)) break;
        ClearFaultsPayload cf;
        memcpy(&cf, pkt.data, sizeof(cf));
        g_fault_flags.fetch_and(~cf.mask, std::memory_order_relaxed);
        ESP_LOGI(TAG, "faults cleared: mask=0x%04X", cf.mask);
        break;
    }

    case CmdId::SET_CONFIG: {
        if (pkt.data_len < sizeof(SetConfigPayload)) break;
        SetConfigPayload sc;
        memcpy(&sc, pkt.data, sizeof(sc));
        if (config_apply(sc.param_id, sc.value)) {
            ESP_LOGI(TAG, "config param 0x%02X updated", sc.param_id);
        } else {
            ESP_LOGW(TAG, "config param 0x%02X rejected", sc.param_id);
        }
        break;
    }

    default:
        ESP_LOGD(TAG, "unknown cmd type 0x%02X", pkt.type);
        break;
    }
}
