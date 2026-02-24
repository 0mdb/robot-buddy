# esp32-face

ESP32-S3 firmware for Robot Buddy face rendering + supervisor link.

## Scope

- Face animation renderer (landscape 320×240, ILI9341)
- Sim V3 animation parity target (13 moods, gestures, system face screens, talking modulation)
- USB CDC command/telemetry protocol
- Touch telemetry + corner button hit-testing
- Pixel-rendered corner button controls (SDF icons, not LVGL widgets):
  - bottom-left `PTT` (MIC icon, 60×46 px zone, tap-toggle listening)
  - bottom-right `ACTION` (X_MARK icon, 60×46 px zone, click event)
  - Icon/state/color driven automatically by conversation state
  - Suppressed (hidden + hit-testing disabled) during system overlays
- Conversation border renderer (SDF frame + glow, 8 conv states)
- WS2812 status LED:
  - talking: orange
  - listening: blue
  - idle: green

Audio codec/microphone handling was removed from this firmware. Audio is owned by supervisor-side USB devices.

## System Screens

System modes drive Buddy's face expression (eyes, mouth, eyelids, color) rather than abstract overlays — matching the Sim V3 approach. Implemented in `system_face.cpp`:

| Mode | Expression | Color | Duration |
|------|-----------|-------|----------|
| BOOTING | Sleepy slits → yawn → blink → happy bounce | Navy → cyan | 3.0 s |
| ERROR_DISPLAY | Confused face + slow headshake | Warm orange | Continuous |
| LOW_BATTERY | Sleepy with droopy eyelids + periodic yawns | Navy (dims with charge) | Continuous |
| UPDATING | Thinking expression, gaze drifts up-right | Blue-violet | Continuous |
| SHUTTING_DOWN | Yawn → droop → eyes close → fade to black | Cyan → navy → black | 2.5 s |

Small SDF icon overlays appear in the lower-right corner: warning triangle (error), battery bar (low battery), progress bar (updating).

The legacy abstract overlay renderer (`system_overlay_v2.cpp`) is retained but no longer called from the render path.

## Command Path Reliability

- `SET_STATE`, `SET_SYSTEM`, `SET_TALKING` use latched channels (latest value wins).
- `GESTURE` uses a FIFO queue for one-shot animations.
- This prevents high-rate talking energy updates from dropping mood/system/gesture commands.

## Rendering Note

- The face canvas uses explicit `LV_COLOR_FORMAT_RGB888` to match `lv_color_t` buffer layout.
- This removed the earlier garbled text/color corruption seen with native-format assumptions.

## Current Parity Gaps

- Face center rendering is not pixel-for-pixel with sim V3 (SDF eye/mouth rasterization differences remain)
- Some sim↔MCU timing divergences documented in [docs/TODO.md](../docs/TODO.md)
- Stage 4 firmware optimization planned (dirty-rect, DMA, RGB565 dithering)

## Protocol

Commands (host → face):

- `0x20` `SET_STATE` — mood, intensity, gaze, brightness
- `0x21` `GESTURE` — one-shot animation (FIFO queue)
- `0x22` `SET_SYSTEM` — system mode + param (boot, error, battery, updating, shutdown)
- `0x23` `SET_TALKING` — lip sync (talking flag + energy)
- `0x24` `SET_FLAGS` — feature toggles (blink, wander, sparkle, afterglow, edge glow)
- `0x25` `SET_CONV_STATE` — conversation border state (0–7)

Telemetry (face → host):

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
