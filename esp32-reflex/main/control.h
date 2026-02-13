#pragma once
// Deterministic control task: runs on PRO core at highest priority.
// Encoder snapshot → rate limiting → FF+PI → deadband comp → yaw damp → motor output.
// Writes telemetry via seqlock. Registered with TWDT.

// FreeRTOS task function. Pin to PRO core (core 0).
void control_task(void* arg);
