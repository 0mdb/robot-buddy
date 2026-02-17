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

## Audio Firmware Status (Frozen Baseline, 2026-02-17)

Current freeze state:

- Boot is stable and startup tone is now shorter/less piercing.
- Runtime audio command path over face CDC works (`SET_CONFIG` + `AUDIO_TEST_TONE_MS`).
- Runtime speaker output is **intermittent**:
  - it can be audible right after reset,
  - then later tone commands may become silent while command sends still succeed.
- Board reset restores runtime tone in this intermittent state.
- Mic probe command executes, but `mic_activity` has not reliably asserted in recent runs.

### Confirmed working

- Hardware is fundamentally good:
  - Freenove vendor firmware produced audible prompt.
  - This firmware produces audible startup tone.
  - This firmware can produce audible runtime tone after reset.
- Audio bring-up is stable:
  - ES8311 init over I2C succeeds.
  - I2S TX/RX init succeeds at 16 kHz.
- Face CDC transport is active and accepts audio config commands.

### Confirmed unresolved

- Runtime tone audibility is not deterministic over time (intermittent silent behavior).
- Root cause is not isolated yet (likely in runtime playback state management rather than basic hardware bring-up).
- Mic activity detection still needs threshold/path tuning and validation.

### What was changed before freeze

1. ES8311 init flow aligned to working reference sequence.
2. I2S mapping and stereo framing validated (mono duplicated to L/R).
3. Amp gate control validated (`GPIO1`, active LOW).
4. Worker stack/priority and queue-liveness checks improved for runtime command handling.
5. Startup tone path moved to synchronous boot self-test and tuned to gentler sound.

### Freeze guidance

- Keep this state as baseline for next iteration.
- Do not introduce broad refactors before isolating intermittent runtime silence.
- Next debug pass should focus on:
  1. long-run runtime tone soak test with explicit state logging (`playing`, amp gate, i2s write result),
  2. mic-activity threshold calibration with captured RMS/peak logs,
  3. supervisor-visible telemetry consistency (`face_audio_playing`, `face_mic_activity`).

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

Current known deviation (2026-02-17 freeze):

- Runtime tone over CDC is intermittent: audible after some resets, then can become silent later without command-send failure.
- CDC telemetry capture during diagnostics is not always consistent enough yet for root-cause isolation.
- Mic activity flag has not been consistently observed in current tests.
