# MCU Firmware Upgrade Plan — v2 Protocol Support

**Version:** 1.0-draft
**Date:** 2026-02-20
**Scope:** In-place refactor of `esp32-reflex` and `esp32-face-v2` firmware to support PROTOCOL.md §3.2 and §5

---

## Decision: Refactor In-Place

Both MCUs are upgraded in-place. No v2 fork. Rationale:

- Changes are surgical — only the protocol serialization layer and shared state additions. Task structure, safety system, control loop, and rendering pipeline are untouched.
- The handshake (SET_PROTOCOL_VERSION) provides backward compatibility — Pi can talk v1 or v2 per-port.
- A fork would create two near-identical codebases with ongoing maintenance burden for zero architectural benefit.

---

## 1. Current State

### Common Protocol Layer (Both MCUs)

```
Wire format:  [type:u8] [seq:u8] [data:N] [crc16:u16-LE]  →  COBS  →  [frame] [0x00]
```

| Aspect | Reflex | Face |
|--------|--------|------|
| Protocol files | `protocol.h` / `protocol.cpp` | Same (independent copy) |
| COBS/CRC | Identical implementation | Identical |
| CRC poly | 0x1021 CCITT, init 0xFFFF | Same |
| seq | u8, per-packet | u8, shared counter |
| t_src_us in packet | None | None |
| MAX_FRAME | 64 bytes | 768 bytes |
| USB transport | `usb_serial_jtag` | TinyUSB CDC |
| Telemetry rate | 20 Hz | 20 Hz |
| `esp_timer_get_time()` | Used internally, cast to u32 | Used internally, cast to u32 |

### Reflex-Specific

| Item | Detail |
|------|--------|
| Control loop | 100 Hz on PRO core (priority 10) |
| Safety task | 50 Hz on PRO core (priority 6) |
| IMU task | 400 Hz on PRO core (priority 8) |
| Telemetry task | 20 Hz on APP core (priority 3) |
| USB RX task | Event-driven on APP core (priority 5) |
| Range task | 20 Hz on APP core (priority 4) |
| STATE payload | 15 bytes (speeds, gyro, battery, faults, range) |
| Shared state | Seqlock (telemetry), double-buffer (IMU, cmd, range), atomics (faults) |
| Command buffer | Ping-pong with `last_cmd_us` timestamp |

### Face-Specific

| Item | Detail |
|------|--------|
| Render loop | 30 FPS on core 0 (priority 5) |
| Telemetry task | 20 Hz on core 1 (priority 6) |
| USB RX task | Event-driven on core 1 (priority 7) |
| FACE_STATUS payload | 4 bytes (mood, gesture, system_mode, flags) |
| Touch/Button | Double-buffered with u32 timestamp_us |
| Shared state | Atomic globals per command type, double-buffer (touch, button) |
| Gesture queue | Ring buffer, capacity 16 |

---

## 2. Target State (v2 Envelope)

### Wire Format

```
v1: [type:u8] [seq:u8]                        [data:N] [crc16:u16-LE]   (4 + N bytes)
v2: [type:u8] [seq:u32-LE] [t_src_us:u64-LE]  [data:N] [crc16:u16-LE]   (15 + N bytes)
```

Header overhead increases from 4 bytes to 15 bytes (+11). COBS overhead unchanged (~1 byte per 254).

### New Packet Types (Both MCUs)

| Type ID | Direction | Name | Payload |
|---------|-----------|------|---------|
| `0x06` | Pi → MCU | `TIME_SYNC_REQ` | `{ping_seq:u32, reserved:u32}` (8 bytes) |
| `0x07` | Pi → MCU | `SET_PROTOCOL_VERSION` | `{version:u8}` (1 byte) |
| `0x86` | MCU → Pi | `TIME_SYNC_RESP` | `{ping_seq:u32, t_src_us:u64}` (12 bytes) |
| `0x87` | MCU → Pi | `PROTOCOL_VERSION_ACK` | `{version:u8}` (1 byte) |

### Extended Telemetry Payloads

**Reflex STATE v2 (0x80):** 15 → 23 bytes

