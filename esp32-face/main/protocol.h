#pragma once
// Face display protocol: COBS framing + CRC16 integrity.
// Wire format identical to esp32-reflex (shared transport layer).
//
// Packet on the wire:
//   [COBS-encoded payload] [0x00 delimiter]
//
// Payload (before COBS):
//   v1: [type:u8] [seq:u8]                        [data:N bytes] [crc16:u16-LE]
//   v2: [type:u8] [seq:u32-LE] [t_src_us:u64-LE]  [data:N bytes] [crc16:u16-LE]

#include <atomic>
#include <cstddef>
#include <cstdint>

// ---- Packet type IDs ----
// Common commands (host -> MCU): 0x00-0x0F
// Common telemetry (MCU -> host): 0x80-0x8F
// Face commands (host -> MCU): 0x20-0x2F
// Face telemetry (MCU -> host): 0x90+

// Protocol handshake / time sync (shared with esp32-reflex)
enum class CommonCmdId : uint8_t {
    TIME_SYNC_REQ = 0x06,        // Pi -> MCU: {ping_seq:u32, reserved:u32}
    SET_PROTOCOL_VERSION = 0x07, // Pi -> MCU: {version:u8}
};

enum class CommonTelId : uint8_t {
    TIME_SYNC_RESP = 0x86,       // MCU -> Pi: {ping_seq:u32, t_src_us:u64}
    PROTOCOL_VERSION_ACK = 0x87, // MCU -> Pi: {version:u8}
};

enum class FaceCmdId : uint8_t {
    SET_STATE = 0x20,      // mood + gaze + brightness
    GESTURE = 0x21,        // trigger one-shot gesture
    SET_SYSTEM = 0x22,     // system mode overlay
    SET_TALKING = 0x23,    // speaking animation state + energy
    SET_FLAGS = 0x24,      // renderer/animation feature toggles
    SET_CONV_STATE = 0x25, // conversation phase (border driver)
};

enum class FaceTelId : uint8_t {
    FACE_STATUS = 0x90,  // current mood/gesture/system/flags
    TOUCH_EVENT = 0x91,  // raw touch press/release/drag
    BUTTON_EVENT = 0x92, // bottom control buttons (PTT/ACTION)
    HEARTBEAT = 0x93,    // periodic liveness + telemetry counters
};

enum class FaceButtonId : uint8_t {
    PTT = 0,
    ACTION = 1,
};

enum class FaceButtonEventType : uint8_t {
    PRESS = 0,
    RELEASE = 1,
    TOGGLE = 2,
    CLICK = 3,
};

// ---- Payload structs (packed, little-endian) ----

struct __attribute__((packed)) FaceSetStatePayload {
    uint8_t mood_id;    // Mood enum (0-12, see face_state.h)
    uint8_t intensity;  // 0-255
    int8_t  gaze_x;     // -128..+127, scaled to +-MAX_GAZE
    int8_t  gaze_y;     // -128..+127, scaled to +-MAX_GAZE
    uint8_t brightness; // 0-255 backlight
};

struct __attribute__((packed)) FaceGesturePayload {
    uint8_t  gesture_id;  // GestureId enum
    uint16_t duration_ms; // 0 = use default
};

struct __attribute__((packed)) FaceSetSystemPayload {
    uint8_t mode;  // SystemMode enum
    uint8_t phase; // reserved
    uint8_t param; // mode-specific (e.g. battery level 0-255)
};

struct __attribute__((packed)) FaceSetTalkingPayload {
    uint8_t talking; // 0=stopped, 1=speaking
    uint8_t energy;  // 0-255, energy level for mouth/eye animation
};

