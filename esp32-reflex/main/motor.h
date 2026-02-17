#pragma once
// TB6612FNG motor driver interface.
// Controls two DC motors via LEDC PWM + direction GPIOs + STBY gate.

#include <cstdint>

enum class MotorSide : uint8_t { LEFT = 0, RIGHT = 1 };

// Initialize LEDC channels + direction GPIOs + STBY pin.
// STBY starts LOW (motors disabled). Call motor_enable() when ready.
void motor_init();

// Enable motor driver (STBY HIGH). Motors will respond to set_output.
void motor_enable();

// Set motor output.  duty: 0..max_pwm, forward: true = forward.
// Has no effect if STBY is LOW (hard-killed).
void motor_set_output(MotorSide side, uint16_t duty, bool forward);

// Brake both motors: IN1=H, IN2=H (TB6612 shorts motor leads).
void motor_brake();

// Coast both motors: IN1=L, IN2=L (TB6612 high-impedance outputs).
// Motors free-spin. Lower power than brake, but no holding torque.
void motor_stop();

// Hard kill: STBY=LOW + PWM=0 + brake direction. Immediate.
void motor_hard_kill();

// Is STBY currently asserted (motors enabled)?
bool motor_is_enabled();
