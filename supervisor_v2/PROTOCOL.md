# Robot Buddy v2 — Unified Message Protocol Specification

**Version:** 2.0-draft
**Date:** 2026-02-20
**Status:** Canonical reference for all message boundaries

---

## 1. Design Principles

### 1.1 Monotonic Clocks Only

No wall clock (`time.time()`, `gettimeofday`, NTP) in any control path, safety decision, or causality chain. Wall time may appear only in human-readable log decorations. All timing uses:

- **Pi:** `time.monotonic_ns()` (`CLOCK_MONOTONIC`, nanosecond resolution)
- **Reflex MCU:** `esp_timer_get_time()` (microseconds since boot)
- **Face MCU:** `esp_timer_get_time()` (microseconds since boot)
- **Server:** `time.monotonic_ns()` (informational only — never used for control decisions)

### 1.2 Timestamp at Acquisition Time

Every datum is timestamped when it was *acquired*, not when it was published, queued, serialized, or received:

- IMU samples → at I2C/SPI read completion or DRDY interrupt
- Encoder readings → at control loop tick boundary
- Ultrasonic range → at echo completion
- Camera frames → sensor timestamp if available, else Pi receive time
- Vision detections → reference the source frame timestamp, not detection-completion time
- Button/touch events → at interrupt/detection on the MCU
- Motor PWM applied → when update committed

### 1.3 Sequence Numbers Everywhere

Every message carries a monotonically increasing sequence number scoped to its source. Gaps indicate drops. Duplicates indicate retransmission or bugs.

- MCU binary protocol: `u32` (upgraded from `u8` in v1)
- NDJSON messages: `int` (unbounded, practically `u64`)
- Server plan responses: echo request `seq` plus unique `plan_id`

### 1.4 Stable Message Contract

All schemas are defined as if they were a Rust `enum` with typed payloads. This means:

- Every message has exactly one canonical schema — no polymorphic "bag of keys"
- New message types are additive (never redefine existing type IDs)
- All fields have explicit types and units in their names (`_mm`, `_ms`, `_mrad_s`, `_ns`, `_us`)
- NDJSON messages are plain JSON — no Python-specific serialization

### 1.5 No Raw Uncompressed Frames Across Process Boundaries

Workers never send raw uncompressed image frames or PCM buffers to Core as opaque blobs. All inter-process messages on the Core↔Worker NDJSON channel are structured. Compressed frames (JPEG) may cross boundaries when explicitly enabled, wrapped in typed NDJSON with metadata (e.g., `vision.frame.jpeg` with `frame_seq`).

Rule: only semantic events and explicitly-requested compressed frames cross the Core↔Worker NDJSON boundary. Raw audio streams use a dedicated data plane (see §6.6).

### 1.6 Schema Version

All NDJSON envelopes carry a `v` field (integer). Binary MCU packets carry an implicit version negotiated via handshake. Unknown fields are ignored by receivers; incompatible versions are rejected.

### 1.7 Core Is the Control Plane, Not the Data Plane

Core is the control plane, not the data plane. Raw audio streams between workers directly via dedicated sockets. Core sends control signals (start/stop/cancel conversation, start/stop mic) and receives semantic events (energy, transcript, emotion, gesture, state changes), but never forwards raw audio bytes.

### 1.8 Wire Format Is Canonical

The NDJSON wire format (§3.1) is the canonical schema. Payload fields are inline — not nested inside a `payload` object. Internal Python dataclasses may use any convenient representation, but serialization to/from the wire must produce the flat inline form:

```json
{"v": 2, "type": "tts.event.energy", "src": "tts", "seq": 11, "t_ns": 0, "energy": 180}
```

Not:

```json
{"v": 2, "type": "tts.event.energy", "src": "tts", "seq": 11, "t_ns": 0, "payload": {"energy": 180}}
```

---

## 2. Clock Domains and Synchronization

### 2.1 Clock Domains

| Domain | Source | Resolution | Type | Epoch |
|--------|--------|------------|------|-------|
| Pi | `CLOCK_MONOTONIC` | nanoseconds | `i64` | Pi boot |
| Reflex MCU | `esp_timer_get_time()` | microseconds | `u64` | MCU boot |
| Face MCU | `esp_timer_get_time()` | microseconds | `u64` | MCU boot |
| Server | `time.monotonic_ns()` | nanoseconds | `i64` | Server boot |

Field naming convention encodes domain and unit:
- `t_pi_ns` — Pi monotonic nanoseconds
- `t_src_us` — MCU source monotonic microseconds
- `t_pi_rx_ns` — Pi receive timestamp
- `t_server_ns` — Server monotonic (informational only)

### 2.2 TIME_SYNC Protocol (Pi ↔ MCU)

Lightweight ping/pong to estimate clock offset between Pi and each MCU.

**New packet types:**

| Type ID | Direction | Name |
|---------|-----------|------|
| `0x06` | Pi → MCU | `TIME_SYNC_REQ` |
| `0x86` | MCU → Pi | `TIME_SYNC_RESP` |

**TIME_SYNC_REQ payload (8 bytes):**
```c
struct TimeSyncReqPayload {
    uint32_t ping_seq;    // incrementing counter
    uint32_t reserved;
};
```

**TIME_SYNC_RESP payload (12 bytes):**
```c
struct TimeSyncRespPayload {
    uint32_t ping_seq;    // echo
    uint64_t t_src_us;    // MCU time at response
};
```

**Scheduling:** TIME_SYNC runs on its own async task, independent of the 50 Hz tick loop. It must never block the tick loop or be gated by tick timing. The sync task updates a shared `ClockSync` object atomically; the tick loop reads it read-only.

```python
@dataclass(slots=True)
class ClockSync:
    state: str              # "unsynced" | "synced" | "degraded"
    offset_ns: int          # best estimate (from min-RTT sample)
    rtt_min_us: int         # minimum RTT observed in window
    drift_us_per_s: float   # estimated drift rate
    samples: int            # total samples collected
    t_last_sync_ns: int     # Pi monotonic of last accepted sample
```

**One outstanding ping at a time:** The sync task sends one `TIME_SYNC_REQ` and waits for the corresponding `TIME_SYNC_RESP` (matched by `ping_seq`) before sending the next. If no response arrives within 500 ms, the ping is considered lost and the next one may be sent. This prevents RTT measurement corruption from pipelined pings.

**Pi-side algorithm:**

1. Record `t_pi_tx_ns = time.monotonic_ns()` before sending
2. On response, record `t_pi_rx_ns = time.monotonic_ns()`
3. `rtt_ns = t_pi_rx_ns - t_pi_tx_ns`
4. `offset_ns = t_pi_rx_ns - (t_src_us * 1000) - (rtt_ns / 2)`
5. Sliding window of 16 samples; use the **minimum RTT** sample as the offset estimate
6. Initial: 5 Hz for first 20 samples. Steady-state: 2 Hz.

**v1 devices:** TIME_SYNC is only active for devices that completed v2 protocol negotiation (§3.2). For v1 devices, clock sync is disabled — `ClockSync.state` remains `"unsynced"` permanently, and all features that depend on clock offset (causality tracing, drift estimation) report "unavailable" rather than using stale or zero values.

**Offset application:**
```
t_pi_est_ns = t_src_us * 1000 + offset_ns
```

### 2.3 Clock Sync Quality Gates

Each device's `ClockSync` transitions through three states:

```
UNSYNCED → SYNCED → DEGRADED → SYNCED
                  ↗
UNSYNCED ─────────
```

| State | Entry Condition | Meaning |
|-------|----------------|---------|
| `unsynced` | Initial state, or v1 device | No usable offset. Features report "unavailable." |
| `synced` | ≥ 5 samples collected AND min RTT < 3 ms (USB threshold) | Offset is trustworthy for diagnostics and causality tracing. |
| `degraded` | No accepted sample in last 5 seconds, OR min RTT > 3 ms for 10 consecutive pings | Offset may be stale or noisy. Logged as warning. |

**RTT threshold:** The 3 ms USB threshold filters out pings that hit USB scheduling jitter. Samples with `rtt_ns > 3_000_000` are recorded in the window but not used for the offset estimate. If all 16 window samples exceed the threshold, state transitions to `degraded`.

**Stale timeout:** If `time.monotonic_ns() - t_last_sync_ns > 5_000_000_000` (5 seconds), state transitions to `degraded` regardless of sample quality.

**Recovery:** A single accepted sample (RTT < threshold) transitions `degraded` back to `synced`.

### 2.4 Drift Estimation

Track `offset_ns` over time using finite-difference with exponential low-pass filtering:

```
raw_drift = (offset_now - offset_prev) / (t_now - t_prev)   # µs/s
drift_filtered = alpha * raw_drift + (1 - alpha) * drift_filtered_prev
```

Where `alpha = 0.1` (slow adaptation, noise rejection). `offset_now` and `offset_prev` are the min-RTT offset estimates from successive accepted samples.

