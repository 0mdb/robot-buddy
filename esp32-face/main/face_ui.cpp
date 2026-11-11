#include "face_ui.h"
#include "config.h"
#include "shared_state.h"
#include "conv_border.h"
#include "display.h"
#include "led.h"
#include "protocol.h"
#include "touch.h"
#include "touch_gesture.h"
#include "system_face.h"
#include "pixel.h"

#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static const char*        TAG = "face_ui";
static constexpr uint32_t TALKING_CMD_TIMEOUT_MS = 450;
static constexpr uint8_t  BG_R = 0;
static constexpr uint8_t  BG_G = 0;
static constexpr uint8_t  BG_B = 0;
// Canvas uses RGB565 to match the ILI9341 display format (no conversion needed).
static constexpr lv_color_format_t CANVAS_COLOR_FORMAT = LV_COLOR_FORMAT_RGB565;
static constexpr std::size_t       CANVAS_BYTES = SCREEN_W * SCREEN_H * sizeof(pixel_t);
static constexpr int               AFTERGLOW_W = SCREEN_W / FACE_AFTERGLOW_DOWNSAMPLE;
static constexpr int               AFTERGLOW_H = SCREEN_H / FACE_AFTERGLOW_DOWNSAMPLE;
static constexpr std::size_t       AFTERGLOW_BYTES = AFTERGLOW_W * AFTERGLOW_H * sizeof(pixel_t);

static float now_s();
static float clampf(float v, float lo, float hi);
static float smoothstepf(float edge0, float edge1, float x);

// ---- LVGL objects ----
static lv_obj_t* canvas_obj = nullptr;
static pixel_t*  canvas_buf = nullptr;
static pixel_t*  afterglow_buf = nullptr;
static lv_obj_t* calib_header_bg = nullptr;
static lv_obj_t* calib_label_touch = nullptr;
static lv_obj_t* calib_label_tf = nullptr;
static lv_obj_t* calib_label_flags = nullptr;

static int s_last_touch_x = SCREEN_W / 2;
static int s_last_touch_y = SCREEN_H / 2;

// Whole-screen gesture state (LVGL-lock protected; see root_touch_event_cb).
static TouchGesture      s_gesture({TOUCH_TAP_MAX_MS, TOUCH_LONG_PRESS_MS, TOUCH_RING_SHOW_MS, TOUCH_MOVE_TOL_PX,
                                    TOUCH_PET_PATH_PX});
static std::atomic<bool> s_boop_pending{false};
// Finger is stroking the screen (local content look, spec §9.5).
static std::atomic<bool> s_petting{false};
// Latest finger position for gaze-follow (written in the LVGL task, read by face_ui_task).
static std::atomic<int16_t> s_finger_x{SCREEN_W / 2};
static std::atomic<int16_t> s_finger_y{SCREEN_H / 2};
static uint8_t              s_last_touch_evt = 0xFF;
static bool                 s_last_touch_active = false;

struct RectI {
    int  x0 = 0;
    int  y0 = 0;
    int  x1 = 0;
    int  y1 = 0;
    bool valid = false;
};

struct DirtyRegion {
    static constexpr uint8_t MAX_RECTS = 16; // overflow falls back to a full redraw
    RectI                    rects[MAX_RECTS] = {};
    uint8_t                  count = 0;
    bool                     full = false;
};

struct PrevBoundsState {
    RectI eye_l = {};
    RectI eye_r = {};
    RectI mouth = {};
    RectI border = {};
    RectI ring = {};
    // Sparkles are single random pixels; track each one's position so the frame it
    // dies on clears it (the canvas is only cleared inside dirty rects).
    int16_t sparkle_x[MAX_SPARKLE_PIXELS] = {};
    int16_t sparkle_y[MAX_SPARKLE_PIXELS] = {};
    uint8_t sparkle_count = 0;
    bool    full = false;
    bool    valid = false;
};

struct RenderPerfSnapshot {
    uint32_t render_us = 0;
    uint32_t eyes_us = 0;
    uint32_t mouth_us = 0;
    uint32_t border_us = 0;
    uint32_t effects_us = 0;
    uint32_t overlay_us = 0;
    uint32_t dirty_px = 0;
};

static RenderPerfSnapshot s_last_render_perf = {};
static bool               s_collect_render_perf = false;
static PrevBoundsState    s_prev_bounds = {};

