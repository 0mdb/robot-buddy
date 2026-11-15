#pragma once
// Face <-> Pi byte link. One of two implementations is compiled in, chosen by
// Kconfig (FACE_TRANSPORT_USB / FACE_TRANSPORT_UART):
//   usb_composite.cpp  TinyUSB CDC-ACM on the side USB-C (bench)
//   uart_link.cpp      UART0 on the P2 connector, GPIO43 TX / GPIO44 RX (in the robot)
// Everything above this API (COBS framing, protocol, telemetry) is transport-agnostic.

#include <cstdint>
#include <cstddef>

// I/O counters, reported in the heartbeat's usb_* fields (the payload layout is
// unchanged across transports). On UART: flush_* are always 0, dtr/rts are 0, and
// rx_errors counts frame/parity errors plus FIFO/ring-buffer overflows.
struct FaceLinkDiag {
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

// Bring up the link. Call once from app_main before the RX/telemetry tasks start.
void face_link_init(void);

// Write one COBS frame (including its trailing 0x00). Frames are written whole
// or not at all, and concurrent callers never interleave. Returns true only if
// the entire frame was queued; on false treat the frame as not sent.
bool face_link_write(const uint8_t* data, size_t len);

// Read whatever bytes are available, waiting up to timeout_ms for the first one.
// Returns the number of bytes read (0 if none).
int face_link_read(uint8_t* buf, size_t max_len, uint32_t timeout_ms);

// Snapshot the link's I/O counters.
FaceLinkDiag face_link_diag_snapshot(void);
