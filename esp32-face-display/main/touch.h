#pragma once
// FT6336 capacitive touch controller + LVGL input device.

#include "lvgl.h"

// Initialize I2C bus (shared with ES8311), FT6336 touch, register with LVGL.
// Also writes touch events to g_touch buffer for telemetry.
void touch_init(lv_display_t* disp);