static void        publish_touch_sample(uint8_t event_type, int x, int y);
static void        publish_button_event(FaceButtonId button_id, FaceButtonEventType event_type, uint8_t state);
static void        root_touch_event_cb(lv_event_t* e);
static void        render_calibration(pixel_t* buf);
static void        update_calibration_labels(uint32_t now_ms, uint32_t next_switch_ms);
static void        afterglow_copy_from_canvas(const pixel_t* canvas);
static DirtyRegion compute_dirty_region(const FaceState& fs, const RectI& ring);
static uint32_t    dirty_region_area(const DirtyRegion& region);

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float smoothstepf(float edge0, float edge1, float x)
{
    if (fabsf(edge1 - edge0) < 1e-6f) {
        return x < edge0 ? 0.0f : 1.0f;
    }
    const float t = clampf((x - edge0) / (edge1 - edge0), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

// ---- Drawing helpers (RGB565 pixel_t) ----

static pixel_t rgb_to_color(uint8_t r, uint8_t g, uint8_t b)
{
    return px_rgb(r, g, b);
}

static pixel_t scale_color(pixel_t c, uint8_t num, uint8_t den)
{
    return px_scale(c, num, den);
}

static void draw_filled_rect(pixel_t* buf, int x, int y, int w, int h, pixel_t color)
{
    // Clip once, then fill whole rows (no per-pixel bounds checks).
    int x0 = x < 0 ? 0 : x;
    int y0 = y < 0 ? 0 : y;
    int x1 = (x + w) > SCREEN_W ? SCREEN_W : (x + w);
    int y1 = (y + h) > SCREEN_H ? SCREEN_H : (y + h);
    if (x1 <= x0 || y1 <= y0) return;
    const int span = x1 - x0;
    for (int py = y0; py < y1; py++) {
        std::fill_n(buf + py * SCREEN_W + x0, span, color);
    }
}

static void draw_span(pixel_t* buf, int y, int x0, int x1_incl, pixel_t color)
{
    if (y < 0 || y >= SCREEN_H) return;
    if (x0 < 0) x0 = 0;
    if (x1_incl >= SCREEN_W) x1_incl = SCREEN_W - 1;
    if (x1_incl < x0) return;
    std::fill_n(buf + y * SCREEN_W + x0, x1_incl - x0 + 1, color);
}

static void draw_hline(pixel_t* buf, int x0, int x1, int y, pixel_t color)
{
    const int x_lo = (x0 < x1) ? x0 : x1;
    const int x_hi = (x0 < x1) ? x1 : x0;
    draw_filled_rect(buf, x_lo, y, x_hi - x_lo + 1, 1, color);
}

static void draw_vline(pixel_t* buf, int x, int y0, int y1, pixel_t color)
{
    const int y_lo = (y0 < y1) ? y0 : y1;
    const int y_hi = (y0 < y1) ? y1 : y0;
    draw_filled_rect(buf, x, y_lo, 1, y_hi - y_lo + 1, color);
}

static void draw_filled_rounded_rect(pixel_t* buf, int x, int y, int w, int h, int radius, pixel_t color)
{
    // Row spans: corner rows are inset by the circle; everything else is a full row.
    if (w <= 0 || h <= 0) return;
    if (radius < 0) radius = 0;
    const int r2 = radius * radius;
    for (int dy = 0; dy < h; dy++) {
        int ddy = -1;
        if (dy < radius) {
            ddy = radius - dy;
        } else if (dy >= h - radius) {
            ddy = dy - (h - radius - 1);
        }
        int lo = 0;
        int hi = w - 1;
        if (ddy >= 0) {
            const int rem = r2 - ddy * ddy;
            if (rem < 0) continue;
            const int reach = static_cast<int>(sqrtf(static_cast<float>(rem)));
            const int left = radius - reach;
            const int right = (w - radius - 1) + reach;
            if (left > lo) lo = left;
            if (right < hi) hi = right;
        }
        draw_span(buf, y + dy, x + lo, x + hi, color);
    }
}

static void draw_filled_circle(pixel_t* buf, int cx, int cy, int radius, pixel_t color)
{
    const int r2 = radius * radius;
    for (int dy = -radius; dy <= radius; dy++) {
        const int reach = static_cast<int>(sqrtf(static_cast<float>(r2 - dy * dy)));
        draw_span(buf, cy + dy, cx - reach, cx + reach, color);
    }
}

// ---- Face rendering ----

static float sd_heart(float px, float py, float cx, float cy, float size)
{
    const float x = fabsf(px - cx) / size;
    const float y = (cy - py) / size + 0.5f;

    float d = 0.0f;
    if (y + x > 1.0f) {
        const float dx = x - 0.25f;
        const float dy = y - 0.75f;
        d = sqrtf(dx * dx + dy * dy) - 0.35355339f;
    } else {
        const float dy1 = y - 1.0f;
        const float d1 = x * x + dy1 * dy1;
        const float t = fmaxf(x + y, 0.0f) * 0.5f;
        const float dx2 = x - t;
        const float dy2 = y - t;
        const float d2 = dx2 * dx2 + dy2 * dy2;
        d = sqrtf(fminf(d1, d2));
        if (x < y) {
            d = -d;
        }
    }

    return d * size;
}

static void draw_heart_shape(pixel_t* buf, float cx, float cy, float size, uint8_t r, uint8_t g, uint8_t b)
{
    if (size < 1.0f) {
        return;
    }
    const int x0 = static_cast<int>(fmaxf(0.0f, cx - size - 2.0f));
    const int x1 = static_cast<int>(fminf(static_cast<float>(SCREEN_W), cx + size + 2.0f));
    const int y0 = static_cast<int>(fmaxf(0.0f, cy - size - 2.0f));
    const int y1 = static_cast<int>(fminf(static_cast<float>(SCREEN_H), cy + size + 2.0f));

    for (int y = y0; y < y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x < x1; x++) {
            const float d = sd_heart(static_cast<float>(x) + 0.5f, static_cast<float>(y) + 0.5f, cx, cy, size);
            const float a = 1.0f - smoothstepf(-0.5f, 0.5f, d);
            if (a > 0.01f) {
                buf[row + x] = px_blend(buf[row + x], r, g, b, a);
            }
        }
    }
}

static void draw_x_shape(pixel_t* buf, int cx, int cy, int size, int thick, pixel_t color)
{
    for (int y = cy - size; y <= cy + size; y++) {
        if (y < 0 || y >= SCREEN_H) continue;
        for (int x = cx - size; x <= cx + size; x++) {
            if (x < 0 || x >= SCREEN_W) continue;
            const int dx = x - cx;
            const int dy = y - cy;
            if (abs(dx + dy) <= thick || abs(dx - dy) <= thick) {
                buf[y * SCREEN_W + x] = color;
            }
        }
    }
}

static void render_eye(pixel_t* buf, const EyeState& eye, const FaceState& fs, bool is_left, float center_x,
                       float center_y)
{
    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);
    pixel_t eye_color = rgb_to_color(r, g, b);
    pixel_t black = rgb_to_color(0, 0, 0);

    const float breath = face_get_breath_scale(fs);
    const float ew = EYE_WIDTH * eye.width_scale * eye.squash_w * breath;
    const float eh = EYE_HEIGHT * eye.height_scale * eye.squash_h * fmaxf(0.25f, eye.openness) * breath;
    if (eh < 2.0f) {
        return;
    }

    const float ex = center_x + eye.gaze_x * GAZE_EYE_SHIFT - ew / 2.0f;
    const float ey = center_y + eye.gaze_y * GAZE_EYE_SHIFT - eh / 2.0f;
    const int   corner = static_cast<int>(EYE_CORNER_R * fminf(eye.width_scale, eye.height_scale));

    if (fs.solid_eye && fs.anim.heart) {
        draw_heart_shape(buf, center_x, center_y, fminf(ew, eh) * 0.5f * HEART_SOLID_SCALE, r, g, b);
    } else if (fs.solid_eye && fs.anim.x_eyes) {
        draw_x_shape(buf, static_cast<int>(center_x), static_cast<int>(center_y),
                     static_cast<int>(fminf(ew, eh) * 0.33f), 3, eye_color);
    } else {
        if (fs.fx.edge_glow) {
            const pixel_t glow = scale_color(eye_color, 2, 5);
            draw_filled_rounded_rect(buf, static_cast<int>(ex) - 2, static_cast<int>(ey) - 2, static_cast<int>(ew) + 4,
                                     static_cast<int>(eh) + 4, corner + 2, glow);
        }
        draw_filled_rounded_rect(buf, static_cast<int>(ex), static_cast<int>(ey), static_cast<int>(ew),
                                 static_cast<int>(eh), corner, eye_color);
    }

    if (!fs.solid_eye) {
        const float max_offset_x = fmaxf(0.0f, ew * 0.5f - PUPIL_R - 5.0f);
        const float max_offset_y = fmaxf(0.0f, eh * 0.5f - PUPIL_R - 5.0f);
        const float px = center_x + clampf(eye.gaze_x * GAZE_PUPIL_SHIFT, -max_offset_x, max_offset_x);
        const float py = center_y + clampf(eye.gaze_y * GAZE_PUPIL_SHIFT, -max_offset_y, max_offset_y);
        const int   pr = static_cast<int>(PUPIL_R * fmaxf(0.4f, eye.openness));
        if (fs.anim.heart) {
            draw_heart_shape(buf, px, py, PUPIL_R * HEART_PUPIL_SCALE, 10, 15, 30);
        } else if (fs.anim.x_eyes) {
            draw_x_shape(buf, static_cast<int>(px), static_cast<int>(py), pr, 2, rgb_to_color(10, 15, 30));
        } else if (pr > 1) {
            draw_filled_circle(buf, static_cast<int>(px), static_cast<int>(py), pr, rgb_to_color(10, 15, 30));
        }
    }

    // V2 eyelid model: top/bottom coverage + diagonal slope.
    const float lid_top = is_left ? fs.eyelids.top_l : fs.eyelids.top_r;
    const float lid_bot = is_left ? fs.eyelids.bottom_l : fs.eyelids.bottom_r;
    const float slope = fs.eyelids.slope;
    const int   x0 = static_cast<int>(ex);
    const int   x1 = static_cast<int>(ex + ew);
    const int   y0 = static_cast<int>(ey);
    const int   y1 = static_cast<int>(ey + eh);

    // Per-column lid limits, then fill row by row (contiguous PSRAM writes).
    // A lid is present when it reaches into the eye box (top_limit > y0 / bot_limit < y1).
    // It then also covers the edge-glow ring around the eye (pad), otherwise the glow's
    // top edge and sides stay visible as a floating "eyebrow" line when the lid drops.
    const int pad = fs.fx.edge_glow ? 3 : 0; // glow is drawn 2 px outside the eye (+1 rounding)
    const int ly0 = y0 - pad;
    const int ly1 = y1 + pad;
    const int cx0 = (x0 - pad) < 0 ? 0 : (x0 - pad);
    const int cx1 = (x1 + pad) > SCREEN_W ? SCREEN_W : (x1 + pad);
    if (cx1 <= cx0) return;
    static int lid_top_y[SCREEN_W]; // static: off the task stack
    static int lid_bot_y[SCREEN_W];
    int        top_max = ly0 - 1;
    int        bot_min = ly1 + 1;
    for (int x = cx0; x < cx1; x++) {
        float nx = (static_cast<float>(x) - (ex + ew * 0.5f)) / fmaxf(1.0f, ew * 0.5f);
        if (!is_left) {
            nx = -nx;
        }
        const float slope_off = slope * 20.0f * nx;
        const int   top_limit = static_cast<int>((ey - 0.5f) + eh * 2.0f * lid_top + slope_off);
        const int   bot_limit = static_cast<int>((ey + eh) - eh * 2.0f * lid_bot);
        lid_top_y[x] = (top_limit > y0) ? top_limit : (ly0 - 1); // ly0-1: no top lid
        lid_bot_y[x] = (bot_limit < y1) ? bot_limit : (ly1 + 1); // ly1+1: no bottom lid
        if (lid_top_y[x] > top_max) top_max = lid_top_y[x];
        if (lid_bot_y[x] < bot_min) bot_min = lid_bot_y[x];
    }
    // A fully closed lid can run past the eye box (top lid below y1, bottom lid above
    // y0), so the row range covers that too.
    int ry0 = (bot_min < ly0) ? bot_min : ly0;
    int ry1 = (top_max > ly1) ? top_max : ly1;
    if (ry0 < 0) ry0 = 0;
    if (ry1 >= SCREEN_H) ry1 = SCREEN_H - 1;
    for (int y = ry0; y <= ry1; y++) {
        if (y > top_max && y < bot_min) {
            continue; // row untouched by either lid
        }
        pixel_t* row = buf + y * SCREEN_W;
        for (int x = cx0; x < cx1; x++) {
            if ((y >= ly0 && y <= lid_top_y[x]) || (y >= lid_bot_y[x] && y <= ly1)) {
                row[x] = black;
            }
        }
    }
}

// Mouth centre: base position + mood offset + a fraction of the (averaged) eye gaze.
static void mouth_center(const FaceState& fs, float& cx, float& cy)
{
    const float gx = 0.5f * (fs.eye_l.gaze_x + fs.eye_r.gaze_x);
    const float gy = 0.5f * (fs.eye_l.gaze_y + fs.eye_r.gaze_y);
    cx = MOUTH_CX + fs.mouth_offset_x * 10.0f + gx * GAZE_MOUTH_SHIFT_X;
    cy = MOUTH_CY + gy * GAZE_MOUTH_SHIFT_Y;
}

static void render_mouth(pixel_t* buf, const FaceState& fs)
{
    if (!fs.show_mouth) return;

    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);

    float cx, cy;
    mouth_center(fs, cx, cy);
    const float w = MOUTH_HALF_W * fs.mouth_width;
    const float thick = MOUTH_THICKNESS;
    const float curve = fs.mouth_curve * 40.0f;
    const float openness = fs.mouth_open * 40.0f;
    if (w < 1.0f) {
        return;
    }

    const int     x0 = static_cast<int>(cx - w - thick);
    const int     x1 = static_cast<int>(cx + w + thick);
    const int     y0 = static_cast<int>(cy - fabsf(curve) - openness - thick);
    const int     y1 = static_cast<int>(cy + fabsf(curve) + openness + thick);
    const float   half_thick = thick * 0.5f;
    const pixel_t mouth_color = rgb_to_color(r, g, b);

    // Same look as the eyes: hard-edged core plus (with edge glow) a 1 px rim at 40 %
    // brightness. No smooth AA: its in-between shades shift hue with viewing angle on
    // this TN panel and streaked. Distance is measured perpendicular to the curve so
    // the stroke keeps its width, and the ends get round caps instead of square cuts.
    const bool    glow = fs.fx.edge_glow;
    const pixel_t glow_color = scale_color(mouth_color, 2, 5);
    const float   rim = glow ? 1.0f : 0.0f;
    const float   reach = half_thick + rim;
    const bool    filled = openness > 1.0f;

    // Per-column curve values are the same for every row: compute them once.
    static constexpr int MAX_MOUTH_COLS = SCREEN_W;
    static float         col_upper[MAX_MOUTH_COLS]; // static: keep ~4 KB off the 8 KB task stack
    static float         col_lower[MAX_MOUTH_COLS];
    static float         col_cos_u[MAX_MOUTH_COLS]; // vertical -> perpendicular distance factors
    static float         col_cos_l[MAX_MOUTH_COLS];
    static bool          col_valid[MAX_MOUTH_COLS];
    const int            cx0 = x0 < 0 ? 0 : x0;
    const int            cx1 = x1 > SCREEN_W ? SCREEN_W : x1;
    float                ymin = cy;
    float                ymax = cy;
    for (int x = cx0; x < cx1; x++) {
        const int   i = x - cx0;
        const float nx = (static_cast<float>(x) + 0.5f - cx) / w;
        col_valid[i] = fabsf(nx) <= 1.0f;
        if (!col_valid[i]) continue;
        const float shape = 1.0f - nx * nx;
        const float dshape = -2.0f * nx / w; // d(shape)/dx
        col_upper[i] = cy + (curve - openness) * shape;
        col_lower[i] = cy + (curve + openness) * shape;
        const float su = (curve - openness) * dshape;
        const float sl = (curve + openness) * dshape;
        col_cos_u[i] = 1.0f / sqrtf(1.0f + su * su);
        col_cos_l[i] = 1.0f / sqrtf(1.0f + sl * sl);
        ymin = fminf(ymin, col_upper[i]);
        ymax = fmaxf(ymax, col_lower[i]);
    }
    int ry0 = static_cast<int>(floorf(ymin - reach));
    int ry1 = static_cast<int>(ceilf(ymax + reach)) + 1;
    if (ry0 < (y0 < 0 ? 0 : y0)) ry0 = (y0 < 0 ? 0 : y0);
    if (ry1 > (y1 > SCREEN_H ? SCREEN_H : y1)) ry1 = (y1 > SCREEN_H ? SCREEN_H : y1);
    const float x_left = cx - w; // both lines meet at (x_end, cy) where shape = 0
    const float x_right = cx + w;

    for (int y = ry0; y < ry1; y++) {
        const int   row = y * SCREEN_W;
        const float py = static_cast<float>(y) + 0.5f;
        for (int x = cx0; x < cx1; x++) {
            const int   i = x - cx0;
            const float px = static_cast<float>(x) + 0.5f;
            float       dist = 0.0f;
            if (col_valid[i]) {
                const float upper_y = col_upper[i];
                const float lower_y = col_lower[i];
                if (py < upper_y - reach * 1.5f || py > lower_y + reach * 1.5f) continue;
                if (!(filled && upper_y < py && py < lower_y)) {
                    dist = fminf(fabsf(py - upper_y) * col_cos_u[i], fabsf(py - lower_y) * col_cos_l[i]);
                }
            } else {
                // Round cap beyond either end.
                const float ex_end = (px < cx) ? x_left : x_right;
                const float dx = px - ex_end;
                const float dy = py - cy;
                dist = sqrtf(dx * dx + dy * dy);
            }
            if (dist <= half_thick) {
                buf[row + x] = mouth_color;
            } else if (dist <= reach) {
                buf[row + x] = glow_color;
            }
        }
    }
}

