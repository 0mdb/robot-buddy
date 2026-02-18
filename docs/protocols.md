# Protocols

## Transport

USB serial between Raspberry Pi 5 and each ESP32-S3.

All packets use the same wire format:
- Raw: `[type:u8] [seq:u8] [payload:N] [crc16:u16-LE]`
- On wire: COBS-encode the raw bytes, then append `0x00` delimiter
- All multi-byte values are little-endian

## Reflex MCU Protocol (v1)

Command IDs: `0x10–0x1F` | Telemetry IDs: `0x80`

### Commands (supervisor → MCU)

| Command | ID | Payload |
|---|---|---|
| SET_TWIST | 0x10 | v_mm_s(i16) w_mrad_s(i16) — 4 bytes |
| STOP | 0x11 | reason(u8) — 1 byte |
| ESTOP | 0x12 | (empty) |
| SET_LIMITS | 0x13 | (reserved) |
| CLEAR_FAULTS | 0x14 | mask(u16) — 2 bytes |
| SET_CONFIG | 0x15 | param_id(u8) value(4 bytes) — 5 bytes |

### Telemetry (MCU → supervisor)

| Telemetry | ID | Payload |
|---|---|---|
| STATE | 0x80 | speed_l(i16) speed_r(i16) gyro_z(i16) battery_mv(u16) fault_flags(u16) range_mm(u16) range_status(u8) — 13 bytes |

### Fault Flags (bitfield)

| Bit | Name |
|---|---|
| 0 | CMD_TIMEOUT |
| 1 | ESTOP |
| 2 | TILT |
| 3 | STALL |
| 4 | IMU_FAIL |
| 5 | BROWNOUT |
| 6 | OBSTACLE |

## Face MCU Protocol (v2)

Command IDs: `0x20–0x2F` | Telemetry IDs: `0x90–0x9F`

Applies to both face backends (`esp32-face` LED matrix and `esp32-face-display` TFT).

### Commands (supervisor → MCU)

| Command | ID | Payload |
|---|---|---|
| SET_STATE | 0x20 | mood_id(u8) intensity(u8) gaze_x(i8) gaze_y(i8) brightness(u8) — 5 bytes |
| GESTURE | 0x21 | gesture_id(u8) duration_ms(u16) — 3 bytes |
| SET_SYSTEM | 0x22 | mode(u8) phase(u8) param(u8) — 3 bytes |
| SET_TALKING | 0x23 | talking(u8) energy(u8) — 2 bytes |
| AUDIO_DATA | 0x24 | chunk_len(u16) pcm_data(N) — 2+N bytes |
| SET_CONFIG | 0x25 | param_id(u8) value(4 bytes) — 5 bytes |

SET_TALKING controls the "speaking" eye animation. The supervisor sends `talking=1` when
TTS audio starts, periodic `energy` updates (0-255, RMS of current audio chunk), and
`talking=0` when audio ends.

AUDIO_DATA streams PCM audio chunks to the ESP32 speaker: 16-bit signed, 16 kHz, mono.
Recommended chunk size: 320 bytes (10 ms of audio).

SET_CONFIG param IDs (current `esp32-face-display` diagnostics):

| Param | ID | Value |
|---|---|---|
| AUDIO_TEST_TONE_MS | 0xA0 | duration_ms (u32 LE), plays 1kHz test tone |
| AUDIO_MIC_PROBE_MS | 0xA1 | duration_ms (u32 LE), logs mic RMS/peak |
| AUDIO_REG_DUMP | 0xA2 | ignored; dumps ES8311 registers to log |
| AUDIO_MIC_STREAM_ENABLE | 0xA3 | 0=off, non-zero=on (continuous mic stream) |

### Telemetry (MCU → supervisor)

| Telemetry | ID | Payload |
|---|---|---|
| FACE_STATUS | 0x90 | mood_id(u8) active_gesture(u8) system_mode(u8) flags(u8) — 4 bytes |
| TOUCH_EVENT | 0x91 | event_type(u8) x(u16) y(u16) — 5 bytes |
| MIC_PROBE | 0x92 | probe diagnostic result (24 bytes) |
| HEARTBEAT | 0x93 | uptime_ms(u32) counters(12 bytes) mic_activity(u8) + optional diag extensions |
| MIC_AUDIO | 0x94 | chunk_seq(u32) chunk_len(u16) flags(u8) reserved(u8) pcm(chunk_len) |

