#pragma once
// System mode face animations — drive Buddy's face for system states.
// Ported from tools/face_sim_v3/render/face.py (_sys_* functions).
// Each mode modifies FaceState fields (eyelids, gaze, mouth, color) so the
// normal face renderer draws the system expression.

#include "face_state.h"
#include "pixel.h"

// Apply system mode expression to face state. Call once per frame before
// rendering eyes/mouth when system.mode != NONE. Modifies eyelids, gaze,
// mouth, brightness, color override, and breathing flag.
void system_face_apply(FaceState& fs, float now_s);

// Small overlay icons drawn on top of the face for system context.
void system_face_render_error_icon(pixel_t* buf);
void system_face_render_battery_icon(pixel_t* buf, float level);
void system_face_render_updating_bar(pixel_t* buf, float progress);
