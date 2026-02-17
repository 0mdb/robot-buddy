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

## Current Runtime Status (2026-02-17)

### Resolved blocker

- Face MCU -> supervisor serial telemetry is now working in runtime.
- Verified in supervisor `/debug/devices` on runtime USB alias:
  - `face.connected=true`
  - `rx_face_status_packets` increments continuously
  - `rx_heartbeat_packets` increments continuously
  - `face_mic_probe` action increments `rx_mic_probe_packets` and populates
    `last_mic_probe`
  - `transport.rx_bytes` and `transport.frames_ok` increment as expected

### Root cause and firmware fix

- Root cause: `usb_rx_task` used `vTaskDelay(pdMS_TO_TICKS(1))` in its idle
  path. With `CONFIG_FREERTOS_HZ=100`, this converts to `0` ticks and can
  starve lower-priority tasks.
- Fix: clamp the idle delay to at least one tick in `main/usb_rx.cpp`:
  `idle_delay_ticks = max(pdMS_TO_TICKS(1), 1)`.

### Production cleanup completed

- Removed temporary debug ACK telemetry packet from firmware:
  - removed `FaceTelId::CMD_ACK` (`0x94`)
  - removed `FaceCmdAckPayload`
  - removed `send_cmd_ack(...)` path in RX command handler
  - removed telemetry loop debug counter API used only by CMD_ACK
- Result: `rx_unknown_packets` stays at `0` in normal operation.

### Remaining observation

- A small number of bad CRC frames can occur during initial USB attach, but
  telemetry recovers and packet flow remains stable.

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

## Personality Server Timeout Tuning

If `personality_connected` flaps with `"/plan returned 504: Model took too long to respond"`, increase both server and supervisor timeouts.

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
  --server-api http://192.168.55.64:8100 \
  --server-timeout 15.0 \
  --http-port 8080
```

Target status fields:

- `"personality_enabled": true`
- `"personality_connected": true`
- `"personality_last_error": ""`

## Supervisor Diagnostics (Added for Face Audio Bring-up)

Use these endpoints while diagnosing face RX/mic issues:

```bash
curl -s http://127.0.0.1:8080/debug/devices
curl -s -X POST http://127.0.0.1:8080/actions \
  -H 'content-type: application/json' \
  -d '{"action":"face_mic_probe","duration_ms":1800}'
```

Most important fields under `face`:

- `transport.rx_bytes`, `transport.tx_bytes`
- `transport.frames_ok`, `transport.frames_bad`
- `rx_face_status_packets`, `rx_mic_probe_packets`, `rx_heartbeat_packets`
- `last_mic_probe`, `last_heartbeat`

## Audio Driver Diagnostics (Current Firmware)

Audio bring-up is now wired for:

- ES8311 codec init over shared touch I2C bus (`GPIO16/15`)
- I2S TX/RX init (`MCK=4`, `BCK=5`, `WS=7`, `DOUT=8`, `DIN=6`)
- Amp gate control (`GPIO1`, active LOW)
- 1kHz tone test
- Mic RMS/peak probe logging
- Current debug toggles in `main/audio.cpp`:
  - `FORCE_SYNC_DIAGNOSTICS=false`
  - `KEEP_AMP_ENABLED_BETWEEN_PLAYS=false`

### Trigger diagnostics over face CDC (`SET_CONFIG`, cmd `0x25`)

Payload format:

- `param_id:u8` + `value:u32 little-endian`

Audio params:

- `0xA0` (`AUDIO_TEST_TONE_MS`): play 1kHz tone for `value` ms
- `0xA1` (`AUDIO_MIC_PROBE_MS`): capture mic for `value` ms and log RMS/peak

Use helper script:

```bash
cd ~/robot-buddy
python tools/face_audio_diag.py --port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 --tone-ms 1500
python tools/face_audio_diag.py --port /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_123456-if00 --mic-ms 3000
```

Target behavior:

- Tone command: audible 1kHz tone from speaker for requested duration
- Mic command: firmware log line with `rms`, `peak`, `dbfs`
- During tone playback, `/status` shows `"face_audio_playing": true`
- After mic probe, `/status` shows `"face_mic_activity": true` when speech/clap is detected

Current known deviation (latest on 2026-02-17):

- No blocking face telemetry deviations are currently known.
- On some attaches, `frames_bad` may briefly increment from a CRC mismatch
  before the stream stabilizes.
