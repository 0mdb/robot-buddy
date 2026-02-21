#pragma once
// On-wire protocol: COBS framing + CRC16 integrity.
//
// Packet format on the wire:
//   [COBS-encoded payload] [0x00 delimiter]
//
// Payload (before COBS encoding):
//   [type:u8] [seq:u8] [data:N bytes] [crc16:u16-LE]
//
// CRC16 covers: type + seq + data (everything except the CRC itself).

#include <cstdint>
#include <cstddef>

// ---- Packet type IDs ----
// Commands (host → MCU): 0x10–0x1F
// Telemetry (MCU → host): 0x80+

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
    uint16_t battery_mv;
    uint16_t fault_flags;
    uint16_t range_mm;
    uint8_t  range_status;
};

// ---- COBS encode/decode ----

// COBS encode `src` (len bytes) into `dst`.
// `dst` must have room for at least len + ceil(len/254) + 1 bytes.
// Returns number of bytes written to dst (does NOT include the trailing 0x00 delimiter).
size_t cobs_encode(const uint8_t* src, size_t len, uint8_t* dst);

// COBS decode `src` (len bytes, NOT including the 0x00 delimiter) into `dst`.
// `dst` must have room for at least len bytes.
// Returns decoded length, or 0 on error.
size_t cobs_decode(const uint8_t* src, size_t len, uint8_t* dst);

// ---- CRC16 (CRC-CCITT / X.25, poly 0x1021, init 0xFFFF) ----

uint16_t crc16(const uint8_t* data, size_t len);

// ---- Packet building (MCU → host) ----

// Build a complete wire-ready packet (COBS-encoded + 0x00 delimiter).
// `type` is the TelId, `seq` is the sequence counter, `payload`/`payload_len`
// is the raw data. Output written to `out`, returns total bytes including delimiter.
// `out` must have room for: (2 + payload_len + 2) * COBS overhead + 1.
// Safe buffer size: payload_len + 8.
size_t packet_build(uint8_t type, uint8_t seq, const uint8_t* payload, size_t payload_len, uint8_t* out,
                    size_t out_cap);

// ---- Packet parsing (host → MCU) ----

struct ParsedPacket {
    uint8_t        type;
    uint8_t        seq;
    const uint8_t* data; // points into caller's decode buffer
    size_t         data_len;
    bool           valid; // CRC passed and structure is sane
};

// Parse a COBS-decoded frame. `frame`/`frame_len` is the raw bytes between
// 0x00 delimiters (before COBS decode). Uses `decode_buf` as scratch space
// (must be at least `frame_len` bytes).
// Returns ParsedPacket with valid=true on success.
ParsedPacket packet_parse(const uint8_t* frame, size_t frame_len, uint8_t* decode_buf, size_t decode_buf_len);