static void render_fire_effect(pixel_t* buf, const FaceState& fs)
{
    for (const auto& px : fs.fx.fire_pixels) {
        if (!px.active || px.life <= 0.0f) continue;
        int x = static_cast<int>(px.x);
        int y = static_cast<int>(px.y);
        if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_H) continue;
        pixel_t c;
        if (px.heat > 0.85f)
            c = rgb_to_color(255, 220, 120);
        else if (px.heat > 0.65f)
            c = rgb_to_color(255, 140, 20);
        else if (px.heat > 0.40f)
            c = rgb_to_color(220, 50, 0);
        else
            c = rgb_to_color(130, 20, 0);
        draw_filled_rect(buf, x - 1, y - 1, 3, 3, c);
    }
}

static void render_sparkles(pixel_t* buf, const FaceState& fs)
{
    for (const auto& sp : fs.fx.sparkle_pixels) {
        if (!sp.active || sp.life == 0) continue;
        if (sp.x < 0 || sp.x >= SCREEN_W || sp.y < 0 || sp.y >= SCREEN_H) continue;
        buf[sp.y * SCREEN_W + sp.x] = rgb_to_color(255, 255, 255);
    }
}

static void apply_afterglow(pixel_t* buf, const FaceState& fs)
{
    if (!fs.fx.afterglow || !afterglow_buf) {
        return;
    }
    const pixel_t bg = rgb_to_color(BG_R, BG_G, BG_B);
    for (int y = 0; y < SCREEN_H; y++) {
        const int ay = (y / FACE_AFTERGLOW_DOWNSAMPLE) * AFTERGLOW_W;
        const int row = y * SCREEN_W;
        for (int x = 0; x < SCREEN_W; x++) {
            const int     aidx = ay + (x / FACE_AFTERGLOW_DOWNSAMPLE);
            const pixel_t prev = afterglow_buf[aidx];
            if (buf[row + x] == bg && prev != bg) {
                buf[row + x] = scale_color(prev, 2, 5);
            }
        }
    }
    afterglow_copy_from_canvas(buf);
}

static void afterglow_copy_from_canvas(const pixel_t* canvas)
{
    if (!afterglow_buf || !canvas) {
        return;
    }
    for (int y = 0; y < AFTERGLOW_H; y++) {
        const int src_y = y * FACE_AFTERGLOW_DOWNSAMPLE;
        const int dst_row = y * AFTERGLOW_W;
        const int src_row = src_y * SCREEN_W;
        for (int x = 0; x < AFTERGLOW_W; x++) {
            afterglow_buf[dst_row + x] = canvas[src_row + (x * FACE_AFTERGLOW_DOWNSAMPLE)];
        }
    }
}

static void render_calibration(pixel_t* buf)
{
    const pixel_t bg = rgb_to_color(8, 8, 10);
    const pixel_t grid = rgb_to_color(34, 34, 38);
    const pixel_t axis = rgb_to_color(74, 74, 84);
    const pixel_t touch = rgb_to_color(255, 228, 128);
    const pixel_t cross = rgb_to_color(240, 250, 255);

    draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, bg);

    for (int x = 0; x < SCREEN_W; x += 20) {
        draw_vline(buf, x, 0, SCREEN_H - 1, (x % 40 == 0) ? axis : grid);
    }
    for (int y = 0; y < SCREEN_H; y += 20) {
        draw_hline(buf, 0, SCREEN_W - 1, y, (y % 40 == 0) ? axis : grid);
    }
    draw_vline(buf, SCREEN_W / 2, 0, SCREEN_H - 1, rgb_to_color(120, 120, 130));
    draw_hline(buf, 0, SCREEN_W - 1, SCREEN_H / 2, rgb_to_color(120, 120, 130));

    const int tx = (s_last_touch_x < 0) ? 0 : ((s_last_touch_x >= SCREEN_W) ? (SCREEN_W - 1) : s_last_touch_x);
    const int ty = (s_last_touch_y < 0) ? 0 : ((s_last_touch_y >= SCREEN_H) ? (SCREEN_H - 1) : s_last_touch_y);
    draw_hline(buf, tx - 10, tx + 10, ty, cross);
    draw_vline(buf, tx, ty - 10, ty + 10, cross);
    draw_filled_circle(buf, tx, ty, 4, touch);
}

static void update_calibration_labels(uint32_t now_ms, uint32_t next_switch_ms)
{
    if (!FACE_CALIBRATION_MODE || !calib_label_touch || !calib_label_tf || !calib_label_flags) {
        return;
    }

    const std::size_t           idx = touch_transform_preset_index();
    const std::size_t           total = touch_transform_preset_count();
    const TouchTransformPreset* tf = touch_transform_preset_get(idx);

    char     line_touch[128];
    char     line_tf[128];
    char     line_flags[128];
    char     line_cycle[32];
    uint32_t secs_left = 0;
    if (static_cast<int32_t>(next_switch_ms - now_ms) > 0) {
        secs_left = (next_switch_ms - now_ms + 999U) / 1000U;
    }

    snprintf(line_touch, sizeof(line_touch), "touch x=%3d y=%3d evt=%u active=%u", s_last_touch_x, s_last_touch_y,
             static_cast<unsigned>(s_last_touch_evt), s_last_touch_active ? 1U : 0U);
    if (CALIB_TOUCH_AUTOCYCLE_MS > 0) {
        snprintf(line_cycle, sizeof(line_cycle), "next %us", static_cast<unsigned>(secs_left));
    } else {
        snprintf(line_cycle, sizeof(line_cycle), "locked");
    }

    snprintf(line_tf, sizeof(line_tf), "tf[%u/%u] %s (%s)", static_cast<unsigned>(idx),
             static_cast<unsigned>(total ? (total - 1) : 0), (tf && tf->name) ? tf->name : "none", line_cycle);
    snprintf(line_flags, sizeof(line_flags), "xmax=%u ymax=%u swap=%u mx=%u my=%u",
             tf ? static_cast<unsigned>(tf->x_max) : 0U, tf ? static_cast<unsigned>(tf->y_max) : 0U,
             tf ? (tf->swap_xy ? 1U : 0U) : 0U, tf ? (tf->mirror_x ? 1U : 0U) : 0U, tf ? (tf->mirror_y ? 1U : 0U) : 0U);

    lv_label_set_text(calib_label_touch, line_touch);
    lv_label_set_text(calib_label_tf, line_tf);
    lv_label_set_text(calib_label_flags, line_flags);
}

static float now_s()
{
    return static_cast<float>(esp_timer_get_time()) / 1'000'000.0f;
}

static RectI make_rect_xyxy(int x0, int y0, int x1, int y1)
{
    RectI out = {};
    if (x1 < x0 || y1 < y0) {
        return out;
    }
    if (x1 < 0 || y1 < 0 || x0 >= SCREEN_W || y0 >= SCREEN_H) {
        return out;
    }
    out.x0 = (x0 < 0) ? 0 : x0;
    out.y0 = (y0 < 0) ? 0 : y0;
    out.x1 = (x1 >= SCREEN_W) ? (SCREEN_W - 1) : x1;
    out.y1 = (y1 >= SCREEN_H) ? (SCREEN_H - 1) : y1;
    out.valid = (out.x1 >= out.x0) && (out.y1 >= out.y0);
    return out;
}

static RectI make_rect_xywh(int x, int y, int w, int h)
{
    if (w <= 0 || h <= 0) return {};
    return make_rect_xyxy(x, y, x + w - 1, y + h - 1);
}

static bool rects_touch_or_overlap(const RectI& a, const RectI& b)
{
    if (!a.valid || !b.valid) return false;
    return !(a.x1 + 1 < b.x0 || b.x1 + 1 < a.x0 || a.y1 + 1 < b.y0 || b.y1 + 1 < a.y0);
}

static void rect_union_inplace(RectI& a, const RectI& b)
{
    if (!b.valid) return;
    if (!a.valid) {
        a = b;
        return;
    }
    if (b.x0 < a.x0) a.x0 = b.x0;
    if (b.y0 < a.y0) a.y0 = b.y0;
    if (b.x1 > a.x1) a.x1 = b.x1;
    if (b.y1 > a.y1) a.y1 = b.y1;
    a.valid = true;
}

static int rect_area(const RectI& r)
{
    return r.valid ? (r.x1 - r.x0 + 1) * (r.y1 - r.y0 + 1) : 0;
}

static bool rects_overlap(const RectI& a, const RectI& b)
{
    return a.valid && b.valid && !(a.x1 < b.x0 || b.x1 < a.x0 || a.y1 < b.y0 || b.y1 < a.y0);
}

static void dirty_region_add_rect(DirtyRegion& region, RectI rect)
{
    if (!rect.valid || region.full) return;

    // Merge with a rect only when they overlap (must merge: no pixel may be cleared
    // or flushed twice) or when touching and the bounding box wastes little. Never
    // merge thin strips into a huge box: the four border strips touch at the corners
    // and used to collapse into the whole screen. Re-scan after every merge so the
    // grown rect is checked against all others again.
    bool merged = true;
    while (merged) {
        merged = false;
        for (int i = 0; i < region.count; i++) {
            const RectI& other = region.rects[i];
            bool         take = rects_overlap(other, rect);
            if (!take && rects_touch_or_overlap(other, rect)) {
                RectI u = rect;
                rect_union_inplace(u, other);
                take = rect_area(u) <= (rect_area(rect) + rect_area(other)) * 5 / 4;
            }
            if (!take) continue;
            rect_union_inplace(rect, other);
            region.rects[i] = region.rects[region.count - 1];
            region.count--;
            merged = true;
            break;
        }
    }

    if (region.count >= DirtyRegion::MAX_RECTS) {
        region.full = true;
        region.count = 0;
        return;
    }
    region.rects[region.count++] = rect;
}

