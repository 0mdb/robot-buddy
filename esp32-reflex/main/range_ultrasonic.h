#pragma once
// Ultrasonic range sensor driver (HC-SR04 or similar).
// Uses RMT peripheral for hardware-timed echo pulse capture.
// Publishes timestamped range readings to g_range double-buffer.

// Initialize GPIO and RMT capture channel for the range sensor.
// Returns true on success.
bool range_init();

// FreeRTOS task function. Runs on APP core at low priority.
// Triggers measurements at CFG.range_hz, publishes to g_range.
void range_task(void* arg);
