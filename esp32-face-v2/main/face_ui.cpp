#include "face_ui.h"
#include "config.h"
#include "shared_state.h"
#include "display.h"
#include "led.h"
#include "protocol.h"
#include "touch.h"

#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static const char* TAG = "face_ui";
static constexpr uint32_t TALKING_CMD_TIMEOUT_MS = 450;
static constexpr int BTN_BAR_H = 54;
static constexpr int BTN_W = 138;
static constexpr int BTN_H = 42;
static constexpr uint8_t BG_R = 0;
static constexpr uint8_t BG_G = 0;
static constexpr uint8_t BG_B = 0;

static float now_s();

// ---- LVGL objects ----
static lv_obj_t* canvas_obj = nullptr;
static lv_color_t* canvas_buf = nullptr;
static lv_color_t* afterglow_buf = nullptr;
static lv_obj_t* ptt_btn = nullptr;
static lv_obj_t* ptt_label = nullptr;
static lv_obj_t* action_btn = nullptr;
static lv_obj_t* calib_header_bg = nullptr;
static lv_obj_t* calib_label_touch = nullptr;
static lv_obj_t* calib_label_tf = nullptr;
static lv_obj_t* calib_label_flags = nullptr;

static int s_last_touch_x = SCREEN_W / 2;
static int s_last_touch_y = SCREEN_H / 2;
static uint8_t s_last_touch_evt = 0xFF;
static bool s_last_touch_active = false;

static void publish_touch_sample(uint8_t event_type, int x, int y);
static void publish_button_event(FaceButtonId button_id, FaceButtonEventType event_type, uint8_t state);
static void update_ptt_button_visual(bool listening);
static void root_touch_event_cb(lv_event_t* e);
static void ptt_button_event_cb(lv_event_t* e);
static void action_button_event_cb(lv_event_t* e);
static void render_calibration(lv_color_t* buf);
static void update_calibration_labels(uint32_t now_ms, uint32_t next_switch_ms);

// ---- Drawing helpers ----

static lv_color_t rgb_to_color(uint8_t r, uint8_t g, uint8_t b)
{
    return lv_color_make(r, g, b);
}

static bool color_eq(const lv_color_t& a, const lv_color_t& b)
{
    return a.red == b.red && a.green == b.green && a.blue == b.blue;
}

static lv_color_t scale_color(const lv_color_t& c, uint8_t num, uint8_t den)
{
    return rgb_to_color(
        static_cast<uint8_t>((static_cast<uint16_t>(c.red) * num) / den),
        static_cast<uint8_t>((static_cast<uint16_t>(c.green) * num) / den),
        static_cast<uint8_t>((static_cast<uint16_t>(c.blue) * num) / den));
}

static void draw_filled_rect(lv_color_t* buf, int x, int y, int w, int h,
                             lv_color_t color)
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

static void draw_hline(lv_color_t* buf, int x0, int x1, int y, lv_color_t color)
{
    const int x_lo = (x0 < x1) ? x0 : x1;
    const int x_hi = (x0 < x1) ? x1 : x0;
    draw_filled_rect(buf, x_lo, y, x_hi - x_lo + 1, 1, color);
}

static void draw_vline(lv_color_t* buf, int x, int y0, int y1, lv_color_t color)
{
    const int y_lo = (y0 < y1) ? y0 : y1;
    const int y_hi = (y0 < y1) ? y1 : y0;
    draw_filled_rect(buf, x, y_lo, 1, y_hi - y_lo + 1, color);
}

static bool point_in_rect(int x, int y, int rx, int ry, int rw, int rh)
{
    return (x >= rx && x < (rx + rw) && y >= ry && y < (ry + rh));
}

static void draw_filled_rounded_rect(lv_color_t* buf, int x, int y, int w, int h,
                                     int radius, lv_color_t color)
{
    // Simple rounded rect: draw main body + corners with distance check
    for (int dy = 0; dy < h; dy++) {
        int py = y + dy;
        if (py < 0 || py >= SCREEN_H) continue;
        for (int dx = 0; dx < w; dx++) {
            int px = x + dx;
            if (px < 0 || px >= SCREEN_W) continue;

            bool inside = true;
            // Check corners
            if (dx < radius && dy < radius) {
                // Top-left
                float dist = sqrtf((float)(radius - dx) * (radius - dx) +
                                   (float)(radius - dy) * (radius - dy));
                if (dist > radius) inside = false;
            } else if (dx >= w - radius && dy < radius) {
                // Top-right
                float dist = sqrtf((float)(dx - (w - radius - 1)) * (dx - (w - radius - 1)) +
                                   (float)(radius - dy) * (radius - dy));
                if (dist > radius) inside = false;
            } else if (dx < radius && dy >= h - radius) {
                // Bottom-left
                float dist = sqrtf((float)(radius - dx) * (radius - dx) +
                                   (float)(dy - (h - radius - 1)) * (dy - (h - radius - 1)));
                if (dist > radius) inside = false;
            } else if (dx >= w - radius && dy >= h - radius) {
                // Bottom-right
                float dist = sqrtf((float)(dx - (w - radius - 1)) * (dx - (w - radius - 1)) +
                                   (float)(dy - (h - radius - 1)) * (dy - (h - radius - 1)));
                if (dist > radius) inside = false;
            }

            if (inside) {
                buf[py * SCREEN_W + px] = color;
            }
        }
    }
}

