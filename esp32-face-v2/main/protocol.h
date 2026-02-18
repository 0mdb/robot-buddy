#pragma once
// Face display protocol: COBS framing + CRC16 integrity.
// Wire format identical to esp32-reflex (shared transport layer).
//
// Packet on the wire:
//   [COBS-encoded payload] [0x00 delimiter]
//
// Payload (before COBS):
//   [type:u8] [seq:u8] [data:N bytes] [crc16:u16-LE]

#include <cstddef>
#include <cstdint>

// ---- Packet type IDs ----
// Face commands (host -> MCU): 0x20-0x2F
// Face telemetry (MCU -> host): 0x90+

enum class FaceCmdId : uint8_t {
    SET_STATE   = 0x20,   // mood + gaze + brightness
    GESTURE     = 0x21,   // trigger one-shot gesture
    SET_SYSTEM  = 0x22,   // system mode overlay
    SET_TALKING = 0x23,   // speaking animation state + energy
};

enum class FaceTelId : uint8_t {
    FACE_STATUS  = 0x90,  // current mood/gesture/system/flags
    TOUCH_EVENT  = 0x91,  // raw touch press/release/drag
    BUTTON_EVENT = 0x92,  // bottom control buttons (PTT/ACTION)
    HEARTBEAT    = 0x93,  // periodic liveness + telemetry counters
};

enum class FaceButtonId : uint8_t {
    PTT    = 0,
    ACTION = 1,
};

enum class FaceButtonEventType : uint8_t {
    PRESS   = 0,
    RELEASE = 1,
    TOGGLE  = 2,
    CLICK   = 3,
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

struct __attribute__((packed)) FaceSetTalkingPayload {
    uint8_t talking;       // 0=stopped, 1=speaking
    uint8_t energy;        // 0-255, energy level for mouth/eye animation
};

struct __attribute__((packed)) FaceStatusPayload {
    uint8_t mood_id;
    uint8_t active_gesture;  // 0xFF = none
    uint8_t system_mode;
    uint8_t flags;           // bit0: touch_active, bit1: talking, bit2: ptt_listening
};

struct __attribute__((packed)) TouchEventPayload {
    uint8_t  event_type;   // 0=press, 1=release, 2=drag
    uint16_t x;
    uint16_t y;
};

struct __attribute__((packed)) FaceButtonEventPayload {
    uint8_t button_id;     // FaceButtonId
    uint8_t event_type;    // FaceButtonEventType
    uint8_t state;         // 0/1 toggle state (for PTT), else 0
    uint8_t reserved;
};

struct __attribute__((packed)) FaceHeartbeatPayload {
    uint32_t uptime_ms;
    uint32_t status_tx_count;
    uint32_t touch_tx_count;
    uint32_t button_tx_count;
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
    uint8_t  ptt_listening;
    uint8_t  reserved;
};

// ---- COBS encode/decode ----

size_t cobs_encode(const uint8_t* src, size_t len, uint8_t* dst);
size_t cobs_decode(const uint8_t* src, size_t len, uint8_t* dst);

// ---- CRC16 (CRC-CCITT, poly 0x1021, init 0xFFFF) ----

uint16_t crc16(const uint8_t* data, size_t len);

// ---- Packet building (MCU -> host) ----

size_t packet_build(uint8_t type, uint8_t seq,
                    const uint8_t* payload, size_t payload_len,
                    uint8_t* out, size_t out_cap);

// ---- Packet parsing (host -> MCU) ----

struct ParsedPacket {
    uint8_t  type;
    uint8_t  seq;
    const uint8_t* data;
    size_t   data_len;
    bool     valid;
};

ParsedPacket packet_parse(const uint8_t* frame, size_t frame_len,
                          uint8_t* decode_buf, size_t decode_buf_len);
