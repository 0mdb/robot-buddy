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

// Cached render masks (built once at startup to remove per-frame SDF/trig work)
static constexpr int         BORDER_DEPTH = BORDER_FRAME_W + BORDER_GLOW_W;
static constexpr std::size_t MAX_FRAME_CACHE =
    static_cast<std::size_t>(2 * BORDER_DEPTH * (SCREEN_W + SCREEN_H - 2 * BORDER_DEPTH));

struct __attribute__((packed)) FrameMaskPixel {
    uint32_t idx;
    uint8_t  alpha_u8;
};

static bool  s_cache_ready = false;
static float s_alpha_lut[256] = {};

static FrameMaskPixel s_frame_mask[MAX_FRAME_CACHE];
static std::size_t    s_frame_mask_count = 0;

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

static uint8_t alpha_to_u8(float alpha)
{
    const float a = clampf(alpha, 0.0f, 1.0f);
    return static_cast<uint8_t>(a * 255.0f + 0.5f);
}

static uint8_t scale_alpha_u8(uint8_t base, uint8_t scale)
{
    return static_cast<uint8_t>((static_cast<uint16_t>(base) * static_cast<uint16_t>(scale) + 127U) / 255U);
}

static void push_frame_mask(uint32_t idx, uint8_t alpha_u8)
{
    if (alpha_u8 == 0 || s_frame_mask_count >= MAX_FRAME_CACHE) return;
    s_frame_mask[s_frame_mask_count++] = {idx, alpha_u8};
}

static void init_alpha_lut()
{
    for (int i = 0; i < 256; i++) {
        s_alpha_lut[i] = static_cast<float>(i) / 255.0f;
    }
}

static void init_frame_mask()
{
    s_frame_mask_count = 0;
    for (int y = 0; y < SCREEN_H; y++) {
        for (int x = 0; x < SCREEN_W; x++) {
            if (y >= BORDER_DEPTH && y < (SCREEN_H - BORDER_DEPTH) && x >= BORDER_DEPTH &&
                x < (SCREEN_W - BORDER_DEPTH)) {
                continue;
            }
            const float d = inner_sdf(static_cast<float>(x) + 0.5f, static_cast<float>(y) + 0.5f);
            float       a = 0.0f;
            if (d > 0.0f) {
                a = 1.0f;
            } else if (d > -BORDER_GLOW_W) {
                const float t = (d + BORDER_GLOW_W) / static_cast<float>(BORDER_GLOW_W);
                a = t * t;
            }
            push_frame_mask(static_cast<uint32_t>(y * SCREEN_W + x), alpha_to_u8(a));
        }
    }
}

static void ensure_render_cache()
{
    if (s_cache_ready) return;
    init_alpha_lut();
    init_frame_mask();
    s_cache_ready = true;
}

static void blend_idx_u8(pixel_t* buf, uint32_t idx, uint8_t r, uint8_t g, uint8_t b, uint8_t alpha_u8)
{
    if (alpha_u8 == 0) return;
    buf[idx] = px_blend(buf[idx], r, g, b, s_alpha_lut[alpha_u8]);
}

static void blend_frame_mask(pixel_t* buf, uint8_t r, uint8_t g, uint8_t b, uint8_t scale_u8)
{
    if (scale_u8 == 0) return;
    for (std::size_t i = 0; i < s_frame_mask_count; i++) {
        const auto&   p = s_frame_mask[i];
        const uint8_t a = scale_alpha_u8(p.alpha_u8, scale_u8);
        blend_idx_u8(buf, p.idx, r, g, b, a);
    }
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
    ensure_render_cache();
    const auto s = static_cast<FaceConvState>(s_border.state);

    if (s_border.alpha < 0.01f && s != FaceConvState::ATTENTION) {
        return;
    }

    // ATTENTION: special sweep effect
    if (s == FaceConvState::ATTENTION && s_border.timer < ATTENTION_DURATION) {
        render_attention(buf);
        return;
    }

    // Cached rounded-frame mask + per-frame alpha scale.
    const uint8_t frame_alpha_u8 = alpha_to_u8(s_border.alpha);
    const uint8_t cr = static_cast<uint8_t>(s_border.color_r);
    const uint8_t cg = static_cast<uint8_t>(s_border.color_g);
    const uint8_t cb = static_cast<uint8_t>(s_border.color_b);
    blend_frame_mask(buf, cr, cg, cb, frame_alpha_u8);

    // THINKING: orbit dots
    if (s == FaceConvState::THINKING && s_border.alpha > 0.01f) {
        render_dots(buf);
    }
}
