# esp32-face-display

## Critical Notes (USB + Boot Stability)

### 1) Boot-loop root cause and required fix

If the board flickers/reboots right after display init, check `main/touch.cpp`:

```cpp
tp_io_cfg.scl_speed_hz = 400000;
```

Without this line, `esp_lcd_new_panel_io_i2c(...)` can fail with:

- `invalid scl frequency`
- `ESP_ERR_INVALID_ARG`

That failure triggers panic/reset and looks like a display flicker boot loop.

### 2) Diagnostic mode warning (can disable supervisor USB)

When enabled, diagnostic mode intentionally disables TinyUSB runtime in `main/config.h`:

```cpp
#define DIAG_DISABLE_TINYUSB 1
```

This prevents the face CDC/UAC interface from enumerating, so the supervisor cannot connect over USB.

Normal mode for supervisor integration is:

```cpp
#define DIAG_DISABLE_TINYUSB 0
```

## Current Runtime Status (2026-02-18)

### CDC full-duplex audio path is implemented

- USB RX command handling is active for:
  - `SET_STATE (0x20)`
  - `GESTURE (0x21)`
  - `SET_SYSTEM (0x22)`
  - `SET_TALKING (0x23)`
  - `AUDIO_DATA (0x24)`
  - `SET_CONFIG (0x25)` including `AUDIO_MIC_STREAM_ENABLE (0xA3)`
- RX frame buffer supports conversational chunk sizes (`MAX_FRAME=768`).
- Speaker path uses non-blocking queue + dedicated playback worker (drop-oldest on overflow).
- Mic path uses dedicated capture worker and emits `MIC_AUDIO (0x94)` telemetry chunks at 10 ms cadence.
- Talking animation is now wired to command energy with timeout auto-clear.
- Heartbeat (`0x93`) includes append-only audio diagnostics tail:
  - speaker rx/play counters
  - mic capture/tx/drop/overrun counters
  - mic queue depth + mic stream enabled flag

### Runtime observations

- Face telemetry and RX command flow are stable in normal runtime operation.
- A few bad CRC frames can appear during initial USB attach; stream recovers quickly.
- Conversational TTS audio reaches the face speaker path (validated by increasing
  `speaker_rx_chunks` and `speaker_play_chunks` with `speaker_play_errors=0`).
- Current main gap is speaker intelligibility/quality; transport is functioning but
  synthesized speech is often hard to understand.
- True mic-turn conversation is still blocked in latest probe: continuous `MIC_AUDIO`
  packets are present, but sampled PCM energy was `0` across the window
  (`energy_p95=0`, `energy_max=0`), so supervisor VAD does not trigger
  `end_utterance`.

## Verified Pi5 Integration Workflow (Face-Only)

Use this when testing face MCU + supervisor before reflex MCU is connected.

1. Confirm face USB path on Pi:

```bash
ls -l /dev/serial/by-id
```

Runtime descriptor can switch during flashing/reset cycles. Common aliases seen:

- `usb-Espressif_Systems_Espressif_Device_123456-if00` (runtime app CDC)
- `usb-Espressif_USB_JTAG_serial_debug_unit_3C:0F:02:DD:C4:B4-if00` (flash/debug path)

Use whichever alias exists at runtime.

2. Run supervisor in face-only mode (`--mock` reflex):

```bash
cd ~/robot-buddy/supervisor
./.venv/bin/python -m supervisor \
  --mock \
  --face-port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 \
  --no-vision \
  --http-port 8080 \
  --log-level INFO
```

3. Validate status:

```bash
curl -s http://127.0.0.1:8080/status
```

Expected:

- `"face_connected": true`
- `"reflex_connected": true` (because `--mock` is enabled)

## Planner Server Timeout Tuning

If `planner_connected` flaps with `"/plan returned 504: Model took too long to respond"`, increase both server and supervisor timeouts.

Server (3090 host):

```bash
cd ~/robot-buddy/server
PLAN_TIMEOUT_S=12 MAX_ACTIONS=4 NUM_CTX=4096 uv run python -m app.main
```

Supervisor (Pi):