static void draw_filled_circle(lv_color_t* buf, int cx, int cy, int radius,
                               lv_color_t color)
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

static void draw_heart_shape(lv_color_t* buf, int cx, int cy, int size, lv_color_t color)
{
    if (size < 1) {
        return;
    }
    for (int y = cy - size; y <= cy + size; y++) {
        if (y < 0 || y >= SCREEN_H) continue;
        for (int x = cx - size; x <= cx + size; x++) {
            if (x < 0 || x >= SCREEN_W) continue;
            const float xf = static_cast<float>(x - cx) / static_cast<float>(size);
            const float yf = static_cast<float>(y - cy) / static_cast<float>(size);
            const float a = xf * xf + yf * yf - 1.0f;
            const float f = a * a * a - xf * xf * yf * yf * yf;
            if (f <= 0.0f) {
                buf[y * SCREEN_W + x] = color;
            }
        }
    }
}

static void draw_x_shape(lv_color_t* buf, int cx, int cy, int size, int thick, lv_color_t color)
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

static void render_eye(lv_color_t* buf, const EyeState& eye, const FaceState& fs,
                       bool is_left, float center_x, float center_y)
{
    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);
    lv_color_t eye_color = rgb_to_color(r, g, b);
    lv_color_t black = rgb_to_color(0, 0, 0);

    const float breath = face_get_breath_scale(fs);
    const float ew = EYE_WIDTH * eye.width_scale * breath;
    const float eh = EYE_HEIGHT * eye.height_scale * fmaxf(0.25f, eye.openness) * breath;
    if (eh < 2.0f) {
        return;
    }

    const float ex = center_x + eye.gaze_x * GAZE_EYE_SHIFT - ew / 2.0f;
    const float ey = center_y + eye.gaze_y * GAZE_EYE_SHIFT - eh / 2.0f;
    const int corner = static_cast<int>(EYE_CORNER_R * fminf(eye.width_scale, eye.height_scale));

    if (fs.solid_eye && fs.anim.heart) {
        draw_heart_shape(buf, static_cast<int>(center_x), static_cast<int>(center_y),
                         static_cast<int>(fminf(ew, eh) * 0.33f), eye_color);
    } else if (fs.solid_eye && fs.anim.x_eyes) {
        draw_x_shape(buf, static_cast<int>(center_x), static_cast<int>(center_y),
                     static_cast<int>(fminf(ew, eh) * 0.33f), 3, eye_color);
    } else {
        if (fs.fx.edge_glow) {
            const lv_color_t glow = scale_color(eye_color, 2, 5);
            draw_filled_rounded_rect(buf, static_cast<int>(ex) - 2, static_cast<int>(ey) - 2,
                                     static_cast<int>(ew) + 4, static_cast<int>(eh) + 4,
                                     corner + 2, glow);
        }
        draw_filled_rounded_rect(buf, static_cast<int>(ex), static_cast<int>(ey),
                                 static_cast<int>(ew), static_cast<int>(eh), corner, eye_color);
    }

    if (!fs.solid_eye) {
        const float px = center_x + eye.gaze_x * GAZE_PUPIL_SHIFT;
        const float py = center_y + eye.gaze_y * GAZE_PUPIL_SHIFT;
        const int pr = static_cast<int>(PUPIL_R * fmaxf(0.4f, eye.openness));
        if (fs.anim.heart) {
            draw_heart_shape(buf, static_cast<int>(px), static_cast<int>(py), pr, rgb_to_color(10, 15, 30));
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
    const int x0 = static_cast<int>(ex);
    const int x1 = static_cast<int>(ex + ew);
    const int y0 = static_cast<int>(ey);
    const int y1 = static_cast<int>(ey + eh);

    for (int x = x0; x < x1; x++) {
        if (x < 0 || x >= SCREEN_W) continue;
        float nx = (static_cast<float>(x) - (ex + ew * 0.5f)) / fmaxf(1.0f, ew * 0.5f);
        if (!is_left) {
            nx = -nx;
        }
        const float slope_off = slope * 20.0f * nx;
        const int top_limit = static_cast<int>((ey - 0.5f) + eh * 2.0f * lid_top + slope_off);
        const int bot_limit = static_cast<int>((ey + eh) - eh * 2.0f * lid_bot);

        if (top_limit > y0) {
            draw_vline(buf, x, y0, top_limit, black);
        }
        if (bot_limit < y1) {
            draw_vline(buf, x, bot_limit, y1, black);
        }
    }
}

static void render_mouth(lv_color_t* buf, const FaceState& fs)
{
    if (!fs.show_mouth) return;

    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);
    lv_color_t color = rgb_to_color(r, g, b);

    float cx = MOUTH_CX + fs.mouth_offset_x * 10.0f;
    float cy = MOUTH_CY;
    float hw = MOUTH_HALF_W * fs.mouth_width;
    float curve = fs.mouth_curve * 40.0f;
    float thick = MOUTH_THICKNESS;
    float openness = fs.mouth_open * 40.0f;

    int num_points = static_cast<int>(hw * 2);
    for (int i = 0; i < num_points; i++) {
        float t = static_cast<float>(i) / static_cast<float>(num_points - 1);  // 0..1
        float x_off = -hw + 2.0f * hw * t;
        float parabola = 1.0f - 4.0f * (t - 0.5f) * (t - 0.5f);
        float y_off = curve * parabola;

        if (fs.mouth_wave > 0.01f) {
            y_off += fs.mouth_wave * 5.0f * sinf(t * 12.0f + now_s() * 8.0f);
        }

        int px = static_cast<int>(cx + x_off);
        int py = static_cast<int>(cy + y_off);

        int th = static_cast<int>(thick < 1.0f ? 1.0f : thick);
        draw_filled_rect(buf, px - th / 2, py - th / 2, th, th, color);

        if (fs.mouth_open > 0.05f && openness > 0.0f) {
            int open_h = static_cast<int>(openness * parabola);
            if (open_h > 0) {
                draw_filled_rect(buf, px - th / 2, py, th, open_h, color);
            }
        }
    }
}

