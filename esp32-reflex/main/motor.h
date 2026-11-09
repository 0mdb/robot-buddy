#pragma once
// TB6612FNG motor driver interface (robot-buddy-reflex v2).
// PWM from LEDC; direction lines through the TCA9554A expander (I²C); STBY is wired
// to the hardware e-stop net, so firmware cannot assert it, only observe it.

#include <cstdint>

enum class MotorSide : uint8_t { LEFT = 0, RIGHT = 1 };

// Initialise LEDC + the expander (direction lines low) + the e-stop sense inputs.
// Motors start disabled in software. Call motor_enable() when ready.
void motor_init();

// Allow motor_set_output() to drive (software gate; the hardware e-stop still rules).
void motor_enable();

// Set motor output. duty: 0..max_pwm, forward: true = forward.
// No effect while disabled. A direction change is sequenced: that side's PWM -> 0,
// expander write + readback, then the new duty. If the readback fails the side stays
// at PWM 0 and Fault::MOTOR_DRV is raised (likely the VM/5 V rail sagging on a flip, or
// a bus fault; docs/v2-defect-register.md A0, docs/TODO.md "Direction-change sequencing").
// Not BROWNOUT: the supervisor speaks that one as "low battery".
void motor_set_output(MotorSide side, uint16_t duty, bool forward);

// Brake both motors: PWM 0 (TB6612 short-brake for any driven direction). Pure LEDC,
// never waits on I²C.
void motor_brake();

// Hard kill: PWM 0, direction lines low (bridge off), software-disabled.
void motor_hard_kill();

// Software-enabled AND the hardware e-stop line is healthy (/ESTOP high).
bool motor_is_enabled();

// /ESTOP high (NC switch intact). False when pressed or the cable is missing.
bool motor_estop_ok();

// /ESTOP_LOOP high: the e-stop cable is plugged in.
bool motor_estop_cable_present();