Warn if `|drift_filtered| > 100 µs/s` (typical ESP32 crystal drift < 50 ppm ≈ 50 µs/s). Persistent high drift (> 10 consecutive warnings) triggers a log-level escalation but no control action — drift is diagnostic only.

### 2.5 Offset Usage Scope

Clock offset (`t_pi_est_ns = t_src_us * 1000 + offset_ns`) is used **only** for:

- **Diagnostics:** command latency calculation, telemetry health dashboard
- **Causality tracing:** correlating MCU events with Pi events in logs
- **Replay alignment:** synchronizing MCU and Pi log streams during offline analysis

Clock offset is **never** used for:

- **Safety decisions:** all safety policies use `t_pi_rx_ns` (Pi receive time), not estimated MCU time
- **Control loop timing:** tick scheduling uses Pi monotonic clock exclusively
- **Staleness checks:** vision/range staleness thresholds compare against `t_pi_rx_ns`

This separation ensures that clock sync quality (or lack thereof) cannot affect safety behavior.

### 2.6 Per-Packet `t_src_us` Semantics

The meaning of `t_src_us` varies by packet type. Each MCU firmware must timestamp at the specified moment:

| Packet Type | `t_src_us` Meaning |
|-------------|-------------------|
| Reflex `STATE` (0x80) | Control loop tick boundary (start of the tick that produced this telemetry) |
| Face `FACE_STATUS` (0x90) | Render completion (when the display buffer was committed) |
| `TIME_SYNC_RESP` (0x86) | Response assembly (immediately before serialization) |
| Face `TOUCH_EVENT` (0x91) | Interrupt/detection time on the touch controller |
| Face `BUTTON_EVENT` (0x92) | Interrupt time (GPIO ISR or debounce completion) |
| Face `HEARTBEAT` (0x93) | Heartbeat assembly time |
| Reflex commands (0x10-0x15) | Pi send time (`t_src_us` = 0 in v2 envelope; Pi uses `t_cmd_tx_ns` instead) |

For outbound commands (Pi → MCU), `t_src_us` in the v2 envelope is set to 0 — the authoritative send timestamp is `t_cmd_tx_ns` recorded Pi-side.

### 2.7 Server Clock

No sync with server. Pi records `t_req_tx_ns` and `t_resp_rx_ns` for each exchange. Server timestamps are informational only.

---

## 3. Envelope Formats

### 3.1 NDJSON Envelope (Core ↔ Workers, Dashboard API)

One JSON line per message, newline-terminated:

```json
{
    "v": 2,
    "type": "domain.entity.verb",
    "src": "source_id",
    "seq": 12345,
    "t_ns": 1708444800000000000,
    ...payload fields inline...
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `v` | `int` | Yes | Schema version (currently `2`) |
| `type` | `string` | Yes | Hierarchical message type |
| `src` | `string` | Yes | Source: `core`, `vision`, `tts`, `ai`, `dashboard` |
| `seq` | `int` | Yes | Per-source monotonic sequence number |
| `t_ns` | `int` | Yes | Pi monotonic nanoseconds at creation |

Optional fields:

| Field | Type | Description |
|-------|------|-------------|
| `ref_seq` | `int` | Seq of message being responded to |
| `ref_type` | `string` | Type of message being responded to |
| `session_id` | `string` | Conversation session identifier |
| `err` | `string` | Error code |

### 3.2 Binary Envelope (MCU Protocol v2)

After protocol version handshake, packets use the v2 envelope:

```
v1: [type:u8] [seq:u8]                        [payload:N] [crc16:u16-LE]
v2: [type:u8] [seq:u32-LE] [t_src_us:u64-LE]  [payload:N] [crc16:u16-LE]
```

Header overhead: 13 bytes (was 2 in v1). CRC covers everything except itself.

**Protocol version handshake:**

| Type ID | Direction | Name |
|---------|-----------|------|
| `0x07` | Pi → MCU | `SET_PROTOCOL_VERSION` (payload: `{version:u8}`) |
| `0x87` | MCU → Pi | `PROTOCOL_VERSION_ACK` (payload: `{version:u8}`) |

Pi sends `SET_PROTOCOL_VERSION(version=2)` at connection. If ACK within 500ms, switch to v2 envelope. Otherwise fall back to v1 for that device.

**Handshake behavior:**
- **Per-port negotiation:** Each MCU port (reflex, face) negotiates independently. Mixed mode (e.g., `reflex_proto=v2, face_proto=v1`) is explicitly supported and logged.
- **Retry on reconnect:** On serial reconnect (USB replug, MCU reboot), Core re-sends `SET_PROTOCOL_VERSION` once. No continuous retry — if the MCU is v1-only, it stays v1.
- **MCU reboot:** Triggers serial reconnect, which triggers fresh handshake.
- **Logging:** Core logs negotiated protocol version per port at startup and on every reconnect: `reflex_proto=v1|v2`, `face_proto=v1|v2`.

### 3.3 Pi Receive Annotation

When Core receives any MCU packet, it attaches:

```python
@dataclass(slots=True)
class AnnotatedPacket:
    pkt_type: int
    seq: int           # u32 in v2, u8 in v1
    t_src_us: int      # MCU monotonic (0 in v1)
    t_pi_rx_ns: int    # Pi monotonic at frame dispatch
    payload: bytes
    raw: bytes          # original COBS frame (for replay log)
```

---

## 4. Message Taxonomy

All types follow `domain.entity.verb`:

### 4.1 Reflex Domain (`reflex.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `reflex.cmd.set_twist` | Pi → Reflex | Linear/angular velocity |
| `reflex.cmd.stop` | Pi → Reflex | Soft stop with reason |
| `reflex.cmd.estop` | Pi → Reflex | Emergency stop |
| `reflex.cmd.clear_faults` | Pi → Reflex | Clear fault bitfield |
| `reflex.cmd.set_config` | Pi → Reflex | Tunable parameter update |
| `reflex.cmd.time_sync_req` | Pi → Reflex | Clock sync ping |
| `reflex.cmd.set_protocol_version` | Pi → Reflex | Version handshake |
| `reflex.tel.state` | Reflex → Pi | Periodic telemetry |
| `reflex.tel.time_sync_resp` | Reflex → Pi | Clock sync pong |
| `reflex.tel.protocol_version_ack` | Reflex → Pi | Version confirmed |

### 4.2 Face Domain (`face.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `face.cmd.set_state` | Pi → Face | Mood, gaze, brightness |
| `face.cmd.gesture` | Pi → Face | One-shot gesture |
| `face.cmd.set_system` | Pi → Face | System mode overlay |
| `face.cmd.set_talking` | Pi → Face | Speaking animation + energy |
| `face.cmd.set_flags` | Pi → Face | Renderer feature toggles |
| `face.cmd.time_sync_req` | Pi → Face | Clock sync ping |
| `face.cmd.set_protocol_version` | Pi → Face | Version handshake |
| `face.tel.status` | Face → Pi | Current mood/gesture/system/flags |
| `face.tel.touch` | Face → Pi | Touch press/release/drag |
| `face.tel.button` | Face → Pi | Button press/release/toggle/click |
| `face.tel.heartbeat` | Face → Pi | Liveness + counters |
| `face.tel.time_sync_resp` | Face → Pi | Clock sync pong |
| `face.tel.protocol_version_ack` | Face → Pi | Version confirmed |

### 4.3 Vision Domain (`vision.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `vision.detection.snapshot` | Vision → Core | Per-frame detection results |
| `vision.config.update` | Core → Vision | HSV thresholds, MJPEG toggle |
| `vision.frame.jpeg` | Vision → Core | MJPEG frame (on request) |
| `vision.status.health` | Vision → Core | FPS, drops, errors |
| `vision.lifecycle.started` | Vision → Core | Worker ready |
| `vision.lifecycle.stopped` | Vision → Core | Worker exiting |
| `vision.lifecycle.error` | Vision → Core | Fatal error |

### 4.4 TTS Domain (`tts.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `tts.config.init` | Core → TTS | Startup config (audio_mode, socket paths, devices) |
| `tts.cmd.speak` | Core → TTS | Request speech + playback |
| `tts.cmd.cancel` | Core → TTS | Cancel current playback + queue |
| `tts.cmd.start_mic` | Core → TTS | Begin arecord capture |
| `tts.cmd.stop_mic` | Core → TTS | Stop capture |
| `tts.event.started` | TTS → Core | Playback started |
| `tts.event.energy` | TTS → Core | Lip sync energy (0-255), best-effort ~20 Hz |
| `tts.event.finished` | TTS → Core | Playback completed |
| `tts.event.cancelled` | TTS → Core | Playback cancelled |
| `tts.event.error` | TTS → Core | TTS/playback failure |
| `tts.event.mic_dropped` | TTS → Core | Mic frames dropped (backpressure) |
| `tts.status.health` | TTS → Core | Queue depth, connection |
| `tts.lifecycle.started` | TTS → Core | Worker ready |
| `tts.lifecycle.stopped` | TTS → Core | Worker exiting |

