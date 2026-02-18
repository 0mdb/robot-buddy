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
static constexpr uint32_t MIC_AUDIO_PACKETS_PER_LOOP = 3;
static constexpr uint32_t TELEMETRY_LOOP_MS = 10;

void telemetry_task(void* arg)
{
    ESP_LOGI(TAG, "telemetry_task started (%d Hz)", TELEMETRY_HZ);

    uint8_t tx_buf[512];
    uint8_t mic_payload[sizeof(FaceMicAudioPayload) + AUDIO_STREAM_PCM_BYTES];
    uint8_t seq = 0;
    uint32_t status_tx_count = 0;
    uint32_t touch_tx_count = 0;
    uint32_t mic_tx_chunks = 0;
    uint32_t last_mic_probe_seq_sent = 0;
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
        const MicProbeStats mic = audio_get_mic_probe_stats();

        // Stream microphone chunks from audio task (single USB writer: telemetry task).
        AudioMicChunk mic_chunk = {};
        for (uint32_t i = 0; i < MIC_AUDIO_PACKETS_PER_LOOP; i++) {
            if (!audio_mic_stream_take_chunk(&mic_chunk, 0)) {
                break;
            }

            FaceMicAudioPayload mh = {};
            mh.chunk_seq = mic_chunk.seq;
            mh.chunk_len = mic_chunk.len;
            mh.flags = mic_chunk.flags;

            memcpy(mic_payload, &mh, sizeof(mh));
            memcpy(mic_payload + sizeof(mh), mic_chunk.pcm, mic_chunk.len);

            const size_t ml = packet_build(
                static_cast<uint8_t>(FaceTelId::MIC_AUDIO),
                seq++,
                mic_payload,
                sizeof(mh) + mic_chunk.len,
                tx_buf,
                sizeof(tx_buf));
            if (ml > 0) {
                usb_cdc_write(tx_buf, ml);
                mic_tx_chunks++;
            }
        }

        // FACE_STATUS + TOUCH at configured telemetry rate.
        if (last_status_us == 0 || (now_us - last_status_us) >= status_period_us) {
            FaceStatusPayload status = {};
            status.mood_id = g_current_mood.load(std::memory_order_relaxed);
            status.active_gesture = g_active_gesture.load(std::memory_order_relaxed);
            status.system_mode = g_system_mode.load(std::memory_order_relaxed);
            if (g_touch_active.load(std::memory_order_relaxed)) {
                status.flags |= 0x01;
            }
            if (audio_is_playing()) {
                status.flags |= 0x02;
            }
            if (audio_mic_activity_detected()) {
                status.flags |= 0x04;
            }

            const size_t len = packet_build(
                static_cast<uint8_t>(FaceTelId::FACE_STATUS),
                seq++,
                reinterpret_cast<const uint8_t*>(&status),
                sizeof(status),
                tx_buf, sizeof(tx_buf));

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
                    tx_buf, sizeof(tx_buf));

                if (tlen > 0) {
                    usb_cdc_write(tx_buf, tlen);
                    touch_tx_count++;
                }

                TouchSample* slot = g_touch.write_slot();
                slot->event_type = 0xFF;
                g_touch.publish();
            }

            last_status_us = now_us;
        }

        // One-shot mic probe result telemetry.
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
            const AudioStreamDiagSnapshot audio_diag = audio_stream_diag_snapshot();
            hb.speaker_rx_chunks = audio_diag.speaker_rx_chunks;
            hb.speaker_rx_drops = audio_diag.speaker_rx_drops;
            hb.speaker_rx_bytes = audio_diag.speaker_rx_bytes;
            hb.speaker_play_chunks = audio_diag.speaker_play_chunks;
            hb.speaker_play_errors = audio_diag.speaker_play_errors;
            hb.mic_capture_chunks = audio_diag.mic_capture_chunks;
            hb.mic_tx_chunks = mic_tx_chunks;
            hb.mic_tx_drops = audio_diag.mic_tx_drops;
            hb.mic_overruns = audio_diag.mic_overruns;
            hb.mic_queue_depth = audio_diag.mic_queue_depth;
            hb.mic_stream_enabled = audio_diag.mic_stream_enabled;
            hb.audio_reserved = 0;

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