static void render_system_overlay(lv_color_t* buf, const FaceState& fs)
{
    const float elapsed = now_s() - fs.system.timer;
    if (fs.system.mode == SystemMode::BOOTING) {
        draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, rgb_to_color(0, 8, 20));
        const int cx = SCREEN_W / 2;
        const int cy = SCREEN_H / 2 - 10;
        const int ring = 70;
        const float ang = fmodf(elapsed * 3.0f, 2.0f * static_cast<float>(M_PI));
        for (int i = 0; i < 360; i += 3) {
            float a = static_cast<float>(i) * static_cast<float>(M_PI) / 180.0f;
            int x = cx + static_cast<int>(cosf(a) * ring);
            int y = cy + static_cast<int>(sinf(a) * ring);
            if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_H) continue;
            float d = fabsf(a - ang);
            while (d > static_cast<float>(M_PI)) d -= static_cast<float>(M_PI);
            const lv_color_t c = (d < 0.5f) ? rgb_to_color(0, 220, 255) : rgb_to_color(0, 80, 150);
            buf[y * SCREEN_W + x] = c;
        }
        const int bar_w = 180;
        const int bar_h = 10;
        const int bx = (SCREEN_W - bar_w) / 2;
        const int by = SCREEN_H - 44;
        draw_filled_rect(buf, bx, by, bar_w, bar_h, rgb_to_color(20, 40, 70));
        const float p = fminf(1.0f, elapsed / 3.0f);
        draw_filled_rect(buf, bx, by, static_cast<int>(bar_w * p), bar_h, rgb_to_color(0, 220, 255));
        return;
    }

    if (fs.system.mode == SystemMode::ERROR_DISPLAY) {
        const bool flash = (static_cast<int>(elapsed * 4.0f) % 2) == 0;
        draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, flash ? rgb_to_color(40, 0, 0) : rgb_to_color(18, 0, 0));
        const int cx = SCREEN_W / 2;
        const int cy = SCREEN_H / 2;
        for (int y = -50; y <= 40; y++) {
            int py = cy + y;
            if (py < 0 || py >= SCREEN_H) continue;
            const int half = (y + 50);
            int w = static_cast<int>(half * 1.2f);
            int x0 = cx - w;
            int x1 = cx + w;
            if (y < -44) continue;
            draw_hline(buf, x0, x1, py, rgb_to_color(220, 190, 20));
        }
        draw_filled_rect(buf, cx - 4, cy - 20, 8, 30, rgb_to_color(20, 0, 0));
        draw_filled_circle(buf, cx, cy + 20, 5, rgb_to_color(20, 0, 0));
        return;
    }

    if (fs.system.mode == SystemMode::LOW_BATTERY) {
        draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, rgb_to_color(8, 10, 16));
        const int cx = SCREEN_W / 2;
        const int cy = SCREEN_H / 2;
        const int bw = 120;
        const int bh = 56;
        draw_filled_rounded_rect(buf, cx - bw / 2, cy - bh / 2, bw, bh, 6, rgb_to_color(180, 180, 190));
        draw_filled_rect(buf, cx + bw / 2, cy - 14, 10, 28, rgb_to_color(180, 180, 190));
        draw_filled_rounded_rect(buf, cx - bw / 2 + 4, cy - bh / 2 + 4, bw - 8, bh - 8, 4, rgb_to_color(0, 0, 0));
        const float lvl = fmaxf(0.0f, fminf(1.0f, fs.system.param));
        lv_color_t fill = (lvl > 0.5f) ? rgb_to_color(0, 220, 100) :
                          (lvl > 0.2f) ? rgb_to_color(220, 170, 0) :
                                         rgb_to_color(220, 40, 40);
        draw_filled_rect(buf, cx - bw / 2 + 6, cy - bh / 2 + 6,
                         static_cast<int>((bw - 12) * lvl), bh - 12, fill);
        return;
    }

    if (fs.system.mode == SystemMode::UPDATING) {
        draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, rgb_to_color(5, 10, 14));
        const int cx = SCREEN_W / 2;
        const int cy = SCREEN_H / 2;
        const float base_ang = elapsed * 4.0f;
        for (int i = 0; i < 72; i++) {
            const float a = base_ang + static_cast<float>(i) * 0.12f;
            const int r = 32 + (i % 6) * 3;
            const int x = cx + static_cast<int>(cosf(a) * r);
            const int y = cy + static_cast<int>(sinf(a) * r);
            if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_H) continue;
            const uint8_t br = static_cast<uint8_t>(80 + (i % 12) * 14);
            buf[y * SCREEN_W + x] = rgb_to_color(0, br, static_cast<uint8_t>(120 + br / 3));
        }
        return;
    }

    if (fs.system.mode == SystemMode::SHUTTING_DOWN) {
        draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, rgb_to_color(0, 0, 0));
        const float t = fmaxf(0.0f, 1.0f - elapsed / 0.8f);
        int w = static_cast<int>(SCREEN_W * t);
        int h = static_cast<int>(SCREEN_H * (0.1f + 0.9f * t));
        if (w < 2) w = 2;
        if (h < 2) h = 2;
        draw_filled_rect(buf, (SCREEN_W - w) / 2, (SCREEN_H - h) / 2, w, h, rgb_to_color(210, 220, 255));
        return;
    }
}

