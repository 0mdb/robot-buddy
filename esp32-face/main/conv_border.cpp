#include "conv_border.h"
#include "config.h"
#include "protocol.h"

#include <cmath>
#include <cstdint>
#include <cstring>

// ══════════════════════════════════════════════════════════════════════
// Constants (must match tools/face_sim_v3/state/constants.py exactly)
// ══════════════════════════════════════════════════════════════════════

// Border geometry
static constexpr int   BORDER_FRAME_W = 4;
static constexpr int   BORDER_GLOW_W = 3;
static constexpr float BORDER_CORNER_R = 3.0f;
static constexpr float BORDER_BLEND_RATE = 8.0f;

// ATTENTION animation
static constexpr float ATTENTION_DURATION = 0.4f;
static constexpr int   ATTENTION_DEPTH = 20;

// LISTENING animation
static constexpr float LISTENING_BREATH_FREQ = 1.5f;
static constexpr float LISTENING_ALPHA_BASE = 0.6f;
static constexpr float LISTENING_ALPHA_MOD = 0.3f;

// PTT animation
static constexpr float PTT_PULSE_FREQ = 0.8f;
static constexpr float PTT_ALPHA_BASE = 0.8f;
static constexpr float PTT_ALPHA_MOD = 0.1f;

// THINKING animation
static constexpr int   THINKING_ORBIT_DOTS = 3;
static constexpr float THINKING_ORBIT_SPACING = 0.12f;
static constexpr float THINKING_ORBIT_SPEED = 0.5f;
static constexpr float THINKING_ORBIT_DOT_R = 4.0f;
static constexpr float THINKING_BORDER_ALPHA = 0.3f;

// SPEAKING animation
static constexpr float SPEAKING_ALPHA_BASE = 0.3f;
static constexpr float SPEAKING_ALPHA_MOD = 0.7f;

// ERROR animation
static constexpr float ERROR_FLASH_DURATION = 0.1f;
static constexpr float ERROR_DECAY_RATE = 5.0f;

// DONE animation
static constexpr float DONE_FADE_SPEED = 2.0f;

// LED scaling
static constexpr float LED_SCALE = 0.16f;

// Corner button zones
static constexpr int BTN_CORNER_W = 60;
static constexpr int BTN_CORNER_H = 46;
static constexpr int BTN_CORNER_INNER_R = 8;
static constexpr int BTN_ICON_SIZE = 18;

// Derived button positions
static constexpr int BTN_ZONE_Y_TOP = SCREEN_H - BTN_CORNER_H;
static constexpr int BTN_LEFT_ZONE_X1 = BTN_CORNER_W;
static constexpr int BTN_RIGHT_ZONE_X0 = SCREEN_W - BTN_CORNER_W;
static constexpr int BTN_LEFT_ICON_CX = BTN_CORNER_W / 2;
static constexpr int BTN_LEFT_ICON_CY = SCREEN_H - BTN_CORNER_H / 2;
static constexpr int BTN_RIGHT_ICON_CX = SCREEN_W - BTN_CORNER_W / 2;
static constexpr int BTN_RIGHT_ICON_CY = BTN_LEFT_ICON_CY;

// Per-state colors (RGB)
struct Color3 {
    uint8_t r, g, b;
};

static constexpr Color3 CONV_COLORS[] = {
    {0, 0, 0},       // IDLE
    {180, 240, 255}, // ATTENTION
    {0, 200, 220},   // LISTENING
    {255, 200, 80},  // PTT
    {120, 100, 255}, // THINKING
    {200, 240, 255}, // SPEAKING
    {255, 160, 60},  // ERROR
    {0, 0, 0},       // DONE
};

// SDF geometry (precomputed)
static constexpr float INNER_HW = SCREEN_W / 2.0f - BORDER_FRAME_W;
static constexpr float INNER_HH = SCREEN_H / 2.0f - BORDER_FRAME_W;
static constexpr float CX = SCREEN_W / 2.0f;
static constexpr float CY = SCREEN_H / 2.0f;

static constexpr float PI = 3.14159265358979323846f;
static constexpr float TWO_PI = 2.0f * PI;

// ══════════════════════════════════════════════════════════════════════
// State
// ══════════════════════════════════════════════════════════════════════

