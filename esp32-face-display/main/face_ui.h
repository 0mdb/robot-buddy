#pragma once
// LVGL-based face rendering on 240x320 TFT.

#include "face_state.h"
#include "lvgl.h"

// Create LVGL objects for the face. Call once after LVGL init.
void face_ui_create(lv_obj_t* parent);

// Update LVGL objects from FaceState. Call under LVGL lock.
void face_ui_update(const FaceState& fs);

// FreeRTOS task: reads g_face_cmd, updates FaceState, renders via LVGL.
void face_ui_task(void* arg);