static void dirty_region_add_xywh(DirtyRegion& region, int x, int y, int w, int h)
{
    dirty_region_add_rect(region, make_rect_xywh(x, y, w, h));
}

static void dirty_region_add_prev_curr(DirtyRegion& region, const RectI& prev, const RectI& curr)
{
    if (prev.valid) dirty_region_add_rect(region, prev);
    if (curr.valid) dirty_region_add_rect(region, curr);
}

static RectI compute_eye_bounds(const FaceState& fs, bool is_left, float center_x, float center_y)
{
    const EyeState& eye = is_left ? fs.eye_l : fs.eye_r;
    const float     breath = face_get_breath_scale(fs);
    const float     ew = EYE_WIDTH * eye.width_scale * eye.squash_w * breath;
    const float     eh = EYE_HEIGHT * eye.height_scale * eye.squash_h * fmaxf(0.25f, eye.openness) * breath;
    if (eh < 2.0f) {
        return {};
    }

    const float ex = center_x + eye.gaze_x * GAZE_EYE_SHIFT - ew / 2.0f;
    const float ey = center_y + eye.gaze_y * GAZE_EYE_SHIFT - eh / 2.0f;
    const float edge_pad = fs.fx.edge_glow ? 4.0f : 2.0f;

    float x_min = ex - edge_pad;
    float x_max = ex + ew + edge_pad;
    float y_min = ey - edge_pad;
    float y_max = ey + eh + edge_pad;

    const float max_offset_x = fmaxf(0.0f, ew * 0.5f - PUPIL_R - 5.0f);
    const float max_offset_y = fmaxf(0.0f, eh * 0.5f - PUPIL_R - 5.0f);
    const float pupil_x = center_x + clampf(eye.gaze_x * GAZE_PUPIL_SHIFT, -max_offset_x, max_offset_x);
    const float pupil_y = center_y + clampf(eye.gaze_y * GAZE_PUPIL_SHIFT, -max_offset_y, max_offset_y);
    const float pupil_r = static_cast<float>(static_cast<int>(PUPIL_R * fmaxf(0.4f, eye.openness)));

    if (fs.solid_eye && fs.anim.heart) {
        const float heart_r = fminf(ew, eh) * 0.5f * HEART_SOLID_SCALE;
        x_min = fminf(x_min, center_x - heart_r - 3.0f);
        x_max = fmaxf(x_max, center_x + heart_r + 3.0f);
        y_min = fminf(y_min, center_y - heart_r - 3.0f);
        y_max = fmaxf(y_max, center_y + heart_r + 3.0f);
    } else if (fs.solid_eye && fs.anim.x_eyes) {
        const float x_r = fminf(ew, eh) * 0.33f + 4.0f;
        x_min = fminf(x_min, center_x - x_r);
        x_max = fmaxf(x_max, center_x + x_r);
        y_min = fminf(y_min, center_y - x_r);
        y_max = fmaxf(y_max, center_y + x_r);
    } else if (!fs.solid_eye) {
        if (fs.anim.heart) {
            const float heart_r = PUPIL_R * HEART_PUPIL_SCALE + 3.0f;
            x_min = fminf(x_min, pupil_x - heart_r);
            x_max = fmaxf(x_max, pupil_x + heart_r);
            y_min = fminf(y_min, pupil_y - heart_r);
            y_max = fmaxf(y_max, pupil_y + heart_r);
        } else if (fs.anim.x_eyes) {
            const float x_r = pupil_r + 4.0f;
            x_min = fminf(x_min, pupil_x - x_r);
            x_max = fmaxf(x_max, pupil_x + x_r);
            y_min = fminf(y_min, pupil_y - x_r);
            y_max = fmaxf(y_max, pupil_y + x_r);
        } else {
            const float p_r = pupil_r + 2.0f;
            x_min = fminf(x_min, pupil_x - p_r);
            x_max = fmaxf(x_max, pupil_x + p_r);
            y_min = fminf(y_min, pupil_y - p_r);
            y_max = fmaxf(y_max, pupil_y + p_r);
        }
    }

    // Eyelid vertical strokes can extend beyond eye box.
    const float lid_top = is_left ? fs.eyelids.top_l : fs.eyelids.top_r;
    const float lid_bot = is_left ? fs.eyelids.bottom_l : fs.eyelids.bottom_r;
    const float slope_mag = fabsf(fs.eyelids.slope) * 20.0f;
    const float top_limit_max = (ey - 0.5f) + eh * 2.0f * lid_top + slope_mag;
    const float bot_limit = (ey + eh) - eh * 2.0f * lid_bot;
    y_min = fminf(y_min, bot_limit - 1.0f);
    y_max = fmaxf(y_max, top_limit_max + 1.0f);

    return make_rect_xyxy(static_cast<int>(floorf(x_min)), static_cast<int>(floorf(y_min)),
                          static_cast<int>(ceilf(x_max)), static_cast<int>(ceilf(y_max)));
}

static RectI compute_mouth_bounds(const FaceState& fs)
{
    if (!fs.show_mouth) return {};

    float cx, cy;
    mouth_center(fs, cx, cy);
    const float w = MOUTH_HALF_W * fs.mouth_width;
    const float thick = MOUTH_THICKNESS;
    const float curve = fs.mouth_curve * 40.0f;
    const float openness = fs.mouth_open * 40.0f;
    if (w < 1.0f) return {};

    const int x0 = static_cast<int>(floorf(cx - w - thick - 2.0f));
    const int x1 = static_cast<int>(ceilf(cx + w + thick + 2.0f));
    const int y0 = static_cast<int>(floorf(cy - fabsf(curve) - openness - thick - 2.0f));
    const int y1 = static_cast<int>(ceilf(cy + fabsf(curve) + openness + thick + 2.0f));
    return make_rect_xyxy(x0, y0, x1, y1);
}

// ---- Long-press ring (spec §9.5) ----
// Ring state is read under the LVGL lock (face_ui_update), like s_gesture.
static bool s_ring_listening_latched = false;

static bool touch_ring_visible(const FaceState& fs, uint32_t now_ms, float& progress, float& flash)
{
    progress = -1.0f;
    flash = 0.0f;
    if (fs.system.mode != SystemMode::NONE) {
        return false;
    }
    const uint32_t since_fire = s_gesture.ms_since_long_fire(now_ms);
    if (since_fire < TOUCH_RING_FLASH_MS) {
        flash = 1.0f - static_cast<float>(since_fire) / static_cast<float>(TOUCH_RING_FLASH_MS);
        return true;
    }
    progress = s_gesture.ring_progress(now_ms);
    return progress >= 0.0f && !s_gesture.long_fired();
}

static RectI touch_ring_bounds(const FaceState& fs, uint32_t now_ms)
{
    float progress = 0.0f;
    float flash = 0.0f;
    if (!touch_ring_visible(fs, now_ms, progress, flash)) {
        return {};
    }
    const int r = TOUCH_RING_RADIUS + 3; // flash grows by up to 2 px, plus AA
    return make_rect_xyxy(s_gesture.x() - r, s_gesture.y() - r, s_gesture.x() + r, s_gesture.y() + r);
}

static void render_touch_ring(pixel_t* buf, const FaceState& fs, uint32_t now_ms)
{
    float progress = 0.0f;
    float flash = 0.0f;
    if (!touch_ring_visible(fs, now_ms, progress, flash)) {
        return;
    }
    if (!s_gesture.long_fired()) {
        // Colour says what the long-press will do; latched at fire so the flash
        // doesn't change colour when the host's PTT state flips.
        s_ring_listening_latched = g_ptt_listening.load(std::memory_order_relaxed);
    }
    const bool    listening = s_ring_listening_latched;
    const uint8_t cr = listening ? 230 : 255;
    const uint8_t cg = listening ? 230 : 180;
    const uint8_t cb = listening ? 230 : 40;

    const float outer = static_cast<float>(TOUCH_RING_RADIUS) + 2.0f * flash;
    const float inner = outer - static_cast<float>(TOUCH_RING_THICKNESS);
    const float two_pi = 2.0f * static_cast<float>(M_PI);
    const int   cx = s_gesture.x();
    const int   cy = s_gesture.y();
    const int   rr = static_cast<int>(ceilf(outer)) + 1;

    for (int y = cy - rr; y <= cy + rr; y++) {
        if (y < 0 || y >= SCREEN_H) continue;
        const int   row = y * SCREEN_W;
        const float dy = static_cast<float>(y - cy);
        for (int x = cx - rr; x <= cx + rr; x++) {
            if (x < 0 || x >= SCREEN_W) continue;
            const float dx = static_cast<float>(x - cx);
            const float d = sqrtf(dx * dx + dy * dy);
            if (d < inner - 1.0f || d > outer + 1.0f) continue;
            // Anti-aliased annulus edge.
            float a = fminf(clampf(d - (inner - 1.0f), 0.0f, 1.0f), clampf((outer + 1.0f) - d, 0.0f, 1.0f));
            if (flash > 0.0f) {
                a *= flash;
            } else {
                // Clockwise from 12 o'clock (screen y grows downward).
                float ang = atan2f(dx, -dy);
                if (ang < 0.0f) ang += two_pi;
                a *= (ang / two_pi <= progress) ? 0.95f : 0.25f; // filled arc vs faint track
            }
            if (a > 0.01f) {
                buf[row + x] = px_blend(buf[row + x], cr, cg, cb, a);
            }
        }
    }
}