static struct {
    uint8_t state = 0;
    float   timer = 0.0f;
    float   alpha = 0.0f;
    float   color_r = 0.0f, color_g = 0.0f, color_b = 0.0f;
    float   orbit_pos = 0.0f;
    float   energy = 0.0f;
    uint8_t led_r = 0, led_g = 0, led_b = 0;
} s_border;

struct ButtonZone {
    BtnIcon  icon = BtnIcon::MIC;
    BtnState state = BtnState::IDLE;
    uint8_t  color_r = 0, color_g = 0, color_b = 0;
    float    flash_timer = 0.0f;
};

static ButtonZone s_btn_left; // default: MIC / IDLE
static ButtonZone s_btn_right = {BtnIcon::X_MARK, BtnState::IDLE, 0, 0, 0, 0.0f};

// ══════════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════════

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float lerp_f(float a, float b, float t)
{
    return a + (b - a) * t;
}

static float inner_sdf(float px, float py)
{
    const float r = BORDER_CORNER_R;
    const float dx = fabsf(px - CX) - INNER_HW + r;
    const float dy = fabsf(py - CY) - INNER_HH + r;
    const float mx = fmaxf(dx, 0.0f);
    const float my = fmaxf(dy, 0.0f);
    return fminf(fmaxf(dx, dy), 0.0f) + sqrtf(mx * mx + my * my) - r;
}

static void perimeter_xy(float t, float& out_x, float& out_y)
{
    const float inset = BORDER_FRAME_W / 2.0f;
    const float w = SCREEN_W - 2.0f * inset;
    const float h = SCREEN_H - 2.0f * inset;
    const float perim = 2.0f * (w + h);
    float       d = fmodf(t, 1.0f);
    if (d < 0.0f) d += 1.0f;
    d *= perim;
    if (d < w) {
        out_x = inset + d;
        out_y = inset;
        return;
    }
    d -= w;
    if (d < h) {
        out_x = inset + w;
        out_y = inset + d;
        return;
    }
    d -= h;
    if (d < w) {
        out_x = inset + w - d;
        out_y = inset + h;
        return;
    }
    d -= w;
    out_x = inset;
    out_y = inset + h - d;
}

// SDF helpers for icon rendering (from tools/face_sim_v3/render/sdf.py)

static float sd_rounded_box(float px, float py, float cx, float cy, float hw, float hh, float r)
{
    const float dx = fabsf(px - cx) - hw + r;
    const float dy = fabsf(py - cy) - hh + r;
    const float mx = fmaxf(dx, 0.0f);
    const float my = fmaxf(dy, 0.0f);
    return fminf(fmaxf(dx, dy), 0.0f) + sqrtf(mx * mx + my * my) - r;
}

static float sdf_alpha(float dist, float aa_width = 1.0f)
{
    // smoothstep(-aa/2, aa/2, dist) inverted
    const float edge0 = -aa_width / 2.0f;
    const float edge1 = aa_width / 2.0f;
    float       t = clampf((dist - edge0) / (edge1 - edge0), 0.0f, 1.0f);
    return 1.0f - t * t * (3.0f - 2.0f * t);
}

static float sd_line_seg(float px, float py, float ax, float ay, float bx, float by)
{
    const float dx = bx - ax, dy = by - ay;
    const float len_sq = dx * dx + dy * dy;
    if (len_sq < 1e-10f) {
        return sqrtf((px - ax) * (px - ax) + (py - ay) * (py - ay));
    }
    const float t = clampf(((px - ax) * dx + (py - ay) * dy) / len_sq, 0.0f, 1.0f);
    const float cx = ax + t * dx, cy = ay + t * dy;
    return sqrtf((px - cx) * (px - cx) + (py - cy) * (py - cy));
}

// ══════════════════════════════════════════════════════════════════════
// Border state control
// ══════════════════════════════════════════════════════════════════════

