#pragma once
// TinyUSB composite device: CDC (serial commands) + UAC (audio, scaffold).
// CDC is functional; UAC is registered but callbacks are stubs.

#include <cstdint>
#include <cstddef>

// Initialize TinyUSB composite device with CDC + UAC endpoints.
void usb_composite_init(void);

// Write bytes to CDC. Non-blocking best-effort.
void usb_cdc_write(const uint8_t* data, size_t len);

// Read bytes from CDC. Returns number of bytes read (0 if none available).
int usb_cdc_read(uint8_t* buf, size_t max_len, uint32_t timeout_ms);
