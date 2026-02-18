#pragma once
// FT6336 capacitive touch controller + LVGL input device.

#include "lvgl.h"

// Initialize I2C bus + FT6336 touch and register with LVGL.
void touch_init(lv_display_t* disp);
