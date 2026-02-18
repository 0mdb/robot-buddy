#pragma once
#include <cstdint>
#include <cmath>

// ---- Display (landscape) ----
constexpr int SCREEN_W = 320;
constexpr int SCREEN_H = 240;
constexpr int SPI_FREQ_HZ = 40'000'000;  // 40 MHz SPI clock

// ---- Face geometry (LVGL coordinates, 320x240 landscape) ----

constexpr float EYE_WIDTH      = 80.0f;
constexpr float EYE_HEIGHT     = 85.0f;
constexpr float EYE_CORNER_R   = 25.0f;
constexpr float PUPIL_R        = 20.0f;

constexpr float LEFT_EYE_CX    = 90.0f;
constexpr float LEFT_EYE_CY    = 85.0f;
constexpr float RIGHT_EYE_CX   = 230.0f;
constexpr float RIGHT_EYE_CY   = 85.0f;

constexpr float GAZE_EYE_SHIFT   = 3.0f;   // eye body shift per unit gaze
constexpr float GAZE_PUPIL_SHIFT = 8.0f;   // pupil shift per unit gaze
constexpr float MAX_GAZE         = 12.0f;

// ---- Mouth geometry ----
constexpr float MOUTH_CX        = 160.0f;
constexpr float MOUTH_CY        = 185.0f;
constexpr float MOUTH_HALF_W    = 60.0f;
constexpr float MOUTH_THICKNESS = 8.0f;

// ---- Timing ----
constexpr int   ANIM_FPS         = 30;     // TFT refresh, 30 FPS is sufficient
constexpr float BLINK_INTERVAL   = 2.0f;   // base seconds between blinks
constexpr float BLINK_VARIATION  = 3.0f;   // random extra seconds
constexpr float IDLE_INTERVAL    = 1.5f;
constexpr float IDLE_VARIATION   = 2.5f;
constexpr float BREATH_SPEED     = 1.8f;   // rad/s
constexpr float BREATH_AMOUNT    = 0.04f;  // ±4% scale (subtler than LED)

// ---- Brightness ----
constexpr uint8_t DEFAULT_BRIGHTNESS = 200;  // TFT backlight (0-255 via LEDC)

// ---- Telemetry ----
constexpr int TELEMETRY_HZ = 20;
