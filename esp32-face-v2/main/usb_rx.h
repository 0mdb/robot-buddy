#pragma once
// USB RX task: reads bytes from TinyUSB CDC, COBS-decodes frames,
// verifies CRC, parses face commands, writes to g_face_cmd buffer.

void usb_rx_task(void* arg);
