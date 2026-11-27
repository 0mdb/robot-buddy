//! Hardware-free reflex MCU logic, ported from `esp32-reflex/main` for the STM32G431 core
//! (`~/kicad-libs/docs/shared-mcu-core.md`). `no_std`, no allocation: the G431 firmware links it,
//! and `cargo test` runs it on the host against vectors from the Pi supervisor
//! (`supervisor/devices/protocol.py`), so the wire format cannot drift.
#![cfg_attr(not(test), no_std)]

pub mod config;
pub mod link;
pub mod protocol;