### 4.5 AI Domain (`ai.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `ai.config.init` | Core → AI | Startup config (audio_mode, socket paths, server URL) |
| `ai.cmd.request_plan` | Core → AI | Request plan from server |
| `ai.cmd.start_conversation` | Core → AI | Open conversation session |
| `ai.cmd.end_conversation` | Core → AI | Close conversation session |
| `ai.cmd.end_utterance` | Core → AI | Signal end of user speech |
| `ai.cmd.cancel` | Core → AI | Cancel active request/conversation |
| `ai.plan.received` | AI → Core | Plan from server (transport-deduped, raw) |
| `ai.conversation.transcription` | AI → Core | User speech transcribed |
| `ai.conversation.emotion` | AI → Core | Emotion metadata from server |
| `ai.conversation.gesture` | AI → Core | Gesture recommendations |
| `ai.conversation.done` | AI → Core | Conversation turn complete |
| `ai.state.changed` | AI → Core | State transition |
| `ai.status.health` | AI → Core | Connection, session, latency |
| `ai.lifecycle.started` | AI → Core | Worker ready |
| `ai.lifecycle.stopped` | AI → Core | Worker exiting |
| `ai.lifecycle.error` | AI → Core | Fatal error |

### 4.6 Core Domain (`core.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `core.state.snapshot` | Core → Dashboard | Full telemetry |
| `core.event.mode_changed` | Core internal/Dashboard | Mode transition |
| `core.event.fault_raised` | Core internal/Dashboard | New fault |
| `core.event.fault_cleared` | Core internal/Dashboard | Fault resolved |
| `core.event.ball_acquired` | Core internal/Dashboard | Ball visible |
| `core.event.ball_lost` | Core internal/Dashboard | Ball lost |
| `core.event.obstacle_close` | Core internal/Dashboard | Range below threshold |
| `core.event.obstacle_cleared` | Core internal/Dashboard | Range above threshold |
| `core.event.vision_healthy` | Core internal/Dashboard | Vision within freshness |
| `core.event.vision_stale` | Core internal/Dashboard | Vision exceeded staleness |

### 4.7 System Domain (`system.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `system.clock.sync_update` | Core internal | Clock offset updated |
| `system.health.device` | Core → Dashboard | Per-device RTT/offset/drift |
| `system.health.worker` | Core → Dashboard | Per-worker health |
| `system.audio.link_up` | Worker → Core | Audio socket connected |
| `system.audio.link_down` | Worker → Core | Audio socket disconnected |
| `system.lifecycle.shutdown` | Core → All Workers | Graceful shutdown |

### 4.8 Dashboard Domain (`dashboard.*`)

| Type | Direction | Description |
|------|-----------|-------------|
| `dashboard.cmd.set_mode` | Dashboard → Core | Mode change request |
| `dashboard.cmd.estop` | Dashboard → Core | Emergency stop |
| `dashboard.cmd.clear_faults` | Dashboard → Core | Clear errors |
| `dashboard.cmd.twist` | Dashboard → Core | Teleop twist input |
| `dashboard.cmd.face_set_state` | Dashboard → Core | Direct mood/gaze |
| `dashboard.cmd.face_gesture` | Dashboard → Core | Trigger gesture |
| `dashboard.cmd.face_set_system` | Dashboard → Core | System mode overlay |
| `dashboard.cmd.face_set_talking` | Dashboard → Core | Direct talking control |
| `dashboard.cmd.face_set_flags` | Dashboard → Core | Renderer toggles |
| `dashboard.cmd.face_manual_lock` | Dashboard → Core | Lock face from planner |
| `dashboard.cmd.set_params` | Dashboard → Core | Bulk parameter update |

---

## 5. MCU Protocol v2

### 5.1 Extended Packet Layout

After version handshake, all packets use:

```
Offset  Size  Field
0       1     type (u8)
1       4     seq (u32-LE)
5       8     t_src_us (u64-LE)
13      N     payload
13+N    2     crc16 (u16-LE, CCITT poly 0x1021, init 0xFFFF)
```

COBS encoding + `0x00` delimiter unchanged.

### 5.2 Reflex STATE v2 (type `0x80`)

Extended payload (15 bytes → 23 bytes):

```c
struct __attribute__((packed)) StatePayloadV2 {
    // Original (15 bytes)
    int16_t  speed_l_mm_s;
    int16_t  speed_r_mm_s;
    int16_t  gyro_z_mrad_s;
    uint16_t battery_mv;
    uint16_t fault_flags;
    uint16_t range_mm;
    uint8_t  range_status;
    // v2 additions (8 bytes)
    uint32_t cmd_seq_last_applied;  // echoes last applied command seq
    uint32_t t_cmd_applied_us;      // MCU time when command was applied
};
```

Pi parser uses payload length to distinguish v1 (15B) from v2 (23B).

### 5.3 Face STATUS v2 (type `0x90`)

Extended payload (4 bytes → 12 bytes):

```c
struct __attribute__((packed)) FaceStatusPayloadV2 {
    // Original (4 bytes)
    uint8_t mood_id;
    uint8_t active_gesture;
    uint8_t system_mode;
    uint8_t flags;
    // v2 additions (8 bytes)
    uint32_t cmd_seq_last_applied;
    uint32_t t_state_applied_us;  // when display was actually updated
};
```

### 5.4 Command Causality

When Core sends a command (e.g., SET_TWIST), it records:
- `cmd_seq` — the v2 `u32` sequence number
- `t_cmd_tx_ns` — Pi monotonic at send

MCU echoes `cmd_seq_last_applied` + `t_cmd_applied_us` in every telemetry packet. This enables:
- **Command latency:** `t_applied_us * 1000 + offset_ns - t_cmd_tx_ns`
- **Round-trip:** `t_pi_rx_ns - t_cmd_tx_ns`

### 5.5 Type ID Registry

| ID | Direction | Name | Payload |
|----|-----------|------|---------|
| `0x06` | Pi → MCU | TIME_SYNC_REQ | `{ping_seq:u32, reserved:u32}` |
| `0x07` | Pi → MCU | SET_PROTOCOL_VERSION | `{version:u8}` |
| `0x10` | Pi → Reflex | SET_TWIST | `{v_mm_s:i16, w_mrad_s:i16}` |
| `0x11` | Pi → Reflex | STOP | `{reason:u8}` |
| `0x12` | Pi → Reflex | ESTOP | (empty) |
| `0x13` | Pi → Reflex | SET_LIMITS | (reserved) |
| `0x14` | Pi → Reflex | CLEAR_FAULTS | `{mask:u16}` |
| `0x15` | Pi → Reflex | SET_CONFIG | `{param_id:u8, value:4B}` |
| `0x20` | Pi → Face | SET_STATE | `{mood:u8, intensity:u8, gaze_x:i8, gaze_y:i8, brightness:u8}` |
| `0x21` | Pi → Face | GESTURE | `{gesture_id:u8, duration_ms:u16}` |
| `0x22` | Pi → Face | SET_SYSTEM | `{mode:u8, phase:u8, param:u8}` |
| `0x23` | Pi → Face | SET_TALKING | `{talking:u8, energy:u8}` |
| `0x24` | Pi → Face | SET_FLAGS | `{flags:u8}` |
| `0x80` | Reflex → Pi | STATE | v1: 15B, v2: 23B |
| `0x86` | MCU → Pi | TIME_SYNC_RESP | `{ping_seq:u32, t_src_us:u64}` |
| `0x87` | MCU → Pi | PROTOCOL_VERSION_ACK | `{version:u8}` |
| `0x90` | Face → Pi | FACE_STATUS | v1: 4B, v2: 12B |
| `0x91` | Face → Pi | TOUCH_EVENT | `{event_type:u8, x:u16, y:u16}` |
| `0x92` | Face → Pi | BUTTON_EVENT | `{button_id:u8, event_type:u8, state:u8, reserved:u8}` |
| `0x93` | Face → Pi | HEARTBEAT | 68B (uptime + counters + USB diagnostics) |

### 5.6 Enums (Canonical, Unchanged)

**Fault Flags (u16 bitfield):**
| Bit | Name | Description |
|-----|------|-------------|
| 0 | CMD_TIMEOUT | No command within timeout |
| 1 | ESTOP | Emergency stop active |
| 2 | TILT | Beyond 45° threshold |
| 3 | STALL | Motor stalled |
| 4 | IMU_FAIL | IMU sensor error |
| 5 | BROWNOUT | Low battery |
| 6 | OBSTACLE | Range < 250mm |

