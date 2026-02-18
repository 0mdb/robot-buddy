#pragma once
// Face display protocol: COBS framing + CRC16 integrity.
// Wire format identical to esp32-reflex (shared transport layer).
//
// Packet on the wire:
//   [COBS-encoded payload] [0x00 delimiter]
//
// Payload (before COBS):
//   [type:u8] [seq:u8] [data:N bytes] [crc16:u16-LE]

#include <cstdint>
#include <cstddef>

// ---- Packet type IDs ----
// Face commands (host → MCU): 0x20–0x2F
// Face telemetry (MCU → host): 0x90+

enum class FaceCmdId : uint8_t {
    SET_STATE   = 0x20,   // mood + gaze + brightness
    GESTURE     = 0x21,   // trigger one-shot gesture
    SET_SYSTEM  = 0x22,   // system mode overlay
    SET_TALKING = 0x23,   // speaking animation state + energy
    AUDIO_DATA  = 0x24,   // PCM audio chunk for speaker playback
    SET_CONFIG  = 0x25,   // tunable config parameters
};

enum class FaceCfgId : uint8_t {
    AUDIO_TEST_TONE_MS = 0xA0,  // value: u32 duration in ms (1kHz sine)
    AUDIO_MIC_PROBE_MS = 0xA1,  // value: u32 probe window in ms
    AUDIO_REG_DUMP     = 0xA2,  // value: ignored; dumps ES8311 registers to log
    AUDIO_MIC_STREAM_ENABLE = 0xA3,  // value: u32 0=off, non-zero=on
};

enum class FaceTelId : uint8_t {
    FACE_STATUS  = 0x90,  // current mood/gesture/system/flags
    TOUCH_EVENT  = 0x91,  // touch press/release/drag
    MIC_PROBE    = 0x92,  // microphone probe diagnostic result
    HEARTBEAT    = 0x93,  // periodic liveness + telemetry counters
    MIC_AUDIO    = 0x94,  // streaming mic PCM chunk
};

// ---- Payload structs (packed, little-endian) ----

struct __attribute__((packed)) FaceSetStatePayload {
    uint8_t mood_id;       // Mood enum (0-11, see face_state.h)
    uint8_t intensity;     // 0-255
    int8_t  gaze_x;        // -128..+127, scaled to +-MAX_GAZE
    int8_t  gaze_y;        // -128..+127, scaled to +-MAX_GAZE
    uint8_t brightness;    // 0-255 backlight
};

struct __attribute__((packed)) FaceGesturePayload {
    uint8_t  gesture_id;   // GestureId enum
    uint16_t duration_ms;  // 0 = use default
};

struct __attribute__((packed)) FaceSetSystemPayload {
    uint8_t mode;          // SystemMode enum
    uint8_t phase;         // reserved
    uint8_t param;         // mode-specific (e.g. battery level 0-255)
};

struct __attribute__((packed)) FaceSetConfigPayload {
    uint8_t param_id;      // FaceCfgId
    uint8_t value[4];      // little-endian u32 payload
};

struct __attribute__((packed)) FaceStatusPayload {
    uint8_t mood_id;
    uint8_t active_gesture;  // 0xFF = none
    uint8_t system_mode;
    uint8_t flags;           // bit0: touch_active, bit1: audio_playing, bit2: mic_activity
};

struct __attribute__((packed)) TouchEventPayload {
    uint8_t  event_type;   // 0=press, 1=release, 2=drag
    uint16_t x;
    uint16_t y;
};

struct __attribute__((packed)) FaceSetTalkingPayload {
    uint8_t talking;       // 0=stopped, 1=speaking
    uint8_t energy;        // 0-255, audio energy level for eye animation
};

struct __attribute__((packed)) FaceAudioDataPayload {
    uint16_t chunk_len;    // PCM data length in bytes
    // Followed by chunk_len bytes of 16-bit signed 16 kHz mono PCM
};

struct __attribute__((packed)) FaceMicProbePayload {
    uint32_t probe_seq;
    uint32_t duration_ms;
    uint32_t sample_count;
    uint16_t read_timeouts;
    uint16_t read_errors;
    uint16_t selected_rms_x10;
    uint16_t selected_peak;
    int16_t  selected_dbfs_x10;
    uint8_t  selected_channel;  // 0=mono, 1=left, 2=right
    uint8_t  active;
};

struct __attribute__((packed)) FaceMicAudioPayload {
    uint32_t chunk_seq;
    uint16_t chunk_len;    // bytes of PCM that follow
    uint8_t  flags;        // bit0: vad_active (reserved for now)
    uint8_t  reserved;
    // Followed by chunk_len bytes of 16-bit signed 16 kHz mono PCM.
};

struct __attribute__((packed)) FaceHeartbeatPayload {
    uint32_t uptime_ms;
    uint32_t status_tx_count;
    uint32_t touch_tx_count;
    uint32_t mic_probe_seq;
    uint8_t  mic_activity;
    // Optional transport diagnostics (appended for backward compatibility).
    uint32_t usb_tx_calls;
    uint32_t usb_tx_bytes_requested;
    uint32_t usb_tx_bytes_queued;
    uint32_t usb_tx_short_writes;
    uint32_t usb_tx_flush_ok;
    uint32_t usb_tx_flush_not_finished;
    uint32_t usb_tx_flush_timeout;
    uint32_t usb_tx_flush_error;
    uint32_t usb_rx_calls;
    uint32_t usb_rx_bytes;
    uint32_t usb_rx_errors;
    uint32_t usb_line_state_events;
    uint8_t  usb_dtr;
    uint8_t  usb_rts;
    // Optional audio-stream diagnostics (append-only).
    uint32_t speaker_rx_chunks;
    uint32_t speaker_rx_drops;
    uint32_t speaker_rx_bytes;
    uint32_t speaker_play_chunks;
    uint32_t speaker_play_errors;
    uint32_t mic_capture_chunks;
    uint32_t mic_tx_chunks;
    uint32_t mic_tx_drops;
    uint32_t mic_overruns;
    uint32_t mic_queue_depth;
    uint8_t  mic_stream_enabled;
    uint8_t  audio_reserved;
};

// ---- COBS encode/decode ----

size_t cobs_encode(const uint8_t* src, size_t len, uint8_t* dst);
size_t cobs_decode(const uint8_t* src, size_t len, uint8_t* dst);

// ---- CRC16 (CRC-CCITT, poly 0x1021, init 0xFFFF) ----

uint16_t crc16(const uint8_t* data, size_t len);

// ---- Packet building (MCU → host) ----

size_t packet_build(uint8_t type, uint8_t seq,
                    const uint8_t* payload, size_t payload_len,
                    uint8_t* out, size_t out_cap);

// ---- Packet parsing (host → MCU) ----

struct ParsedPacket {
    uint8_t  type;
    uint8_t  seq;
    const uint8_t* data;
    size_t   data_len;
    bool     valid;
};

ParsedPacket packet_parse(const uint8_t* frame, size_t frame_len,
                          uint8_t* decode_buf, size_t decode_buf_len);
