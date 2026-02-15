#pragma once
// BMI270 IMU driver on dedicated I²C bus.
// Provides imu_task() which reads gyro+accel and publishes to g_imu.

// Initialize I²C bus 1 and configure the BMI270 (including config file upload).
// Returns true on success, false if CHIP_ID check or config load fails.
bool imu_init();

// FreeRTOS task function. Runs on PRO core at high priority.
// Reads gyro+accel at ODR rate, publishes to g_imu double-buffer.
// On repeated I²C failures, attempts bus recovery + reinit.
void imu_task(void* arg);