**Mood IDs (u8):**
| ID | Name | ID | Name |
|----|------|----|------|
| 0 | NEUTRAL | 6 | ANGRY |
| 1 | HAPPY | 7 | SURPRISED |
| 2 | EXCITED | 8 | SLEEPY |
| 3 | CURIOUS | 9 | LOVE |
| 4 | SAD | 10 | SILLY |
| 5 | SCARED | 11 | THINKING |

**Gesture IDs (u8):**
| ID | Name | ID | Name |
|----|------|----|------|
| 0 | BLINK | 7 | X_EYES |
| 1 | WINK_L | 8 | SLEEPY |
| 2 | WINK_R | 9 | RAGE |
| 3 | CONFUSED | 10 | NOD |
| 4 | LAUGH | 11 | HEADSHAKE |
| 5 | SURPRISE | 12 | WIGGLE |
| 6 | HEART | | |

**System Modes (u8):** NONE(0), BOOTING(1), ERROR_DISPLAY(2), LOW_BATTERY(3), UPDATING(4), SHUTTING_DOWN(5)

**Button IDs:** PTT(0), ACTION(1)

**Button Events:** PRESS(0), RELEASE(1), TOGGLE(2), CLICK(3)

**Touch Events:** PRESS(0), RELEASE(1), DRAG(2)

**Face Flags (u8 bitfield):** IDLE_WANDER(0), AUTOBLINK(1), SOLID_EYE(2), SHOW_MOUTH(3), EDGE_GLOW(4), SPARKLE(5), AFTERGLOW(6)

**Range Status (u8):** OK(0), TIMEOUT(1), OUT_OF_RANGE(2), NOT_READY(3)

---

## 6. Core ↔ Worker Messages

### 6.1 Transport

Each worker communicates with Core via its own dedicated NDJSON-over-stdio pipes. There is no shared pipe — Core spawns each worker as a separate child process with its own stdin/stdout pair. Core maintains a separate async reader task per worker stdout.

stderr is reserved for human-readable log output routed to Core's log aggregator.

**Lifecycle:**

1. Core spawns worker as child process (dedicated stdin/stdout/stderr)
2. Core starts an async reader task for the worker's stdout
3. Worker writes `<domain>.lifecycle.started` to stdout
4. Core sends configuration/commands via worker stdin
5. Worker sends events/status via stdout
6. On shutdown, Core sends `system.lifecycle.shutdown`
7. Worker writes `<domain>.lifecycle.stopped` and exits

**Large message atomicity:** Workers must write each NDJSON line atomically (single `write()` call or buffered flush). This prevents interleaving when a worker uses multiple internal threads. This is especially important for large messages like `vision.frame.jpeg` (50-200 KB base64) — a partial write followed by a small message would corrupt both.

### 6.2 NDJSON Channel Emission Rules

Each worker has its own stdout pipe to Core (§6.1). Within a single worker's pipe, high-rate messages can still delay that worker's heartbeats. To prevent false worker-death detection, each message class has a maximum emission rate and coalescing rule:

| Message Class | Max Rate | Coalescing | Rationale |
|---------------|----------|------------|-----------|
| `*.lifecycle.*` | On transition only | None | Rare, always delivered |
| `*.status.health` | 1 Hz | None (already 1 Hz) | Heartbeat — must never be starved |
| `tts.event.energy` | 20 Hz | Last-value-wins | Lip sync doesn't need >20 Hz; prevents pipe flooding |
| `vision.detection.snapshot` | 10 Hz | Last-value-wins | Core doesn't need 30 Hz detections; worker runs CV at full FPS internally |
| `vision.frame.jpeg` | 5 Hz | Last-value-wins | Large payloads; only when MJPEG enabled |
| `ai.plan.received` | Unbounded | None | Rare, large, critical — always delivered immediately |
| `ai.conversation.*` | Unbounded | None | Low-rate semantic events — always delivered |
| `ai.state.changed` | On transition only | None | Rare, always delivered |
| `tts.event.started/finished/cancelled` | On transition only | None | Rare, always delivered |
| `system.audio.link_*` | On transition only | None | Rare, always delivered |

**Worker-side enforcement:** Workers are responsible for respecting these rates. If a worker's internal processing generates data faster than the emission rate, it coalesces locally (keeps latest value) and emits at the capped rate.

**Core-side heartbeat robustness:** Core's worker heartbeat timeout (5 seconds) is deliberately generous relative to worst-case pipe drain latency. Even if 100 queued messages (~100 KB) need to drain before a heartbeat, this takes <10 ms on a local pipe. The 5s timeout accommodates worker CPU stalls, not pipe congestion.

**Ordering guarantee:** Messages on a single stdout pipe are always delivered in write order. No priority reordering is applied — emission rate limits at the worker are the only mechanism. This keeps the design simple (no multiplexer, no priority queue).

### 6.3 Vision Worker

**Core → Vision:**

`vision.config.update`:
```json
{
    "v": 2, "type": "vision.config.update", "src": "core", "seq": 1, "t_ns": 0,
    "mjpeg_enabled": false,
    "floor_hsv_low": [0, 0, 50],
    "floor_hsv_high": [180, 80, 220],
    "ball_hsv_low": [0, 120, 70],
    "ball_hsv_high": [15, 255, 255],
    "min_ball_radius": 10
}
```

**Vision → Core:**

`vision.detection.snapshot` (emitted at ≤ 10 Hz to Core; worker runs CV at full camera FPS internally):
```json
{
    "v": 2, "type": "vision.detection.snapshot", "src": "vision", "seq": 42, "t_ns": 0,
    "frame_seq": 1234,
    "t_frame_ns": 1708444800000000000,
    "t_det_done_ns": 1708444800005000000,
    "clear_confidence": 0.85,
    "ball_confidence": 0.92,
    "ball_bearing_deg": -12.3,
    "fps": 30.1
}
```

`vision.frame.jpeg` (only when MJPEG enabled):
```json
{
    "v": 2, "type": "vision.frame.jpeg", "src": "vision", "seq": 43, "t_ns": 0,
    "frame_seq": 1234,
    "data_b64": "<base64 JPEG>"
}
```

`vision.status.health`:
```json
{
    "v": 2, "type": "vision.status.health", "src": "vision", "seq": 50, "t_ns": 0,
    "fps": 30.1,
    "frames_processed": 10234,
    "frames_dropped": 12,
    "camera_ok": true,
    "last_error": ""
}
```

### 6.4 TTS Worker

**Core → TTS:**

`tts.config.init` (sent once after worker starts, before any commands):
```json
{
    "v": 2, "type": "tts.config.init", "src": "core", "seq": 1, "t_ns": 0,
    "audio_mode": "direct",
    "mic_socket_path": "/tmp/rb-mic-12345.sock",
    "spk_socket_path": "/tmp/rb-spk-12345.sock",
    "speaker_device": "default",
    "mic_device": "default",
    "tts_endpoint": "http://10.0.0.20:8100/tts"
}
```

`audio_mode` values:
- `"direct"` (Mode A): TTS worker connects to `mic_socket_path` and `spk_socket_path` for direct audio streaming with AI worker
- `"relay"` (Mode B): No audio sockets; audio is relayed via Core using NDJSON base64 (dev/test only)

`tts.cmd.speak` (deterministic speech from planner/speech policy):
```json
{
    "v": 2, "type": "tts.cmd.speak", "src": "core", "seq": 5, "t_ns": 0,
    "text": "Hello friend!",
    "emotion": "happy",
    "source": "planner",
    "priority": 1
}
```

`tts.cmd.cancel`:
```json
{"v": 2, "type": "tts.cmd.cancel", "src": "core", "seq": 7, "t_ns": 0}
```

`tts.cmd.start_mic`:
```json
{"v": 2, "type": "tts.cmd.start_mic", "src": "core", "seq": 8, "t_ns": 0}
```

`tts.cmd.stop_mic`:
```json
{"v": 2, "type": "tts.cmd.stop_mic", "src": "core", "seq": 9, "t_ns": 0}
```

**TTS → Core:**

`tts.event.started`:
```json
{
    "v": 2, "type": "tts.event.started", "src": "tts", "seq": 10, "t_ns": 0,
    "ref_seq": 5,
    "text": "Hello friend!"
}
```

`tts.event.energy` (lip sync, best-effort, coalesced to ~20 Hz):
```json
{"v": 2, "type": "tts.event.energy", "src": "tts", "seq": 11, "t_ns": 0, "energy": 180}
```

Energy is best-effort: the TTS worker computes energy per audio chunk internally (~100 Hz) but coalesces to **last-value-wins at ~20 Hz** before writing to stdout. This prevents stdout backpressure from blocking the audio playback thread. Core reuses the last received energy value if no new sample arrives this tick.

`tts.event.finished`:
```json
{
    "v": 2, "type": "tts.event.finished", "src": "tts", "seq": 200, "t_ns": 0,
    "ref_seq": 5,
    "duration_ms": 1450,
    "chunks_played": 145
}
```