```c
struct StatePayloadV2 {
    // Original (15 bytes)
    int16_t  speed_l_mm_s;
    int16_t  speed_r_mm_s;
    int16_t  gyro_z_mrad_s;
    uint16_t battery_mv;
    uint16_t fault_flags;
    uint16_t range_mm;
    uint8_t  range_status;
    // v2 additions (8 bytes)
    uint32_t cmd_seq_last_applied;
    uint32_t t_cmd_applied_us;       // low 32 bits of MCU time when applied
};
```

**Face FACE_STATUS v2 (0x90):** 4 → 12 bytes

```c
struct FaceStatusPayloadV2 {
    // Original (4 bytes)
    uint8_t mood_id;
    uint8_t active_gesture;
    uint8_t system_mode;
    uint8_t flags;
    // v2 additions (8 bytes)
    uint32_t cmd_seq_last_applied;
    uint32_t t_state_applied_us;     // when display buffer was committed
};
```

Pi-side parser uses payload length to distinguish v1 from v2 (already specified in PROTOCOL.md §5.2/§5.3).

### Packet Size Budget

| Packet | v1 total | v2 total | v2 + COBS (worst) | Fits MAX_FRAME? |
|--------|----------|----------|-------------------|-----------------|
| Reflex STATE | ~22 | ~41 | ~43 | 64: yes (tight). Bump to 128. |
| Face STATUS | ~11 | ~30 | ~32 | 768: yes |
| TIME_SYNC_RESP | — | ~30 | ~32 | Both: yes |
| SET_TWIST (cmd) | ~9 | ~20 | ~22 | Both: yes |

**Action:** Bump Reflex `MAX_FRAME` from 64 to 128.

---

## 3. Implementation Plan

### Phase 1: Protocol Layer (Both MCUs — identical changes)

**Files:** `protocol.h`, `protocol.cpp`

#### 1a. Add version state

```c
// protocol.h
extern std::atomic<uint8_t> g_protocol_version;  // 1 or 2, default 1
```

#### 1b. Expand `packet_build()` for v2 envelope

Current signature:
```c
int packet_build(uint8_t type, uint8_t seq, const uint8_t* data, size_t data_len,
                 uint8_t* out, size_t out_cap);
```

New signature (v2-aware):
```c
int packet_build_v2(uint8_t type, uint32_t seq, uint64_t t_src_us,
                    const uint8_t* data, size_t data_len,
                    uint8_t* out, size_t out_cap);
```

- If `g_protocol_version == 1`: call existing `packet_build()` (truncate seq to u8, no t_src_us)
- If `g_protocol_version == 2`: build v2 envelope

Keep `packet_build()` as-is for backward compatibility during transition. Add `packet_build_v2()` alongside.

#### 1c. Expand `packet_parse()` for v2 envelope

Current `ParsedPacket`:
```c
struct ParsedPacket {
    uint8_t  type;
    uint8_t  seq;
    const uint8_t* data;
    size_t   data_len;
    bool     valid;
};
```

Expanded:
```c
struct ParsedPacket {
    uint8_t  type;
    uint32_t seq;          // u32 in v2, zero-extended u8 in v1
    uint64_t t_src_us;     // 0 in v1
    const uint8_t* data;
    size_t   data_len;
    bool     valid;
};
```

Parser checks `g_protocol_version` to know which envelope to decode. CRC covers everything except itself in both versions.

#### 1d. Add SET_PROTOCOL_VERSION handler

In `usb_rx.cpp`, add case in `handle_packet()`:

```c
case 0x07: {  // SET_PROTOCOL_VERSION
    if (pkt.data_len >= 1 && pkt.data[0] == 2) {
        g_protocol_version.store(2, std::memory_order_release);
        // Send ACK with version=2
        uint8_t ack_payload = 2;
        packet_build_v2(0x87, next_seq(), esp_timer_get_time(),
                        &ack_payload, 1, tx_buf, sizeof(tx_buf));
        usb_write(tx_buf, len);
    }
    break;
}
```

