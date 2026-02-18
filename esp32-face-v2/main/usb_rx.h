#pragma once
// USB RX task: reads bytes from TinyUSB CDC, COBS-decodes frames,
// verifies CRC, parses face commands, and updates latched command channels
// plus the one-shot gesture queue.

void usb_rx_task(void* arg);
