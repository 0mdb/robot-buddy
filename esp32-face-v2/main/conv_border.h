#pragma once
// Conversation border renderer — visual feedback of conversation phase.
// Ported from tools/face_sim_v3/render/border.py (canonical reference).

#include "pixel.h"
#include <cstdint>

// ---- Border state control ----

void conv_border_set_state(uint8_t state); // FaceConvState (0-7)
void conv_border_set_energy(float energy); // Talking energy for SPEAKING [0,1]
void conv_border_update(float dt);         // Advance animation (call every frame)

// ---- Border rendering ----

void conv_border_render(pixel_t* buf);         // Frame + glow overlay
void conv_border_render_buttons(pixel_t* buf); // Corner button zones

// ---- LED sync ----

void conv_border_get_led(uint8_t& r, uint8_t& g, uint8_t& b);
bool conv_border_active(); // True when border alpha > threshold

// ---- Corner button control ----

enum class BtnIcon : uint8_t {
    NONE = 0,
    MIC = 1,
    X_MARK = 2,
    CHECK = 3,
    REPEAT = 4,
    STAR = 5,
    SPEAKER = 6,
};

enum class BtnState : uint8_t {
    IDLE = 0,
    ACTIVE = 1,
    PRESSED = 2,
};

void conv_border_set_button_left(BtnIcon icon, BtnState state, uint8_t r, uint8_t g, uint8_t b);
void conv_border_set_button_right(BtnIcon icon, BtnState state, uint8_t r, uint8_t g, uint8_t b);
bool conv_border_hit_test_left(int x, int y);
bool conv_border_hit_test_right(int x, int y);