#### 1e. Add TIME_SYNC handler

In `usb_rx.cpp`:

```c
case 0x06: {  // TIME_SYNC_REQ
    if (pkt.data_len >= 8) {
        uint32_t ping_seq;
        memcpy(&ping_seq, pkt.data, 4);
        // Build TIME_SYNC_RESP immediately (minimize latency)
        uint64_t now_us = esp_timer_get_time();
        TimeSyncRespPayload resp = { .ping_seq = ping_seq, .t_src_us = now_us };
        // t_src_us in envelope = now_us (response assembly time, per §2.6)
        packet_build_v2(0x86, next_seq(), now_us,
                        (uint8_t*)&resp, sizeof(resp), tx_buf, sizeof(tx_buf));
        usb_write(tx_buf, len);
    }
    break;
}
```

**Critical:** TIME_SYNC_RESP must be sent immediately in the RX handler — no queuing, no deferred task. The `t_src_us` in the response must be captured as close to serialization as possible (per PROTOCOL.md §2.6).

#### 1f. Global sequence counter

Replace per-type u8 counters with a single global u32:

```c
// protocol.h
extern std::atomic<uint32_t> g_tx_seq;

inline uint32_t next_seq() {
    return g_tx_seq.fetch_add(1, std::memory_order_relaxed);
}
```

#### 1g. Bump Reflex MAX_FRAME

In `usb_rx.cpp`:
```c
static constexpr size_t MAX_FRAME = 128;  // was 64
```

---

### Phase 2: Shared State Additions

#### Reflex

**File:** `shared_state.h`

Add to `CommandBuffer`:
```c
struct Command {
    int16_t v_mm_s;
    int16_t w_mrad_s;
    uint32_t cmd_seq;       // NEW: from v2 envelope
};
```

Add to `TelemetryState`:
```c
struct TelemetryState {
    // ...existing fields...
    uint32_t cmd_seq_last_applied;   // NEW
    uint32_t t_cmd_applied_us;       // NEW: low 32 bits of esp_timer when applied
    // seqlock unchanged
};
```

**File:** `usb_rx.cpp`

When handling SET_TWIST, store `pkt.seq` in the command buffer:
```c
case CmdId::SET_TWIST: {
    auto* slot = g_cmd.next();
    slot->v_mm_s = payload->v_mm_s;
    slot->w_mrad_s = payload->w_mrad_s;
    slot->cmd_seq = pkt.seq;           // NEW: v2 seq (0 in v1)
    g_cmd.publish(now_us);
    break;
}
```

**File:** `control.cpp`

When applying command in control loop tick:
```c
auto* cmd = g_cmd.current.load(std::memory_order_acquire);
// ...apply v_mm_s, w_mrad_s...
// Track last applied
tel.cmd_seq_last_applied = cmd->cmd_seq;
tel.t_cmd_applied_us = static_cast<uint32_t>(esp_timer_get_time());
```

**File:** `telemetry.cpp`

Build v2 payload when `g_protocol_version == 2`:
```c
if (g_protocol_version.load(std::memory_order_acquire) == 2) {
    StatePayloadV2 payload = { ...existing fields..., tel.cmd_seq_last_applied, tel.t_cmd_applied_us };
    packet_build_v2(0x80, next_seq(), t_src_us, (uint8_t*)&payload, sizeof(payload), ...);
} else {
    StatePayload payload = { ...existing fields... };
    packet_build(0x80, seq_u8++, (uint8_t*)&payload, sizeof(payload), ...);
}
```

#### Face

**File:** `shared_state.h`

Add atomic globals for command tracking:
```c
extern std::atomic<uint32_t> g_cmd_seq_last;        // last received cmd seq
extern std::atomic<uint32_t> g_cmd_applied_us;      // when display committed
```

**File:** `usb_rx.cpp`

On every command dispatch, store `pkt.seq`:
```c
g_cmd_seq_last.store(pkt.seq, std::memory_order_release);
```

**File:** `face_ui.cpp`

After display buffer commit (render completion):
```c
g_cmd_applied_us.store(static_cast<uint32_t>(esp_timer_get_time()), std::memory_order_release);
```

