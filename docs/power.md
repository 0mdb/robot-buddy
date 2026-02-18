# Power

## Goal
Run Raspberry Pi 5 + 2× ESP32-S3 + WS2812 face + motors from a 2S pack reliably.

## Recommended topology
- 2S pack -> main fuse -> switch -> split rails
  - Dirty rail: motors (TB6612 VM)
  - Clean rail: 2S -> high-quality buck -> 5V bus (Pi 5 + ESP32s + LEDs)

## TODO
- [ ] Decide 5V buck part + current rating (target 8–10A class)
- [ ] Add bulk capacitance near Pi 5 5V input
- [ ] Add bulk capacitance near LED 5V input
- [ ] Confirm grounding + wiring gauge recommendations
