# Architecture

## Locked Decisions
- 2× ESP32-S3:
  - Face MCU (ES3C28P): 320x240 TFT display (ILI9341) + touch/buttons, LVGL rendering (`esp32-face-v2`)
  - Reflex MCU (WROOM): motors/encoders/IMU/ultrasonic/safety (ESP-IDF, PCNT + LEDC)
- Raspberry Pi 5 runs the Python supervisor and orchestrates timing at 50 Hz.
- AI planner services run off-robot on a 3090 Ti server (vLLM + Qwen2.5-3B-Instruct, Ollama legacy fallback) via local network.
- Battery is 2S; separate "dirty" motor rail vs "clean" regulated 5V rail.

## Key principle
Reflexes are local and deterministic; planner can be remote and optional.

## Open Questions
- Final battery pack choice (2S LiPo vs welded 2S 18650 pack with BMS)
- Motor voltage strategy (raw 2S capped PWM vs regulated motor rail)
