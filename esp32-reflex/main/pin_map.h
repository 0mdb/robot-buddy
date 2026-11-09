#pragma once
// GPIO assignments — Reflex MCU (Waveshare ESP32-S3-Zero on robot-buddy-reflex v2).
// All pin choices in one place. Must match the board: hardware/kicad/pcb_qc.py §3
// checks every PIN_* here against the schematic netlist.
//
// v2 board (docs/v2-defect-register.md §A0, §M11): the module is soldered flat with its
// PERIMETER pads only (no underside cluster), so GPIO17/18/38/39 are gone. The four
// TB6612 direction lines moved to a TCA9554A I²C expander (U4), and TB6612 STBY is tied
// to the hardware e-stop net, not to a GPIO.

#include "driver/gpio.h"

#include <cstdint>

// ---- Motor driver (TB6612FNG) ----
// PWM outputs (LEDC channels). U1 pads 7/8. R1/R2 100k pull-downs hold them low at boot.
constexpr gpio_num_t PIN_PWMA = GPIO_NUM_4; // left motor PWM
constexpr gpio_num_t PIN_PWMB = GPIO_NUM_5; // right motor PWM

// Direction lines are TCA9554A port bits, not GPIOs (U4: P0-P3 = U4 pins 4-7).
// The expander powers up with every port an input; R12-R15 100k pull-downs hold all
// four lines low until firmware drives them (register A2: power-up state is a safety
// property). Set a direction only through motor.cpp, which sequences PWM around it.
constexpr uint8_t EXP_I2C_ADDR = 0x38;    // TCA9554A, A2..A0 = GND
constexpr uint8_t EXP_BIT_AIN1 = 1u << 0; // P0: left fwd
constexpr uint8_t EXP_BIT_AIN2 = 1u << 1; // P1: left rev
constexpr uint8_t EXP_BIT_BIN1 = 1u << 2; // P2: right fwd
constexpr uint8_t EXP_BIT_BIN2 = 1u << 3; // P3: right rev
constexpr uint8_t EXP_DIR_MASK = 0x0F;    // P4-P7 unconnected (stay inputs)

// ---- Encoders (quadrature, directly to PCNT) ----
// Powered from +3V3 on v2 (register M7): A/B are 3.3 V logic into these pins.
constexpr gpio_num_t PIN_ENC_L_A = GPIO_NUM_9;
constexpr gpio_num_t PIN_ENC_L_B = GPIO_NUM_10;
constexpr gpio_num_t PIN_ENC_R_A = GPIO_NUM_11;
constexpr gpio_num_t PIN_ENC_R_B = GPIO_NUM_12;

// ---- Shared I²C bus: BMI270 IMU (via Qwiic J5) + TCA9554A expander (U4) ----
// U1 pads 26/25. R16/R17 4.7k pull-ups to +3V3 on the board. One bus, owned by
// i2c_bus.cpp; both devices hang off it.
constexpr gpio_num_t PIN_I2C_SDA = GPIO_NUM_7;
constexpr gpio_num_t PIN_I2C_SCL = GPIO_NUM_8;
// Names the IMU code (and pcb_qc.py) use for the same two pins.
constexpr gpio_num_t PIN_IMU_SDA = PIN_I2C_SDA;
constexpr gpio_num_t PIN_IMU_SCL = PIN_I2C_SCL;

// ---- Ultrasonic range sensor (HC-SR04) ----
constexpr gpio_num_t PIN_RANGE_TRIG = GPIO_NUM_3; // output: 10 µs trigger pulse
constexpr gpio_num_t PIN_RANGE_ECHO = GPIO_NUM_2; // input: echo via the R5/R6 divider

// ---- E-stop (register E3: fail-safe, with cable detect) ----
// /ESTOP: +3V3 through the NC contact. HIGH = switch intact, robot may run.
// LOW = stopped (pressed or cable missing; R4 pulls it down). The same net drives TB6612
// STBY directly, so the hardware kill needs no firmware; this pin is for reporting.
constexpr gpio_num_t PIN_ESTOP_N = GPIO_NUM_13; // active-low, external pull-DOWN (R4)
// /ESTOP_LOOP: J7 pin 3, tied to pin 1 (+3V3) at the switch in the harness.
// HIGH = cable present; LOW = cable missing (R18 pull-down).
constexpr gpio_num_t PIN_ESTOP_LOOP = GPIO_NUM_6;

// Battery voltage sense is Pi-side (Waveshare UPS HAT (B) INA219 over I²C), see
// docs/power.md. GPIO1 (U1 pad 4) is free.
