#pragma once
// GPIO assignments for ESP32-S3 WROOM — Reflex MCU
// All pin choices in one place. Adjust to match your PCB/wiring.

#include "driver/gpio.h"

// ---- Motor driver (TB6612FNG) ----
// PWM outputs (LEDC channels)
constexpr gpio_num_t PIN_PWMA        = GPIO_NUM_4;   // left motor PWM
constexpr gpio_num_t PIN_PWMB        = GPIO_NUM_5;   // right motor PWM
// Direction outputs
constexpr gpio_num_t PIN_AIN1        = GPIO_NUM_6;   // left fwd
constexpr gpio_num_t PIN_AIN2        = GPIO_NUM_7;   // left rev
constexpr gpio_num_t PIN_BIN1        = GPIO_NUM_15;  // right fwd
constexpr gpio_num_t PIN_BIN2        = GPIO_NUM_16;  // right rev
// Standby (active-high enable; external pulldown required)
constexpr gpio_num_t PIN_STBY        = GPIO_NUM_8;

// ---- Encoders (quadrature, directly to PCNT) ----
constexpr gpio_num_t PIN_ENC_L_A     = GPIO_NUM_9;
constexpr gpio_num_t PIN_ENC_L_B     = GPIO_NUM_10;
constexpr gpio_num_t PIN_ENC_R_A     = GPIO_NUM_11;
constexpr gpio_num_t PIN_ENC_R_B     = GPIO_NUM_12;

// ---- IMU (LSM6DSV16X) — dedicated I²C bus 1 ----
constexpr gpio_num_t PIN_IMU_SDA     = GPIO_NUM_17;
constexpr gpio_num_t PIN_IMU_SCL     = GPIO_NUM_18;

// ---- Ultrasonic range sensor (HC-SR04 or similar) ----
constexpr gpio_num_t PIN_RANGE_TRIG  = GPIO_NUM_1;   // output: 10 µs trigger pulse
constexpr gpio_num_t PIN_RANGE_ECHO  = GPIO_NUM_2;   // input: echo pulse (level-shift if 5 V)

// ---- Optional ----
constexpr gpio_num_t PIN_ESTOP_N     = GPIO_NUM_13;  // active-low, external pull-up
constexpr gpio_num_t PIN_VBAT_SENSE  = GPIO_NUM_14;  // ADC input, voltage divider
