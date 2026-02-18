# Architecture

## Locked Decisions
- 2× ESP32-S3 WROOM:
  - Face MCU: WS2812 eyes + animations (ESP-IDF `led_strip` / RMT)
  - Reflex MCU: motors/encoders/safety (ESP-IDF, PCNT + LEDC)
- Raspberry Pi 5 runs the Python supervisor and orchestrates timing at 50 Hz.
- AI personality services run off-robot on a 3090 Ti server (Ollama + Qwen 3 14B) via local network.
- Battery is 2S; separate "dirty" motor rail vs "clean" regulated 5V rail.

## Key principle
Reflexes are local and deterministic; personality can be remote and optional.

## Open Questions
- Final battery pack choice (2S LiPo vs welded 2S 18650 pack with BMS)
- Motor voltage strategy (raw 2S capped PWM vs regulated motor rail)
