#pragma once
// Single WS2812B RGB LED for status indication.

#include <cstdint>

void led_init(void);
void led_set_rgb(uint8_t r, uint8_t g, uint8_t b);
void led_off(void);
