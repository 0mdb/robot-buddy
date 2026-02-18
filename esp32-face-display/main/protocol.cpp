#include "protocol.h"
#include <cstring>

// ---- COBS encode ----
// Reference: https://en.wikipedia.org/wiki/Consistent_Overhead_Byte_Stuffing

size_t cobs_encode(const uint8_t* src, size_t len, uint8_t* dst)
{
    size_t read_idx = 0;
    size_t write_idx = 1;
    size_t code_idx = 0;
    uint8_t code = 1;

    while (read_idx < len) {
        if (src[read_idx] == 0x00) {
            dst[code_idx] = code;
            code_idx = write_idx++;
            code = 1;
        } else {
            dst[write_idx++] = src[read_idx];
            code++;
            if (code == 0xFF) {
                dst[code_idx] = code;
                code_idx = write_idx++;
                code = 1;
            }
        }
        read_idx++;
    }
    dst[code_idx] = code;
    return write_idx;
}

// ---- COBS decode ----

size_t cobs_decode(const uint8_t* src, size_t len, uint8_t* dst)
{
    if (len == 0) return 0;

    size_t read_idx = 0;
    size_t write_idx = 0;

    while (read_idx < len) {
        uint8_t code = src[read_idx++];
        if (code == 0) return 0;

        for (uint8_t i = 1; i < code; i++) {
            if (read_idx >= len) return 0;
            dst[write_idx++] = src[read_idx++];
        }

        if (code < 0xFF && read_idx < len) {
            dst[write_idx++] = 0x00;
        }
    }

    return write_idx;
}

// ---- CRC16-CCITT (poly 0x1021, init 0xFFFF) ----

uint16_t crc16(const uint8_t* data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= static_cast<uint16_t>(data[i]) << 8;
        for (int b = 0; b < 8; b++) {
            if (crc & 0x8000)
                crc = (crc << 1) ^ 0x1021;
            else
                crc = crc << 1;
        }
    }
    return crc;
}

// ---- Packet build (MCU → host) ----

size_t packet_build(uint8_t type, uint8_t seq,
                    const uint8_t* payload, size_t payload_len,
                    uint8_t* out, size_t out_cap)
{
    // Must fit conversational telemetry packets (e.g., MIC_AUDIO 10 ms chunk).
    constexpr size_t MAX_RAW_PACKET_LEN = 768;
    const size_t raw_len = 2 + payload_len + 2;
    if (raw_len > MAX_RAW_PACKET_LEN) return 0;

    uint8_t raw[MAX_RAW_PACKET_LEN];
    raw[0] = type;
    raw[1] = seq;
    if (payload_len > 0) {
        memcpy(&raw[2], payload, payload_len);
    }

    uint16_t c = crc16(raw, 2 + payload_len);
    raw[2 + payload_len]     = static_cast<uint8_t>(c & 0xFF);
    raw[2 + payload_len + 1] = static_cast<uint8_t>((c >> 8) & 0xFF);

    const size_t max_cobs = raw_len + (raw_len / 254) + 2;
    if (out_cap < max_cobs + 1) return 0;

    size_t encoded_len = cobs_encode(raw, raw_len, out);
    out[encoded_len] = 0x00;
    return encoded_len + 1;
}

// ---- Packet parse (host → MCU) ----

ParsedPacket packet_parse(const uint8_t* frame, size_t frame_len,
                          uint8_t* decode_buf, size_t decode_buf_len)
{
    ParsedPacket pkt = {};
    pkt.valid = false;

    if (frame_len == 0 || frame_len > decode_buf_len) return pkt;

    size_t decoded_len = cobs_decode(frame, frame_len, decode_buf);

    if (decoded_len < 4) return pkt;

    size_t crc_offset = decoded_len - 2;
    uint16_t received_crc = static_cast<uint16_t>(decode_buf[crc_offset])
                          | (static_cast<uint16_t>(decode_buf[crc_offset + 1]) << 8);
    uint16_t computed_crc = crc16(decode_buf, crc_offset);

    if (received_crc != computed_crc) return pkt;

    pkt.type     = decode_buf[0];
    pkt.seq      = decode_buf[1];
    pkt.data     = &decode_buf[2];
    pkt.data_len = crc_offset - 2;
    pkt.valid    = true;
    return pkt;
}