void conv_border_set_state(uint8_t state)
{
    if (state == s_border.state) return;
    s_border.state = state;
    s_border.timer = 0.0f;

    // Snap color for instant-response states
    if (state <= 7) {
        const auto& c = CONV_COLORS[state];
        if (state == static_cast<uint8_t>(FaceConvState::ATTENTION) ||
            state == static_cast<uint8_t>(FaceConvState::ERROR)) {
            s_border.color_r = c.r;
            s_border.color_g = c.g;
            s_border.color_b = c.b;
        }
    }

    // Drive corner button visuals from conversation state (parity with sim __main__.py)
    const auto cs = static_cast<FaceConvState>(state);
    if (cs == FaceConvState::PTT || cs == FaceConvState::LISTENING) {
        const auto& c = CONV_COLORS[state];
        conv_border_set_button_left(BtnIcon::MIC, BtnState::ACTIVE, c.r, c.g, c.b);
        conv_border_set_button_right(BtnIcon::X_MARK, BtnState::ACTIVE, c.r, c.g, c.b);
    } else if (cs == FaceConvState::THINKING || cs == FaceConvState::SPEAKING) {
        const auto& c = CONV_COLORS[state];
        conv_border_set_button_left(BtnIcon::MIC, BtnState::IDLE, 0, 0, 0);
        conv_border_set_button_right(BtnIcon::X_MARK, BtnState::ACTIVE, c.r, c.g, c.b);
    } else {
        conv_border_set_button_left(BtnIcon::MIC, BtnState::IDLE, 0, 0, 0);
        conv_border_set_button_right(BtnIcon::X_MARK, BtnState::IDLE, 0, 0, 0);
    }
}

void conv_border_set_energy(float energy)
{
    s_border.energy = clampf(energy, 0.0f, 1.0f);
}

void conv_border_update(float dt)
{
    const auto  s = static_cast<FaceConvState>(s_border.state);
    const float blend = fminf(1.0f, dt * BORDER_BLEND_RATE);

    switch (s) {
    case FaceConvState::IDLE:
        s_border.alpha = clampf(s_border.alpha - dt * BORDER_BLEND_RATE, 0.0f, 1.0f);
        break;

    case FaceConvState::ATTENTION:
        if (s_border.timer < ATTENTION_DURATION) {
            s_border.alpha = 1.0f;
            const auto& c = CONV_COLORS[static_cast<uint8_t>(FaceConvState::ATTENTION)];
            s_border.color_r = c.r;
            s_border.color_g = c.g;
            s_border.color_b = c.b;
        }
        break;

    case FaceConvState::LISTENING: {
        const float target =
            LISTENING_ALPHA_BASE + LISTENING_ALPHA_MOD * sinf(s_border.timer * TWO_PI * LISTENING_BREATH_FREQ);
        s_border.alpha += (target - s_border.alpha) * blend;
        const auto& c = CONV_COLORS[static_cast<uint8_t>(FaceConvState::LISTENING)];
        s_border.color_r = lerp_f(s_border.color_r, c.r, blend);
        s_border.color_g = lerp_f(s_border.color_g, c.g, blend);
        s_border.color_b = lerp_f(s_border.color_b, c.b, blend);
        break;
    }

    case FaceConvState::PTT: {
        const float target = PTT_ALPHA_BASE + PTT_ALPHA_MOD * sinf(s_border.timer * TWO_PI * PTT_PULSE_FREQ);
        s_border.alpha += (target - s_border.alpha) * blend;
        const auto& c = CONV_COLORS[static_cast<uint8_t>(FaceConvState::PTT)];
        s_border.color_r = lerp_f(s_border.color_r, c.r, blend);
        s_border.color_g = lerp_f(s_border.color_g, c.g, blend);
        s_border.color_b = lerp_f(s_border.color_b, c.b, blend);
        break;
    }

    case FaceConvState::THINKING: {
        s_border.alpha += (THINKING_BORDER_ALPHA - s_border.alpha) * blend;
        const auto& c = CONV_COLORS[static_cast<uint8_t>(FaceConvState::THINKING)];
        s_border.color_r = lerp_f(s_border.color_r, c.r, blend);
        s_border.color_g = lerp_f(s_border.color_g, c.g, blend);
        s_border.color_b = lerp_f(s_border.color_b, c.b, blend);
        s_border.orbit_pos = fmodf(s_border.orbit_pos + THINKING_ORBIT_SPEED * dt, 1.0f);
        break;
    }

    case FaceConvState::SPEAKING: {
        const float target = SPEAKING_ALPHA_BASE + SPEAKING_ALPHA_MOD * s_border.energy;
        s_border.alpha += (target - s_border.alpha) * blend;
        const auto& c = CONV_COLORS[static_cast<uint8_t>(FaceConvState::SPEAKING)];
        s_border.color_r = lerp_f(s_border.color_r, c.r, blend);
        s_border.color_g = lerp_f(s_border.color_g, c.g, blend);
        s_border.color_b = lerp_f(s_border.color_b, c.b, blend);
        break;
    }

    case FaceConvState::ERROR:
        if (s_border.timer < ERROR_FLASH_DURATION) {
            s_border.alpha = 1.0f;
            const auto& c = CONV_COLORS[static_cast<uint8_t>(FaceConvState::ERROR)];
            s_border.color_r = c.r;
            s_border.color_g = c.g;
            s_border.color_b = c.b;
        } else {
            s_border.alpha = expf(-(s_border.timer - ERROR_FLASH_DURATION) * ERROR_DECAY_RATE);
        }
        break;

    case FaceConvState::DONE:
        s_border.alpha = clampf(s_border.alpha - dt * DONE_FADE_SPEED, 0.0f, 1.0f);
        break;
    }

    // LED: mirror border color at reduced brightness
    if (s_border.alpha > 0.01f) {
        const float ls = s_border.alpha * LED_SCALE;
        s_border.led_r = static_cast<uint8_t>(clampf(s_border.color_r * ls, 0.0f, 255.0f));
        s_border.led_g = static_cast<uint8_t>(clampf(s_border.color_g * ls, 0.0f, 255.0f));
        s_border.led_b = static_cast<uint8_t>(clampf(s_border.color_b * ls, 0.0f, 255.0f));
    } else {
        s_border.led_r = 0;
        s_border.led_g = 0;
        s_border.led_b = 0;
    }

    // Button flash decay
    if (s_btn_left.flash_timer > 0.0f) {
        s_btn_left.flash_timer -= dt;
        if (s_btn_left.flash_timer <= 0.0f && s_btn_left.state == BtnState::PRESSED) {
            s_btn_left.state = BtnState::ACTIVE;
        }
    }
    if (s_btn_right.flash_timer > 0.0f) {
        s_btn_right.flash_timer -= dt;
        if (s_btn_right.flash_timer <= 0.0f && s_btn_right.state == BtnState::PRESSED) {
            s_btn_right.state = BtnState::ACTIVE;
        }
    }

    s_border.timer += dt;
}

