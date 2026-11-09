#pragma once
// TCA9554A I²C GPIO expander (U4) carrying the TB6612 direction lines (v2 board).
// Call only through motor.cpp: a direction change must be sequenced with PWM.

#include <cstdint>

// Add the device to the shared bus, drive P0-P3 low, then make them outputs.
// Order matters: the output register is written BEFORE the config register, so the
// lines go from "input, pulled low by R12-R15" straight to "driven low" with no glitch.
bool expander_init();

// Write P0-P3 (EXP_DIR_MASK bits of `bits`) and read the INPUT port back: returns true
// only if the pins actually show the written levels.
bool expander_write_dir(uint8_t bits);

// Is the expander initialised and answering?
bool expander_ok();