### 6.5 AI Worker

**Core → AI:**

`ai.config.init` (sent once after worker starts, before any commands):
```json
{
    "v": 2, "type": "ai.config.init", "src": "core", "seq": 1, "t_ns": 0,
    "audio_mode": "direct",
    "mic_socket_path": "/tmp/rb-mic-12345.sock",
    "spk_socket_path": "/tmp/rb-spk-12345.sock",
    "server_base_url": "http://10.0.0.20:8100",
    "robot_id": "buddy-01"
}
```

`ai.cmd.request_plan`:
```json
{
    "v": 2, "type": "ai.cmd.request_plan", "src": "core", "seq": 100, "t_ns": 0,
    "world_state": {
        "robot_id": "buddy-01",
        "mode": "WANDER",
        "battery_mv": 7800,
        "range_mm": 1200,
        "faults": [],
        "ball_detected": true,
        "ball_confidence": 0.91,
        "ball_bearing_deg": -5.2,
        "vision_age_ms": 45.0,
        "speed_l_mm_s": 80,
        "speed_r_mm_s": 75,
        "trigger": "ball_seen",
        "recent_events": ["core.event.ball_acquired"],
        "planner_active_skill": "investigate_ball",
        "face_talking": false,
        "face_listening": false
    }
}
```

`ai.cmd.start_conversation`:
```json
{
    "v": 2, "type": "ai.cmd.start_conversation", "src": "core", "seq": 101, "t_ns": 0,
    "session_id": "sess-abc123",
    "turn_id": 1
}
```

`ai.cmd.end_utterance` (increments turn for next exchange):
```json
{
    "v": 2, "type": "ai.cmd.end_utterance", "src": "core", "seq": 103, "t_ns": 0,
    "session_id": "sess-abc123",
    "turn_id": 1
}
```

`ai.cmd.cancel`:
```json
{"v": 2, "type": "ai.cmd.cancel", "src": "core", "seq": 104, "t_ns": 0}
```

**AI → Core:**

`ai.plan.received` (transport-deduped, raw — Core validates):
```json
{
    "v": 2, "type": "ai.plan.received", "src": "ai", "seq": 50, "t_ns": 0,
    "ref_seq": 100,
    "plan_id": "a1b2c3d4e5f6",
    "plan_seq": 7,
    "t_server_ms": 987654321,
    "actions": [
        {"action": "emote", "name": "excited", "intensity": 0.8},
        {"action": "gesture", "name": "nod"},
        {"action": "say", "text": "I see a ball!"},
        {"action": "skill", "name": "investigate_ball"}
    ],
    "ttl_ms": 2000
}
```

`ai.state.changed`:
```json
{
    "v": 2, "type": "ai.state.changed", "src": "ai", "seq": 55, "t_ns": 0,
    "state": "thinking",
    "prev_state": "listening",
    "session_id": "sess-abc123",
    "turn_id": 3,
    "reason": "end_utterance_received"
}
```

`ai.conversation.transcription`:
```json
{
    "v": 2, "type": "ai.conversation.transcription", "src": "ai", "seq": 56, "t_ns": 0,
    "session_id": "sess-abc123",
    "turn_id": 3,
    "text": "Can you find the ball?"
}
```

`ai.conversation.emotion`:
```json
{
    "v": 2, "type": "ai.conversation.emotion", "src": "ai", "seq": 57, "t_ns": 0,
    "session_id": "sess-abc123",
    "turn_id": 3,
    "emotion": "excited",
    "intensity": 0.8
}
```

`ai.conversation.gesture`:
```json
{
    "v": 2, "type": "ai.conversation.gesture", "src": "ai", "seq": 58, "t_ns": 0,
    "session_id": "sess-abc123",
    "turn_id": 3,
    "names": ["nod", "blink"]
}
```

`ai.conversation.done`:
```json
{
    "v": 2, "type": "ai.conversation.done", "src": "ai", "seq": 80, "t_ns": 0,
    "session_id": "sess-abc123",
    "turn_id": 3
}
```

### 6.6 Worker Responsibility Matrix

| Responsibility | Core | Vision | TTS | AI |
|---|:---:|:---:|:---:|:---:|
| MCU serial I/O | ✓ | | | |
| Safety policies | ✓ | | | |
| State machine | ✓ | | | |
| 50 Hz tick loop | ✓ | | | |
| Event bus / edge detection | ✓ | | | |
| Plan semantic validation | ✓ | | | |
| Plan ordering / dedup (semantic) | ✓ | | | |
| Action scheduling + cooldowns | ✓ | | | |
| Speech arbitration (§8.1) | ✓ | | | |
| Face intent composition (§8.2) | ✓ | | | |
| Audio socket creation + path distribution | ✓ | | | |
| Camera capture + CV | | ✓ | | |
| MJPEG encoding | | ✓ | | |
| Audio playback (aplay / socket) | | | ✓ | |
| Audio capture (arecord / socket) | | | ✓ | |
| Lip sync energy calc | | | ✓ | |
| HTTP to /tts | | | ✓ | |
| Direct audio streaming (mic → AI) | | | ✓ | ✓ |
| Direct audio streaming (TTS ← AI) | | | ✓ | ✓ |
| HTTP to /plan | | | | ✓ |
| WebSocket to /converse | | | | ✓ |
| Transport-level plan dedup | | | | ✓ |
| Conversation state machine | | | | ✓ |
| Dashboard HTTP/WS | ✓ | | | |
| Telemetry recording | ✓ | | | |

### 6.7 Audio Data Plane

#### Design Rationale

Core is the control plane, not the data plane (Principle 1.7). During conversation, raw audio (~32 KB/s at 16 kHz 16-bit mono) flows directly between TTS and AI workers via two dedicated unix domain sockets (one per direction). Core never touches audio bytes — it only sends control signals (`start_mic`, `stop_mic`, `start_conversation`, `end_utterance`, `cancel`) and receives semantic events (`energy`, `transcription`, `emotion`, `gesture`, `done`).

#### Modes

| Mode | Name | Audio Path | Use Case |
|------|------|-----------|----------|
| A | `direct` | Two unix domain sockets (mic + spk) between TTS ↔ AI | Production (default) |
| B | `relay` | NDJSON base64 via Core | Dev/test, mock workers |

Mode is chosen at startup and passed to workers via `tts.config.init` and `ai.config.init`. Mode is never changed mid-session.

#### Socket Lifecycle (Mode A)

1. Core creates socket directory at startup, cleans up any stale socket files
2. Core passes both socket paths to workers in their `*.config.init` messages:
   - `/tmp/rb-mic-<pid>.sock` — mic audio (TTS → AI)
   - `/tmp/rb-spk-<pid>.sock` — speaker audio (AI → TTS)
3. AI worker binds and listens on both sockets (server role)
4. TTS worker connects to both sockets (client role)
5. Each socket carries a single unidirectional stream — no multiplexing, no direction byte
6. On Core shutdown, both socket files are cleaned up

Using two separate sockets eliminates head-of-line blocking: a stall on the speaker path cannot block mic capture, and vice versa. Each side needs only a single reader or writer per socket — no multiplexing logic required.

#### Socket Reconnect Behavior

**AI worker (server role):**
- On startup: `unlink` socket path (if exists), then `bind` + `listen`. Always. No "check if exists" — stale files from a previous crash are expected.
- On TTS disconnect: close accepted fd, return to `listen`. Emit `system.audio.link_down` for the affected socket.
- On accept: emit `system.audio.link_up`. Resume audio I/O.
- AI worker must never exit or crash due to socket errors — it is the stable side of the link.

**TTS worker (client role):**
- On startup: attempt `connect` to both sockets. If AI worker isn't ready yet, retry every 100 ms (bounded, max 30 seconds). Log at 1s intervals.
- During retry: mic capture continues into the ring buffer. Frames are dropped (ring buffer overwrites oldest) and `tts.event.mic_dropped` is emitted. Speaker playback is paused (no data source).
- On disconnect mid-conversation: emit `system.audio.link_down`, start connect-retry loop. Never block mic capture waiting for reconnect.
- On reconnect: emit `system.audio.link_up`. Resume audio I/O.

**Link state events (via NDJSON to Core):**

| Type | Direction | Description |
|------|-----------|-------------|
| `system.audio.link_up` | Worker → Core | Audio socket connected (includes `socket: "mic"\|"spk"`) |
| `system.audio.link_down` | Worker → Core | Audio socket disconnected (includes `socket: "mic"\|"spk"`, `reason`) |

**Core behavior on link events:**
- Core tracks link state for both sockets. Both must be `up` before Core sends `ai.cmd.start_conversation`.
- If either link drops mid-conversation, Core sends `ai.cmd.cancel` and `tts.cmd.stop_mic` to terminate the conversation deterministically. Core does not attempt to resume — the next conversation starts fresh after links are re-established.

