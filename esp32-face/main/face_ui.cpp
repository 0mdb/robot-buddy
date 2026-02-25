#include "face_ui.h"
#include "config.h"
#include "shared_state.h"
#include "conv_border.h"
#include "display.h"
#include "led.h"
#include "protocol.h"
#include "touch.h"
#include "system_face.h"
#include "system_overlay_v2.h"
#include "pixel.h"

#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

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

static int     s_last_touch_x = SCREEN_W / 2;
static int     s_last_touch_y = SCREEN_H / 2;
static uint8_t s_last_touch_evt = 0xFF;
static bool    s_last_touch_active = false;

struct DirtyRect {
    int  x0 = 0;
    int  y0 = 0;
    int  x1 = 0;
    int  y1 = 0;
    bool valid = false;
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

static void      publish_touch_sample(uint8_t event_type, int x, int y);
static void      publish_button_event(FaceButtonId button_id, FaceButtonEventType event_type, uint8_t state);
static void      root_touch_event_cb(lv_event_t* e);
static void      render_calibration(pixel_t* buf);
static void      update_calibration_labels(uint32_t now_ms, uint32_t next_switch_ms);
static void      afterglow_copy_from_canvas(const pixel_t* canvas);
static DirtyRect compute_dirty_rect(const FaceState& fs);
static uint32_t  dirty_rect_area(const DirtyRect& rect);

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
    for (int dy = 0; dy < h; dy++) {
        int py = y + dy;
        if (py < 0 || py >= SCREEN_H) continue;
        for (int dx = 0; dx < w; dx++) {
            int px = x + dx;
            if (px < 0 || px >= SCREEN_W) continue;
            buf[py * SCREEN_W + px] = color;
        }
    }
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

static bool point_in_rect(int x, int y, int rx, int ry, int rw, int rh)
{
    return (x >= rx && x < (rx + rw) && y >= ry && y < (ry + rh));
}

static void draw_filled_rounded_rect(pixel_t* buf, int x, int y, int w, int h, int radius, pixel_t color)
{
    const int r2 = radius * radius;
    for (int dy = 0; dy < h; dy++) {
        int py = y + dy;
        if (py < 0 || py >= SCREEN_H) continue;
        for (int dx = 0; dx < w; dx++) {
            int px = x + dx;
            if (px < 0 || px >= SCREEN_W) continue;

            bool inside = true;
            if (dx < radius && dy < radius) {
                int ddx = radius - dx, ddy = radius - dy;
                if (ddx * ddx + ddy * ddy > r2) inside = false;
            } else if (dx >= w - radius && dy < radius) {
                int ddx = dx - (w - radius - 1), ddy = radius - dy;
                if (ddx * ddx + ddy * ddy > r2) inside = false;
            } else if (dx < radius && dy >= h - radius) {
                int ddx = radius - dx, ddy = dy - (h - radius - 1);
                if (ddx * ddx + ddy * ddy > r2) inside = false;
            } else if (dx >= w - radius && dy >= h - radius) {
                int ddx = dx - (w - radius - 1), ddy = dy - (h - radius - 1);
                if (ddx * ddx + ddy * ddy > r2) inside = false;
            }

            if (inside) {
                buf[py * SCREEN_W + px] = color;
            }
        }
    }
}

static void draw_filled_circle(pixel_t* buf, int cx, int cy, int radius, pixel_t color)
{
    int r2 = radius * radius;
    for (int dy = -radius; dy <= radius; dy++) {
        int py = cy + dy;
        if (py < 0 || py >= SCREEN_H) continue;
        for (int dx = -radius; dx <= radius; dx++) {
            int px = cx + dx;
            if (px < 0 || px >= SCREEN_W) continue;
            if (dx * dx + dy * dy <= r2) {
                buf[py * SCREEN_W + px] = color;
            }
        }
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
    const float ew = EYE_WIDTH * eye.width_scale * breath;
    const float eh = EYE_HEIGHT * eye.height_scale * fmaxf(0.25f, eye.openness) * breath;
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

    for (int x = x0; x < x1; x++) {
        if (x < 0 || x >= SCREEN_W) continue;
        float nx = (static_cast<float>(x) - (ex + ew * 0.5f)) / fmaxf(1.0f, ew * 0.5f);
        if (!is_left) {
            nx = -nx;
        }
        const float slope_off = slope * 20.0f * nx;
        const int   top_limit = static_cast<int>((ey - 0.5f) + eh * 2.0f * lid_top + slope_off);
        const int   bot_limit = static_cast<int>((ey + eh) - eh * 2.0f * lid_bot);

        if (top_limit > y0) {
            draw_vline(buf, x, y0, top_limit, black);
        }
        if (bot_limit < y1) {
            draw_vline(buf, x, bot_limit, y1, black);
        }
    }
}

static void render_mouth(pixel_t* buf, const FaceState& fs)
{
    if (!fs.show_mouth) return;

    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);

    const float cx = MOUTH_CX + fs.mouth_offset_x * 10.0f;
    const float cy = MOUTH_CY;
    const float w = MOUTH_HALF_W * fs.mouth_width;
    const float thick = MOUTH_THICKNESS;
    const float curve = fs.mouth_curve * 40.0f;
    const float openness = fs.mouth_open * 40.0f;
    if (w < 1.0f) {
        return;
    }

    const int   x0 = static_cast<int>(cx - w - thick);
    const int   x1 = static_cast<int>(cx + w + thick);
    const int   y0 = static_cast<int>(cy - fabsf(curve) - openness - thick);
    const int   y1 = static_cast<int>(cy + fabsf(curve) + openness + thick);
    const float half_thick = thick * 0.5f;

    for (int y = (y0 < 0 ? 0 : y0); y < (y1 > SCREEN_H ? SCREEN_H : y1); y++) {
        const int row = y * SCREEN_W;
        for (int x = (x0 < 0 ? 0 : x0); x < (x1 > SCREEN_W ? SCREEN_W : x1); x++) {
            const float px = static_cast<float>(x) + 0.5f;
            const float py = static_cast<float>(y) + 0.5f;
            const float nx = (px - cx) / w;
            if (fabsf(nx) > 1.0f) continue;

            const float shape = 1.0f - nx * nx;
            const float curve_y = curve * shape;
            const float upper_y = cy + curve_y - openness * shape;
            const float lower_y = cy + curve_y + openness * shape;

            float dist = 0.0f;
            if (openness > 1.0f && upper_y < py && py < lower_y) {
                dist = 0.0f;
            } else {
                dist = fminf(fabsf(py - upper_y), fabsf(py - lower_y));
            }

            const float alpha = 1.0f - smoothstepf(half_thick - 1.0f, half_thick + 1.0f, dist);
            if (alpha > 0.01f) {
                buf[row + x] = px_blend(buf[row + x], r, g, b, alpha);
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
    const pixel_t ptt_outline = rgb_to_color(34, 180, 102);
    const pixel_t action_outline = rgb_to_color(190, 98, 54);
    const pixel_t ptt_fill = rgb_to_color(20, 96, 64);
    const pixel_t action_fill = rgb_to_color(148, 78, 42);
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

    const int hit = UI_ICON_HITBOX;
    const int vis = UI_ICON_DIAMETER;
    const int vis_r = vis / 2;
    const int ptt_x = UI_ICON_MARGIN;
    const int ptt_y = SCREEN_H - UI_ICON_MARGIN - hit;
    const int action_x = SCREEN_W - UI_ICON_MARGIN - hit;
    const int action_y = SCREEN_H - UI_ICON_MARGIN - hit;
    const int ptt_cx = ptt_x + hit / 2;
    const int ptt_cy = ptt_y + hit / 2;
    const int action_cx = action_x + hit / 2;
    const int action_cy = action_y + hit / 2;

    draw_hline(buf, ptt_x, ptt_x + hit - 1, ptt_y, ptt_outline);
    draw_hline(buf, ptt_x, ptt_x + hit - 1, ptt_y + hit - 1, ptt_outline);
    draw_vline(buf, ptt_x, ptt_y, ptt_y + hit - 1, ptt_outline);
    draw_vline(buf, ptt_x + hit - 1, ptt_y, ptt_y + hit - 1, ptt_outline);
    draw_hline(buf, action_x, action_x + hit - 1, action_y, action_outline);
    draw_hline(buf, action_x, action_x + hit - 1, action_y + hit - 1, action_outline);
    draw_vline(buf, action_x, action_y, action_y + hit - 1, action_outline);
    draw_vline(buf, action_x + hit - 1, action_y, action_y + hit - 1, action_outline);

    draw_filled_circle(buf, ptt_cx, ptt_cy, vis_r, ptt_fill);
    draw_filled_circle(buf, action_cx, action_cy, vis_r, action_fill);

    if (s_last_touch_active && point_in_rect(s_last_touch_x, s_last_touch_y, ptt_x, ptt_y, hit, hit)) {
        draw_filled_circle(buf, ptt_cx, ptt_cy, vis_r - 4, rgb_to_color(58, 214, 145));
    }
    if (s_last_touch_active && point_in_rect(s_last_touch_x, s_last_touch_y, action_x, action_y, hit, hit)) {
        draw_filled_circle(buf, action_cx, action_cy, vis_r - 4, rgb_to_color(255, 140, 84));
    }

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
    if (next_switch_ms > now_ms) {
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

static void dirty_rect_add(DirtyRect& rect, int x, int y, int w, int h)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    int x0 = x;
    int y0 = y;
    int x1 = x + w - 1;
    int y1 = y + h - 1;
    if (x1 < 0 || y1 < 0 || x0 >= SCREEN_W || y0 >= SCREEN_H) {
        return;
    }
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= SCREEN_W) x1 = SCREEN_W - 1;
    if (y1 >= SCREEN_H) y1 = SCREEN_H - 1;

    if (!rect.valid) {
        rect.x0 = x0;
        rect.y0 = y0;
        rect.x1 = x1;
        rect.y1 = y1;
        rect.valid = true;
        return;
    }
    if (x0 < rect.x0) rect.x0 = x0;
    if (y0 < rect.y0) rect.y0 = y0;
    if (x1 > rect.x1) rect.x1 = x1;
    if (y1 > rect.y1) rect.y1 = y1;
}

static DirtyRect compute_dirty_rect(const FaceState& fs)
{
    DirtyRect rect = {};

    if (!FACE_DIRTY_RECT || FACE_CALIBRATION_MODE) {
        dirty_rect_add(rect, 0, 0, SCREEN_W, SCREEN_H);
        return rect;
    }

    if (fs.system.mode != SystemMode::NONE || fs.fx.afterglow || fs.anim.rage || fs.fx.sparkle) {
        dirty_rect_add(rect, 0, 0, SCREEN_W, SCREEN_H);
        return rect;
    }

    // Conservative central region covering eyes + most gaze motion + mouth.
    dirty_rect_add(rect, 12, 0, SCREEN_W - 24, 215);

    // Border and corner buttons only affect edge strips.
    if (conv_border_active()) {
        const int edge = 20;
        dirty_rect_add(rect, 0, 0, SCREEN_W, edge);
        dirty_rect_add(rect, 0, SCREEN_H - edge, SCREEN_W, edge);
        dirty_rect_add(rect, 0, edge, edge, SCREEN_H - 2 * edge);
        dirty_rect_add(rect, SCREEN_W - edge, edge, edge, SCREEN_H - 2 * edge);
    }

    if (!rect.valid) {
        dirty_rect_add(rect, 0, 0, SCREEN_W, SCREEN_H);
    }
    return rect;
}

static uint32_t dirty_rect_area(const DirtyRect& rect)
{
    if (!rect.valid) return static_cast<uint32_t>(SCREEN_W * SCREEN_H);
    const uint32_t w = static_cast<uint32_t>(rect.x1 - rect.x0 + 1);
    const uint32_t h = static_cast<uint32_t>(rect.y1 - rect.y0 + 1);
    return w * h;
}

static void publish_touch_sample(uint8_t event_type, int x, int y)
{
    TouchSample* slot = g_touch.write_slot();
    slot->event_type = event_type;
    slot->x = static_cast<uint16_t>(x < 0 ? 0 : (x >= SCREEN_W ? SCREEN_W - 1 : x));
    slot->y = static_cast<uint16_t>(y < 0 ? 0 : (y >= SCREEN_H ? SCREEN_H - 1 : y));
    slot->timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
    g_touch.publish();
}

static void publish_button_event(FaceButtonId button_id, FaceButtonEventType event_type, uint8_t state)
{
    ButtonEventSample* slot = g_button.write_slot();
    slot->button_id = static_cast<uint8_t>(button_id);
    slot->event_type = static_cast<uint8_t>(event_type);
    slot->state = state;
    slot->timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
    g_button.publish();
}

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

    const lv_event_code_t code = lv_event_get_code(e);
    if (code == LV_EVENT_PRESSED) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 0;
        s_last_touch_active = true;
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(0, p.x, p.y);

        // Corner button hit-testing — disabled during system overlays (spec §4.4)
        const bool sys_overlay = g_system_mode.load(std::memory_order_relaxed) != 0;
        if (!sys_overlay && conv_border_hit_test_left(p.x, p.y)) {
            publish_button_event(FaceButtonId::PTT, FaceButtonEventType::PRESS,
                                 g_ptt_listening.load(std::memory_order_relaxed) ? 1 : 0);
        } else if (!sys_overlay && conv_border_hit_test_right(p.x, p.y)) {
            publish_button_event(FaceButtonId::ACTION, FaceButtonEventType::PRESS, 0);
        }
    } else if (code == LV_EVENT_PRESSING) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 2;
        s_last_touch_active = true;
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(2, p.x, p.y);
    } else if (code == LV_EVENT_RELEASED) {
        const int press_x = s_last_touch_x;
        const int press_y = s_last_touch_y;
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 1;
        s_last_touch_active = false;
        g_touch_active.store(false, std::memory_order_relaxed);
        publish_touch_sample(1, p.x, p.y);

        // Corner button release + click detection — disabled during system overlays (spec §4.4)
        const bool sys_overlay_r = g_system_mode.load(std::memory_order_relaxed) != 0;
        if (!sys_overlay_r && conv_border_hit_test_left(press_x, press_y) && conv_border_hit_test_left(p.x, p.y)) {
            publish_button_event(FaceButtonId::PTT, FaceButtonEventType::RELEASE,
                                 g_ptt_listening.load(std::memory_order_relaxed) ? 1 : 0);
            // Toggle PTT on click (press+release in same zone)
            const bool listening = !g_ptt_listening.load(std::memory_order_relaxed);
            g_ptt_listening.store(listening, std::memory_order_relaxed);
            publish_button_event(FaceButtonId::PTT, FaceButtonEventType::TOGGLE, listening ? 1 : 0);
        } else if (!sys_overlay_r && conv_border_hit_test_right(press_x, press_y) &&
                   conv_border_hit_test_right(p.x, p.y)) {
            publish_button_event(FaceButtonId::ACTION, FaceButtonEventType::RELEASE, 0);
            publish_button_event(FaceButtonId::ACTION, FaceButtonEventType::CLICK, 0);
        }
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
    draw_filled_rect(canvas_buf, 0, 0, SCREEN_W, SCREEN_H, rgb_to_color(BG_R, BG_G, BG_B));

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

        // Conversation border overlay + corner buttons — suppress during system overlays (spec §4.4)
        if (fs.system.mode == SystemMode::NONE) {
            conv_border_render(canvas_buf);
            conv_border_render_buttons(canvas_buf);
        }
        sample_stage(perf.border_us);

        if ((fs.system.mode != SystemMode::NONE || !fs.fx.afterglow) && afterglow_buf) {
            afterglow_copy_from_canvas(canvas_buf);
        }
    }

    const DirtyRect dirty = compute_dirty_rect(fs);
    perf.dirty_px = dirty_rect_area(dirty);
    if (FACE_DIRTY_RECT && dirty.valid) {
        lv_area_t area = {
            .x1 = static_cast<int32_t>(dirty.x0),
            .y1 = static_cast<int32_t>(dirty.y0),
            .x2 = static_cast<int32_t>(dirty.x1),
            .y2 = static_cast<int32_t>(dirty.y1),
        };
        lv_obj_invalidate_area(canvas_obj, &area);
    } else {
        // Invalidate canvas to trigger LVGL refresh
        lv_obj_invalidate(canvas_obj);
    }

    if (FACE_PERF_TELEMETRY && s_collect_render_perf && render_start_us > 0ULL) {
        perf.render_us = static_cast<uint32_t>(static_cast<uint64_t>(esp_timer_get_time()) - render_start_us);
        s_last_render_perf = perf;
    }
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

TouchBuffer           g_touch;
ButtonEventBuffer     g_button;
FacePerfBuffer        g_face_perf;
std::atomic<bool>     g_touch_active{false};
std::atomic<bool>     g_talking_active{false};
std::atomic<bool>     g_ptt_listening{false};
std::atomic<uint8_t>  g_current_mood{0};
std::atomic<uint8_t>  g_active_gesture{0xFF};
std::atomic<uint8_t>  g_system_mode{0};
std::atomic<uint32_t> g_cmd_seq_last{0};
std::atomic<uint32_t> g_cmd_applied_us{0};

void face_ui_task(void* arg)
{
    ESP_LOGI(TAG, "face_ui_task started (%d FPS)", ANIM_FPS);

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
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        const uint32_t now_ms = now_us / 1000U;
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

            if (mood_id <= static_cast<uint8_t>(Mood::THINKING)) {
                face_set_mood(fs, static_cast<Mood>(mood_id));
            }
            face_set_expression_intensity(fs, static_cast<float>(intensity_u8) / 255.0f);

            const float gx = static_cast<float>(gaze_x_i8) / 127.0f * MAX_GAZE;
            const float gy = static_cast<float>(gaze_y_i8) / 127.0f * MAX_GAZE;
            face_set_gaze(fs, gx, gy);

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
            conv_border_set_state(g_cmd_conv_state.load(std::memory_order_relaxed));
        }

        // Feed talking energy to border for SPEAKING reactivity.
        conv_border_set_energy(fs.talking_energy);

        // Advance border animation.
        conv_border_update(1.0f / ANIM_FPS);

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

        // 6. Advance animations
        face_state_update(fs);

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

            const RenderPerfSnapshot rp = s_last_render_perf;
            perf_render_sum_us += rp.render_us;
            if (rp.render_us > perf_render_max_us) {
                perf_render_max_us = rp.render_us;
            }
            perf_dirty_px_sum += rp.dirty_px;
            perf_spi_bytes_sum += static_cast<uint64_t>(rp.dirty_px) * 2ULL;

            if ((frame_idx % FACE_PERF_SAMPLE_DIV) == 0U) {
                perf_stage_samples++;
                perf_eyes_sum_us += rp.eyes_us;
                perf_mouth_sum_us += rp.mouth_us;
                perf_border_sum_us += rp.border_us;
                perf_effects_sum_us += rp.effects_us;
                perf_overlay_sum_us += rp.overlay_us;
            }

            if (latest_cmd_rx_us != 0U) {
                const uint32_t applied_us = g_cmd_applied_us.load(std::memory_order_acquire);
                if (applied_us > latest_cmd_rx_us) {
                    perf_cmd_latency_sum_us += static_cast<uint64_t>(applied_us - latest_cmd_rx_us);
                    perf_cmd_latency_samples++;
                }
            }

            if (static_cast<int32_t>(now_ms - next_perf_pub_ms) >= 0) {
                FacePerfSnapshot* out = g_face_perf.write_slot();
                out->window_frames = perf_window_frames;
                out->frame_us_avg =
                    perf_window_frames > 0U ? static_cast<uint32_t>(perf_frame_sum_us / perf_window_frames) : 0U;
                out->frame_us_max = perf_frame_max_us;
                out->render_us_avg =
                    perf_window_frames > 0U ? static_cast<uint32_t>(perf_render_sum_us / perf_window_frames) : 0U;
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
            const float    fps = (avg_us > 0U) ? (1'000'000.0f / static_cast<float>(avg_us)) : 0.0f;
            ESP_LOGI(TAG, "frame stats avg=%u us max=%u us fps=%.1f system=%u", static_cast<unsigned>(avg_us),
                     static_cast<unsigned>(frame_max_us), fps, static_cast<unsigned>(fs.system.mode));
            frame_count = 0;
            frame_accum_us = 0;
            frame_max_us = 0;
            next_frame_log_ms = now_ms + FRAME_TIME_LOG_INTERVAL_MS;
        }

        // 7. Sleep for frame period
        frame_idx++;
        vTaskDelay(pdMS_TO_TICKS(1000 / ANIM_FPS));
    }
}