void conv_border_get_led(uint8_t& r, uint8_t& g, uint8_t& b)
{
    r = s_border.led_r;
    g = s_border.led_g;
    b = s_border.led_b;
}

bool conv_border_active()
{
    return s_border.alpha > 0.01f;
}

// ══════════════════════════════════════════════════════════════════════
// Border rendering
// ══════════════════════════════════════════════════════════════════════

static void render_frame_px(pixel_t* buf, int idx, int x, int y)
{
    const float d = inner_sdf(static_cast<float>(x) + 0.5f, static_cast<float>(y) + 0.5f);
    float       a;
    if (d > 0.0f) {
        a = s_border.alpha;
    } else if (d > -BORDER_GLOW_W) {
        const float t = (d + BORDER_GLOW_W) / static_cast<float>(BORDER_GLOW_W);
        a = s_border.alpha * t * t;
    } else {
        return;
    }
    if (a > 0.01f) {
        buf[idx] = px_blend(buf[idx], static_cast<uint8_t>(s_border.color_r), static_cast<uint8_t>(s_border.color_g),
                            static_cast<uint8_t>(s_border.color_b), a);
    }
}

static void render_attention(pixel_t* buf)
{
    const float progress = s_border.timer / ATTENTION_DURATION;
    const float sweep = static_cast<float>(ATTENTION_DEPTH) * progress;
    const float fade_global = 1.0f - progress * 0.5f;
    const int   limit = static_cast<int>(sweep) + 1;
    const auto& col = CONV_COLORS[static_cast<uint8_t>(FaceConvState::ATTENTION)];

    for (int y = 0; y < SCREEN_H; y++) {
        const int dv = (y < SCREEN_H - 1 - y) ? y : (SCREEN_H - 1 - y);
        const int row = y * SCREEN_W;
        if (dv > limit) {
            // Only left/right edges
            for (int x = 0; x < limit && x < SCREEN_W; x++) {
                const float dist = static_cast<float>(x);
                if (dist < sweep) {
                    const float f = (1.0f - dist / fmaxf(1.0f, sweep)) * fade_global;
                    const float a = f * f;
                    if (a > 0.01f) {
                        buf[row + x] = px_blend(buf[row + x], col.r, col.g, col.b, a);
                    }
                }
            }
            for (int x = SCREEN_W - limit; x < SCREEN_W; x++) {
                if (x < 0) continue;
                const float dist = static_cast<float>(SCREEN_W - 1 - x);
                if (dist < sweep) {
                    const float f = (1.0f - dist / fmaxf(1.0f, sweep)) * fade_global;
                    const float a = f * f;
                    if (a > 0.01f) {
                        buf[row + x] = px_blend(buf[row + x], col.r, col.g, col.b, a);
                    }
                }
            }
        } else {
            // Full row
            for (int x = 0; x < SCREEN_W; x++) {
                const int   dh = (x < SCREEN_W - 1 - x) ? x : (SCREEN_W - 1 - x);
                const float dist = static_cast<float>((dh < dv) ? dh : dv);
                if (dist < sweep) {
                    const float f = (1.0f - dist / fmaxf(1.0f, sweep)) * fade_global;
                    const float a = f * f;
                    if (a > 0.01f) {
                        buf[row + x] = px_blend(buf[row + x], col.r, col.g, col.b, a);
                    }
                }
            }
        }
    }
}