static void render_fire_effect(lv_color_t* buf, const FaceState& fs)
{
    for (const auto& px : fs.fx.fire_pixels) {
        if (!px.active || px.life <= 0.0f) continue;
        int x = static_cast<int>(px.x);
        int y = static_cast<int>(px.y);
        if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_H) continue;
        lv_color_t c;
        if (px.heat > 0.85f) c = rgb_to_color(255, 220, 120);
        else if (px.heat > 0.65f) c = rgb_to_color(255, 140, 20);
        else if (px.heat > 0.40f) c = rgb_to_color(220, 50, 0);
        else c = rgb_to_color(130, 20, 0);
        draw_filled_rect(buf, x - 1, y - 1, 3, 3, c);
    }
}

static void render_sparkles(lv_color_t* buf, const FaceState& fs)
{
    for (const auto& sp : fs.fx.sparkle_pixels) {
        if (!sp.active || sp.life == 0) continue;
        if (sp.x < 0 || sp.x >= SCREEN_W || sp.y < 0 || sp.y >= SCREEN_H) continue;
        buf[sp.y * SCREEN_W + sp.x] = rgb_to_color(255, 255, 255);
    }
}

static void apply_afterglow(lv_color_t* buf, const FaceState& fs)
{
    if (!fs.fx.afterglow || !afterglow_buf) {
        return;
    }
    const lv_color_t bg = rgb_to_color(BG_R, BG_G, BG_B);
    for (int i = 0; i < SCREEN_W * SCREEN_H; i++) {
        if (color_eq(buf[i], bg) && !color_eq(afterglow_buf[i], bg)) {
            const lv_color_t faded = scale_color(afterglow_buf[i], 2, 5);
            buf[i] = faded;
        }
    }
    memcpy(afterglow_buf, buf, SCREEN_W * SCREEN_H * sizeof(lv_color_t));
}