**Per-socket state machine (each worker, each socket):**
```
disconnected → connecting → connected → disconnected
```
- AI: `disconnected` → `connecting` (listening) → `connected` (accepted) → `disconnected` (peer close)
- TTS: `disconnected` → `connecting` (connect retry) → `connected` (connect success) → `disconnected` (peer close / error)

#### Restart Scenarios

**AI worker restart mid-conversation:**
1. AI process dies → Core detects via stdout EOF
2. Both audio sockets close (AI was server) → TTS detects disconnect on both sockets
3. TTS emits `system.audio.link_down` for mic and spk → Core receives link-down events
4. Core cancels active conversation: sends `tts.cmd.stop_mic`, `tts.cmd.cancel`
5. Core respawns AI worker per restart policy (backoff, max 5 restarts)
6. New AI worker sends `ai.lifecycle.started`, receives `ai.config.init`
7. AI worker `unlink`s + `bind`s + `listen`s on both sockets
8. TTS worker's connect-retry loop succeeds → both emit `system.audio.link_up`
9. Core sees both links up → next conversation can start

**TTS worker restart mid-conversation:**
1. TTS process dies → Core detects via stdout EOF
2. Audio sockets close (TTS was client) → AI detects disconnect, emits `system.audio.link_down`
3. Core cancels active conversation: sends `ai.cmd.cancel`
4. Core respawns TTS worker per restart policy
5. New TTS worker sends `tts.lifecycle.started`, receives `tts.config.init`
6. TTS worker connects to both sockets (AI is still listening) → both emit `system.audio.link_up`
7. Core sees both links up → next conversation can start

**Core restart (full process restart):**
1. Core process dies → all child workers receive SIGHUP/broken pipe and exit
2. On restart, Core cleans up stale socket files in `/tmp/rb-*-<old_pid>.sock`
3. Core spawns fresh workers, fresh sockets with new PID in path
4. Normal startup sequence: config.init → link_up → ready

**Key invariant:** No conversation is ever resumed after a restart. All restarts result in clean state. The only recovery is starting a new conversation after all links are re-established.

#### Wire Format (Binary Framed PCM)

Each audio socket carries simple binary-framed PCM — no JSON, no base64, no NDJSON envelope overhead:

```
[chunk_len:u16-LE] [pcm_data:N]
```

| Field | Size | Description |
|-------|------|-------------|
| `chunk_len` | 2 bytes (u16-LE) | PCM payload length in bytes (typically 320 = 10ms) |
| `pcm_data` | N bytes | Raw PCM: 16 kHz, 16-bit signed LE, mono |

Maximum `chunk_len`: 4096 bytes. Receiver must handle partial reads (standard stream socket buffering).

#### Socket Semantics

| Socket | Path | Producer | Consumer | When |
|--------|------|----------|----------|------|
| Mic | `/tmp/rb-mic-<pid>.sock` | TTS worker (arecord) | AI worker → server WS | During `listening` state |
| Speaker | `/tmp/rb-spk-<pid>.sock` | AI worker (from server WS) | TTS worker (aplay) | During `speaking` state |

#### Flow Control

**Mic path (TTS → AI):** The mic capture loop must never block. TTS worker maintains a bounded ring buffer (200 ms / ~6400 bytes). If the mic socket cannot accept writes (AI worker slow or disconnected), the TTS worker drops the oldest mic frames and emits `tts.event.mic_dropped` with a count. The `arecord` pipe is always drained to prevent ALSA kernel buffer overflow.

**Speaker path (AI → TTS):** Blocking is tolerable — it manifests as playback underrun/jitter, which is preferable to dropped audio. AI worker may block on `write()` with a bounded timeout (500 ms). If the timeout expires, the chunk is dropped and `ai.state.changed` → `error` is emitted.

**Disconnection:** If either socket disconnects mid-conversation, both workers emit error events via NDJSON and the conversation is terminated.

#### Mode B Relay Messages

When `audio_mode="relay"`, Core uses these additional NDJSON messages to relay audio (not present in Mode A):

| Type | Direction | Description |
|------|-----------|-------------|
| `tts.event.audio_chunk` | TTS → Core | Mic PCM (base64) |
| `ai.cmd.send_audio` | Core → AI | Forwarded mic PCM (base64) |
| `ai.conversation.audio` | AI → Core | TTS PCM from server (base64) |
| `tts.cmd.play_audio` | Core → TTS | Forwarded TTS PCM (base64) |

These types exist only for Mode B compatibility. They carry `"data_b64"` fields with base64-encoded PCM. Mode B is not recommended for production due to serialization overhead and Core throughput impact.

---

## 7. AI Worker Protocol

### 7.1 Session and Turn Tracking

| Concept | Scope | Generated By |
|---------|-------|-------------|
| `session_id` | One conversation (button press to end) | Core |
| `turn_id` | One exchange within a session (user speaks + robot responds) | Core |
| `plan_seq` | Planner plan sequence (independent of conversation) | AI worker |

Core owns both `session_id` and `turn_id` because Core is the authority on conversation lifecycle — it sees button events, enforces cancellation, and decides when turns begin and end. Core sends `turn_id` in `ai.cmd.start_conversation` (first turn) and `ai.cmd.end_utterance` (increments turn). AI worker echoes `session_id` and `turn_id` on every semantic event. Core rejects events with a mismatched `turn_id` (stale events from reconnect).

### 7.2 State Machine

```
IDLE → CONNECTING → LISTENING → THINKING → SPEAKING → LISTENING
                                                    → IDLE (session end)
Any  → ERROR → IDLE (after backoff)
```

The AI worker emits `ai.state.changed` on every transition with `state`, `prev_state`, `session_id`, `turn_id`, and `reason`.

Valid states: `idle`, `connecting`, `listening`, `thinking`, `speaking`, `error`.

### 7.3 Transport Hygiene Rules (Non-Negotiable)

1. **Own your connections.** AI worker manages all WebSocket and HTTP sessions to the server. Core never talks to server directly.

2. **Retry with backoff.** WebSocket disconnect: 1s, 2s, 4s, cap 8s. HTTP plan failure: 3s fixed. Emit `ai.state.changed` → `error` with reason.

3. **Transport-level dedup.** Track `plan_id` values in a window (256 entries / 60 seconds). If the same `plan_id` arrives again (e.g., reconnect replay), silently drop it. This is the AI worker's responsibility.

4. **Core does semantic validation.** The AI worker emits `ai.plan.received` with the raw plan from the server. Core stamps `t_plan_rx_ns = time.monotonic_ns()` on receipt and is authoritative for:
   - Action whitelist validation (allowed actions, skills, emotions, gestures)
   - TTL enforcement: `expiry_ns = t_plan_rx_ns + ttl_ms * 1_000_000`; drop if `now > expiry_ns`. TTL is always relative to Pi receive time, never server time.
   - Sequence ordering (`plan_seq <= last_accepted` → drop)
   - Scheduling and cooldowns

5. **One clean plan per server response.** If the server sends fragments, accumulate and emit one `ai.plan.received` when complete.

6. **No audio buffering.** Audio chunks from server are forwarded immediately to the TTS worker via the direct audio socket (Mode A) or via `ai.conversation.audio` through Core (Mode B). AI worker does not play audio — that's TTS worker's job.

7. **Dedup conversation artifacts.** Server may send duplicate `done` on reconnect. Track per-session turn state, ignore duplicate finals.

8. **Session recovery.** On WebSocket drop mid-conversation, reconnect with `session_seq` incremented. If server doesn't support recovery, start fresh session.

9. **Clean shutdown.** On `system.lifecycle.shutdown`, close WebSocket gracefully, emit `ai.lifecycle.stopped`, exit.

### 7.4 Conversation Flow (Mode A — Direct Audio Socket)

```
Face button press → Core detects PTT toggle
  → Core sends ai.cmd.start_conversation (session_id, turn_id=1) to AI worker
  → Core sends tts.cmd.start_mic to TTS worker
  → AI worker opens WebSocket to /converse
  → AI worker emits ai.state.changed → connecting → listening

  ┌─ AUDIO DATA PLANE (direct sockets, bypass Core) ──────────────┐
  │ TTS worker starts arecord                                      │
  │   → mic PCM written to rb-mic socket                           │
  │   → AI worker reads from rb-mic socket                         │
  │   → AI worker forwards to server: {"type":"audio","data":"…"}  │
  └────────────────────────────────────────────────────────────────┘

  → User stops talking
  → Core sends ai.cmd.end_utterance (control plane, via NDJSON)
  → AI worker sends {"type":"end_utterance"} to server
  → AI worker emits ai.state.changed → thinking

  → Server sends transcription → ai.conversation.transcription (semantic event → Core)
  → Server sends emotion → ai.conversation.emotion → Core sends face.cmd.set_state
  → Server sends gestures → ai.conversation.gesture → Core sends face.cmd.gesture
  → AI worker emits ai.state.changed → speaking

  ┌─ AUDIO DATA PLANE (direct sockets, bypass Core) ──────────────┐
  │ Server sends audio chunks                                      │
  │   → AI worker writes TTS PCM to rb-spk socket                  │
  │   → TTS worker reads from rb-spk socket                        │
  │   → TTS worker plays via aplay                                 │
  └────────────────────────────────────────────────────────────────┘

  → TTS worker emits tts.event.energy (semantic event → Core)
  → Core translates energy → face.cmd.set_talking(True, energy)

  → Server sends done → ai.conversation.done (semantic event → Core)
  → AI worker emits ai.state.changed → listening
  → TTS worker finishes playback → tts.event.finished
  → Core sends face.cmd.set_talking(False, 0)

  → Next turn or session end
  → Core sends ai.cmd.end_conversation
  → AI worker closes WebSocket
  → AI worker emits ai.state.changed → idle
```