static void render_dots(pixel_t* buf)
{
    static constexpr float brightnesses[] = {1.0f, 0.7f, 0.4f};
    const auto&            dot_col = CONV_COLORS[static_cast<uint8_t>(FaceConvState::THINKING)];
    const float            r = THINKING_ORBIT_DOT_R;

    for (int i = 0; i < THINKING_ORBIT_DOTS; i++) {
        float pos = fmodf(s_border.orbit_pos - static_cast<float>(i) * THINKING_ORBIT_SPACING, 1.0f);
        if (pos < 0.0f) pos += 1.0f;

        float dx, dy;
        perimeter_xy(pos, dx, dy);

        const float   bri = brightnesses[i];
        const uint8_t cr = static_cast<uint8_t>(clampf(static_cast<float>(dot_col.r) * bri, 0.0f, 255.0f));
        const uint8_t cg = static_cast<uint8_t>(clampf(static_cast<float>(dot_col.g) * bri, 0.0f, 255.0f));
        const uint8_t cb = static_cast<uint8_t>(clampf(static_cast<float>(dot_col.b) * bri, 0.0f, 255.0f));

        const int x0 = static_cast<int>(fmaxf(0.0f, dx - r - 1.0f));
        const int x1 = static_cast<int>(fminf(static_cast<float>(SCREEN_W), dx + r + 2.0f));
        const int y0 = static_cast<int>(fmaxf(0.0f, dy - r - 1.0f));
        const int y1 = static_cast<int>(fminf(static_cast<float>(SCREEN_H), dy + r + 2.0f));

        for (int y = y0; y < y1; y++) {
            const int row = y * SCREEN_W;
            for (int x = x0; x < x1; x++) {
                const float ddx = static_cast<float>(x) + 0.5f - dx;
                const float ddy = static_cast<float>(y) + 0.5f - dy;
                const float d = sqrtf(ddx * ddx + ddy * ddy);
                if (d < r) {
                    const float ratio = d / r;
                    float       a = fminf(1.0f, (1.0f - ratio * ratio) * 2.5f);
                    if (a > 0.01f) {
                        buf[row + x] = px_blend(buf[row + x], cr, cg, cb, a);
                    }
                }
            }
        }
    }
}

