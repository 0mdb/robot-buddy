# Protocols

## Transport
USB serial between Raspberry Pi 5 and each ESP32.

USB serial between Raspberry Pi 5 and each ESP32-S3.

All packets use the same wire format:
- Raw: `[type:u8] [seq:u8] [payload:N] [crc16:u16-LE]`
- On wire: COBS-encode the raw bytes, then append `0x00` delimiter
- All multi-byte values are little-endian

## Reflex MCU Protocol (v1)

Command IDs: `0x10–0x1F` | Telemetry IDs: `0x80`

### Commands (supervisor → MCU)

| Command      | ID   | Payload                               |
| ------------ | ---- | ------------------------------------- |
| SET_TWIST    | 0x10 | v_mm_s(i16) w_mrad_s(i16) — 4 bytes   |
| STOP         | 0x11 | reason(u8) — 1 byte                   |
| ESTOP        | 0x12 | (empty)                               |
| SET_LIMITS   | 0x13 | (reserved)                            |
| CLEAR_FAULTS | 0x14 | mask(u16) — 2 bytes                   |
| SET_CONFIG   | 0x15 | param_id(u8) value(4 bytes) — 5 bytes |

### Telemetry (MCU → supervisor)

| Telemetry | ID   | Payload                                                                                                          |
| --------- | ---- | ---------------------------------------------------------------------------------------------------------------- |
| STATE     | 0x80 | speed_l(i16) speed_r(i16) gyro_z(i16) battery_mv(u16) fault_flags(u16) range_mm(u16) range_status(u8) — 13 bytes |

### Fault Flags (bitfield)

| Bit | Name        |
| --- | ----------- |
| 0   | CMD_TIMEOUT |
| 1   | ESTOP       |
| 2   | TILT        |
| 3   | STALL       |
| 4   | IMU_FAIL    |
| 5   | BROWNOUT    |
| 6   | OBSTACLE    |

## Face MCU Protocol (v3)

Command IDs: `0x20–0x2F` | Telemetry IDs: `0x90–0x9F`

Applies to current face display backend (`esp32-face`).

### Commands (supervisor → MCU)

| Command       | ID   | Payload                                                                    |
| ------------- | ---- | -------------------------------------------------------------------------- |
| SET_STATE     | 0x20 | mood_id(u8) intensity(u8) gaze_x(i8) gaze_y(i8) brightness(u8) — 5 bytes  |
| GESTURE       | 0x21 | gesture_id(u8) duration_ms(u16) — 3 bytes                                 |
| SET_SYSTEM    | 0x22 | mode(u8) phase(u8) param(u8) — 3 bytes                                    |
| SET_TALKING   | 0x23 | talking(u8) energy(u8) — 2 bytes                                          |
| SET_FLAGS     | 0x24 | flags(u8) — 1 byte                                                        |
| SET_CONV_STATE| 0x25 | conv_state(u8) — 1 byte                                                   |

SET_TALKING controls the "speaking" animation state. The supervisor sends
`talking=1` during local speaker playback with periodic energy updates and sends
`talking=0` when playback ends.

SET_FLAGS controls renderer/animation feature toggles. The `flags` byte is a
bitfield; unset bits disable the corresponding feature:

| Bit | Constant          | Description                              |
| --- | ----------------- | ---------------------------------------- |
| 0   | IDLE_WANDER       | Idle gaze wander animation               |
| 1   | AUTOBLINK         | Autonomous blink timing                  |
| 2   | SOLID_EYE         | Solid fill eyes (no gradient)            |
| 3   | SHOW_MOUTH        | Render mouth feature                     |
| 4   | EDGE_GLOW         | Edge glow effect                         |
| 5   | SPARKLE           | Sparkle particle effect                  |
| 6   | AFTERGLOW         | Afterglow trail effect                   |

SET_CONV_STATE sets the current conversation phase, which drives the border
animation rendered around the face display:

| Value | Name      | Border Effect                             |
| ----- | --------- | ----------------------------------------- |
| 0     | IDLE      | No border                                 |
| 1     | ATTENTION | Pulse on                                  |
| 2     | LISTENING | Steady colored frame                      |
| 3     | PTT       | PTT-color frame                           |
| 4     | THINKING  | Animated shimmer                          |
| 5     | SPEAKING  | Ripple/pulse driven by speech energy      |
| 6     | ERROR     | Red flash                                 |
| 7     | DONE      | Fade out                                  |

Command channel semantics in `esp32-face`:
- `SET_STATE`, `SET_SYSTEM`, `SET_TALKING`, `SET_FLAGS`, `SET_CONV_STATE` are latched last-value channels.
- `GESTURE` is a FIFO one-shot queue.
- High-rate `SET_TALKING` updates must not overwrite queued gestures or latched mood/system.

