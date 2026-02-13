#pragma once
// Quadrature encoder interface using ESP32-S3 PCNT peripheral.
// Two channels: left and right wheel.

#include <cstdint>

enum class EncoderSide : uint8_t { LEFT = 0, RIGHT = 1 };

// Initialize PCNT units for both encoders in quadrature mode.
void encoder_init();

// Read the raw accumulated count for one encoder.
// Thread-safe (PCNT register read is atomic on ESP32-S3).
int32_t encoder_get_count(EncoderSide side);

// Snapshot both encoder counts simultaneously (as close as possible).
// Stores into out_left, out_right.
void encoder_snapshot(int32_t* out_left, int32_t* out_right);

// Convert a delta count over dt_us to linear speed in mm/s.
// Uses config: wheel_diameter_mm, counts_per_rev.
float encoder_delta_to_mm_s(int32_t delta_counts, uint32_t dt_us);