void conv_border_render(pixel_t* buf)
{
    const auto s = static_cast<FaceConvState>(s_border.state);

    if (s_border.alpha < 0.01f && s != FaceConvState::ATTENTION) {
        return;
    }

    // ATTENTION: special sweep effect
    if (s == FaceConvState::ATTENTION && s_border.timer < ATTENTION_DURATION) {
        render_attention(buf);
        return;
    }

    // Standard SDF frame + glow
    constexpr int depth = BORDER_FRAME_W + BORDER_GLOW_W;

    for (int y = 0; y < SCREEN_H; y++) {
        const int dv = (y < SCREEN_H - 1 - y) ? y : (SCREEN_H - 1 - y);
        const int row = y * SCREEN_W;
        if (dv >= depth) {
            // Middle rows — only left/right border bands
            for (int x = 0; x < depth; x++) {
                render_frame_px(buf, row + x, x, y);
            }
            for (int x = SCREEN_W - depth; x < SCREEN_W; x++) {
                render_frame_px(buf, row + x, x, y);
            }
        } else {
            // Top/bottom rows — full width
            for (int x = 0; x < SCREEN_W; x++) {
                const int dh = (x < SCREEN_W - 1 - x) ? x : (SCREEN_W - 1 - x);
                if (dh >= depth && dv >= depth) continue;
                render_frame_px(buf, row + x, x, y);
            }
        }
    }

    // THINKING: orbit dots
    if (s == FaceConvState::THINKING && s_border.alpha > 0.01f) {
        render_dots(buf);
    }
}

// ══════════════════════════════════════════════════════════════════════
// Corner button rendering
// ══════════════════════════════════════════════════════════════════════

static constexpr uint8_t BTN_IDLE_BG_R = 40, BTN_IDLE_BG_G = 44, BTN_IDLE_BG_B = 52;
static constexpr uint8_t BTN_IDLE_BORDER_R = 80, BTN_IDLE_BORDER_G = 90, BTN_IDLE_BORDER_B = 100;
static constexpr float   BTN_IDLE_ALPHA = 0.35f;
static constexpr uint8_t BTN_ICON_COLOR_R = 200, BTN_ICON_COLOR_G = 210, BTN_ICON_COLOR_B = 220;

void conv_border_set_button_left(BtnIcon icon, BtnState state, uint8_t r, uint8_t g, uint8_t b)
{
    s_btn_left.icon = icon;
    s_btn_left.state = state;
    s_btn_left.color_r = r;
    s_btn_left.color_g = g;
    s_btn_left.color_b = b;
    if (state == BtnState::PRESSED) {
        s_btn_left.flash_timer = 0.15f;
    }
}

void conv_border_set_button_right(BtnIcon icon, BtnState state, uint8_t r, uint8_t g, uint8_t b)
{
    s_btn_right.icon = icon;
    s_btn_right.state = state;
    s_btn_right.color_r = r;
    s_btn_right.color_g = g;
    s_btn_right.color_b = b;
    if (state == BtnState::PRESSED) {
        s_btn_right.flash_timer = 0.15f;
    }
}

bool conv_border_hit_test_left(int x, int y)
{
    return x >= 0 && x < BTN_LEFT_ZONE_X1 && y >= BTN_ZONE_Y_TOP && y < SCREEN_H;
}

bool conv_border_hit_test_right(int x, int y)
{
    return x >= BTN_RIGHT_ZONE_X0 && x < SCREEN_W && y >= BTN_ZONE_Y_TOP && y < SCREEN_H;
}

