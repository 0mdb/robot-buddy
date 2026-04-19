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
| FACE_STATUS  | 0x90 | v1: mood_id(u8) active_gesture(u8) system_mode(u8) flags(u8) — 4 bytes; v2: adds cmd_seq_last_applied(u32) + t_state_applied_us(u32) — 12 bytes total |
| TOUCH_EVENT  | 0x91 | event_type(u8) x(u16) y(u16) — 5 bytes                             |
| BUTTON_EVENT | 0x92 | button_id(u8) event_type(u8) state(u8) reserved(u8) — 4 bytes      |
| HEARTBEAT    | 0x93 | base payload: uptime + tx counters + USB diagnostics + ptt_listening (68 bytes) + optional perf tail (56 bytes, parsed by length) |

`BUTTON_EVENT` IDs:
- button `0`: PTT (tap-toggle)
- button `1`: ACTION (click)

UI note: face-v2 renders these as small bottom-corner icon controls; telemetry IDs and event types are unchanged.

`BUTTON_EVENT` types:
- `0`: PRESS
- `1`: RELEASE
- `2`: TOGGLE
- `3`: CLICK

`HEARTBEAT` optional perf tail fields (appended only when present):
- `window_frames(u32)`
- `frame_us_avg(u32)`, `frame_us_max(u32)`
- `render_us_avg(u32)`, `render_us_max(u32)`
- `eyes_us_avg(u32)`, `mouth_us_avg(u32)`, `border_us_avg(u32)`, `effects_us_avg(u32)`, `overlay_us_avg(u32)`
- `dirty_px_avg(u32)`, `spi_bytes_per_s(u32)`, `cmd_rx_to_apply_us_avg(u32)`
- `perf_sample_div(u16)`, `dirty_rect_enabled(u8)`, `afterglow_downsample(u8)`

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

## MCU Benchmark Harness

Cross-MCU performance benchmark with a shared core and target-specific adapters.
Collects time-series telemetry samples, computes percentile stats, writes versioned
JSON artifacts, and supports A/B comparison.

### Quick Start

```bash
# Face benchmark against live supervisor (5 scenarios, 100 samples each)
just mcu-benchmark --target face --base-url http://192.168.55.201:8080

# Custom sample count + output directory
just mcu-benchmark --target face --samples 200 --out docs/perf

# Reflex benchmark (idle only — safe default)
just mcu-benchmark --target reflex --base-url http://192.168.55.201:8080

# Reflex with motion scenario (requires explicit opt-in)
just mcu-benchmark --target reflex --allow-motion --base-url http://...

# Compare two artifacts (A/B telemetry overhead, <=1% FPS drop gate)
just mcu-benchmark --compare docs/perf/baseline.json docs/perf/test.json
```

### Supervisor API

| Endpoint | Method | Description |
|---|---|---|
| `/debug/mcu_benchmark` | GET | Current run status (idle/running/completed/failed) |
| `/ws` | WS `mcu_benchmark.start` | Start a benchmark run |
| `/ws` | WS `mcu_benchmark.cancel` | Cancel a running benchmark |

WS start payload:
```json
{
  "type": "mcu_benchmark.start",
  "target": "face",
  "profile": "stage4_face",
  "samples": 100,
  "base_url": "http://localhost:8080",
  "out_dir": "docs/perf",
  "allow_motion": false
}
```

### Face Scenarios

| Scenario | Setup | What it stresses |
|---|---|---|
| `idle` | Neutral mood, no animation | Baseline frame cost |
| `listening_proxy` | LISTENING conv state | Border pulse animation |
| `thinking_border` | THINKING conv state | Heavy border animation (hotspot) |
| `talking_energy` | Happy + talking + energy=180 | Mouth animation + energy |
| `rage_effects` | Angry mood | Effects pipeline |

### Reflex Scenarios

| Scenario | Requires | What it measures |
|---|---|---|
| `idle_hold` | (always) | State update rate, jitter, age |
| `step_response` | `--allow-motion` | Velocity tracking error |

### Output Artifacts

Written to `docs/perf/` as versioned JSON (schema v2):

```json
{
  "version": 2,
  "target": "face",
  "profile": "stage4_face",
  "captured_at": "2026-02-26T...",
  "endpoint": "http://...",
  "scenarios": {
    "idle": {
      "frames": 6400,
      "frame_us_avg": 75000,
      "frame_us_max": 80000,
      "frame_us_p50": 74500.0,
      "frame_us_p95": 79200.0,
      "render_us_avg": 7500,
      "render_us_p50": 7200.0,
      "render_us_p95": 8100.0,
      "border_us_avg": 23000,
      "border_us_p50": 22800.0,
      "border_us_p95": 24100.0,
      "mouth_us_avg": 6900,
      "mouth_us_p50": 6800.0,
      "mouth_us_p95": 7200.0,
      "fps_est": 13.33,
      "eyes_us_avg": 12700,
      "effects_us_avg": 17000,
      "overlay_us_avg": 5,
      "dirty_px_avg": 9600,
      "spi_bytes_per_s": 192000,
      "cmd_rx_to_apply_us_avg": 1000,
      "samples": 100,
      "elapsed_s": 99.1
    }
  }
}
```

Legacy fields (`frame_us_avg`, `frame_us_max`, etc.) are preserved for backward
comparison with v1 artifacts. New fields: `frame_us_p50`, `frame_us_p95`,
`render_us_p50/p95`, `border_us_p50/p95`, `mouth_us_p50/p95`.

### Compare Mode

Compares two artifacts and reports per-scenario FPS delta with pass/fail:

```bash
just mcu-benchmark --compare docs/perf/baseline.json docs/perf/with_telemetry.json
```

Output includes `fps_drop_pct` per scenario and `overall_pass` (true if all
scenarios stay within the threshold, default <=1% FPS drop).

### Architecture

```
supervisor/api/
├── mcu_benchmark.py          # Shared core: stats, lifecycle, artifact I/O, compare, CLI
├── mcu_benchmark_face.py     # Face adapter: 5 scenarios, heartbeat polling, p50/p95
└── mcu_benchmark_reflex.py   # Reflex adapter: rate/jitter/age, opt-in motion
```

The harness runs against an already-running supervisor endpoint. It polls
`/debug/devices` for telemetry and sends face/reflex commands via `/ws`.
Flashing/deploy remains manual.
