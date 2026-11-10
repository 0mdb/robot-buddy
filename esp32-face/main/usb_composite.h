#pragma once
// TinyUSB CDC transport for face commands and telemetry.

#include <cstdint>
#include <cstddef>

struct UsbCdcDiagSnapshot {
    uint32_t tx_calls;
    uint32_t tx_bytes_requested;
    uint32_t tx_bytes_queued;
    uint32_t tx_short_writes;
    uint32_t tx_flush_ok;
    uint32_t tx_flush_not_finished;
    uint32_t tx_flush_timeout;
    uint32_t tx_flush_error;
    uint32_t rx_calls;
    uint32_t rx_bytes;
    uint32_t rx_errors;
    uint32_t line_state_events;
    uint8_t  dtr;
    uint8_t  rts;
};

// Initialize TinyUSB CDC device.
void usb_composite_init(void);

// Write one COBS frame (including its trailing 0x00) to CDC. Frames are written
// whole or not at all, and concurrent callers never interleave. Returns true
// only if the entire frame was queued; on false the caller should treat the
// frame as not sent (and retry later if it matters).
bool usb_cdc_write(const uint8_t* data, size_t len);

// Read bytes from CDC. Returns number of bytes read (0 if none available).
int usb_cdc_read(uint8_t* buf, size_t max_len, uint32_t timeout_ms);

// Snapshot USB CDC I/O diagnostics for troubleshooting telemetry transport.
UsbCdcDiagSnapshot usb_cdc_diag_snapshot(void);
