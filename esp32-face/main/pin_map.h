#pragma once
#include "driver/gpio.h"

// WS2812B data line (directly to first LED DIN via RMT)
constexpr gpio_num_t PIN_LED_DATA = GPIO_NUM_48;
