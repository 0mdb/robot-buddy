#pragma once
// Face animation state machine for TFT renderer.
// Behavior is aligned with tools/face_state_v2.py.

#include "config.h"
#include <cstdint>

// ---- Enums ----

enum class Mood : uint8_t {
    NEUTRAL = 0,   // calm, attentive default
    HAPPY = 1,     // pleased, upturned eyes
    EXCITED = 2,   // wide open, high energy
    CURIOUS = 3,   // one brow raised, attentive
    SAD = 4,       // droopy, glistening
    SCARED = 5,    // wide eyes, shrunk pupils
    ANGRY = 6,     // narrowed, intense (mild for kids)
    SURPRISED = 7, // wide open, raised brows
    SLEEPY = 8,    // half-closed, slow blinks
    LOVE = 9,      // heart-shaped / warm glow
    SILLY = 10,    // cross-eyed or asymmetric
    THINKING = 11, // looking up/aside
    CONFUSED = 12, // puzzled, asymmetric mouth
};

enum class GestureId : uint8_t {
    BLINK = 0,
    WINK_L = 1,
    WINK_R = 2,
    CONFUSED = 3,
    LAUGH = 4,
    SURPRISE = 5,
    HEART = 6,
    X_EYES = 7,
    SLEEPY = 8,
    RAGE = 9,
    NOD = 10,
    HEADSHAKE = 11,
    WIGGLE = 12,
};

enum class SystemMode : uint8_t {
    NONE = 0,
    BOOTING = 1,
    ERROR_DISPLAY = 2,
    LOW_BATTERY = 3,
    UPDATING = 4,
    SHUTTING_DOWN = 5,
};

// ---- Per-eye state ----

struct EyeState {
    float openness = 0.0f; // 0=closed, 1=open (starts closed for boot)
    float openness_target = 1.0f;
    bool  is_open = true;

    float gaze_x = 0.0f;
    float gaze_x_target = 0.0f;
    float gaze_y = 0.0f;
    float gaze_y_target = 0.0f;
    float vx = 0.0f;
    float vy = 0.0f;

    float width_scale = 1.0f;
    float width_scale_target = 1.0f;
    float height_scale = 1.0f;
    float height_scale_target = 1.0f;
};

// ---- Eyelid overlay state (v2 model) ----

struct EyelidState {
    float top_l = 0.0f;
    float top_r = 0.0f;
    float bottom_l = 0.0f;
    float bottom_r = 0.0f;
    float slope = 0.0f;
    float slope_target = 0.0f;
};

// ---- Animation timers ----

struct AnimTimers {
    // Auto-blink
    bool  autoblink = true;
    float next_blink = 0.0f;

    // Idle gaze wander
    bool  idle = true;
    float next_idle = 0.0f;
    float next_saccade = 0.0f;

    // One-shot gestures (active + timer)
    bool  confused = false;
    float confused_timer = 0.0f;
    bool  confused_toggle = true;
    float confused_duration = 0.5f;

    bool  laugh = false;
    float laugh_timer = 0.0f;
    bool  laugh_toggle = true;
    float laugh_duration = 0.5f;

    bool  surprise = false;
    float surprise_timer = 0.0f;
    float surprise_duration = 0.8f;

    bool  heart = false;
    float heart_timer = 0.0f;
    float heart_duration = 2.0f;

    bool  x_eyes = false;
    float x_eyes_timer = 0.0f;
    float x_eyes_duration = 1.5f;

    bool  sleepy = false;
    float sleepy_timer = 0.0f;
    float sleepy_duration = 3.0f;

    bool  rage = false;
    float rage_timer = 0.0f;
    float rage_duration = 3.0f;

    bool  nod = false;
    float nod_timer = 0.0f;
    float nod_duration = 0.35f;

    bool  headshake = false;
    float headshake_timer = 0.0f;
    float headshake_duration = 0.35f;

    // Flicker (driven by confused/laugh)
    bool  h_flicker = false;
    bool  h_flicker_alt = false;
    float h_flicker_amp = 1.5f;
    bool  v_flicker = false;
    bool  v_flicker_alt = false;
    float v_flicker_amp = 1.5f;
};

// ---- Effects state (display-agnostic) ----

constexpr int MAX_SPARKLE_PIXELS = 48;
constexpr int MAX_FIRE_PIXELS = 64;

struct SparklePixel {
    int16_t x = 0;
    int16_t y = 0;
    uint8_t life = 0;
    bool    active = false;
};

struct FirePixel {
    float x = 0.0f;
    float y = 0.0f;
    float life = 0.0f;
    float heat = 0.0f;
    bool  active = false;
};

struct EffectsState {
    // Breathing
    bool  breathing = true;
    float breath_phase = 0.0f;
    float breath_speed = BREATH_SPEED;
    float breath_amount = BREATH_AMOUNT;

    // Boot sequence
    bool  boot_active = true;
    float boot_timer = 0.0f;
    int   boot_phase = 0;

    bool         sparkle = true;
    float        sparkle_chance = 0.05f;
    SparklePixel sparkle_pixels[MAX_SPARKLE_PIXELS]{};

    bool  afterglow = true;
    bool  edge_glow = true;
    float edge_glow_falloff = 0.4f;

    FirePixel fire_pixels[MAX_FIRE_PIXELS]{};
};

// ---- System display state ----

struct SystemState {
    SystemMode mode = SystemMode::NONE;
    float      timer = 0.0f;
    int        phase = 0;
    float      param = 0.0f; // e.g. battery level 0..1
};

// ---- Top-level face state ----

struct FaceState {
    EyeState     eye_l;
    EyeState     eye_r;
    EyelidState  eyelids;
    AnimTimers   anim;
    EffectsState fx;
    SystemState  system;

    Mood  mood = Mood::NEUTRAL;
    float brightness = 1.0f;
    float expression_intensity = 1.0f;
    bool  solid_eye = true;
    bool  show_mouth = true;

    // Talking animation (driven by supervisor during TTS playback)
    bool  talking = false;
    float talking_energy = 0.0f; // 0.0–1.0, current audio energy level
    float talking_phase = 0.0f;

    // Mouth state
    float mouth_curve = 0.2f;
    float mouth_curve_target = 0.2f;
    float mouth_open = 0.0f;
    float mouth_open_target = 0.0f;
    float mouth_wave = 0.0f;
    float mouth_wave_target = 0.0f;
    float mouth_offset_x = 0.0f;
    float mouth_offset_x_target = 0.0f;
    float mouth_width = 1.0f;
    float mouth_width_target = 1.0f;

    uint8_t active_gesture = 0xFF; // GestureId or 0xFF when idle.
    float   active_gesture_until = 0.0f;

    // Color override (set by system face animations, reset each frame)
    bool    color_override_active = false;
    uint8_t color_override_r = 0;
    uint8_t color_override_g = 0;
    uint8_t color_override_b = 0;
};

// ---- API ----

void  face_state_update(FaceState& fs);
float face_get_breath_scale(const FaceState& fs);
void  face_get_emotion_color(const FaceState& fs, uint8_t& r, uint8_t& g, uint8_t& b);

void face_blink(FaceState& fs);
void face_wink_left(FaceState& fs);
void face_wink_right(FaceState& fs);
void face_set_gaze(FaceState& fs, float x, float y);
void face_set_mood(FaceState& fs, Mood mood);
void face_set_expression_intensity(FaceState& fs, float intensity);
void face_trigger_gesture(FaceState& fs, GestureId gesture, uint16_t duration_ms = 0);
void face_set_system_mode(FaceState& fs, SystemMode mode, float param = 0.0f);