static void render_calibration(lv_color_t* buf)
{
    const lv_color_t bg = rgb_to_color(8, 8, 10);
    const lv_color_t grid = rgb_to_color(34, 34, 38);
    const lv_color_t axis = rgb_to_color(74, 74, 84);
    const lv_color_t bar = rgb_to_color(18, 18, 20);
    const lv_color_t ptt_outline = rgb_to_color(34, 180, 102);
    const lv_color_t action_outline = rgb_to_color(190, 98, 54);
    const lv_color_t touch = rgb_to_color(255, 228, 128);
    const lv_color_t cross = rgb_to_color(240, 250, 255);

    draw_filled_rect(buf, 0, 0, SCREEN_W, SCREEN_H, bg);

    for (int x = 0; x < SCREEN_W; x += 20) {
        draw_vline(buf, x, 0, SCREEN_H - 1, (x % 40 == 0) ? axis : grid);
    }
    for (int y = 0; y < SCREEN_H; y += 20) {
        draw_hline(buf, 0, SCREEN_W - 1, y, (y % 40 == 0) ? axis : grid);
    }
    draw_vline(buf, SCREEN_W / 2, 0, SCREEN_H - 1, rgb_to_color(120, 120, 130));
    draw_hline(buf, 0, SCREEN_W - 1, SCREEN_H / 2, rgb_to_color(120, 120, 130));

    const int bar_y = SCREEN_H - BTN_BAR_H;
    draw_filled_rect(buf, 0, bar_y, SCREEN_W, BTN_BAR_H, bar);
    draw_hline(buf, 0, SCREEN_W - 1, bar_y, rgb_to_color(70, 42, 42));

    const int ptt_x = 10;
    const int ptt_y = SCREEN_H - 6 - BTN_H;
    const int action_x = SCREEN_W - 10 - BTN_W;
    const int action_y = SCREEN_H - 6 - BTN_H;

    draw_hline(buf, ptt_x, ptt_x + BTN_W - 1, ptt_y, ptt_outline);
    draw_hline(buf, ptt_x, ptt_x + BTN_W - 1, ptt_y + BTN_H - 1, ptt_outline);
    draw_vline(buf, ptt_x, ptt_y, ptt_y + BTN_H - 1, ptt_outline);
    draw_vline(buf, ptt_x + BTN_W - 1, ptt_y, ptt_y + BTN_H - 1, ptt_outline);

    draw_hline(buf, action_x, action_x + BTN_W - 1, action_y, action_outline);
    draw_hline(buf, action_x, action_x + BTN_W - 1, action_y + BTN_H - 1, action_outline);
    draw_vline(buf, action_x, action_y, action_y + BTN_H - 1, action_outline);
    draw_vline(buf, action_x + BTN_W - 1, action_y, action_y + BTN_H - 1, action_outline);

    if (s_last_touch_active && point_in_rect(s_last_touch_x, s_last_touch_y, ptt_x, ptt_y, BTN_W, BTN_H)) {
        draw_filled_rect(buf, ptt_x + 2, ptt_y + 2, BTN_W - 4, BTN_H - 4, rgb_to_color(14, 52, 30));
    }
    if (s_last_touch_active && point_in_rect(s_last_touch_x, s_last_touch_y, action_x, action_y, BTN_W, BTN_H)) {
        draw_filled_rect(buf, action_x + 2, action_y + 2, BTN_W - 4, BTN_H - 4, rgb_to_color(64, 30, 16));
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

    const std::size_t idx = touch_transform_preset_index();
    const std::size_t total = touch_transform_preset_count();
    const TouchTransformPreset* tf = touch_transform_preset_get(idx);

    char line_touch[128];
    char line_tf[128];
    char line_flags[128];
    char line_cycle[32];
    uint32_t secs_left = 0;
    if (next_switch_ms > now_ms) {
        secs_left = (next_switch_ms - now_ms + 999U) / 1000U;
    }

    snprintf(
        line_touch,
        sizeof(line_touch),
        "touch x=%3d y=%3d evt=%u active=%u",
        s_last_touch_x,
        s_last_touch_y,
        static_cast<unsigned>(s_last_touch_evt),
        s_last_touch_active ? 1U : 0U
    );
    if (CALIB_TOUCH_AUTOCYCLE_MS > 0) {
        snprintf(line_cycle, sizeof(line_cycle), "next %us", static_cast<unsigned>(secs_left));
    } else {
        snprintf(line_cycle, sizeof(line_cycle), "locked");
    }

    snprintf(
        line_tf,
        sizeof(line_tf),
        "tf[%u/%u] %s (%s)",
        static_cast<unsigned>(idx),
        static_cast<unsigned>(total ? (total - 1) : 0),
        (tf && tf->name) ? tf->name : "none",
        line_cycle
    );
    snprintf(
        line_flags,
        sizeof(line_flags),
        "xmax=%u ymax=%u swap=%u mx=%u my=%u",
        tf ? static_cast<unsigned>(tf->x_max) : 0U,
        tf ? static_cast<unsigned>(tf->y_max) : 0U,
        tf ? (tf->swap_xy ? 1U : 0U) : 0U,
        tf ? (tf->mirror_x ? 1U : 0U) : 0U,
        tf ? (tf->mirror_y ? 1U : 0U) : 0U
    );

    lv_label_set_text(calib_label_touch, line_touch);
    lv_label_set_text(calib_label_tf, line_tf);
    lv_label_set_text(calib_label_flags, line_flags);
}

static float now_s()
{
    return static_cast<float>(esp_timer_get_time()) / 1'000'000.0f;
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

static void update_ptt_button_visual(bool listening)
{
    if (!ptt_btn || !ptt_label) {
        return;
    }
    if (listening) {
        lv_obj_set_style_bg_color(ptt_btn, lv_color_hex(0x2F80ED), LV_PART_MAIN);
        lv_label_set_text(ptt_label, "Listening");
    } else {
        lv_obj_set_style_bg_color(ptt_btn, lv_color_hex(0x1F6F43), LV_PART_MAIN);
        lv_label_set_text(ptt_label, "Push To Talk");
    }
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
    } else if (code == LV_EVENT_PRESSING) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 2;
        s_last_touch_active = true;
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(2, p.x, p.y);
    } else if (code == LV_EVENT_RELEASED) {
        s_last_touch_x = p.x;
        s_last_touch_y = p.y;
        s_last_touch_evt = 1;
        s_last_touch_active = false;
        g_touch_active.store(false, std::memory_order_relaxed);
        publish_touch_sample(1, p.x, p.y);
    }
}