static DirtyRegion compute_dirty_region(const FaceState& fs, const RectI& ring)
{
    DirtyRegion region = {};

    if (!FACE_DIRTY_RECT || FACE_CALIBRATION_MODE || PANEL_TUNE_MODE) {
        region.full = true;
        s_prev_bounds = {};
        s_prev_bounds.valid = true;
        s_prev_bounds.full = true;
        return region;
    }

    // Sparkles no longer force a full redraw: they are added as 1x1 rects below.
    const bool full_now = (fs.system.mode != SystemMode::NONE) || fs.fx.afterglow || fs.anim.rage;
    const bool full_prev = s_prev_bounds.valid && s_prev_bounds.full;

    RectI eye_l = {};
    RectI eye_r = {};
    RectI mouth = {};
    RectI border = {};

    if (!full_now) {
        eye_l = compute_eye_bounds(fs, true, LEFT_EYE_CX, LEFT_EYE_CY);
        eye_r = compute_eye_bounds(fs, false, RIGHT_EYE_CX, RIGHT_EYE_CY);
        mouth = compute_mouth_bounds(fs);
        border.valid = conv_border_active();
    }

    if (full_now || full_prev) {
        region.full = true;
    } else {
        dirty_region_add_prev_curr(region, s_prev_bounds.eye_l, eye_l);
        dirty_region_add_prev_curr(region, s_prev_bounds.eye_r, eye_r);
        dirty_region_add_prev_curr(region, s_prev_bounds.mouth, mouth);

        dirty_region_add_prev_curr(region, s_prev_bounds.ring, ring);

        for (uint8_t i = 0; i < s_prev_bounds.sparkle_count; i++) {
            dirty_region_add_xywh(region, s_prev_bounds.sparkle_x[i], s_prev_bounds.sparkle_y[i], 1, 1);
        }

        if (border.valid || s_prev_bounds.border.valid) {
            constexpr int edge = 20;
            dirty_region_add_xywh(region, 0, 0, SCREEN_W, edge);
            dirty_region_add_xywh(region, 0, SCREEN_H - edge, SCREEN_W, edge);
            dirty_region_add_xywh(region, 0, edge, edge, SCREEN_H - 2 * edge);
            dirty_region_add_xywh(region, SCREEN_W - edge, edge, edge, SCREEN_H - 2 * edge);
        }

        // count == 0: nothing visible changed (e.g. eyes closed, no border) -> no redraw.
    }

    s_prev_bounds.eye_l = eye_l;
    s_prev_bounds.eye_r = eye_r;
    s_prev_bounds.mouth = mouth;
    s_prev_bounds.border = border;
    s_prev_bounds.ring = ring;
    s_prev_bounds.sparkle_count = 0;
    for (const auto& sp : fs.fx.sparkle_pixels) {
        // Same visibility test as render_sparkles().
        if (!sp.active || sp.life == 0 || sp.x < 0 || sp.x >= SCREEN_W || sp.y < 0 || sp.y >= SCREEN_H) continue;
        if (!full_now) {
            dirty_region_add_xywh(region, sp.x, sp.y, 1, 1);
        }
        s_prev_bounds.sparkle_x[s_prev_bounds.sparkle_count] = sp.x;
        s_prev_bounds.sparkle_y[s_prev_bounds.sparkle_count] = sp.y;
        s_prev_bounds.sparkle_count++;
    }
    s_prev_bounds.full = full_now;
    s_prev_bounds.valid = true;

    return region;
}

static uint32_t dirty_region_area(const DirtyRegion& region)
{
    if (region.full) {
        return static_cast<uint32_t>(SCREEN_W * SCREEN_H);
    }
    uint32_t sum = 0;
    for (uint8_t i = 0; i < region.count; i++) {
        const RectI& r = region.rects[i];
        if (!r.valid) continue;
        const uint32_t w = static_cast<uint32_t>(r.x1 - r.x0 + 1);
        const uint32_t h = static_cast<uint32_t>(r.y1 - r.y0 + 1);
        sum += w * h;
    }
    return sum;
}

static void publish_touch_sample(uint8_t event_type, int x, int y)
{
    TouchSample sample = {};
    sample.event_type = event_type;
    sample.x = static_cast<uint16_t>(x < 0 ? 0 : (x >= SCREEN_W ? SCREEN_W - 1 : x));
    sample.y = static_cast<uint16_t>(y < 0 ? 0 : (y >= SCREEN_H ? SCREEN_H - 1 : y));
    sample.timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
    (void)g_touch.push(sample); // full: drop (PRESSING stream backs up first)
}

static void publish_button_event(FaceButtonId button_id, FaceButtonEventType event_type, uint8_t state)
{
    ButtonEventSample ev = {};
    ev.button_id = static_cast<uint8_t>(button_id);
    ev.event_type = static_cast<uint8_t>(event_type);
    ev.state = state;
    ev.timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
    (void)g_button.push(ev);
}

static uint32_t touch_now_ms()
{
    return static_cast<uint32_t>(static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL);
}

static void publish_gesture(TouchGestureEvent ev)
{
    if (ev == TouchGestureEvent::TAP) {
        publish_button_event(FaceButtonId::SCREEN, FaceButtonEventType::CLICK, 0);
        // Local "boop" acknowledgement when no conversation is running (spec §9.5).
        if (g_cmd_conv_state.load(std::memory_order_relaxed) == static_cast<uint8_t>(FaceConvState::IDLE)) {
            s_boop_pending.store(true, std::memory_order_relaxed);
        }
    } else if (ev == TouchGestureEvent::LONG_PRESS) {
        publish_button_event(FaceButtonId::SCREEN, FaceButtonEventType::LONG_PRESS,
                             g_ptt_listening.load(std::memory_order_relaxed) ? 1 : 0);
    } else if (ev == TouchGestureEvent::PET) {
        publish_button_event(FaceButtonId::SCREEN, FaceButtonEventType::PET, 0);
    }
    s_petting.store(s_gesture.petting(), std::memory_order_relaxed);
}

// Runs in the LVGL task with the LVGL lock held (as does face_ui_update), so
// s_gesture needs no further locking. The face_ui_task loop reads only the atomics.
static void root_touch_event_cb(lv_event_t* e)
{
    if (!e) {
        return;
    }
    lv_indev_t* indev = lv_indev_get_act();
    if (!indev) {
        return;
    }

    lv_point_t p = {};
    lv_indev_get_point(indev, &p);
    const uint32_t now_ms = touch_now_ms();
    // Gestures are off during system overlays (spec §4.4); raw touch samples still flow.
    const bool sys_overlay = g_system_mode.load(std::memory_order_relaxed) != 0;

    const lv_event_code_t code = lv_event_get_code(e);
    if (code == LV_EVENT_PRESSED || code == LV_EVENT_PRESSING) {
        s_finger_x.store(static_cast<int16_t>(p.x), std::memory_order_relaxed);
        s_finger_y.store(static_cast<int16_t>(p.y), std::memory_order_relaxed);
    }
    if (code == LV_EVENT_PRESSED) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 0;
        s_last_touch_active = true;
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(0, p.x, p.y);
        if (sys_overlay) {
            s_gesture.reset();
        } else {
            s_gesture.press(p.x, p.y, now_ms);
        }
    } else if (code == LV_EVENT_PRESSING) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 2;
        s_last_touch_active = true;
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(2, p.x, p.y);
        if (sys_overlay) {
            s_gesture.reset();
            s_petting.store(false, std::memory_order_relaxed);
        } else {
            s_gesture.move(p.x, p.y, now_ms);
            publish_gesture(s_gesture.tick(now_ms));
        }
    } else if (code == LV_EVENT_RELEASED) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 1;
        s_last_touch_active = false;
        g_touch_active.store(false, std::memory_order_relaxed);
        publish_touch_sample(1, p.x, p.y);
        if (!sys_overlay) {
            publish_gesture(s_gesture.release(p.x, p.y, now_ms));
        }
        s_petting.store(false, std::memory_order_relaxed);
    }
}

// ---- Public API ----