static void render_corner_zone(pixel_t* buf, bool is_left, const ButtonZone& btn)
{
    uint8_t bg_r, bg_g, bg_b;
    float   bg_alpha;
    uint8_t brd_r, brd_g, brd_b;
    uint8_t ico_r, ico_g, ico_b;

    if (btn.state == BtnState::PRESSED || btn.flash_timer > 0.0f) {
        bg_r = static_cast<uint8_t>(clampf(btn.color_r * 1.3f, 0, 255));
        bg_g = static_cast<uint8_t>(clampf(btn.color_g * 1.3f, 0, 255));
        bg_b = static_cast<uint8_t>(clampf(btn.color_b * 1.3f, 0, 255));
        bg_alpha = 0.75f;
        brd_r = 255;
        brd_g = 255;
        brd_b = 255;
        ico_r = 255;
        ico_g = 255;
        ico_b = 255;
    } else if (btn.state == BtnState::ACTIVE) {
        bg_r = btn.color_r;
        bg_g = btn.color_g;
        bg_b = btn.color_b;
        bg_alpha = 0.55f;
        brd_r = static_cast<uint8_t>(clampf(btn.color_r * 1.2f, 0, 255));
        brd_g = static_cast<uint8_t>(clampf(btn.color_g * 1.2f, 0, 255));
        brd_b = static_cast<uint8_t>(clampf(btn.color_b * 1.2f, 0, 255));
        ico_r = 255;
        ico_g = 255;
        ico_b = 255;
    } else {
        bg_r = BTN_IDLE_BG_R;
        bg_g = BTN_IDLE_BG_G;
        bg_b = BTN_IDLE_BG_B;
        bg_alpha = BTN_IDLE_ALPHA;
        brd_r = BTN_IDLE_BORDER_R;
        brd_g = BTN_IDLE_BORDER_G;
        brd_b = BTN_IDLE_BORDER_B;
        ico_r = BTN_ICON_COLOR_R;
        ico_g = BTN_ICON_COLOR_G;
        ico_b = BTN_ICON_COLOR_B;
    }

    const int   x0 = is_left ? 0 : BTN_RIGHT_ZONE_X0;
    const int   x1 = is_left ? BTN_LEFT_ZONE_X1 : SCREEN_W;
    const float R = static_cast<float>(BTN_CORNER_INNER_R);
    const float rcx = is_left ? static_cast<float>(BTN_LEFT_ZONE_X1 - BTN_CORNER_INNER_R)
                              : static_cast<float>(BTN_RIGHT_ZONE_X0 + BTN_CORNER_INNER_R);
    const float rcy = static_cast<float>(BTN_ZONE_Y_TOP + BTN_CORNER_INNER_R);

    for (int y = BTN_ZONE_Y_TOP; y < SCREEN_H; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x < x1; x++) {
            const float px = static_cast<float>(x) + 0.5f;
            const float py = static_cast<float>(y) + 0.5f;

            bool in_corner_quad = is_left ? (px > rcx && py < rcy) : (px < rcx && py < rcy);
            if (in_corner_quad) {
                const float ddx = px - rcx;
                const float ddy = py - rcy;
                const float dist = sqrtf(ddx * ddx + ddy * ddy);
                if (dist > R + 0.5f) continue;
                if (dist > R - 0.5f) {
                    float a = bg_alpha * clampf(R + 0.5f - dist, 0.0f, 1.0f);
                    if (a > 0.01f) {
                        buf[row + x] = px_blend(buf[row + x], bg_r, bg_g, bg_b, a);
                    }
                    float ba = clampf(1.0f - fabsf(dist - R), 0.0f, 1.0f) * 0.6f;
                    if (ba > 0.01f) {
                        buf[row + x] = px_blend(buf[row + x], brd_r, brd_g, brd_b, ba);
                    }
                    continue;
                }
            }

            buf[row + x] = px_blend(buf[row + x], bg_r, bg_g, bg_b, bg_alpha);

            // Thin border on inner edges
            bool on_top = (y == BTN_ZONE_Y_TOP) && !in_corner_quad;
            bool on_inner_side = (is_left && x == x1 - 1) || (!is_left && x == x0);
            if (on_inner_side && py >= rcy) {
                buf[row + x] = px_blend(buf[row + x], brd_r, brd_g, brd_b, 0.6f);
            } else if (on_top) {
                bool on_top_valid = is_left ? (px <= rcx) : (px >= rcx);
                if (on_top_valid) {
                    buf[row + x] = px_blend(buf[row + x], brd_r, brd_g, brd_b, 0.6f);
                }
            }
        }
    }

    // Icon rendering
    const float icx = is_left ? static_cast<float>(BTN_LEFT_ICON_CX) : static_cast<float>(BTN_RIGHT_ICON_CX);
    const float icy = is_left ? static_cast<float>(BTN_LEFT_ICON_CY) : static_cast<float>(BTN_RIGHT_ICON_CY);
    const float sz = static_cast<float>(BTN_ICON_SIZE);
    const bool  active = btn.state != BtnState::IDLE;

    if (btn.icon == BtnIcon::MIC) {
        // Microphone: capsule body + base bar + sound arcs
        const float mic_cx = icx - sz * 0.22f;
        const float body_hw = sz * 0.19f;
        const float body_hh = sz * 0.39f;
        const float body_r = body_hw;
        const float base_y = icy + sz * 0.5f;
        const float base_hw = sz * 0.22f;
        const float base_hh = sz * 0.06f;
        const float arc_radii[] = {sz * 0.44f, sz * 0.67f, sz * 0.89f};
        const float arc_thick = sz * 0.072f;
        const float arc_min = -70.0f * PI / 180.0f;
        const float arc_max = 70.0f * PI / 180.0f;

        const int ix0 = static_cast<int>(fmaxf(0.0f, icx - sz - 1.0f));
        const int ix1 = static_cast<int>(fminf(static_cast<float>(SCREEN_W), icx + sz + 1.0f));
        const int iy0 = static_cast<int>(fmaxf(0.0f, icy - sz - 1.0f));
        const int iy1 = static_cast<int>(fminf(static_cast<float>(SCREEN_H), icy + sz + 1.0f));

        for (int y = iy0; y < iy1; y++) {
            const int row = y * SCREEN_W;
            for (int x = ix0; x < ix1; x++) {
                const float ppx = static_cast<float>(x) + 0.5f;
                const float ppy = static_cast<float>(y) + 0.5f;

                // Mic body (capsule)
                float d_body = sd_rounded_box(ppx, ppy, mic_cx, icy, body_hw, body_hh, body_r);
                float a_body = sdf_alpha(d_body);
                if (a_body > 0.01f) {
                    buf[row + x] = px_blend(buf[row + x], ico_r, ico_g, ico_b, a_body * 0.9f);
                    continue;
                }

                // Base bar
                float d_base = sd_rounded_box(ppx, ppy, mic_cx, base_y, base_hw, base_hh, 0.5f);
                float a_base = sdf_alpha(d_base);
                if (a_base > 0.01f) {
                    buf[row + x] = px_blend(buf[row + x], ico_r, ico_g, ico_b, a_base * 0.7f);
                    continue;
                }

                // Sound wave arcs (right side)
                const float dx_a = ppx - mic_cx;
                const float dy_a = ppy - icy;
                const float dist = sqrtf(dx_a * dx_a + dy_a * dy_a);
                const float angle = atan2f(dy_a, dx_a);
                if (angle >= arc_min && angle <= arc_max) {
                    for (int ai = 0; ai < 3; ai++) {
                        const float ad = fabsf(dist - arc_radii[ai]);
                        if (ad < arc_thick) {
                            float a = 1.0f - ad / arc_thick;
                            if (active) {
                                const float phase = fmodf(s_border.timer * 3.0f - arc_radii[ai] / (sz * 0.78f), 1.0f);
                                a *= 0.5f + 0.5f * fmaxf(0.0f, sinf(phase * PI));
                            }
                            buf[row + x] = px_blend(buf[row + x], ico_r, ico_g, ico_b, a * 0.9f);
                            break;
                        }
                    }
                }
            }
        }
    } else if (btn.icon == BtnIcon::X_MARK) {
        // X/cross mark
        const float arm = sz * 0.5f;
        const float thick = sz * 0.14f;

        const int ix0 = static_cast<int>(fmaxf(0.0f, icx - arm - 2.0f));
        const int ix1 = static_cast<int>(fminf(static_cast<float>(SCREEN_W), icx + arm + 2.0f));
        const int iy0 = static_cast<int>(fmaxf(0.0f, icy - arm - 2.0f));
        const int iy1 = static_cast<int>(fminf(static_cast<float>(SCREEN_H), icy + arm + 2.0f));

        for (int y = iy0; y < iy1; y++) {
            const int row = y * SCREEN_W;
            for (int x = ix0; x < ix1; x++) {
                const float ppx = static_cast<float>(x) + 0.5f;
                const float ppy = static_cast<float>(y) + 0.5f;
                // Rotate 45 degrees
                const float rx = (ppx - icx) * 0.707f - (ppy - icy) * 0.707f;
                const float ry = (ppx - icx) * 0.707f + (ppy - icy) * 0.707f;
                const float d1 = sd_rounded_box(rx, ry, 0, 0, thick, arm, 1.0f);
                const float d2 = sd_rounded_box(rx, ry, 0, 0, arm, thick, 1.0f);
                const float d = fminf(d1, d2);
                const float a = sdf_alpha(d);
                if (a > 0.01f) {
                    buf[row + x] = px_blend(buf[row + x], ico_r, ico_g, ico_b, a * 0.9f);
                }
            }
        }
    }
}

void conv_border_render_buttons(pixel_t* buf)
{
    if (s_btn_left.icon != BtnIcon::NONE) {
        render_corner_zone(buf, true, s_btn_left);
    }
    if (s_btn_right.icon != BtnIcon::NONE) {
        render_corner_zone(buf, false, s_btn_right);
    }
}