### Telemetry (MCU → supervisor)

| Telemetry    | ID   | Payload                                                            |
| ------------ | ---- | ------------------------------------------------------------------ |
| FACE_STATUS  | 0x90 | mood_id(u8) active_gesture(u8) system_mode(u8) flags(u8) — 4 bytes |
| TOUCH_EVENT  | 0x91 | event_type(u8) x(u16) y(u16) — 5 bytes                             |
| BUTTON_EVENT | 0x92 | button_id(u8) event_type(u8) state(u8) reserved(u8) — 4 bytes      |
| HEARTBEAT    | 0x93 | uptime + tx counters + USB diagnostics + ptt_listening             |

`BUTTON_EVENT` IDs:
- button `0`: PTT (tap-toggle)
- button `1`: ACTION (click)

UI note: face-v2 renders these as small bottom-corner icon controls; telemetry IDs and event types are unchanged.

`BUTTON_EVENT` types:
- `0`: PRESS
- `1`: RELEASE
- `2`: TOGGLE
- `3`: CLICK

### Mood IDs (canonical — C++ `face_state.h` is source of truth)

| ID  | Name      | Description                       |
| --- | --------- | --------------------------------- |
| 0   | NEUTRAL   | Calm, attentive default           |
| 1   | HAPPY     | Pleased, upturned eyes            |
| 2   | EXCITED   | Wide open, high energy            |
| 3   | CURIOUS   | One brow raised, attentive        |
| 4   | SAD       | Droopy, glistening                |
| 5   | SCARED    | Wide eyes, shrunk pupils          |
| 6   | ANGRY     | Narrowed, intense (mild for kids) |
| 7   | SURPRISED | Wide open, raised brows           |
| 8   | SLEEPY    | Half-closed, slow blinks          |
| 9   | LOVE      | Heart-shaped / warm glow          |
| 10  | SILLY     | Cross-eyed or asymmetric          |
| 11  | THINKING  | Looking up/aside                  |
| 12  | CONFUSED  | Head-tilt, questioning look       |

### Gesture IDs

| ID  | Name      | Trigger                  |
| --- | --------- | ------------------------ |
| 0   | BLINK     | Auto / commanded         |
| 1   | WINK_L    | Playful emphasis         |
| 2   | WINK_R    | Playful emphasis         |
| 3   | CONFUSED  | Doesn't understand       |
| 4   | LAUGH     | Joke / funny moment      |
| 5   | SURPRISE  | Sudden realization       |
| 6   | HEART     | Affection burst          |
| 7   | X_EYES    | Silly "broken"           |
| 8   | SLEEPY    | Drifting off             |
| 9   | RAGE      | Frustrated (comedic)     |
| 10  | NOD       | Agreement/acknowledgment |
| 11  | HEADSHAKE | Disagreement/no          |
| 12  | WIGGLE    | Playful shimmy           |

Canonical gesture names used by server/supervisor validation:
`blink, wink_l, wink_r, confused, laugh, surprise, heart, x_eyes, sleepy, rage, nod, headshake, wiggle`

### System Modes

| ID  | Name          |
| --- | ------------- |
| 0   | NONE          |
| 1   | BOOTING       |
| 2   | ERROR_DISPLAY |
| 3   | LOW_BATTERY   |
| 4   | UPDATING      |
| 5   | SHUTTING_DOWN |

### Touch Event Types

| ID  | Name    |
| --- | ------- |
| 0   | PRESS   |
| 1   | RELEASE |
| 2   | DRAG    |

### FACE_STATUS Flags (bitfield)

| Bit | Name          |
| --- | ------------- |
| 0   | touch_active  |
| 1   | talking       |
| 2   | ptt_listening |

## Audio

Audio is owned by supervisor-side USB devices in face-v2.

- Face MCU no longer carries speaker/mic PCM over CDC protocol.
- Face MCU only receives `SET_TALKING` energy updates to animate speech.
- Touch/button telemetry from face is used by supervisor to drive local audio control
  (PTT toggle and action events).

## Conversation Pipeline

For real-time conversation (kid speaks → robot responds with emotional speech):

```
Kid speaks → Pi USB mic → Pi supervisor → 3090 Ti server
  → Whisper STT → Qwen3 14B LLM → Orpheus TTS
  → emotion + audio stream back to Pi → Pi USB speaker + ESP32 face animation
```

The server exposes `WS /converse` for bidirectional streaming. Emotion metadata
is sent before audio so the face changes expression before the robot starts speaking.

See the full pipeline design in the plan document.