static void ptt_button_event_cb(lv_event_t* e)
{
    if (!e) {
        return;
    }

    const lv_event_code_t code = lv_event_get_code(e);
    if (code == LV_EVENT_PRESSED) {
        publish_button_event(FaceButtonId::PTT, FaceButtonEventType::PRESS, g_ptt_listening.load(std::memory_order_relaxed) ? 1 : 0);
    } else if (code == LV_EVENT_RELEASED) {
        publish_button_event(FaceButtonId::PTT, FaceButtonEventType::RELEASE, g_ptt_listening.load(std::memory_order_relaxed) ? 1 : 0);
    } else if (code == LV_EVENT_CLICKED) {
        const bool listening = !g_ptt_listening.load(std::memory_order_relaxed);
        g_ptt_listening.store(listening, std::memory_order_relaxed);
        update_ptt_button_visual(listening);
        publish_button_event(FaceButtonId::PTT, FaceButtonEventType::TOGGLE, listening ? 1 : 0);
    }
}

static void action_button_event_cb(lv_event_t* e)
{
    if (!e) {
        return;
    }

    const lv_event_code_t code = lv_event_get_code(e);
    if (code == LV_EVENT_PRESSED) {
        publish_button_event(FaceButtonId::ACTION, FaceButtonEventType::PRESS, 0);
    } else if (code == LV_EVENT_RELEASED) {
        publish_button_event(FaceButtonId::ACTION, FaceButtonEventType::RELEASE, 0);
    } else if (code == LV_EVENT_CLICKED) {
        publish_button_event(FaceButtonId::ACTION, FaceButtonEventType::CLICK, 0);
    }
}

// ---- Public API ----

