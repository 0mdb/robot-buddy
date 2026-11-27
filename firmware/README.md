# firmware

The STM32G431 firmware (reflex v3 onward) lives in **`~/mcu-core`** (one Cargo workspace for
robot-buddy and robot-scout, Ben 2026-11-27): `boards/buddy-reflex` (port of `esp32-reflex`),
`crates/buddy-reflex-core` (logic, wire-compat tests against `supervisor/devices/protocol.py`),
`boards/nucleo-bench` (phase 0 bench). Moved out of this repo after `9ba1f14`.

The ESP32 firmware stays here: `esp32-reflex/` (v2 board), `esp32-face/`.