**File:** `telemetry.cpp`

Build v2 status when protocol == 2:
```c
if (g_protocol_version.load(std::memory_order_acquire) == 2) {
    FaceStatusPayloadV2 status = {
        .mood_id = ..., .active_gesture = ..., .system_mode = ..., .flags = ...,
        .cmd_seq_last_applied = g_cmd_seq_last.load(std::memory_order_acquire),
        .t_state_applied_us = g_cmd_applied_us.load(std::memory_order_acquire)
    };
    packet_build_v2(0x90, next_seq(), t_src_us, ...);
} else {
    // existing v1 path
}
```

---

### Phase 3: t_src_us Semantics (Per PROTOCOL.md §2.6)

Each packet type timestamps at the specified acquisition moment:

| MCU | Packet | `t_src_us` source |
|-----|--------|-------------------|
| Reflex | STATE (0x80) | `esp_timer_get_time()` at control loop tick start |
| Reflex | TIME_SYNC_RESP (0x86) | `esp_timer_get_time()` immediately before serialization |
| Face | FACE_STATUS (0x90) | `esp_timer_get_time()` at render completion (`lv_obj_invalidate`) |
| Face | TOUCH_EVENT (0x91) | `esp_timer_get_time()` from touch ISR/callback |
| Face | BUTTON_EVENT (0x92) | `esp_timer_get_time()` from button ISR/callback |
| Face | HEARTBEAT (0x93) | `esp_timer_get_time()` at heartbeat assembly |
| Face | TIME_SYNC_RESP (0x86) | `esp_timer_get_time()` immediately before serialization |

**Important:** Use full u64 from `esp_timer_get_time()` for the v2 envelope field. Internal dt calculations can continue using u32 casts — the u64 is only needed for the wire format.

---

## 4. Files Changed Per MCU

### Reflex (`esp32-reflex/main/`)

| File | Changes |
|------|---------|
| `protocol.h` | Add v2 structs, new CmdId/TelId entries, `g_protocol_version`, `g_tx_seq`, `next_seq()`, `ParsedPacket` expansion |
| `protocol.cpp` | Add `packet_build_v2()`, update `packet_parse()` for v2 envelope |
| `shared_state.h` | Add `cmd_seq` to `Command`, add `cmd_seq_last_applied` + `t_cmd_applied_us` to `TelemetryState` |
| `usb_rx.cpp` | Add SET_PROTOCOL_VERSION + TIME_SYNC_REQ handlers, store `pkt.seq` in command buffer, bump MAX_FRAME to 128 |
| `telemetry.cpp` | Conditional v1/v2 STATE payload building, use `next_seq()` + `t_src_us` |
| `control.cpp` | Track `cmd_seq_last_applied` + `t_cmd_applied_us` in telemetry publish |

**Unchanged:** `safety.cpp`, `motor.cpp`, `encoder.cpp`, `imu.cpp`, `range_ultrasonic.cpp`, `config.cpp`, `app_main.cpp`, `pin_map.h`

### Face (`esp32-face-v2/main/`)

| File | Changes |
|------|---------|
| `protocol.h` | Add v2 structs, new CmdId/TelId entries, `g_protocol_version`, `g_tx_seq`, `next_seq()`, `ParsedPacket` expansion |
| `protocol.cpp` | Add `packet_build_v2()`, update `packet_parse()` for v2 envelope |
| `shared_state.h` | Add `g_cmd_seq_last`, `g_cmd_applied_us` atomics |
| `usb_rx.cpp` | Add SET_PROTOCOL_VERSION + TIME_SYNC_REQ handlers, store `pkt.seq` on dispatch |
| `telemetry.cpp` | Conditional v1/v2 STATUS payload building, use `next_seq()` + `t_src_us` for all packet types |
| `face_ui.cpp` | Store render-completion timestamp in `g_cmd_applied_us` |

**Unchanged:** `face_state.cpp`, `display.cpp`, `touch.cpp`, `led.cpp`, `system_overlay_v2.cpp`, `usb_composite.cpp`, `app_main.cpp`, `config.h`, `pin_map.h`