**Mode B (Relay):** When `audio_mode="relay"`, mic audio and TTS audio flow through Core as base64 NDJSON messages instead of the direct socket. Core forwards `tts.event.audio_chunk` → `ai.cmd.send_audio` and `ai.conversation.audio` → `tts.cmd.play_audio`. This mode exists for dev/test scenarios (mock workers, single-worker testing) and is not recommended for production due to Core throughput overhead (~32 KB/s base64).

---

## 8. Core Arbitration

Core is the sole authority for what the robot says and how the face looks. Multiple sources generate speech and face intent — Core resolves conflicts using explicit priority and composition rules.

### 8.1 Speech Arbitration

Only one speech stream is active at a time. When a higher-priority source requests speech, Core cancels the active stream before starting the new one.

**Priority levels (highest first):**

| Priority | Source | Example | Preempts |
|----------|--------|---------|----------|
| 0 (highest) | Safety | "Battery low", "Emergency stop" | All |
| 1 | Conversation | AI-generated response during active conversation | Safety only preempts this |
| 2 | Planner | `say` action from plan | Safety, Conversation |
| 3 (lowest) | Idle | Ambient remarks, idle chatter | All above |

**Rules:**

1. **One active stream.** Core tracks which source owns the current `tts.cmd.speak`. If a new request arrives at equal or lower priority, it is queued (planner) or dropped (idle).
2. **Higher priority preempts.** Core sends `tts.cmd.cancel` before issuing the new `tts.cmd.speak`. The interrupted source receives `tts.event.cancelled`.
3. **Conversation is special.** During an active conversation session, conversation-sourced audio arrives via the direct audio socket, not `tts.cmd.speak`. Core does not preempt conversation audio for planner speech — conversation holds priority 1 for the entire session. Planner `say` actions are held in the action queue until the conversation ends.
4. **Safety always wins.** Safety speech (low battery, estop, tilt) preempts everything immediately, including active conversation. Core sends `ai.cmd.cancel` + `tts.cmd.cancel`, plays safety message, then conversation may resume if conditions allow.
5. **Cooldowns still apply.** Speech arbitration happens before cooldown checks. A preempted `say` does not consume its cooldown.

**Speech channel state machine (Core-side):**
```
IDLE → PLAYING(source, priority) → IDLE
     → CANCELLING → IDLE
```

### 8.2 Face Intent Composition

The face is a layered renderer. Core composes a single `face.cmd.set_state` + optional `face.cmd.gesture` per tick from multiple intent sources. No worker or external source ever sends directly to the Face MCU — Core is the sole compositor.

**Layers (highest priority first):**

| Layer | Source | Controls | Override Behavior |
|-------|--------|----------|------------------|
| System | Core safety/lifecycle | System mode overlay (boot, error, shutdown) | Overrides all layers below |
| Talking | TTS energy events | Talking animation + energy | Overrides mood during speech |
| Conversation | AI emotion/gesture events | Mood + gestures during conversation | Overrides planner during session |
| Planner | Plan `emote`/`gesture` actions | Mood + gestures from planner | Overrides idle |
| Idle | Default behavior | Idle wander, auto-blink, base mood | Lowest priority |

**Composition rules:**

1. **System layer:** When active (boot, error, low battery, shutdown), system mode overlay is sent via `face.cmd.set_system`. All other layers are suppressed.
2. **Talking layer:** When `tts.event.energy` is active, Core sends `face.cmd.set_talking(True, energy)`. Mood is preserved from the conversation/planner layer — only the mouth animation is overlaid.
3. **Conversation layer:** During active conversation, `ai.conversation.emotion` sets the mood, `ai.conversation.gesture` triggers gestures. Planner emote/gesture actions are held (not dropped) until conversation ends.
4. **Planner layer:** Plan `emote` actions map to `face.cmd.set_state`. Plan `gesture` actions map to `face.cmd.gesture`. Subject to cooldowns (Appendix B).
5. **Idle layer:** Default mood (neutral), idle wander gaze, auto-blink. Active when no higher layer has intent.
6. **Manual lock:** Dashboard `face_manual_lock` suppresses planner and idle layers. Conversation and safety still override.

**Per-tick output:** Core evaluates all layers top-down and emits at most one `face.cmd.set_state` and one `face.cmd.gesture` per tick. If nothing changed since last tick, no command is sent (suppress duplicate writes).

---

## 9. Server API (Reference)

The server API is unchanged in v2 but with enhanced timestamp awareness.

### 9.1 POST /plan

**Request:**
```json
{
    "robot_id": "buddy-01",
    "seq": 42,
    "monotonic_ts_ms": 123456789,
    "mode": "WANDER",
    "battery_mv": 7800,
    "range_mm": 1200,
    "faults": [],
    "clear_confidence": 0.85,
    "ball_detected": true,
    "ball_confidence": 0.91,
    "ball_bearing_deg": -5.2,
    "vision_age_ms": 45.0,
    "speed_l_mm_s": 80,
    "speed_r_mm_s": 75,
    "v_capped": 80.0,
    "w_capped": 120.0,
    "trigger": "ball_seen",
    "recent_events": ["core.event.ball_acquired"],
    "planner_active_skill": "investigate_ball",
    "face_talking": false,
    "face_listening": false
}
```

**Response:**
```json
{
    "plan_id": "a1b2c3d4e5f6...",
    "robot_id": "buddy-01",
    "seq": 42,
    "monotonic_ts_ms": 123456789,
    "server_monotonic_ts_ms": 987654321,
    "actions": [...],
    "ttl_ms": 2000
}
```

### 9.2 POST /tts

**Request:** `{"text": "...", "emotion": "happy", "stream": true, "robot_id": "...", "seq": N}`

**Response:** Streaming `application/octet-stream` (raw PCM 16kHz 16-bit mono, 320B chunks).

### 9.3 WS /converse

**Query:** `?robot_id=<id>&session_seq=<seq>&session_monotonic_ts_ms=<ts>`

| Direction | Type | Fields |
|-----------|------|--------|
| Client → Server | `audio` | `data` (base64 PCM) |
| Client → Server | `end_utterance` | — |
| Client → Server | `cancel` | — |
| Client → Server | `text` | `text` (bypass STT) |
| Server → Client | `listening` | — |
| Server → Client | `transcription` | `text` |
| Server → Client | `emotion` | `emotion`, `intensity` |
| Server → Client | `gestures` | `names` (list) |
| Server → Client | `audio` | `data`, `sample_rate`, `chunk_index` |
| Server → Client | `done` | — |
| Server → Client | `error` | `message` |

### 9.4 Allowed Plan Actions

| Action | Fields | Constraints |
|--------|--------|-------------|
| `say` | `text` | max 200 chars |
| `emote` | `name`, `intensity` | 12 emotions, intensity 0.0-1.0 |
| `gesture` | `name` | 13 gestures |
| `skill` | `name` | 7 skills |

**Canonical emotions:** neutral, happy, excited, curious, sad, scared, angry, surprised, sleepy, love, silly, thinking

**Canonical gestures:** blink, wink_l, wink_r, confused, laugh, surprise, heart, x_eyes, sleepy, rage, nod, headshake, wiggle

**Allowed skills:** patrol_drift, investigate_ball, avoid_obstacle, greet_on_button, scan_for_target, approach_until_range, retreat_and_recover

### 9.5 Audio Format (All Boundaries)

| Parameter | Value |
|-----------|-------|
| Sample rate | 16,000 Hz |
| Sample width | 16-bit signed LE |
| Channels | 1 (mono) |
| Chunk size | 320 bytes (10 ms) |

---

## 10. Telemetry and Diagnostics

### 10.1 Raw Binary Log (Authoritative Replay Stream)

For every MCU packet received, the raw binary log records:

```
[t_pi_rx_ns:i64-LE] [src_id_len:u8] [src_id:utf8] [frame_len:u16-LE] [raw_bytes:N]
```

