# esp32-face-v2

ESP32-S3 firmware for Robot Buddy face rendering + supervisor link.

## Scope

- Face animation renderer (landscape 320x240)
- Python-v2 animation parity target (moods, gestures, system overlays, talking modulation)
- USB CDC command/telemetry protocol
- Touch telemetry
- Discreet corner icon controls:
  - bottom-left `PTT` (`LV_SYMBOL_AUDIO`, tap-toggle listening state)
  - bottom-right `ACTION` (`LV_SYMBOL_CHARGE`, click event)
  - visual diameter `32px`, hitbox `40px`, margin `8px`
- WS2812 status LED:
  - talking: orange
  - listening: blue
  - idle: green

Audio codec/microphone handling was removed from this firmware. Audio is owned by supervisor-side USB devices.

## Command Path Reliability

- `SET_STATE`, `SET_SYSTEM`, `SET_TALKING` use latched channels (latest value wins).
- `GESTURE` uses a FIFO queue for one-shot animations.
- This prevents high-rate talking energy updates from dropping mood/system/gesture commands.

## Rendering Note

- The face canvas uses explicit `LV_COLOR_FORMAT_RGB888` to match `lv_color_t` buffer layout.
- This removed the earlier garbled text/color corruption seen with native-format assumptions.
- System overlays are rendered through `system_overlay_v2.cpp` for Python-v2 parity:
  - booting/error/low-battery/updating/shutdown visual modes
  - scanlines + vignette post FX (config-gated in `main/config.h`)

## Current Parity Gaps

- Face center rendering is not pixel-for-pixel with sim V3 (SDF eye/mouth rasterization differences remain)
- Some sim↔MCU timing divergences documented in [docs/TODO.md](../docs/TODO.md)
- Stage 4 firmware optimization planned (dirty-rect, DMA, RGB565 dithering)

## Protocol

Commands (host -> face):

- `0x20` `SET_STATE` — mood, intensity, gaze, brightness
- `0x21` `GESTURE` — one-shot animation (FIFO queue)
- `0x22` `SET_SYSTEM` — system overlays (boot, error, battery)
- `0x23` `SET_TALKING` — lip sync (talking flag + energy)
- `0x24` `SET_FLAGS` — feature toggles (blink, wander, sparkle)
- `0x25` `SET_CONV_STATE` — conversation border state

Telemetry (face -> host):

- `0x90` `FACE_STATUS` (20 Hz)
- `0x91` `TOUCH_EVENT` (on change)
- `0x92` `BUTTON_EVENT` (on change)
- `0x93` `HEARTBEAT` (1 Hz)

## Build

```bash
idf.py build
```

## Flash + Monitor

```bash
idf.py -p /dev/ttyACM0 flash monitor
```
