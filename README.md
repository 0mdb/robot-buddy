# Robot Buddy (Working Name)

A kid-proof, expressive robot platform combining real-time motor control, an animated LED face, and networked local AI (LLM/TTS) for personality and interaction.

See `docs/architecture.md` for the current source-of-truth design decisions.

## Quick Start (Repo layout)
- `esp32-face/`   Face MCU firmware (ESP32-S3, ESP-IDF). Drives 2× 16×16 WS2812 "eyes".
- `esp32-reflex/` Reflex MCU firmware (ESP32-S3, ESP-IDF). Motors + encoders + safety.
- `jetson-runtime/` Python runtime on Jetson Nano. Orchestrates behavior, face, audio, and talks to both MCUs over USB serial.
- `server/`       Optional 3090 Ti personality services (LLM/TTS/STT) on local network.
- `docs/`         Architecture, protocols, power, and bring-up guides.

## TODO: First bring-up milestones
- [ ] Bring up Face MCU with solid-color + XY mapping
- [ ] Implement Face protocol (USB serial) + Jetson `face_client.py`
- [ ] Bring up Reflex MCU: motor driver PWM + direction
- [ ] Add encoders (PCNT) + wheel speed reporting
- [ ] Add closed-loop speed PID
- [ ] Power: stable 2S→5V rail sized for Jetson + LEDs; fuse + caps