This enables deterministic replay: feed `raw_bytes` through the COBS decoder and packet parser, timestamp with recorded `t_pi_rx_ns`.

### 10.2 Derived JSONL Log

Extended from v1:

```json
{
    "wall": "2026-02-20T14:30:00",
    "t_ns": 1708444800000000000,
    "tick_seq": 500000,
    "...existing RobotState fields...",
    "clock_sync": {
        "reflex": {"state": "synced", "offset_ns": 12345, "rtt_min_us": 450, "drift_us_per_s": 12.3, "samples": 48},
        "face": {"state": "synced", "offset_ns": -5678, "rtt_min_us": 380, "drift_us_per_s": 8.1, "samples": 42}
    },
    "worker_health": {
        "vision": {"alive": true, "fps": 30.1, "last_seq": 1234, "seq_gaps": 0},
        "tts": {"alive": true, "speaking": false, "queue_depth": 0},
        "ai": {"alive": true, "state": "idle", "connected": true, "plan_seq": 42}
    }
}
```

### 10.3 Health Metrics

**Per MCU:**

| Metric | Description |
|--------|-------------|
| `sync_state` | Clock sync state: `unsynced`, `synced`, `degraded` |
| `rtt_min_us` | Minimum TIME_SYNC RTT |
| `rtt_avg_us` | Average RTT (last 16 samples) |
| `offset_ns` | Estimated clock offset |
| `drift_us_per_s` | Estimated drift rate (filtered) |
| `sync_samples` | Total accepted sync samples |
| `seq_last` | Last received sequence number |
| `seq_gaps` | Detected sequence gaps |
| `heartbeat_age_ms` | Time since last packet |

**Per Worker:**

| Metric | Description |
|--------|-------------|
| `alive` | Process running |
| `last_seq` | Last received message seq |
| `msg_rate_hz` | Messages per second (5s window) |
| `last_error` | Most recent error |
| `state` | Worker-specific state |

### 10.4 Causality Tracing

Every command from Core is logged:
```json
{"cmd_type": "reflex.cmd.set_twist", "cmd_seq": 12345, "t_cmd_tx_ns": 0, "v_mm_s": 80, "w_mrad_s": 120}
```

On MCU echo (`cmd_seq_last_applied = 12345`):
- **Command latency:** `t_applied_us * 1000 + offset_ns - t_cmd_tx_ns`
- **Round-trip:** `t_pi_rx_ns - t_cmd_tx_ns`

For planner requests:
```json
{"req_seq": 100, "t_req_tx_ns": 0, "t_resp_rx_ns": 250000000, "rtt_ms": 250.0, "plan_id": "a1b2c3d4e5f6"}
```

### 10.5 Replay

The raw binary log + NDJSON worker log form the complete replay dataset. A replay tool:

1. Reads raw binary entries, feeds through packet parser at recorded timestamps
2. Reads NDJSON entries, replays at `t_ns` timestamps
3. State machine, safety policies, event bus replay deterministically

---

## 11. Dashboard API

### 11.1 Existing Endpoints (Unchanged)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Full RobotState JSON |
| `GET` | `/params` | Parameter registry |
| `POST` | `/params` | Bulk parameter update |
| `POST` | `/actions` | RPC (set_mode, e_stop, clear_e_stop) |
| `GET` | `/video` | MJPEG stream |
| `GET` | `/debug/devices` | Device connection/transport debug |
| `GET` | `/debug/planner` | Planner state/events/scheduler |
| `WS` | `/ws` | Telemetry stream (JSON, 10-20 Hz) |
| `WS` | `/ws/logs` | Live log stream |

### 11.2 New v2 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/debug/clocks` | Clock sync status for all devices |
| `GET` | `/debug/workers` | Worker health/state |
| `GET` | `/debug/causality` | Recent command-response pairs with latency |
| `WS` | `/ws/events` | Event bus stream (NDJSON, real-time) |

---

## Appendix A: Core Event Bus Events

Edge-detected from combined RobotState + WorldState:

| Event | Trigger | Payload |
|-------|---------|---------|
| `core.event.mode_changed` | Mode transition | `{from, to}` |
| `core.event.ball_acquired` | Ball confidence ≥ 0.60 | `{confidence, bearing_deg}` |
| `core.event.ball_lost` | Ball confidence < 0.35 | `{confidence}` |
| `core.event.vision_healthy` | Vision age ≤ 500ms | `{vision_age_ms}` |
| `core.event.vision_stale` | Vision age > 500ms | `{vision_age_ms}` |
| `core.event.obstacle_close` | Range < 450mm | `{range_mm}` |
| `core.event.obstacle_cleared` | Range > 650mm | `{range_mm}` |
| `core.event.fault_raised` | Fault transitions 0→1 | `{flags, faults}` |
| `core.event.fault_cleared` | All faults clear | `{flags, faults}` |
| `face.tel.button` (pass-through) | Button event from MCU | `{button_id, event_type, state}` |
| `face.tel.touch` (pass-through) | Touch event from MCU | `{event_type, x, y}` |

Hysteresis thresholds (configurable):
- Ball acquire: ≥ 0.60 / lost: < 0.35
- Obstacle close: < 450mm / cleared: > 650mm
- Vision stale: > 500ms

---

## Appendix B: Action Scheduling

Core validates and schedules plan actions from `ai.plan.received`:

**Cooldowns (per action type):**

| Action | Type Cooldown | Key-Specific Cooldown |
|--------|---------------|-----------------------|
| say | 3s | 12s (per unique text) |
| emote | 600ms | 1.8s (per emotion name) |
| gesture | 800ms | 2s (per gesture name) |
| skill | 500ms | 500ms (per skill name) |

**Execution:** Core pops due actions each tick. Face-locked check (talking/listening) holds emote/gesture. Manual lock blocks planner face commands.

---

## Appendix C: Constants Reference

| Constant | Value | Unit |
|----------|-------|------|
| Tick rate | 50 | Hz |
| Telemetry broadcast | 20 | Hz |
| TIME_SYNC initial | 5 | Hz |
| TIME_SYNC steady-state | 2 | Hz |
| TIME_SYNC window | 16 | samples |
| TIME_SYNC ping timeout | 500 | ms |
| TIME_SYNC RTT threshold | 3 | ms (USB jitter filter) |
| TIME_SYNC stale timeout | 5 | seconds |
| TIME_SYNC min samples for synced | 5 | samples |
| Drift filter alpha | 0.1 | — |
| Audio sample rate | 16,000 | Hz |
| Audio sample width | 2 | bytes (16-bit signed) |
| Audio channels | 1 | mono |
| Audio chunk size | 320 | bytes (10ms) |
| Mic ring buffer | 200 | ms (~6400 bytes) |
| Speaker write timeout | 500 | ms |
| Audio socket connect retry | 100 | ms |
| Audio socket connect timeout | 30 | seconds |
| Energy emission rate (max) | 20 | Hz |
| Vision snapshot emission rate (max) | 10 | Hz |
| MJPEG frame emission rate (max) | 5 | Hz |
| Plan TTL min | 500 | ms |
| Plan TTL max | 5,000 | ms |
| Max say text length | 200 | chars |
| Plan dedup window | 256 | entries |
| Plan dedup TTL | 60 | seconds |
| Vision stale threshold | 500 | ms |
| Worker heartbeat interval | 1 | second |
| Worker heartbeat timeout | 5 | seconds |
| Worker max restarts | 5 | count |
| Worker restart backoff | 1-5 | seconds |
| WebSocket reconnect backoff | 1-8 | seconds (exponential) |
| HTTP plan retry backoff | 3 | seconds (fixed) |

---

## Appendix D: Migration from v1

### Phase 1: MCU protocol timestamps
- Implement SET_PROTOCOL_VERSION / PROTOCOL_VERSION_ACK handshake
- Add TIME_SYNC_REQ / TIME_SYNC_RESP to both MCU firmwares
- Extend Pi-side parser for v2 envelopes (u32 seq, u64 t_src_us)
- Graceful v1 fallback if MCU doesn't ACK v2

### Phase 2: Worker extraction
- Vision: multiprocessing.Queue → NDJSON-over-stdio worker
- TTS: inline AudioOrchestrator → TTS worker process
- AI: PlannerClient + ConversationManager → AI worker process
- Core creates two audio unix domain sockets (mic + spk) and passes paths to TTS + AI workers
- Audio streams directly between TTS ↔ AI workers (Mode A); Core handles only control signals and semantic events

### Phase 3: Causality and replay
- Add cmd_seq_last_applied to Reflex and Face telemetry
- Implement raw binary log writer
- Implement replay tool
- Add clock sync dashboard panel

### Phase 4: Rust core preparation
- Formalize all NDJSON schemas (JSON Schema or equivalent)
- Ensure no Python-specific serialization
- Worker protocol is language-agnostic (NDJSON over stdio)
