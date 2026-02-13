#pragma once
#include <cstdint>
#include <cmath>

// ---- Grid ----
constexpr int GRID_W = 16;
constexpr int GRID_H = 16;
constexpr int NUM_PIXELS = GRID_W * GRID_H;

// ---- Eye geometry (pixels on shared 16x16 grid) ----
constexpr float EYE_WIDTH      = 6.0f;
constexpr float EYE_HEIGHT     = 6.0f;
constexpr float EYE_CORNER_R   = 2.0f;
constexpr float PUPIL_R        = 1.5f;

constexpr float LEFT_EYE_CX    = 4.0f;
constexpr float LEFT_EYE_CY    = 5.5f;
constexpr float RIGHT_EYE_CX   = 12.0f;
constexpr float RIGHT_EYE_CY   = 5.5f;

constexpr float GAZE_EYE_SHIFT   = 0.15f;
constexpr float GAZE_PUPIL_SHIFT = 0.5f;
constexpr float MAX_GAZE         = 3.0f;

// ---- Mouth geometry ----
constexpr float MOUTH_CX        = 8.0f;
constexpr float MOUTH_CY        = 12.5f;
constexpr float MOUTH_HALF_W    = 4.0f;
constexpr float MOUTH_THICKNESS = 1.0f;

// ---- Timing ----
constexpr int   ANIM_FPS         = 60;
constexpr float BLINK_INTERVAL   = 2.0f;   // base seconds between blinks
constexpr float BLINK_VARIATION  = 3.0f;   // random extra seconds
constexpr float IDLE_INTERVAL    = 1.5f;
constexpr float IDLE_VARIATION   = 2.5f;
constexpr float BREATH_SPEED     = 1.8f;   // rad/s
constexpr float BREATH_AMOUNT    = 0.06f;  // ±6% scale

// ---- Brightness ----
constexpr uint8_t DEFAULT_BRIGHTNESS = 40;  // 0-255, keep low for power
