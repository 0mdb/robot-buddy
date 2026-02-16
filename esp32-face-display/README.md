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

## Verified Pi5 Integration Workflow (Face-Only)

Use this when testing face MCU + supervisor before reflex MCU is connected.

1. Confirm face USB path on Pi:

```bash
ls -l /dev/serial/by-id
```

Expected runtime descriptor in current build:

- `usb-Espressif_Systems_Espressif_Device_123456-if00`

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
