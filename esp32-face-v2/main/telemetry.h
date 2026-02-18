#pragma once
// Telemetry task: sends face status + touch/button events at TELEMETRY_HZ.

#include <cstdint>

void telemetry_task(void* arg);
