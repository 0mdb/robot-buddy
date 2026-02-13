#pragma once
// LSM6DSV16X IMU driver on dedicated I²C bus.
// Provides imu_task() which reads gyro+accel and publishes to g_imu.

// Initialize I²C bus 1 and configure the LSM6DSV16X.
// Returns true on success, false if WHO_AM_I check fails.
bool imu_init();

// FreeRTOS task function. Runs on PRO core at high priority.
// Reads gyro+accel at ~200-400 Hz, publishes to g_imu double-buffer.
// On repeated I²C failures, attempts bus recovery + reinit.
void imu_task(void* arg);