void face_ui_create(lv_obj_t* parent)
{
    // Allocate canvas buffer in PSRAM
    canvas_buf = static_cast<pixel_t*>(heap_caps_malloc(CANVAS_BYTES, MALLOC_CAP_SPIRAM));
    if (!canvas_buf) {
        ESP_LOGE(TAG, "failed to allocate canvas buffer in PSRAM!");
        return;
    }
    afterglow_buf = static_cast<pixel_t*>(heap_caps_malloc(AFTERGLOW_BYTES, MALLOC_CAP_SPIRAM));
    if (!afterglow_buf) {
        ESP_LOGW(TAG, "failed to allocate afterglow buffer; disabling afterglow effect");
    } else {
        memset(afterglow_buf, 0, AFTERGLOW_BYTES);
    }

    canvas_obj = lv_canvas_create(parent);
    lv_canvas_set_buffer(canvas_obj, canvas_buf, SCREEN_W, SCREEN_H, CANVAS_COLOR_FORMAT);
    lv_obj_align(canvas_obj, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_add_flag(canvas_obj, LV_OBJ_FLAG_CLICKABLE);

    // Clear to black
    lv_canvas_fill_bg(canvas_obj, lv_color_black(), LV_OPA_COVER);

    // Root touch telemetry hooks (press / drag / release).
    lv_obj_add_event_cb(canvas_obj, root_touch_event_cb, LV_EVENT_PRESSED, nullptr);
    lv_obj_add_event_cb(canvas_obj, root_touch_event_cb, LV_EVENT_PRESSING, nullptr);
    lv_obj_add_event_cb(canvas_obj, root_touch_event_cb, LV_EVENT_RELEASED, nullptr);

    // Corner button zones are now pixel-rendered by conv_border_render_buttons().
    // Touch hit-testing is handled in root_touch_event_cb via conv_border_hit_test_*.

    if (FACE_CALIBRATION_MODE) {
        calib_header_bg = lv_obj_create(parent);
        lv_obj_set_size(calib_header_bg, SCREEN_W, 50);
        lv_obj_align(calib_header_bg, LV_ALIGN_TOP_LEFT, 0, 0);
        lv_obj_set_style_radius(calib_header_bg, 0, LV_PART_MAIN);
        lv_obj_set_style_border_width(calib_header_bg, 0, LV_PART_MAIN);
        lv_obj_set_style_bg_color(calib_header_bg, lv_color_black(), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(calib_header_bg, LV_OPA_70, LV_PART_MAIN);
        lv_obj_set_style_pad_all(calib_header_bg, 0, LV_PART_MAIN);

        calib_label_touch = lv_label_create(calib_header_bg);
        lv_obj_align(calib_label_touch, LV_ALIGN_TOP_LEFT, 4, 2);
        lv_obj_set_style_text_color(calib_label_touch, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
        lv_label_set_text(calib_label_touch, "touch x=0 y=0 evt=255 active=0");

        calib_label_tf = lv_label_create(calib_header_bg);
        lv_obj_align(calib_label_tf, LV_ALIGN_TOP_LEFT, 4, 18);
        lv_obj_set_style_text_color(calib_label_tf, lv_color_hex(0xEAF3FF), LV_PART_MAIN);
        lv_label_set_text(calib_label_tf, "tf[0/0] init");

        calib_label_flags = lv_label_create(calib_header_bg);
        lv_obj_align(calib_label_flags, LV_ALIGN_TOP_LEFT, 4, 34);
        lv_obj_set_style_text_color(calib_label_flags, lv_color_hex(0xD4F0DA), LV_PART_MAIN);
        lv_label_set_text(calib_label_flags, "xmax=0 ymax=0 swap=0 mx=0 my=0");

        lv_obj_move_foreground(calib_header_bg);
    }

    ESP_LOGI(TAG, "face UI created (%dx%d canvas in PSRAM, afterglow=%dx%d)", SCREEN_W, SCREEN_H, AFTERGLOW_W,
             AFTERGLOW_H);
}

// Big 7-segment digit for PANEL_TUNE_MODE (which preset is active).
static void draw_digit(pixel_t* buf, int x, int y, int d, pixel_t c)
{
    // Segments a..g as bits; 0-9.
    static constexpr uint8_t SEG[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
    const uint8_t            m = SEG[d % 10];
    constexpr int            W = 22, H = 40, T = 5;
    if (m & 0x01) draw_filled_rect(buf, x, y, W, T, c);                     // a
    if (m & 0x02) draw_filled_rect(buf, x + W - T, y, T, H / 2, c);         // b
    if (m & 0x04) draw_filled_rect(buf, x + W - T, y + H / 2, T, H / 2, c); // c
    if (m & 0x08) draw_filled_rect(buf, x, y + H - T, W, T, c);             // d
    if (m & 0x10) draw_filled_rect(buf, x, y + H / 2, T, H / 2, c);         // e
    if (m & 0x20) draw_filled_rect(buf, x, y, T, H / 2, c);                 // f
    if (m & 0x40) draw_filled_rect(buf, x, y + H / 2 - T / 2, W, T, c);     // g
}

static int s_panel_preset_shown = -1;

void face_ui_update(const FaceState& fs)
{
    if (!canvas_buf) return;

    const uint64_t render_start_us =
        (FACE_PERF_TELEMETRY && s_collect_render_perf) ? static_cast<uint64_t>(esp_timer_get_time()) : 0ULL;
    uint64_t stage_start_us = render_start_us;
    auto     sample_stage = [&](uint32_t& out_us) {
        if (!(FACE_PERF_TELEMETRY && s_collect_render_perf)) {
            return;
        }
        const uint64_t now = static_cast<uint64_t>(esp_timer_get_time());
        out_us = static_cast<uint32_t>(now - stage_start_us);
        stage_start_us = now;
    };

    RenderPerfSnapshot perf = {};
    const uint32_t     now_ms = touch_now_ms();

    // Long-press fires at the threshold even if LVGL sends no PRESSING event this frame.
    if (fs.system.mode == SystemMode::NONE) {
        publish_gesture(s_gesture.tick(now_ms));
    }

    // Work out what changes this frame first, then clear only those areas. Every
    // element is drawn inside its own prev/curr dirty bounds, so pixels outside the
    // dirty region are already correct from the last frame.
    const RectI       ring = touch_ring_bounds(fs, now_ms);
    const DirtyRegion dirty = compute_dirty_region(fs, ring);
    perf.dirty_px = dirty_region_area(dirty);
    const pixel_t bg = rgb_to_color(BG_R, BG_G, BG_B);
    if (dirty.full) {
        if (bg == 0) {
            memset(canvas_buf, 0, CANVAS_BYTES);
        } else {
            std::fill_n(canvas_buf, SCREEN_W * SCREEN_H, bg);
        }
    } else {
        for (uint8_t i = 0; i < dirty.count; i++) {
            const RectI& r = dirty.rects[i];
            if (!r.valid) continue;
            draw_filled_rect(canvas_buf, r.x0, r.y0, r.x1 - r.x0 + 1, r.y1 - r.y0 + 1, bg);
        }
    }

    if (FACE_CALIBRATION_MODE) {
        render_calibration(canvas_buf);
        sample_stage(perf.overlay_us);
    } else {
        // Always render face (system modes drive face state via system_face_apply)
        render_eye(canvas_buf, fs.eye_l, fs, true, LEFT_EYE_CX, LEFT_EYE_CY);
        render_eye(canvas_buf, fs.eye_r, fs, false, RIGHT_EYE_CX, RIGHT_EYE_CY);
        sample_stage(perf.eyes_us);

        render_mouth(canvas_buf, fs);
        sample_stage(perf.mouth_us);

        if (fs.anim.rage) {
            render_fire_effect(canvas_buf, fs);
        }
        render_sparkles(canvas_buf, fs);
        apply_afterglow(canvas_buf, fs);
        sample_stage(perf.effects_us);

        // System mode icon overlays (drawn on top of face)
        if (fs.system.mode == SystemMode::ERROR_DISPLAY) {
            system_face_render_error_icon(canvas_buf);
        } else if (fs.system.mode == SystemMode::LOW_BATTERY) {
            system_face_render_battery_icon(canvas_buf, fs.system.param);
        } else if (fs.system.mode == SystemMode::UPDATING) {
            system_face_render_updating_bar(canvas_buf, fs.system.param);
        }
        sample_stage(perf.overlay_us);

        // Conversation border + long-press ring — suppressed during system overlays (spec §4.4)
        if (fs.system.mode == SystemMode::NONE) {
            conv_border_render(canvas_buf);
            render_touch_ring(canvas_buf, fs, now_ms);
        }
        if (PANEL_TUNE_MODE && s_panel_preset_shown >= 0) {
            draw_digit(canvas_buf, 8, 8, s_panel_preset_shown, rgb_to_color(255, 255, 255));
        }
        sample_stage(perf.border_us);

        if ((fs.system.mode != SystemMode::NONE || !fs.fx.afterglow) && afterglow_buf) {
            afterglow_copy_from_canvas(canvas_buf);
        }
    }

    if (FACE_DIRTY_RECT && !dirty.full) {
        for (uint8_t i = 0; i < dirty.count; i++) {
            const RectI& r = dirty.rects[i];
            if (!r.valid) continue;
            lv_area_t area = {
                .x1 = static_cast<int32_t>(r.x0),
                .y1 = static_cast<int32_t>(r.y0),
                .x2 = static_cast<int32_t>(r.x1),
                .y2 = static_cast<int32_t>(r.y1),
            };
            lv_obj_invalidate_area(canvas_obj, &area);
        }
    } else {
        // Invalidate canvas to trigger LVGL refresh
        lv_obj_invalidate(canvas_obj);
    }

    if (FACE_PERF_TELEMETRY && s_collect_render_perf && render_start_us > 0ULL) {
        perf.render_us = static_cast<uint32_t>(static_cast<uint64_t>(esp_timer_get_time()) - render_start_us);
    }
    s_last_render_perf = perf; // dirty_px every frame; stage timings only when sampled
}

static void apply_face_flags(FaceState& fs, uint8_t flags)
{
    const uint8_t masked = static_cast<uint8_t>(flags & FACE_FLAGS_ALL);
    fs.anim.idle = (masked & FACE_FLAG_IDLE_WANDER) != 0;
    fs.anim.autoblink = (masked & FACE_FLAG_AUTOBLINK) != 0;
    fs.solid_eye = (masked & FACE_FLAG_SOLID_EYE) != 0;
    fs.show_mouth = (masked & FACE_FLAG_SHOW_MOUTH) != 0;
    fs.fx.edge_glow = (masked & FACE_FLAG_EDGE_GLOW) != 0;
    fs.fx.sparkle = (masked & FACE_FLAG_SPARKLE) != 0;
    fs.fx.afterglow = (masked & FACE_FLAG_AFTERGLOW) != 0;
}

// ---- FreeRTOS task ----

// Global state instances
std::atomic<uint8_t>  g_cmd_state_mood{0};
std::atomic<uint8_t>  g_cmd_state_intensity{255};
std::atomic<int8_t>   g_cmd_state_gaze_x{0};
std::atomic<int8_t>   g_cmd_state_gaze_y{0};
std::atomic<uint8_t>  g_cmd_state_brightness{DEFAULT_BRIGHTNESS};
std::atomic<uint32_t> g_cmd_state_us{0};

std::atomic<uint8_t>  g_cmd_system_mode{static_cast<uint8_t>(SystemMode::NONE)};
std::atomic<uint8_t>  g_cmd_system_param{0};
std::atomic<uint32_t> g_cmd_system_us{0};

std::atomic<uint8_t>  g_cmd_talking{0};
std::atomic<uint8_t>  g_cmd_talking_energy{0};
std::atomic<uint32_t> g_cmd_talking_us{0};

std::atomic<uint8_t>  g_cmd_flags{static_cast<uint8_t>(FACE_FLAGS_ALL & ~FACE_FLAG_AFTERGLOW)};
std::atomic<uint32_t> g_cmd_flags_us{0};

std::atomic<uint8_t>  g_cmd_conv_state{0};
std::atomic<uint32_t> g_cmd_conv_state_us{0};

GestureQueue g_gesture_queue;

TouchQueue            g_touch;
ButtonEventQueue      g_button;
FacePerfBuffer        g_face_perf;
std::atomic<bool>     g_touch_active{false};
std::atomic<bool>     g_talking_active{false};
std::atomic<bool>     g_ptt_listening{false};
std::atomic<bool>     g_host_link_lost{false};
std::atomic<uint32_t> g_last_host_rx_us{0};
std::atomic<uint8_t>  g_current_mood{0};
std::atomic<uint8_t>  g_active_gesture{0xFF};
std::atomic<uint8_t>  g_system_mode{0};
std::atomic<uint32_t> g_cmd_seq_last{0};
std::atomic<uint32_t> g_cmd_applied_us{0};

void face_ui_task(void* arg)
{
    ESP_LOGI(TAG, "face_ui_task started (%d FPS)", ANIM_FPS);

    static constexpr uint64_t ANIM_STEP_US = 1'000'000ULL / ANIM_FPS;
    static constexpr uint32_t MAX_ANIM_CATCHUP_STEPS = 3;
    const TickType_t          frame_period = pdMS_TO_TICKS(1000 / ANIM_FPS) > 0 ? pdMS_TO_TICKS(1000 / ANIM_FPS) : 1;
    TickType_t                last_wake = xTaskGetTickCount();
    uint64_t                  last_anim_us64 = 0;
    uint64_t                  anim_accum_us = 0;
    float                     host_gaze_x = 0.0f;
    float                     host_gaze_y = 0.0f;
    bool                      finger_gaze_prev = false;
    bool                      host_lost = false;
    uint32_t                  next_panel_preset_ms = 0;

    FaceState fs;
    uint32_t  last_state_cmd_us = 0;
    uint32_t  last_system_cmd_us = 0;
    uint32_t  last_talking_cmd_us = 0;
    uint32_t  last_flags_cmd_us = 0;
    uint32_t  last_conv_state_cmd_us = 0;
    bool      last_led_talking = false;
    bool      last_led_listening = false;
    uint32_t  next_touch_cycle_ms = 0;
    uint32_t  next_frame_log_ms = static_cast<uint32_t>(esp_timer_get_time() / 1000ULL) + FRAME_TIME_LOG_INTERVAL_MS;
    uint32_t  frame_count = 0;
    uint64_t  frame_accum_us = 0;
    uint32_t  frame_max_us = 0;
    uint32_t  frame_idx = 0;
    uint32_t  next_perf_pub_ms = static_cast<uint32_t>(esp_timer_get_time() / 1000ULL) + 1000U;
    uint64_t  perf_frame_sum_us = 0;
    uint32_t  perf_frame_max_us = 0;
    uint64_t  perf_render_sum_us = 0;
    uint32_t  perf_render_max_us = 0;
    uint64_t  perf_eyes_sum_us = 0;
    uint64_t  perf_mouth_sum_us = 0;
    uint64_t  perf_border_sum_us = 0;
    uint64_t  perf_effects_sum_us = 0;
    uint64_t  perf_overlay_sum_us = 0;
    uint32_t  perf_stage_samples = 0;
    uint64_t  perf_dirty_px_sum = 0;
    uint64_t  perf_spi_bytes_sum = 0;
    uint64_t  perf_cmd_latency_sum_us = 0;
    uint32_t  perf_cmd_latency_samples = 0;
    uint32_t  perf_window_frames = 0;
    uint32_t  latest_cmd_rx_us = 0;

    apply_face_flags(fs, g_cmd_flags.load(std::memory_order_relaxed));
    if (!afterglow_buf) {
        fs.fx.afterglow = false;
    }

    display_set_backlight(DEFAULT_BRIGHTNESS);

    if (FACE_CALIBRATION_MODE) {
        touch_transform_apply(CALIB_TOUCH_DEFAULT_INDEX);
        if (CALIB_TOUCH_AUTOCYCLE_MS > 0) {
            next_touch_cycle_ms = static_cast<uint32_t>(esp_timer_get_time() / 1000ULL) + CALIB_TOUCH_AUTOCYCLE_MS;
            ESP_LOGI(TAG, "calibration mode enabled; cycling touch transform every %u ms",
                     static_cast<unsigned>(CALIB_TOUCH_AUTOCYCLE_MS));
        } else {
            next_touch_cycle_ms = 0;
            ESP_LOGI(TAG, "calibration mode enabled; touch transform locked at preset %u",
                     static_cast<unsigned>(CALIB_TOUCH_DEFAULT_INDEX));
        }
    }

    while (true) {
        const uint64_t frame_start_us = static_cast<uint64_t>(esp_timer_get_time());
        // Command timestamps are 32-bit microseconds, so now_us wraps every ~71.6 min;
        // only compare it by unsigned difference. now_ms comes from the 64-bit timer so
        // it wraps every ~49.7 days, not when now_us does (deadlines use int32 diffs).
        const uint64_t now_us64 = static_cast<uint64_t>(esp_timer_get_time());
        const uint32_t now_us = static_cast<uint32_t>(now_us64);
        const uint32_t now_ms = static_cast<uint32_t>(now_us64 / 1000ULL);
        // 1. Apply latest latched state command.
        const uint32_t state_cmd_us = g_cmd_state_us.load(std::memory_order_acquire);
        if (state_cmd_us != 0 && state_cmd_us != last_state_cmd_us) {
            last_state_cmd_us = state_cmd_us;
            latest_cmd_rx_us = state_cmd_us;
            const uint8_t mood_id = g_cmd_state_mood.load(std::memory_order_relaxed);
            const uint8_t intensity_u8 = g_cmd_state_intensity.load(std::memory_order_relaxed);
            const int8_t  gaze_x_i8 = g_cmd_state_gaze_x.load(std::memory_order_relaxed);
            const int8_t  gaze_y_i8 = g_cmd_state_gaze_y.load(std::memory_order_relaxed);
            const uint8_t brightness_u8 = g_cmd_state_brightness.load(std::memory_order_relaxed);

            if (mood_id <= static_cast<uint8_t>(Mood::CONFUSED)) {
                face_set_mood(fs, static_cast<Mood>(mood_id));
            }
            face_set_expression_intensity(fs, static_cast<float>(intensity_u8) / 255.0f);

            host_gaze_x = static_cast<float>(gaze_x_i8) / 127.0f * MAX_GAZE;
            host_gaze_y = static_cast<float>(gaze_y_i8) / 127.0f * MAX_GAZE;
            face_set_gaze(fs, host_gaze_x, host_gaze_y);

            display_set_backlight(brightness_u8);
        }

        // 2. Apply queued one-shot gestures in FIFO order.
        GestureEvent ev = {};
        while (g_gesture_queue.pop(&ev)) {
            if (ev.gesture_id <= static_cast<uint8_t>(GestureId::WIGGLE)) {
                face_trigger_gesture(fs, static_cast<GestureId>(ev.gesture_id), ev.duration_ms);
                latest_cmd_rx_us = ev.timestamp_us;
            }
        }

        // 3. Apply latest latched system command.
        const uint32_t system_cmd_us = g_cmd_system_us.load(std::memory_order_acquire);
        if (system_cmd_us != 0 && system_cmd_us != last_system_cmd_us) {
            last_system_cmd_us = system_cmd_us;
            latest_cmd_rx_us = system_cmd_us;
            const uint8_t mode_u8 = g_cmd_system_mode.load(std::memory_order_relaxed);
            const uint8_t param_u8 = g_cmd_system_param.load(std::memory_order_relaxed);
            if (mode_u8 <= static_cast<uint8_t>(SystemMode::SHUTTING_DOWN)) {
                const float param = static_cast<float>(param_u8) / 255.0f;
                face_set_system_mode(fs, static_cast<SystemMode>(mode_u8), param);
            }
        }

        // 4. Apply latest latched talking command.
        const uint32_t talking_cmd_us = g_cmd_talking_us.load(std::memory_order_acquire);
        if (talking_cmd_us != 0 && talking_cmd_us != last_talking_cmd_us) {
            last_talking_cmd_us = talking_cmd_us;
            latest_cmd_rx_us = talking_cmd_us;
            fs.talking = g_cmd_talking.load(std::memory_order_relaxed) != 0;
            fs.talking_energy = static_cast<float>(g_cmd_talking_energy.load(std::memory_order_relaxed)) / 255.0f;
            if (!fs.talking) {
                fs.talking_energy = 0.0f;
            }
        }

        if (fs.talking && last_talking_cmd_us != 0) {
            const uint32_t age_us = now_us - last_talking_cmd_us;
            if (age_us > TALKING_CMD_TIMEOUT_MS * 1000U) {
                fs.talking = false;
                fs.talking_energy = 0.0f;
            }
        }

        // 5. Apply latest latched flags command.
        const uint32_t flags_cmd_us = g_cmd_flags_us.load(std::memory_order_acquire);
        if (flags_cmd_us != 0 && flags_cmd_us != last_flags_cmd_us) {
            last_flags_cmd_us = flags_cmd_us;
            latest_cmd_rx_us = flags_cmd_us;
            const uint8_t flags = g_cmd_flags.load(std::memory_order_relaxed);
            apply_face_flags(fs, flags);
            if (!afterglow_buf) {
                fs.fx.afterglow = false;
            }
        }

        // 5b. Apply latest latched conv_state command.
        const uint32_t conv_state_cmd_us = g_cmd_conv_state_us.load(std::memory_order_acquire);
        if (conv_state_cmd_us != 0 && conv_state_cmd_us != last_conv_state_cmd_us) {
            last_conv_state_cmd_us = conv_state_cmd_us;
            latest_cmd_rx_us = conv_state_cmd_us;
            const uint8_t conv_state = g_cmd_conv_state.load(std::memory_order_relaxed);
            conv_border_set_state(conv_state);
            g_ptt_listening.store(conv_state == static_cast<uint8_t>(FaceConvState::PTT), std::memory_order_relaxed);
        }

        // Feed talking energy to border for SPEAKING reactivity.
        conv_border_set_energy(fs.talking_energy);

        // Fixed-timestep animation: face_state/conv_border advance in 1/ANIM_FPS steps
        // (matches the Python sim). If a frame overran, run catch-up steps so motion
        // keeps real-time speed instead of slowing down with the frame rate.
        uint32_t anim_steps = 1;
        if (last_anim_us64 != 0) {
            anim_accum_us += now_us64 - last_anim_us64;
            anim_steps = static_cast<uint32_t>(anim_accum_us / ANIM_STEP_US);
            if (anim_steps > MAX_ANIM_CATCHUP_STEPS) {
                anim_steps = MAX_ANIM_CATCHUP_STEPS;
                anim_accum_us = 0; // long stall: drop the backlog, don't fast-forward
            } else {
                anim_accum_us -= static_cast<uint64_t>(anim_steps) * ANIM_STEP_US;
            }
        }
        last_anim_us64 = now_us64;

        // Advance border animation.
        for (uint32_t i = 0; i < anim_steps; i++) {
            conv_border_update(1.0f / ANIM_FPS);
        }

        if (FACE_CALIBRATION_MODE && CALIB_TOUCH_AUTOCYCLE_MS > 0) {
            const int32_t delta_ms = static_cast<int32_t>(now_ms - next_touch_cycle_ms);
            if (delta_ms >= 0) {
                const std::size_t count = touch_transform_preset_count();
                if (count > 0) {
                    const std::size_t next = (touch_transform_preset_index() + 1) % count;
                    touch_transform_apply(next);
                }
                next_touch_cycle_ms = now_ms + CALIB_TOUCH_AUTOCYCLE_MS;
            }
        }

        // 5b2. Host link watchdog (spec §4.4). Any packet, incl. 2 Hz time sync, counts.
        {
            const uint32_t last_rx_us = g_last_host_rx_us.load(std::memory_order_acquire);
            const bool     lost =
                (last_rx_us == 0) ? (now_ms > HOST_SILENCE_MS) : ((now_us - last_rx_us) > HOST_SILENCE_MS * 1000U);
            if (lost != host_lost) {
                host_lost = lost;
                g_host_link_lost.store(lost, std::memory_order_relaxed);
                if (lost) {
                    ESP_LOGW(TAG, "host link lost (no packet for %u ms): local sleepy face",
                             static_cast<unsigned>(HOST_SILENCE_MS));
                    // Stale conversation visuals would mislead: clear border, PTT, talking.
                    conv_border_set_state(static_cast<uint8_t>(FaceConvState::IDLE));
                    g_ptt_listening.store(false, std::memory_order_relaxed);
                    fs.talking = false;
                    fs.talking_energy = 0.0f;
                } else {
                    ESP_LOGI(TAG, "host link restored: re-applying latched host state");
                    // Host only resends on change, so replay what it last told us (the
                    // latched atomics hold boot defaults if it never sent anything).
                    const uint8_t mood_id = g_cmd_state_mood.load(std::memory_order_relaxed);
                    face_set_mood(fs, mood_id <= static_cast<uint8_t>(Mood::CONFUSED) ? static_cast<Mood>(mood_id)
                                                                                      : Mood::NEUTRAL);
                    face_set_expression_intensity(
                        fs, static_cast<float>(g_cmd_state_intensity.load(std::memory_order_relaxed)) / 255.0f);
                    apply_face_flags(fs, g_cmd_flags.load(std::memory_order_relaxed));
                    if (!afterglow_buf) {
                        fs.fx.afterglow = false;
                    }
                    // Conversation state is NOT replayed: a restarted supervisor starts idle
                    // and only sends conv state on change, so a replayed PTT/LISTENING
                    // would stick. Stay idle until the host says otherwise.
                    g_cmd_conv_state.store(static_cast<uint8_t>(FaceConvState::IDLE), std::memory_order_relaxed);
                    conv_border_set_state(static_cast<uint8_t>(FaceConvState::IDLE));
                    g_ptt_listening.store(false, std::memory_order_relaxed);
                }
            }
            if (host_lost) {
                face_set_mood(fs, Mood::SLEEPY);
                face_set_expression_intensity(fs, 0.5f);
                fs.anim.idle = true; // slow look-around, "where did everyone go?"
            }
        }

        // 5c. Local touch reactions (spec §9.5), off during system overlays.
        const bool sys_none = fs.system.mode == SystemMode::NONE;
        if (s_boop_pending.exchange(false, std::memory_order_relaxed) && sys_none) {
            face_trigger_gesture(fs, GestureId::BLINK, 0);
        }
        if (sys_none && s_petting.load(std::memory_order_relaxed)) {
            face_pet(fs);
        }
        const bool finger_gaze = TOUCH_GAZE_FOLLOW && sys_none && g_touch_active.load(std::memory_order_relaxed);
        const bool idle_wander_flag = fs.anim.idle;
        if (finger_gaze) {
            // Eyes look toward the finger; idle wander paused so it can't pull them away.
            const float fx = static_cast<float>(s_finger_x.load(std::memory_order_relaxed));
            const float fy = static_cast<float>(s_finger_y.load(std::memory_order_relaxed));
            face_set_gaze(fs, (fx - SCREEN_W * 0.5f) / (SCREEN_W * 0.5f) * MAX_GAZE,
                          (fy - SCREEN_H * 0.5f) / (SCREEN_H * 0.5f) * MAX_GAZE);
            fs.anim.idle = false;
        } else if (finger_gaze_prev) {
            face_set_gaze(fs, host_gaze_x, host_gaze_y); // back to the host-commanded gaze
        }
        finger_gaze_prev = finger_gaze;

        // 6. Advance animations
        for (uint32_t i = 0; i < anim_steps; i++) {
            face_state_update(fs);
        }
        if (finger_gaze) {
            fs.anim.idle = idle_wander_flag;
        }

        // 6b. System face: override face state for system modes (before render)
        if (fs.system.mode != SystemMode::NONE) {
            system_face_apply(fs, now_s());
        }

        // 7. Update telemetry atomics
        g_current_mood.store(static_cast<uint8_t>(fs.mood), std::memory_order_relaxed);
        g_active_gesture.store(fs.active_gesture, std::memory_order_relaxed);
        g_system_mode.store(static_cast<uint8_t>(fs.system.mode), std::memory_order_relaxed);
        g_talking_active.store(fs.talking, std::memory_order_relaxed);

        const bool listening = g_ptt_listening.load(std::memory_order_relaxed);
        if (conv_border_active()) {
            uint8_t led_r, led_g, led_b;
            conv_border_get_led(led_r, led_g, led_b);
            led_set_rgb(led_r, led_g, led_b);
        } else if (fs.talking != last_led_talking || listening != last_led_listening) {
            if (fs.talking) {
                led_set_rgb(180, 80, 0); // talking
            } else if (listening) {
                led_set_rgb(0, 90, 180); // ready to listen
            } else {
                led_set_rgb(0, 40, 0); // idle/connected
            }
            last_led_talking = fs.talking;
            last_led_listening = listening;
        }

        // 6. Render under LVGL lock
        s_collect_render_perf = FACE_PERF_TELEMETRY && ((frame_idx % FACE_PERF_SAMPLE_DIV) == 0U);
        s_last_render_perf = {};
        if (lvgl_port_lock(100)) {
            if (PANEL_TUNE_MODE && static_cast<int32_t>(now_ms - next_panel_preset_ms) >= 0) {
                s_panel_preset_shown = (s_panel_preset_shown + 1) % display_panel_preset_count();
                display_apply_panel_preset(s_panel_preset_shown);
                next_panel_preset_ms = now_ms + PANEL_TUNE_PERIOD_MS;
            }
            face_ui_update(fs);
            if (FACE_CALIBRATION_MODE) {
                update_calibration_labels(now_ms, next_touch_cycle_ms);
            }
            lvgl_port_unlock();

            // v2: record when display buffer was committed (render completion)
            g_cmd_applied_us.store(static_cast<uint32_t>(esp_timer_get_time()), std::memory_order_release);
        }
        s_collect_render_perf = false;

        const uint32_t frame_us = static_cast<uint32_t>(static_cast<uint64_t>(esp_timer_get_time()) - frame_start_us);
        frame_accum_us += frame_us;
        frame_count++;
        if (frame_us > frame_max_us) {
            frame_max_us = frame_us;
        }

        if (FACE_PERF_TELEMETRY) {
            perf_window_frames++;
            perf_frame_sum_us += frame_us;
            if (frame_us > perf_frame_max_us) {
                perf_frame_max_us = frame_us;
            }

            // dirty_px is recorded every frame; timings only on sampled frames.
            const RenderPerfSnapshot rp = s_last_render_perf;
            perf_dirty_px_sum += rp.dirty_px;
            perf_spi_bytes_sum += static_cast<uint64_t>(rp.dirty_px) * 2ULL;

            if ((frame_idx % FACE_PERF_SAMPLE_DIV) == 0U) {
                perf_stage_samples++;
                perf_render_sum_us += rp.render_us;
                if (rp.render_us > perf_render_max_us) {
                    perf_render_max_us = rp.render_us;
                }
                perf_eyes_sum_us += rp.eyes_us;
                perf_mouth_sum_us += rp.mouth_us;
                perf_border_sum_us += rp.border_us;
                perf_effects_sum_us += rp.effects_us;
                perf_overlay_sum_us += rp.overlay_us;
            }

            if (latest_cmd_rx_us != 0U) {
                const uint32_t applied_us = g_cmd_applied_us.load(std::memory_order_acquire);
                // Wrap-safe: both are truncated 32-bit microsecond stamps.
                const int32_t latency_us = static_cast<int32_t>(applied_us - latest_cmd_rx_us);
                if (latency_us > 0) {
                    perf_cmd_latency_sum_us += static_cast<uint64_t>(latency_us);
                    perf_cmd_latency_samples++;
                    latest_cmd_rx_us = 0U; // one sample per command, not one per frame
                }
            }

            if (static_cast<int32_t>(now_ms - next_perf_pub_ms) >= 0) {
                FacePerfSnapshot* out = g_face_perf.write_slot();
                out->window_frames = perf_window_frames;
                out->frame_us_avg =
                    perf_window_frames > 0U ? static_cast<uint32_t>(perf_frame_sum_us / perf_window_frames) : 0U;
                out->frame_us_max = perf_frame_max_us;
                out->render_us_avg =
                    perf_stage_samples > 0U ? static_cast<uint32_t>(perf_render_sum_us / perf_stage_samples) : 0U;
                out->render_us_max = perf_render_max_us;
                out->eyes_us_avg =
                    perf_stage_samples > 0U ? static_cast<uint32_t>(perf_eyes_sum_us / perf_stage_samples) : 0U;
                out->mouth_us_avg =
                    perf_stage_samples > 0U ? static_cast<uint32_t>(perf_mouth_sum_us / perf_stage_samples) : 0U;
                out->border_us_avg =
                    perf_stage_samples > 0U ? static_cast<uint32_t>(perf_border_sum_us / perf_stage_samples) : 0U;
                out->effects_us_avg =
                    perf_stage_samples > 0U ? static_cast<uint32_t>(perf_effects_sum_us / perf_stage_samples) : 0U;
                out->overlay_us_avg =
                    perf_stage_samples > 0U ? static_cast<uint32_t>(perf_overlay_sum_us / perf_stage_samples) : 0U;
                out->dirty_px_avg =
                    perf_window_frames > 0U ? static_cast<uint32_t>(perf_dirty_px_sum / perf_window_frames) : 0U;
                out->spi_bytes_per_s = static_cast<uint32_t>(perf_spi_bytes_sum);
                out->cmd_rx_to_apply_us_avg =
                    perf_cmd_latency_samples > 0U
                        ? static_cast<uint32_t>(perf_cmd_latency_sum_us / perf_cmd_latency_samples)
                        : 0U;
                out->perf_sample_div = FACE_PERF_SAMPLE_DIV;
                out->dirty_rect_enabled = FACE_DIRTY_RECT ? 1U : 0U;
                out->afterglow_downsample = FACE_AFTERGLOW_DOWNSAMPLE;
                g_face_perf.publish();

                perf_frame_sum_us = 0;
                perf_frame_max_us = 0;
                perf_render_sum_us = 0;
                perf_render_max_us = 0;
                perf_eyes_sum_us = 0;
                perf_mouth_sum_us = 0;
                perf_border_sum_us = 0;
                perf_effects_sum_us = 0;
                perf_overlay_sum_us = 0;
                perf_stage_samples = 0;
                perf_dirty_px_sum = 0;
                perf_spi_bytes_sum = 0;
                perf_cmd_latency_sum_us = 0;
                perf_cmd_latency_samples = 0;
                perf_window_frames = 0;
                next_perf_pub_ms = now_ms + 1000U;
            }
        }
        if (FRAME_TIME_LOG_INTERVAL_MS > 0 && static_cast<int32_t>(now_ms - next_frame_log_ms) >= 0) {
            const uint32_t avg_us = (frame_count > 0) ? static_cast<uint32_t>(frame_accum_us / frame_count) : 0U;
            // Real frame rate: frames delivered over the log interval (not 1/work-time).
            const float fps =
                static_cast<float>(frame_count) * 1000.0f / static_cast<float>(FRAME_TIME_LOG_INTERVAL_MS);
            ESP_LOGI(TAG, "frame stats work_avg=%u us work_max=%u us fps=%.1f system=%u", static_cast<unsigned>(avg_us),
                     static_cast<unsigned>(frame_max_us), fps, static_cast<unsigned>(fs.system.mode));
            frame_count = 0;
            frame_accum_us = 0;
            frame_max_us = 0;
            next_frame_log_ms = now_ms + FRAME_TIME_LOG_INTERVAL_MS;
        }

        // 7. Sleep until the next frame slot (fixed rate, not "work + delay").
        frame_idx++;
        if (xTaskDelayUntil(&last_wake, frame_period) == pdFALSE) {
            last_wake = xTaskGetTickCount(); // overran: re-anchor instead of bursting
        }
    }
}