---

## 5. Shared Code Opportunity

Both MCUs have independent but identical copies of `protocol.h` / `protocol.cpp` (COBS, CRC16, packet_build, packet_parse). The v2 changes are identical for both.

**Options:**
1. **Copy-paste (current approach):** Apply identical changes to both. Simple, no build system changes.
2. **Shared component:** Extract to `components/rb_protocol/` as an ESP-IDF component, referenced by both projects via `EXTRA_COMPONENT_DIRS`.

**Recommendation:** Option 1 for now. The protocol layer is ~300 lines. A shared component adds CMake complexity for minimal benefit. Revisit if a third MCU is added.

---

## 6. Testing Strategy

### Unit Tests (Pi-side, pytest)

The existing Pi-side `supervisor/tests/` already tests protocol encoding/decoding and CRC. These need to be extended:

- **v2 envelope round-trip:** Build v2 packet → COBS encode → COBS decode → parse → verify seq(u32), t_src_us(u64), payload
- **v1/v2 coexistence:** Build v1 packet, parse with v2-aware parser (should still work — payload length distinguishes)
- **TIME_SYNC_RESP parsing:** Verify ping_seq echo and t_src_us extraction
- **StatePayloadV2 parsing:** Verify cmd_seq_last_applied and t_cmd_applied_us fields
- **FaceStatusPayloadV2 parsing:** Same

### Integration Tests (Pi + MCU)

- **Handshake:** Pi sends SET_PROTOCOL_VERSION(2), verify ACK received, verify subsequent packets use v2 envelope
- **Handshake timeout:** Pi sends SET_PROTOCOL_VERSION(2) to v1-only MCU (no response), verify fallback to v1
- **TIME_SYNC round-trip:** Pi sends TIME_SYNC_REQ, verify RESP with valid ping_seq echo and plausible t_src_us
- **Command causality:** Pi sends SET_TWIST with known seq, verify STATE echoes `cmd_seq_last_applied` matches
- **Mixed mode:** Reflex at v2, Face at v1 — verify independent operation

### MCU-Side Validation

- **Packet size:** Verify all v2 packets fit within MAX_FRAME after COBS encoding
- **Timing:** Verify TIME_SYNC_RESP latency < 1 ms (measure with logic analyzer or USB sniffer)
- **No regression:** All existing commands still work after v2 handshake
- **Seq monotonicity:** Verify `g_tx_seq` increments correctly across all packet types

---

## 7. Rollout Order

1. **Flash Reflex MCU first** — it has the safety-critical control loop. Verify handshake + TIME_SYNC + cmd_seq echo with existing Pi supervisor (v1 fallback).
2. **Flash Face MCU second** — verify handshake + TIME_SYNC + FACE_STATUS v2.
3. **Update Pi-side parser** — add v2 envelope parsing, v2 payload parsing (length-based detection).
4. **Enable TIME_SYNC** — activate the async sync task on Pi for v2-negotiated devices.
5. **Enable causality logging** — start recording cmd_seq round-trips.

Each step is independently testable. Mixed v1/v2 is supported at every stage.

---

## 8. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| v2 packet too large for USB buffer | Budget analysis above shows max ~43 bytes. USB CDC buffers are typically 64+ bytes. |
| TIME_SYNC_RESP delayed by task scheduling | Handler runs in USB RX task (highest IO priority). Response is built and written inline — no queue. |
| u32 timestamp wrap in t_cmd_applied_us | 71 minute wrap. Acceptable for command latency measurement (typical latency < 10 ms). Pi uses full u64 t_src_us from envelope for sync. |
| Handshake lost on noisy USB | Pi retries once on reconnect (per PROTOCOL.md §3.2). If still no ACK, stays v1. |
| Breaking existing Pi supervisor | Handshake ensures v2 is opt-in. No v2 packets are sent until Pi requests version 2. |
| Reflex safety regression | Safety task, control loop, motor driver, fault detection — all unchanged. Only the telemetry serialization path is modified. |
