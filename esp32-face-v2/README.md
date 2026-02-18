# esp32-face-v2

ESP32-S3 firmware for Robot Buddy face rendering + supervisor link.

## Scope

- Face animation renderer (landscape 320x240)
- USB CDC command/telemetry protocol
- Touch telemetry
- Bottom touch buttons:
  - `PTT` (tap-toggle listening state)
  - `ACTION` (click event)
- WS2812 status LED:
  - talking: orange
  - listening: blue
  - idle: green

Audio codec/microphone handling was removed from this firmware. Audio is owned by supervisor-side USB devices.

## Protocol (v3)

Commands (host -> face):

- `0x20` `SET_STATE`
- `0x21` `GESTURE`
- `0x22` `SET_SYSTEM`
- `0x23` `SET_TALKING`

Telemetry (face -> host):

- `0x90` `FACE_STATUS`
- `0x91` `TOUCH_EVENT`
- `0x92` `BUTTON_EVENT`
- `0x93` `HEARTBEAT`

## Build

```bash
idf.py build
```

## Flash + Monitor

```bash
idf.py -p /dev/ttyACM0 flash monitor
```
