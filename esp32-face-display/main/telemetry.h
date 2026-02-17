#pragma once
// Telemetry task: sends face status + touch events to host at TELEMETRY_HZ.

#include <cstdint>

void telemetry_task(void* arg);