// Face render/runtime feature flags used by SET_FLAGS.
constexpr uint8_t FACE_FLAG_IDLE_WANDER = 1u << 0;
constexpr uint8_t FACE_FLAG_AUTOBLINK = 1u << 1;
constexpr uint8_t FACE_FLAG_SOLID_EYE = 1u << 2;
constexpr uint8_t FACE_FLAG_SHOW_MOUTH = 1u << 3;
constexpr uint8_t FACE_FLAG_EDGE_GLOW = 1u << 4;
constexpr uint8_t FACE_FLAG_SPARKLE = 1u << 5;
constexpr uint8_t FACE_FLAG_AFTERGLOW = 1u << 6;
constexpr uint8_t FACE_FLAGS_ALL =
    static_cast<uint8_t>(FACE_FLAG_IDLE_WANDER | FACE_FLAG_AUTOBLINK | FACE_FLAG_SOLID_EYE | FACE_FLAG_SHOW_MOUTH |
                         FACE_FLAG_EDGE_GLOW | FACE_FLAG_SPARKLE | FACE_FLAG_AFTERGLOW);

struct __attribute__((packed)) FaceSetFlagsPayload {
    uint8_t flags; // bitfield, see FACE_FLAG_* constants
};

// Conversation phase — drives border animation + gaze/flag overrides.
enum class FaceConvState : uint8_t {
    IDLE = 0,
    ATTENTION = 1,
    LISTENING = 2,
    PTT = 3,
    THINKING = 4,
    SPEAKING = 5,
    ERROR = 6,
    DONE = 7,
};

struct __attribute__((packed)) FaceSetConvStatePayload {
    uint8_t conv_state; // FaceConvState (0-7)
};

struct __attribute__((packed)) FaceStatusPayload {
    uint8_t mood_id;
    uint8_t active_gesture; // 0xFF = none
    uint8_t system_mode;
    uint8_t flags; // bit0: touch_active, bit1: talking, bit2: ptt_listening
};

struct __attribute__((packed)) TouchEventPayload {
    uint8_t  event_type; // 0=press, 1=release, 2=drag
    uint16_t x;
    uint16_t y;
};

struct __attribute__((packed)) FaceButtonEventPayload {
    uint8_t button_id;  // FaceButtonId
    uint8_t event_type; // FaceButtonEventType
    uint8_t state;      // 0/1 toggle state (for PTT), else 0
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

// ---- v2 extended payloads ----

struct __attribute__((packed)) FaceStatusPayloadV2 {
    // Original (4 bytes)
    uint8_t mood_id;
    uint8_t active_gesture;
    uint8_t system_mode;
    uint8_t flags;
    // v2 additions (8 bytes)
    uint32_t cmd_seq_last_applied;
    uint32_t t_state_applied_us; // when display buffer was committed
};

struct __attribute__((packed)) TimeSyncRespPayload {
    uint32_t ping_seq;
    uint64_t t_src_us;
};

struct __attribute__((packed)) ProtocolVersionPayload {
    uint8_t version;
};

// ---- COBS encode/decode ----

size_t cobs_encode(const uint8_t* src, size_t len, uint8_t* dst);
size_t cobs_decode(const uint8_t* src, size_t len, uint8_t* dst);

// ---- CRC16 (CRC-CCITT, poly 0x1021, init 0xFFFF) ----

uint16_t crc16(const uint8_t* data, size_t len);

// ---- Protocol version negotiation ----

extern std::atomic<uint8_t>  g_protocol_version; // 1 or 2, default 1
extern std::atomic<uint32_t> g_tx_seq;           // global monotonic TX seq

inline uint32_t next_seq()
{
    return g_tx_seq.fetch_add(1, std::memory_order_relaxed);
}

// ---- Packet building (MCU -> host) ----

// v1 builder (legacy — kept for backward compat)
size_t packet_build(uint8_t type, uint8_t seq, const uint8_t* payload, size_t payload_len, uint8_t* out,
                    size_t out_cap);

// v2 builder (uses v2 envelope when g_protocol_version==2, else falls back to v1)
size_t packet_build_v2(uint8_t type, uint32_t seq, uint64_t t_src_us, const uint8_t* payload, size_t payload_len,
                       uint8_t* out, size_t out_cap);

// ---- Packet parsing (host -> MCU) ----

struct ParsedPacket {
    uint8_t        type;
    uint32_t       seq;      // u32 in v2, zero-extended u8 in v1
    uint64_t       t_src_us; // 0 in v1
    const uint8_t* data;
    size_t         data_len;
    bool           valid;
};

ParsedPacket packet_parse(const uint8_t* frame, size_t frame_len, uint8_t* decode_buf, size_t decode_buf_len);