```bash
cd ~/robot-buddy/supervisor
./.venv/bin/python -m supervisor \
  --mock \
  --face-port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 \
  --no-vision \
  --planner-api http://192.168.55.64:8100 \
  --planner-timeout 15.0 \
  --http-port 8080
```

Target status fields:

- `"planner_enabled": true`
- `"planner_connected": true`
- `"planner_last_error": ""`

## Supervisor Diagnostics (Face Audio Bring-up)

Use these endpoints while diagnosing face RX/mic issues:

```bash
curl -s http://127.0.0.1:8080/status
curl -s http://127.0.0.1:8080/debug/devices
curl -s -X POST http://127.0.0.1:8080/actions \
  -H 'content-type: application/json' \
  -d '{"action":"face_mic_probe","duration_ms":1800}'
```

Most important fields under `face`:

- `transport.rx_bytes`, `transport.tx_bytes`
- `transport.frames_ok`, `transport.frames_bad`
- `rx_face_status_packets`, `rx_mic_probe_packets`, `rx_mic_audio_packets`, `rx_heartbeat_packets`
- `last_mic_probe`, `last_mic_audio`, `last_heartbeat`
- `last_heartbeat.audio.*` counters (speaker/mic stream health)

## Audio Validation Workflow (Current Firmware)

Audio bring-up is now wired for:

- ES8311 codec init over shared touch I2C bus (`GPIO16/15`)
- I2S TX/RX init (`MCK=4`, `BCK=5`, `WS=7`, `DOUT=8`, `DIN=6`)
- Amp gate control (`GPIO1`, active LOW)
- 1kHz tone test
- Mic RMS/peak probe logging
- 10 ms speaker stream ingest (`AUDIO_DATA`) into playback queue
- 10 ms mic stream telemetry (`MIC_AUDIO`) when enabled
- Current debug toggles in `main/audio.cpp`:
  - `FORCE_SYNC_DIAGNOSTICS=false`
  - `KEEP_AMP_ENABLED_BETWEEN_PLAYS=false`

### Trigger diagnostics over face CDC (`SET_CONFIG`, cmd `0x25`)

Payload format:

- `param_id:u8` + `value:u32 little-endian`

Audio params:

- `0xA0` (`AUDIO_TEST_TONE_MS`): play 1kHz tone for `value` ms
- `0xA1` (`AUDIO_MIC_PROBE_MS`): capture mic for `value` ms and log RMS/peak
- `0xA3` (`AUDIO_MIC_STREAM_ENABLE`): `0=off`, `1=on` for continuous `MIC_AUDIO` uplink

Use helper script:

```bash
cd ~/robot-buddy
python tools/face_audio_diag.py --port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 --tone-ms 1500
python tools/face_audio_diag.py --port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 --mic-ms 3000
```

Quick pass criteria:

- Tone command: audible 1kHz tone from speaker for requested duration
- Mic command: firmware log line with `rms`, `peak`, `dbfs`
- During tone playback, `/status` shows `"face_audio_playing": true`
- After mic probe, `/status` shows `"face_mic_activity": true` when speech/clap is detected

### Continuous stream soak (downlink + uplink)

Use the soak tool for sustained CDC streaming:

```bash
cd ~/robot-buddy
python tools/face_audio_soak.py \
  --port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 \
  --seconds 120
```

Expected:

- `tx_audio_chunks` increases at ~100 chunks/s.
- `rx_mic_audio_packets` increases continuously while mic stream is enabled.
- `heartbeat.audio.speaker_play_errors` remains at `0`.
- `heartbeat.audio.speaker_rx_drops` remains at `0`.

Observed under heavy full-duplex stress (10-minute run):

- Speaker path remained stable (`speaker_play_errors=0`, `speaker_rx_drops=0`).
- Mic uplink remained active, but queue pressure can produce `mic_tx_drops`,
  `mic_overruns`, and non-zero `mic_seq_gaps` when host/USB is saturated.

### Reconnect validation

- USB unplug/replug recovery has been verified.
- After re-enumeration, supervisor reconnects and `rx_mic_audio_packets` and
  heartbeat audio counters resume incrementing.