void face_ui_create(lv_obj_t* parent)
{
    // Allocate canvas buffer in PSRAM
    canvas_buf = static_cast<lv_color_t*>(
        heap_caps_malloc(SCREEN_W * SCREEN_H * sizeof(lv_color_t), MALLOC_CAP_SPIRAM));
    if (!canvas_buf) {
        ESP_LOGE(TAG, "failed to allocate canvas buffer in PSRAM!");
        return;
    }
    afterglow_buf = static_cast<lv_color_t*>(
        heap_caps_malloc(SCREEN_W * SCREEN_H * sizeof(lv_color_t), MALLOC_CAP_SPIRAM));
    if (!afterglow_buf) {
        ESP_LOGW(TAG, "failed to allocate afterglow buffer; disabling afterglow effect");
    } else {
        memset(afterglow_buf, 0, SCREEN_W * SCREEN_H * sizeof(lv_color_t));
    }

    canvas_obj = lv_canvas_create(parent);
    lv_canvas_set_buffer(canvas_obj, canvas_buf, SCREEN_W, SCREEN_H, LV_COLOR_FORMAT_NATIVE);
    lv_obj_align(canvas_obj, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_add_flag(canvas_obj, LV_OBJ_FLAG_CLICKABLE);

    // Clear to black
    lv_canvas_fill_bg(canvas_obj, lv_color_black(), LV_OPA_COVER);

    // Root touch telemetry hooks (press / drag / release).
    lv_obj_add_event_cb(parent, root_touch_event_cb, LV_EVENT_PRESSED, nullptr);
    lv_obj_add_event_cb(parent, root_touch_event_cb, LV_EVENT_PRESSING, nullptr);
    lv_obj_add_event_cb(parent, root_touch_event_cb, LV_EVENT_RELEASED, nullptr);

    // Bottom control bar buttons.
    ptt_btn = lv_button_create(parent);
    lv_obj_set_size(ptt_btn, BTN_W, BTN_H);
    lv_obj_align(ptt_btn, LV_ALIGN_BOTTOM_LEFT, 10, -6);
    lv_obj_set_style_radius(ptt_btn, 10, LV_PART_MAIN);
    lv_obj_set_style_border_width(ptt_btn, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(ptt_btn, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_add_event_cb(ptt_btn, ptt_button_event_cb, LV_EVENT_ALL, nullptr);
    ptt_label = lv_label_create(ptt_btn);
    lv_obj_center(ptt_label);

    action_btn = lv_button_create(parent);
    lv_obj_set_size(action_btn, BTN_W, BTN_H);
    lv_obj_align(action_btn, LV_ALIGN_BOTTOM_RIGHT, -10, -6);
    lv_obj_set_style_radius(action_btn, 10, LV_PART_MAIN);
    lv_obj_set_style_border_width(action_btn, 0, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(action_btn, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_bg_color(action_btn, lv_color_hex(0xA4472A), LV_PART_MAIN);
    lv_obj_add_event_cb(action_btn, action_button_event_cb, LV_EVENT_ALL, nullptr);
    lv_obj_t* action_label = lv_label_create(action_btn);
    lv_label_set_text(action_label, "Action");
    lv_obj_center(action_label);

    update_ptt_button_visual(false);

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

    ESP_LOGI(TAG, "face UI created (%dx%d canvas in PSRAM)", SCREEN_W, SCREEN_H);
}

void face_ui_update(const FaceState& fs)
{
    if (!canvas_buf) return;

    draw_filled_rect(canvas_buf, 0, 0, SCREEN_W, SCREEN_H, rgb_to_color(BG_R, BG_G, BG_B));

    if (FACE_CALIBRATION_MODE) {
        render_calibration(canvas_buf);
    } else {
        if (fs.system.mode != SystemMode::NONE) {
            render_system_overlay(canvas_buf, fs);
        } else {
            render_eye(canvas_buf, fs.eye_l, fs, true, LEFT_EYE_CX, LEFT_EYE_CY);
            render_eye(canvas_buf, fs.eye_r, fs, false, RIGHT_EYE_CX, RIGHT_EYE_CY);
            render_mouth(canvas_buf, fs);
            if (fs.anim.rage) {
                render_fire_effect(canvas_buf, fs);
            }
            render_sparkles(canvas_buf, fs);
            apply_afterglow(canvas_buf, fs);
        }

        if ((fs.system.mode != SystemMode::NONE || !fs.fx.afterglow) && afterglow_buf) {
            memcpy(afterglow_buf, canvas_buf, SCREEN_W * SCREEN_H * sizeof(lv_color_t));
        }
    }

    // Invalidate canvas to trigger LVGL refresh
    lv_obj_invalidate(canvas_obj);
}

// ---- FreeRTOS task ----

// Global state instances
std::atomic<uint8_t> g_cmd_state_mood{0};
std::atomic<uint8_t> g_cmd_state_intensity{255};
std::atomic<int8_t>  g_cmd_state_gaze_x{0};
std::atomic<int8_t>  g_cmd_state_gaze_y{0};
std::atomic<uint8_t> g_cmd_state_brightness{DEFAULT_BRIGHTNESS};
std::atomic<uint32_t> g_cmd_state_us{0};

std::atomic<uint8_t> g_cmd_system_mode{static_cast<uint8_t>(SystemMode::NONE)};
std::atomic<uint8_t> g_cmd_system_param{0};
std::atomic<uint32_t> g_cmd_system_us{0};

std::atomic<uint8_t> g_cmd_talking{0};
std::atomic<uint8_t> g_cmd_talking_energy{0};
std::atomic<uint32_t> g_cmd_talking_us{0};

GestureQueue g_gesture_queue;

TouchBuffer g_touch;
ButtonEventBuffer g_button;
std::atomic<bool> g_touch_active{false};
std::atomic<bool> g_talking_active{false};
std::atomic<bool> g_ptt_listening{false};
std::atomic<uint8_t> g_current_mood{0};
std::atomic<uint8_t> g_active_gesture{0xFF};
std::atomic<uint8_t> g_system_mode{0};

void face_ui_task(void* arg)
{
    ESP_LOGI(TAG, "face_ui_task started (%d FPS)", ANIM_FPS);

    FaceState fs;
    uint32_t last_state_cmd_us = 0;
    uint32_t last_system_cmd_us = 0;
    uint32_t last_talking_cmd_us = 0;
    bool last_led_talking = false;
    bool last_led_listening = false;
    uint32_t next_touch_cycle_ms = 0;

    if (!afterglow_buf) {
        fs.fx.afterglow = false;
    }

    display_set_backlight(DEFAULT_BRIGHTNESS);

    if (FACE_CALIBRATION_MODE) {
        touch_transform_apply(CALIB_TOUCH_DEFAULT_INDEX);
        if (CALIB_TOUCH_AUTOCYCLE_MS > 0) {
            next_touch_cycle_ms =
                static_cast<uint32_t>(esp_timer_get_time() / 1000ULL) + CALIB_TOUCH_AUTOCYCLE_MS;
            ESP_LOGI(
                TAG,
                "calibration mode enabled; cycling touch transform every %u ms",
                static_cast<unsigned>(CALIB_TOUCH_AUTOCYCLE_MS)
            );
        } else {
            next_touch_cycle_ms = 0;
            ESP_LOGI(
                TAG,
                "calibration mode enabled; touch transform locked at preset %u",
                static_cast<unsigned>(CALIB_TOUCH_DEFAULT_INDEX)
            );
        }
    }

    while (true) {
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        const uint32_t now_ms = now_us / 1000U;
        // 1. Apply latest latched state command.
        const uint32_t state_cmd_us = g_cmd_state_us.load(std::memory_order_acquire);
        if (state_cmd_us != 0 && state_cmd_us != last_state_cmd_us) {
            last_state_cmd_us = state_cmd_us;
            const uint8_t mood_id = g_cmd_state_mood.load(std::memory_order_relaxed);
            const uint8_t intensity_u8 = g_cmd_state_intensity.load(std::memory_order_relaxed);
            const int8_t gaze_x_i8 = g_cmd_state_gaze_x.load(std::memory_order_relaxed);
            const int8_t gaze_y_i8 = g_cmd_state_gaze_y.load(std::memory_order_relaxed);
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
            }
        }

        // 3. Apply latest latched system command.
        const uint32_t system_cmd_us = g_cmd_system_us.load(std::memory_order_acquire);
        if (system_cmd_us != 0 && system_cmd_us != last_system_cmd_us) {
            last_system_cmd_us = system_cmd_us;
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
            fs.talking = g_cmd_talking.load(std::memory_order_relaxed) != 0;
            fs.talking_energy =
                static_cast<float>(g_cmd_talking_energy.load(std::memory_order_relaxed)) / 255.0f;
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

        if (FACE_CALIBRATION_MODE && CALIB_TOUCH_AUTOCYCLE_MS > 0) {
            const int32_t delta_ms = static_cast<int32_t>(now_ms - next_touch_cycle_ms);
            if (delta_ms >= 0) {
                const std::size_t count = touch_transform_preset_count();
                if (count > 0) {
                    const std::size_t next =
                        (touch_transform_preset_index() + 1) % count;
                    touch_transform_apply(next);
                }
                next_touch_cycle_ms = now_ms + CALIB_TOUCH_AUTOCYCLE_MS;
            }
        }

        // 3. Advance animations
        face_state_update(fs);

        // 5. Update telemetry atomics
        g_current_mood.store(static_cast<uint8_t>(fs.mood), std::memory_order_relaxed);
        g_active_gesture.store(fs.active_gesture, std::memory_order_relaxed);
        g_system_mode.store(static_cast<uint8_t>(fs.system.mode), std::memory_order_relaxed);
        g_talking_active.store(fs.talking, std::memory_order_relaxed);

        const bool listening = g_ptt_listening.load(std::memory_order_relaxed);
        if (fs.talking != last_led_talking || listening != last_led_listening) {
            if (fs.talking) {
                led_set_rgb(180, 80, 0);      // talking
            } else if (listening) {
                led_set_rgb(0, 90, 180);      // ready to listen
            } else {
                led_set_rgb(0, 40, 0);        // idle/connected
            }
            last_led_talking = fs.talking;
            last_led_listening = listening;
        }

        // 6. Render under LVGL lock
        if (lvgl_port_lock(100)) {
            face_ui_update(fs);
            if (FACE_CALIBRATION_MODE) {
                update_calibration_labels(now_ms, next_touch_cycle_ms);
            }
            lvgl_port_unlock();
        }

        // 7. Sleep for frame period
        vTaskDelay(pdMS_TO_TICKS(1000 / ANIM_FPS));
    }
}
