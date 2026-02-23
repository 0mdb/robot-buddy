#pragma once
// FT6336 capacitive touch controller + LVGL input device.

#include <cstddef>
#include <cstdint>
#include "lvgl.h"

// Initialize I2C bus + FT6336 touch and register with LVGL.
void touch_init(lv_display_t* disp);

struct TouchTransformPreset {
    const char* name;
    uint16_t    x_max;
    uint16_t    y_max;
    bool        swap_xy;
    bool        mirror_x;
    bool        mirror_y;
};

std::size_t                 touch_transform_preset_count();
const TouchTransformPreset* touch_transform_preset_get(std::size_t index);
std::size_t                 touch_transform_preset_index();
bool                        touch_transform_apply(std::size_t index);