`MIC_AUDIO` chunks use 16-bit signed 16 kHz mono PCM. Target chunk size is 320 bytes (10 ms).

`HEARTBEAT` is append-only:
- base payload (17 bytes): uptime/status/touch/mic activity
- optional USB transport diagnostics extension
- optional audio-stream diagnostics extension

### Mood IDs (canonical — C++ `face_state.h` is source of truth)

| ID | Name | Description |
|---|---|---|
| 0 | NEUTRAL | Calm, attentive default |
| 1 | HAPPY | Pleased, upturned eyes |
| 2 | EXCITED | Wide open, high energy |
| 3 | CURIOUS | One brow raised, attentive |
| 4 | SAD | Droopy, glistening |
| 5 | SCARED | Wide eyes, shrunk pupils |
| 6 | ANGRY | Narrowed, intense (mild for kids) |
| 7 | SURPRISED | Wide open, raised brows |
| 8 | SLEEPY | Half-closed, slow blinks |
| 9 | LOVE | Heart-shaped / warm glow |
| 10 | SILLY | Cross-eyed or asymmetric |
| 11 | THINKING | Looking up/aside |

### Gesture IDs

| ID | Name | Trigger |
|---|---|---|
| 0 | BLINK | Auto / commanded |
| 1 | WINK_L | Playful emphasis |
| 2 | WINK_R | Playful emphasis |
| 3 | CONFUSED | Doesn't understand |
| 4 | LAUGH | Joke / funny moment |
| 5 | SURPRISE | Sudden realization |
| 6 | HEART | Affection burst |
| 7 | X_EYES | Silly "broken" |
| 8 | SLEEPY | Drifting off |
| 9 | RAGE | Frustrated (comedic) |
| 10 | NOD | Agreement/acknowledgment |
| 11 | HEADSHAKE | Disagreement/no |
| 12 | WIGGLE | Playful shimmy |

### System Modes

| ID | Name |
|---|---|
| 0 | NONE |
| 1 | BOOTING |
| 2 | ERROR_DISPLAY |
| 3 | LOW_BATTERY |
| 4 | UPDATING |
| 5 | SHUTTING_DOWN |

### Touch Event Types

| ID | Name |
|---|---|
| 0 | PRESS |
| 1 | RELEASE |
| 2 | DRAG |

### FACE_STATUS Flags (bitfield)

| Bit | Name |
|---|---|
| 0 | touch_active |
| 1 | audio_playing |
| 2 | mic_activity (latest probe above threshold) |

## Audio

Current production audio path for `esp32-face-display` is **CDC packet transport** over USB serial:
- **Downlink (speaker)**: supervisor sends `AUDIO_DATA` (0x24) packets with PCM chunks
- **Uplink (mic)**: face MCU sends `MIC_AUDIO` (0x94) telemetry packets with PCM chunks
- **Talking animation**: supervisor sends `SET_TALKING` (0x23) with per-chunk energy

Audio flow:
1. Personality server emits emotional response and PCM chunks
2. Supervisor forwards chunked PCM to face MCU via `AUDIO_DATA`
3. ESP32 I2S TX → ES8311 DAC/amp → speaker
4. ESP32 I2S RX mic chunks are sent back via `MIC_AUDIO`
5. Supervisor forwards mic chunks to server `/converse` STT pipeline

`esp32-face-display` still initializes TinyUSB through the composite stack, but USB Audio Class (UAC/ALSA device mode) is not the active conversational transport in this milestone.

## Conversation Pipeline

For real-time conversation (kid speaks → robot responds with emotional speech):

```
Kid speaks → ESP32 mic → Pi supervisor → 3090 Ti server
  → Whisper STT → Qwen3 14B LLM → Orpheus TTS
  → emotion + audio stream back to Pi → ESP32 face + speaker
```

The server exposes `WS /converse` for bidirectional streaming. Emotion metadata
is sent before audio so the face changes expression before the robot starts speaking.

See the full pipeline design in the plan document.
