#pragma once
// Safety task: runs on PRO core, evaluates fault conditions, applies stop policy.
// Checks: command timeout (soft stop), ESTOP/tilt (hard stop), stall detection.

// FreeRTOS task function. Pin to PRO core (core 0).
void safety_task(void* arg);
