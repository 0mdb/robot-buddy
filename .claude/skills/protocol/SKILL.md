---
name: protocol
description: Reference for the binary serial protocol between supervisor and MCUs. Use when working on protocol changes, adding message types, debugging serial communication, or understanding packet formats.
---

Load the serial protocol reference. Use `$ARGUMENTS` to focus on a specific area, or load the full overview.

## Key source files

Read these files for authoritative protocol definitions:

### Reflex MCU protocol
- `esp32-reflex/main/protocol.h` — command/telemetry enums, packet structs, ConfigParam IDs
- `esp32-reflex/main/protocol.cpp` — COBS encode/decode, CRC16, packet build/parse

### Face MCU protocol
- `esp32-face/main/protocol.h` — face commands, moods, gestures, system modes, v1/v2 envelope, flags
- `esp32-face/main/protocol.cpp` — COBS/CRC16, protocol version negotiation

### Supervisor (Python)
- `supervisor/devices/protocol.py` — Python enums mirroring MCU definitions
- `supervisor/io/serial_transport.py` — async serial with COBS framing, auto-reconnect
- `supervisor/io/cobs.py` — COBS encode/decode
- `supervisor/io/crc.py` — CRC16-CCITT

### Docs
- `docs/protocols.md` — wire protocol specification

## Wire format

```
On the wire:  [COBS-encoded payload] [0x00 delimiter]

v1 envelope (both MCUs):
  [type:u8] [seq:u8] [payload:N] [crc16:u16-LE]

v2 envelope (Face MCU only, after negotiation):
  [type:u8] [seq:u32-LE] [t_src_us:u64-LE] [payload:N] [crc16:u16-LE]
```

- CRC16-CCITT: poly=0x1021, init=0xFFFF, covers everything before CRC
- COBS: escapes 0x00 bytes, ~0.4% overhead
- Endianness: little-endian throughout
- Baudrate: 115200

## Reflex commands (Supervisor → Reflex)

| Command      | ID   | Payload                        |
|--------------|------|--------------------------------|
| SET_TWIST    | 0x10 | v_mm_s(i16) w_mrad_s(i16)     |
| STOP         | 0x11 | reason(u8)                     |
| ESTOP        | 0x12 | (empty)                        |
| SET_LIMITS   | 0x13 | (reserved)                     |
| CLEAR_FAULTS | 0x14 | mask(u16)                      |
| SET_CONFIG   | 0x15 | param_id(u8) value(4 bytes)    |

## Reflex telemetry (Reflex → Supervisor)

| Telemetry | ID   | Payload (13 bytes)                                                              |
|-----------|------|---------------------------------------------------------------------------------|
| STATE     | 0x80 | speed_l(i16) speed_r(i16) gyro_z(i16) battery(u16) faults(u16) range(u16) range_status(u8) |

## Face commands (Supervisor → Face)

| Command     | ID   | Payload                                            |
|-------------|------|----------------------------------------------------|
| SET_STATE   | 0x20 | mood(u8) intensity(u8) gaze_x(i8) gaze_y(i8) brightness(u8) |
| GESTURE     | 0x21 | gesture_id(u8) duration_ms(u16)                    |
| SET_SYSTEM  | 0x22 | mode(u8) phase(u8) param(u8)                       |
| SET_TALKING | 0x23 | talking(u8) energy(u8)                             |
| SET_FLAGS   | 0x24 | flags(u8)                                          |

## Face telemetry (Face → Supervisor)

| Telemetry    | ID   | Payload                                              |
|--------------|------|------------------------------------------------------|
| FACE_STATUS  | 0x90 | mood(u8) gesture(u8) system_mode(u8) flags(u8)       |
| TOUCH_EVENT  | 0x91 | event_type(u8) x(u16) y(u16)                         |
| BUTTON_EVENT | 0x92 | button_id(u8) event_type(u8) state(u8) reserved(u8)  |
| HEARTBEAT    | 0x93 | uptime_ms(u32) + counters + USB diag (64 bytes)      |

## Common (protocol sync)

| Message              | ID   | Direction | Payload                        |
|----------------------|------|-----------|--------------------------------|
| TIME_SYNC_REQ        | 0x06 | Pi → MCU  | ping_seq(u32) reserved(u32)    |
| SET_PROTOCOL_VERSION | 0x07 | Pi → MCU  | version(u8)                    |
| TIME_SYNC_RESP       | 0x86 | MCU → Pi  | ping_seq(u32) t_src_us(u64)    |
| PROTOCOL_VERSION_ACK | 0x87 | MCU → Pi  | version(u8)                    |

## Adding a new message type

When adding a new command or telemetry type, update ALL of these:

1. **MCU protocol.h** — add enum value, define payload struct
2. **MCU protocol.cpp** — add build/parse function
3. **Supervisor protocol.py** — add matching Python enum + struct format
4. **Supervisor device client** — add send/receive handling
5. **Tests** — add encoding/decoding round-trip test
