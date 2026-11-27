# reflex-core

Hardware-free reflex MCU logic for the STM32G431 port, `no_std`, no allocation. Ported from
`esp32-reflex/main`; the G431 firmware (`../nucleo-g431`, later the reflex v3 board) links it.

- `protocol`: COBS + CRC16 framing, v1/v2 envelopes, command decode, STATE layout
  (`protocol.{h,cpp}`, `usb_rx.cpp`).
- `link`: the host session, **protocol v2 only** (v1 exists only on the ESP32s): accepts the v1
  handshake request and ACKs in v2, drops other v1 frames; time sync, TX seq, last command seq.
- `config`: defaults and SET_CONFIG IDs (`config.{h,cpp}`).
- Not yet ported: control (FF + PI, rate limits, yaw damping) and safety (soft/hard stop, tilt,
  stall, obstacle latch).

```sh
cargo test                                    # host tests
python3 tests/gen_vectors.py                  # (from the repo root) regenerate supervisor vectors
```

`tests/wire_compat.rs` checks every frame in `tests/vectors.txt` byte for byte. That file is
generated from `supervisor/devices/protocol.py`'s own builders, so if the supervisor's protocol
changes, regenerate it and the test shows whether the firmware still matches.
