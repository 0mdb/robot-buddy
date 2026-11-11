#pragma once
// ILI9341 TFT display + LVGL integration.

#include "lvgl.h"

// Initialize SPI bus, ILI9341 panel, LVGL port, backlight PWM.
// Returns the LVGL display handle.
lv_display_t* display_init(void);

// Set backlight brightness 0-255.
void display_set_backlight(uint8_t brightness);

// ILI9341 drive presets (row-crosstalk tuning). Index into the table in display.cpp.
int  display_panel_preset_count(void);
void display_apply_panel_preset(int index);
