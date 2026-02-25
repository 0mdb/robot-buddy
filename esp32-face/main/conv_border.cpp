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

// Cached render masks (built once at startup to remove per-frame SDF/trig work)
static constexpr int         BORDER_DEPTH = BORDER_FRAME_W + BORDER_GLOW_W;
static constexpr std::size_t MAX_FRAME_CACHE =
    static_cast<std::size_t>(2 * BORDER_DEPTH * (SCREEN_W + SCREEN_H - 2 * BORDER_DEPTH));
static constexpr std::size_t BTN_ZONE_PIXELS = static_cast<std::size_t>(BTN_CORNER_W * BTN_CORNER_H);
static constexpr std::size_t MAX_MIC_BODY_PIXELS = 512;
static constexpr std::size_t MAX_MIC_BASE_PIXELS = 256;
static constexpr std::size_t MAX_MIC_ARC_PIXELS = 512;
static constexpr std::size_t MAX_X_ICON_PIXELS = 512;

struct __attribute__((packed)) FrameMaskPixel {
    uint32_t idx;
    uint8_t  alpha_u8;
};

struct __attribute__((packed)) ZoneMaskPixel {
    uint8_t x;
    uint8_t y;
    uint8_t alpha_u8;
};

struct __attribute__((packed)) IconMaskPixel {
    int8_t  dx;
    int8_t  dy;
    uint8_t alpha_u8;
};

static bool  s_cache_ready = false;
static float s_alpha_lut[256] = {};

static FrameMaskPixel s_frame_mask[MAX_FRAME_CACHE];
static std::size_t    s_frame_mask_count = 0;

static ZoneMaskPixel s_zone_bg_mask[BTN_ZONE_PIXELS];
static std::size_t   s_zone_bg_mask_count = 0;
static ZoneMaskPixel s_zone_border_mask[BTN_ZONE_PIXELS];
static std::size_t   s_zone_border_mask_count = 0;
static uint32_t      s_zone_row_base[BTN_CORNER_H] = {};

static IconMaskPixel s_mic_body_mask[MAX_MIC_BODY_PIXELS];
static std::size_t   s_mic_body_mask_count = 0;
static IconMaskPixel s_mic_base_mask[MAX_MIC_BASE_PIXELS];
static std::size_t   s_mic_base_mask_count = 0;
static IconMaskPixel s_mic_arc_masks[3][MAX_MIC_ARC_PIXELS];
static std::size_t   s_mic_arc_mask_count[3] = {0, 0, 0};
static IconMaskPixel s_x_icon_mask[MAX_X_ICON_PIXELS];
static std::size_t   s_x_icon_mask_count = 0;

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

static void push_zone_mask(ZoneMaskPixel* dst, std::size_t& count, std::size_t max_count, uint8_t x, uint8_t y,
                           uint8_t alpha_u8)
{
    if (alpha_u8 == 0 || count >= max_count) return;
    dst[count++] = {x, y, alpha_u8};
}

