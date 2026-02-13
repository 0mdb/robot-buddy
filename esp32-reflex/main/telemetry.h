#pragma once
// Telemetry task: periodically reads g_telemetry, serializes a STATE packet,
// COBS-encodes it, and sends over USB CDC. Best-effort — drops on backpressure.
// Runs on APP core.

// FreeRTOS task function.
void telemetry_task(void* arg);
