#pragma once

#include "face_state.h"
#include "lvgl.h"

// Render full-screen system overlays (boot/error/battery/updating/shutdown)
// with Python-v2 parity effects.
void render_system_overlay_v2(lv_color_t* buf, const FaceState& fs, float now_seconds);