static void push_icon_mask(IconMaskPixel* dst, std::size_t& count, std::size_t max_count, int dx, int dy,
                           uint8_t alpha_u8)
{
    if (alpha_u8 == 0 || count >= max_count) return;
    if (dx < -127 || dx > 127 || dy < -127 || dy > 127) return;
    dst[count++] = {static_cast<int8_t>(dx), static_cast<int8_t>(dy), alpha_u8};
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

static void init_zone_masks()
{
    s_zone_bg_mask_count = 0;
    s_zone_border_mask_count = 0;

    for (int y = 0; y < BTN_CORNER_H; y++) {
        s_zone_row_base[y] = static_cast<uint32_t>((BTN_ZONE_Y_TOP + y) * SCREEN_W);
    }

    const float R = static_cast<float>(BTN_CORNER_INNER_R);
    const float rcx = static_cast<float>(BTN_LEFT_ZONE_X1 - BTN_CORNER_INNER_R);
    const float rcy = static_cast<float>(BTN_CORNER_INNER_R);

    for (int y = 0; y < BTN_CORNER_H; y++) {
        const float py = static_cast<float>(y) + 0.5f;
        for (int x = 0; x < BTN_CORNER_W; x++) {
            const float px = static_cast<float>(x) + 0.5f;
            const bool  in_corner_quad = (px > rcx && py < rcy);

            float bg_cov = 1.0f;
            float border_alpha = 0.0f;
            bool  visible = true;

            if (in_corner_quad) {
                const float ddx = px - rcx;
                const float ddy = py - rcy;
                const float dist = sqrtf(ddx * ddx + ddy * ddy);
                if (dist > R + 0.5f) {
                    visible = false;
                } else if (dist > R - 0.5f) {
                    bg_cov = clampf(R + 0.5f - dist, 0.0f, 1.0f);
                    border_alpha = clampf(1.0f - fabsf(dist - R), 0.0f, 1.0f) * 0.6f;
                }
            }

            if (!visible) continue;

            const uint8_t bg_cov_u8 = alpha_to_u8(bg_cov);
            push_zone_mask(s_zone_bg_mask, s_zone_bg_mask_count, BTN_ZONE_PIXELS, static_cast<uint8_t>(x),
                           static_cast<uint8_t>(y), bg_cov_u8);

            if (!in_corner_quad) {
                const bool on_inner_side = (x == (BTN_CORNER_W - 1)) && (py >= rcy);
                const bool on_top = (y == 0);
                if (on_inner_side) {
                    border_alpha = 0.6f;
                } else if (on_top && px <= rcx) {
                    border_alpha = 0.6f;
                }
            }

            push_zone_mask(s_zone_border_mask, s_zone_border_mask_count, BTN_ZONE_PIXELS, static_cast<uint8_t>(x),
                           static_cast<uint8_t>(y), alpha_to_u8(border_alpha));
        }
    }
}

static void init_icon_masks()
{
    s_mic_body_mask_count = 0;
    s_mic_base_mask_count = 0;
    s_x_icon_mask_count = 0;
    for (int i = 0; i < 3; i++) {
        s_mic_arc_mask_count[i] = 0;
    }

    const float sz = static_cast<float>(BTN_ICON_SIZE);
    const float mic_cx = -sz * 0.22f;
    const float body_hw = sz * 0.19f;
    const float body_hh = sz * 0.39f;
    const float body_r = body_hw;
    const float base_y = sz * 0.5f;
    const float base_hw = sz * 0.22f;
    const float base_hh = sz * 0.06f;
    const float arc_radii[] = {sz * 0.44f, sz * 0.67f, sz * 0.89f};
    const float arc_thick = sz * 0.072f;
    const float arc_min = -70.0f * PI / 180.0f;
    const float arc_max = 70.0f * PI / 180.0f;

    const int ix0 = static_cast<int>(floorf(-sz - 1.0f));
    const int ix1 = static_cast<int>(ceilf(sz + 1.0f));
    const int iy0 = static_cast<int>(floorf(-sz - 1.0f));
    const int iy1 = static_cast<int>(ceilf(sz + 1.0f));

    for (int y = iy0; y < iy1; y++) {
        for (int x = ix0; x < ix1; x++) {
            const float ppx = static_cast<float>(x) + 0.5f;
            const float ppy = static_cast<float>(y) + 0.5f;

            const float d_body = sd_rounded_box(ppx, ppy, mic_cx, 0.0f, body_hw, body_hh, body_r);
            const float a_body = sdf_alpha(d_body) * 0.9f;
            if (a_body > 0.01f) {
                push_icon_mask(s_mic_body_mask, s_mic_body_mask_count, MAX_MIC_BODY_PIXELS, x, y, alpha_to_u8(a_body));
                continue;
            }

            const float d_base = sd_rounded_box(ppx, ppy, mic_cx, base_y, base_hw, base_hh, 0.5f);
            const float a_base = sdf_alpha(d_base) * 0.7f;
            if (a_base > 0.01f) {
                push_icon_mask(s_mic_base_mask, s_mic_base_mask_count, MAX_MIC_BASE_PIXELS, x, y, alpha_to_u8(a_base));
                continue;
            }

            const float dx_a = ppx - mic_cx;
            const float dy_a = ppy;
            const float dist = sqrtf(dx_a * dx_a + dy_a * dy_a);
            const float angle = atan2f(dy_a, dx_a);
            if (angle >= arc_min && angle <= arc_max) {
                for (int ai = 0; ai < 3; ai++) {
                    const float ad = fabsf(dist - arc_radii[ai]);
                    if (ad < arc_thick) {
                        const float a_arc = (1.0f - ad / arc_thick) * 0.9f;
                        push_icon_mask(s_mic_arc_masks[ai], s_mic_arc_mask_count[ai], MAX_MIC_ARC_PIXELS, x, y,
                                       alpha_to_u8(a_arc));
                        break;
                    }
                }
            }
        }
    }

    const float arm = sz * 0.5f;
    const float thick = sz * 0.14f;
    const int   xx0 = static_cast<int>(floorf(-arm - 2.0f));
    const int   xx1 = static_cast<int>(ceilf(arm + 2.0f));
    const int   yy0 = static_cast<int>(floorf(-arm - 2.0f));
    const int   yy1 = static_cast<int>(ceilf(arm + 2.0f));

    for (int y = yy0; y < yy1; y++) {
        for (int x = xx0; x < xx1; x++) {
            const float ppx = static_cast<float>(x) + 0.5f;
            const float ppy = static_cast<float>(y) + 0.5f;
            const float rx = ppx * 0.707f - ppy * 0.707f;
            const float ry = ppx * 0.707f + ppy * 0.707f;
            const float d1 = sd_rounded_box(rx, ry, 0.0f, 0.0f, thick, arm, 1.0f);
            const float d2 = sd_rounded_box(rx, ry, 0.0f, 0.0f, arm, thick, 1.0f);
            const float a = sdf_alpha(fminf(d1, d2)) * 0.9f;
            if (a > 0.01f) {
                push_icon_mask(s_x_icon_mask, s_x_icon_mask_count, MAX_X_ICON_PIXELS, x, y, alpha_to_u8(a));
            }
        }
    }
}

static void ensure_render_cache()
{
    if (s_cache_ready) return;
    init_alpha_lut();
    init_frame_mask();
    init_zone_masks();
    init_icon_masks();
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

static void blend_zone_mask(pixel_t* buf, const ZoneMaskPixel* mask, std::size_t count, bool is_left, uint8_t r,
                            uint8_t g, uint8_t b, uint8_t scale_u8)
{
    if (scale_u8 == 0) return;
    const uint32_t x_base = is_left ? 0U : static_cast<uint32_t>(BTN_RIGHT_ZONE_X0);
    for (std::size_t i = 0; i < count; i++) {
        const auto&    p = mask[i];
        const uint8_t  x = is_left ? p.x : static_cast<uint8_t>((BTN_CORNER_W - 1) - p.x);
        const uint32_t idx = s_zone_row_base[p.y] + x_base + x;
        const uint8_t  a = scale_alpha_u8(p.alpha_u8, scale_u8);
        blend_idx_u8(buf, idx, r, g, b, a);
    }
}

static void blend_icon_mask(pixel_t* buf, const IconMaskPixel* mask, std::size_t count, int cx, int cy, uint8_t r,
                            uint8_t g, uint8_t b, uint8_t scale_u8)
{
    if (scale_u8 == 0) return;
    for (std::size_t i = 0; i < count; i++) {
        const auto& p = mask[i];
        const int   x = cx + static_cast<int>(p.dx);
        const int   y = cy + static_cast<int>(p.dy);
        if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_H) continue;
        const uint8_t a = scale_alpha_u8(p.alpha_u8, scale_u8);
        blend_idx_u8(buf, static_cast<uint32_t>(y * SCREEN_W + x), r, g, b, a);
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
    ensure_render_cache();

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

    blend_zone_mask(buf, s_zone_bg_mask, s_zone_bg_mask_count, is_left, bg_r, bg_g, bg_b, alpha_to_u8(bg_alpha));
    blend_zone_mask(buf, s_zone_border_mask, s_zone_border_mask_count, is_left, brd_r, brd_g, brd_b, 255U);

    // Icon rendering
    const int  icx = is_left ? BTN_LEFT_ICON_CX : BTN_RIGHT_ICON_CX;
    const int  icy = is_left ? BTN_LEFT_ICON_CY : BTN_RIGHT_ICON_CY;
    const bool active = btn.state != BtnState::IDLE;

    if (btn.icon == BtnIcon::MIC) {
        const float sz = static_cast<float>(BTN_ICON_SIZE);
        const float arc_radii[] = {sz * 0.44f, sz * 0.67f, sz * 0.89f};

        blend_icon_mask(buf, s_mic_body_mask, s_mic_body_mask_count, icx, icy, ico_r, ico_g, ico_b, 255U);
        blend_icon_mask(buf, s_mic_base_mask, s_mic_base_mask_count, icx, icy, ico_r, ico_g, ico_b, 255U);

        for (int ai = 0; ai < 3; ai++) {
            uint8_t arc_scale_u8 = 255U;
            if (active) {
                const float phase = fmodf(s_border.timer * 3.0f - arc_radii[ai] / (sz * 0.78f), 1.0f);
                const float pulse = 0.5f + 0.5f * fmaxf(0.0f, sinf(phase * PI));
                arc_scale_u8 = alpha_to_u8(pulse);
            }
            blend_icon_mask(buf, s_mic_arc_masks[ai], s_mic_arc_mask_count[ai], icx, icy, ico_r, ico_g, ico_b,
                            arc_scale_u8);
        }
    } else if (btn.icon == BtnIcon::X_MARK) {
        blend_icon_mask(buf, s_x_icon_mask, s_x_icon_mask_count, icx, icy, ico_r, ico_g, ico_b, 255U);
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
