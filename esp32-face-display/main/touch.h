#pragma once
// FT6336 capacitive touch controller + LVGL input device.

#include "lvgl.h"
#include "driver/i2c_master.h"

// Initialize I2C bus (shared with ES8311), FT6336 touch, register with LVGL.
// Also writes touch events to g_touch buffer for telemetry.
void touch_init(lv_display_t* disp);

// Shared I2C master bus used by touch and audio codec.
i2c_master_bus_handle_t touch_get_i2c_bus(void);
