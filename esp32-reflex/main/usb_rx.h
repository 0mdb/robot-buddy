#pragma once
// USB RX task: reads bytes from USB CDC, COBS-decodes frames,
// verifies CRC, parses commands, writes to g_cmd ping-pong buffer.
// Runs on APP core.

// FreeRTOS task function.
void usb_rx_task(void* arg);
