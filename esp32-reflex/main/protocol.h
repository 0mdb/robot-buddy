#pragma once
// Reflex MCU protocol: COBS framing + CRC16 integrity.
// Wire format identical to esp32-face (shared transport layer).
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
// Reflex commands (host -> MCU): 0x10-0x1F
// Reflex telemetry (MCU -> host): 0x80+

// Protocol handshake / time sync (shared with esp32-face)
enum class CommonCmdId : uint8_t {
    TIME_SYNC_REQ = 0x06,        // Pi -> MCU: {ping_seq:u32, reserved:u32}
    SET_PROTOCOL_VERSION = 0x07, // Pi -> MCU: {version:u8}
};

enum class CommonTelId : uint8_t {
    TIME_SYNC_RESP = 0x86,       // MCU -> Pi: {ping_seq:u32, t_src_us:u64}
    PROTOCOL_VERSION_ACK = 0x87, // MCU -> Pi: {version:u8}
};

enum class CmdId : uint8_t {
    SET_TWIST = 0x10,
    STOP = 0x11,
    ESTOP = 0x12,
    SET_LIMITS = 0x13,
    CLEAR_FAULTS = 0x14,
    SET_CONFIG = 0x15,
};

enum class TelId : uint8_t {
    STATE = 0x80,
};

// ---- Payload structs (packed, little-endian) ----

struct __attribute__((packed)) TwistPayload {
    int16_t v_mm_s;
    int16_t w_mrad_s;
};

struct __attribute__((packed)) StopPayload {
    uint8_t reason;
};

struct __attribute__((packed)) ClearFaultsPayload {
    uint16_t mask;
};

struct __attribute__((packed)) SetConfigPayload {
    uint8_t param_id;
    uint8_t value[4]; // little-endian float, u32, or i32 depending on param
};

struct __attribute__((packed)) StatePayload {
    int16_t  speed_l_mm_s;
    int16_t  speed_r_mm_s;
    int16_t  gyro_z_mrad_s;
    int16_t  accel_x_mg; // milli-g
    int16_t  accel_y_mg;
    int16_t  accel_z_mg;
    uint16_t battery_mv;
    uint16_t fault_flags;
    uint16_t range_mm;
    uint8_t  range_status;
};

// ---- v2 extended payloads ----

struct __attribute__((packed)) StatePayloadV2 {
    // Core fields (19 bytes)
    int16_t  speed_l_mm_s;
    int16_t  speed_r_mm_s;
    int16_t  gyro_z_mrad_s;
    int16_t  accel_x_mg; // milli-g
    int16_t  accel_y_mg;
    int16_t  accel_z_mg;
    uint16_t battery_mv;
    uint16_t fault_flags;
    uint16_t range_mm;
    uint8_t  range_status;
    // v2 additions (8 bytes)
    uint32_t cmd_seq_last_applied; // echo of last command seq applied
    uint32_t t_cmd_applied_us;     // when motor output was committed
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
