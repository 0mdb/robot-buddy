#include "system_overlay_v2.h"

#include "config.h"

#include <cmath>
#include <cstdint>

namespace {

constexpr float PI = 3.14159265358979323846f;

struct Rgb {
    int r;
    int g;
    int b;
};

constexpr Rgb BG{10, 10, 14};

static int clampi(int v, int lo, int hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float smoothstep(float edge0, float edge1, float x)
{
    const float denom = edge1 - edge0;
    if (fabsf(denom) < 1e-6f) {
        return (x < edge0) ? 0.0f : 1.0f;
    }
    const float t = clampf((x - edge0) / denom, 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

static lv_color_t rgb_to_color(const Rgb& c)
{
    return lv_color_make(
        static_cast<uint8_t>(clampi(c.r, 0, 255)),
        static_cast<uint8_t>(clampi(c.g, 0, 255)),
        static_cast<uint8_t>(clampi(c.b, 0, 255)));
}

static void fill_screen(lv_color_t* buf, const Rgb& c)
{
    const lv_color_t color = rgb_to_color(c);
    for (int i = 0; i < SCREEN_W * SCREEN_H; i++) {
        buf[i] = color;
    }
}

static void set_px_blend(lv_color_t* buf, int idx, const Rgb& c, float alpha)
{
    if (!buf || idx < 0 || idx >= (SCREEN_W * SCREEN_H) || alpha <= 0.0f) {
        return;
    }
    alpha = clampf(alpha, 0.0f, 1.0f);
    const int tr = clampi(c.r, 0, 255);
    const int tg = clampi(c.g, 0, 255);
    const int tb = clampi(c.b, 0, 255);
    if (alpha >= 0.999f) {
        buf[idx] = lv_color_make(
            static_cast<uint8_t>(tr),
            static_cast<uint8_t>(tg),
            static_cast<uint8_t>(tb));
        return;
    }
    const lv_color_t bg = buf[idx];
    const int r = static_cast<int>(bg.red + (tr - bg.red) * alpha);
    const int g = static_cast<int>(bg.green + (tg - bg.green) * alpha);
    const int b = static_cast<int>(bg.blue + (tb - bg.blue) * alpha);
    buf[idx] = lv_color_make(
        static_cast<uint8_t>(clampi(r, 0, 255)),
        static_cast<uint8_t>(clampi(g, 0, 255)),
        static_cast<uint8_t>(clampi(b, 0, 255)));
}

static float sd_rounded_box(float px, float py, float cx, float cy, float hw, float hh, float r)
{
    const float dx = fabsf(px - cx) - hw + r;
    const float dy = fabsf(py - cy) - hh + r;
    const float inner = fminf(fmaxf(dx, dy), 0.0f);
    const float outer = sqrtf(fmaxf(dx, 0.0f) * fmaxf(dx, 0.0f) + fmaxf(dy, 0.0f) * fmaxf(dy, 0.0f));
    return inner + outer - r;
}

static float sd_circle(float px, float py, float cx, float cy, float r)
{
    const float dx = px - cx;
    const float dy = py - cy;
    return sqrtf(dx * dx + dy * dy) - r;
}

static float sd_equilateral_triangle(float px, float py, float cx, float cy, float r)
{
    px -= cx;
    py -= cy;
    constexpr float k = 1.7320508075688772f;  // sqrt(3)
    px = fabsf(px) - r;
    py = py + r / k;
    if (px + k * py > 0.0f) {
        const float old_px = px;
        px = (px - k * py) * 0.5f;
        py = (-k * old_px - py) * 0.5f;
    }
    px -= clampf(px, -2.0f * r, 0.0f);
    const float dist = sqrtf(px * px + py * py);
    return (py < 0.0f) ? -dist : dist;
}

static float noise01(int x, int y, int t)
{
    uint32_t h = static_cast<uint32_t>(x) * 0x1f123bb5U;
    h ^= static_cast<uint32_t>(y) * 0x5f356495U;
    h ^= static_cast<uint32_t>(t) * 0x9e3779b9U;
    h ^= (h >> 16);
    h *= 0x85ebca6bU;
    h ^= (h >> 13);
    h *= 0xc2b2ae35U;
    h ^= (h >> 16);
    return static_cast<float>(h & 0xFFFFU) / 65535.0f;
}

static void render_booting(lv_color_t* buf, float elapsed)
{
    fill_screen(buf, BG);
    const int cx = SCREEN_W / 2;
    const int cy = SCREEN_H / 2;
    const float angle = fmodf(elapsed * 3.0f, 2.0f * PI);
    const float radar_r = 90.0f;

    for (int y = 0; y < SCREEN_H; y++) {
        const int row = y * SCREEN_W;
        for (int x = 0; x < SCREEN_W; x++) {
            if ((x % 40) == 0 || (y % 40) == 0) {
                set_px_blend(buf, row + x, Rgb{0, 50, 100}, 0.2f);
            }
        }
    }

    const int x0 = clampi(static_cast<int>(cx - radar_r), 0, SCREEN_W - 1);
    const int x1 = clampi(static_cast<int>(cx + radar_r), 0, SCREEN_W - 1);
    const int y0 = clampi(static_cast<int>(cy - radar_r), 0, SCREEN_H - 1);
    const int y1 = clampi(static_cast<int>(cy + radar_r), 0, SCREEN_H - 1);

    const int tick = static_cast<int>(elapsed * 120.0f);
    for (int y = y0; y <= y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x <= x1; x++) {
            const float dx = static_cast<float>(x - cx);
            const float dy = static_cast<float>(y - cy);
            const float dist = sqrtf(dx * dx + dy * dy);

            const float ring_sdf = fabsf(dist - radar_r);
            const float alpha_ring = 1.0f - smoothstep(1.0f, 3.0f, ring_sdf);
            if (alpha_ring > 0.0f) {
                set_px_blend(buf, row + x, Rgb{0, 200, 255}, alpha_ring);
            }

            if (dist < radar_r) {
                const float pixel_angle = atan2f(dy, dx);
                float diff = fmodf((pixel_angle - angle + PI), 2.0f * PI);
                if (diff < 0.0f) diff += 2.0f * PI;
                diff -= PI;
                if (diff < 0.0f) diff += 2.0f * PI;
                if (diff > 0.0f && diff < 1.0f) {
                    float intensity = (1.0f - diff) * 0.6f;
                    if (((x * y) % 43 == 0) && (noise01(x, y, tick) < 0.10f)) {
                        intensity = 1.0f;
                    }
                    const int g = static_cast<int>(255.0f * intensity);
                    const int b = static_cast<int>(200.0f * intensity);
                    set_px_blend(buf, row + x, Rgb{0, g, b}, intensity);
                }
            }
        }
    }

    const int bar_w = 200;
    const int bar_h = 10;
    const int bar_y = cy + 60;
    const int bar_x0 = cx - bar_w / 2;
    const int bar_x1 = bar_x0 + bar_w - 1;
    const int bar_y1 = bar_y + bar_h - 1;
    const float prog = fminf(1.0f, elapsed / 3.0f);
    const int fill_x = bar_x0 + static_cast<int>(bar_w * prog);
    for (int y = bar_y; y <= bar_y1; y++) {
        if (y < 0 || y >= SCREEN_H) continue;
        const int row = y * SCREEN_W;
        for (int x = bar_x0; x <= bar_x1; x++) {
            if (x < 0 || x >= SCREEN_W) continue;
            const bool border = (x == bar_x0 || x == bar_x1 || y == bar_y || y == bar_y1);
            if (border) {
                buf[row + x] = rgb_to_color(Rgb{0, 150, 255});
            } else if (x < fill_x) {
                buf[row + x] = rgb_to_color(Rgb{0, 200, 255});
            }
        }
    }
}

static void render_error(lv_color_t* buf, float elapsed)
{
    const int cx = SCREEN_W / 2;
    const int cy = SCREEN_H / 2;
    const float tri_r = 70.0f;
    const float pulse = (sinf(elapsed * 8.0f) + 1.0f) * 0.5f;
    const Rgb bg{static_cast<int>(40.0f * pulse), 0, 0};
    const int tick = static_cast<int>(elapsed * 60.0f);

    auto alpha_pair = [cx, cy, tri_r](float sx, float sy, float* ay, float* am) {
        const float d_tri = sd_equilateral_triangle(sx, sy, static_cast<float>(cx), static_cast<float>(cy), tri_r);
        const float d_in = sd_equilateral_triangle(sx, sy, static_cast<float>(cx), static_cast<float>(cy + 5), tri_r - 15.0f);
        const float d_mark = fminf(
            sd_rounded_box(sx, sy, static_cast<float>(cx), static_cast<float>(cy - 10), 6.0f, 20.0f, 2.0f),
            sd_circle(sx, sy, static_cast<float>(cx), static_cast<float>(cy + 25), 6.0f));
        *ay = 1.0f - smoothstep(0.0f, 2.0f, fminf(d_tri, -d_in));
        *am = 1.0f - smoothstep(0.0f, 2.0f, d_mark);
    };

    for (int y = 0; y < SCREEN_H; y++) {
        const int row = y * SCREEN_W;
        const int off_x = (SYSTEM_FX_GLITCH && noise01(17, y, tick) < 0.05f)
            ? static_cast<int>(noise01(23, y, tick) * 21.0f) - 10
            : 0;
        for (int x = 0; x < SCREEN_W; x++) {
            float ay_r = 0.0f, am_r = 0.0f;
            float ay_g = 0.0f, am_g = 0.0f;
            float ay_b = 0.0f, am_b = 0.0f;
            alpha_pair(static_cast<float>(x + off_x - 4), static_cast<float>(y), &ay_r, &am_r);
            alpha_pair(static_cast<float>(x + off_x), static_cast<float>(y), &ay_g, &am_g);
            alpha_pair(static_cast<float>(x + off_x + 4), static_cast<float>(y), &ay_b, &am_b);

            int r = bg.r;
            int g = bg.g;
            int b = bg.b;
            if (ay_r > 0.0f) r = 255;
            if (am_r > 0.0f) r = 10;
            if (ay_g > 0.0f) g = 200;
            if (am_g > 0.0f) g = 0;
            if (ay_b > 0.0f) b = 0;
            if (am_b > 0.0f) b = 0;
            buf[row + x] = lv_color_make(
                static_cast<uint8_t>(clampi(r, 0, 255)),
                static_cast<uint8_t>(clampi(g, 0, 255)),
                static_cast<uint8_t>(clampi(b, 0, 255)));
        }
    }
}

static void render_battery(lv_color_t* buf, const FaceState& fs, float elapsed)
{
    fill_screen(buf, BG);
    const float lvl = clampf(fs.system.param, 0.0f, 1.0f);
    const int cx = SCREEN_W / 2;
    const int cy = SCREEN_H / 2;
    const int bw = 80;
    const int bh = 40;

    Rgb col{};
    if (lvl > 0.5f) {
        col = {0, 220, 100};
    } else if (lvl > 0.2f) {
        col = {220, 180, 0};
    } else {
        col = {220, 40, 40};
    }

    const int x0 = clampi(cx - 100, 0, SCREEN_W - 1);
    const int x1 = clampi(cx + 100, 0, SCREEN_W - 1);
    const int y0 = clampi(cy - 60, 0, SCREEN_H - 1);
    const int y1 = clampi(cy + 60, 0, SCREEN_H - 1);

    for (int y = y0; y <= y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x <= x1; x++) {
            const float px = static_cast<float>(x) + 0.5f;
            const float py = static_cast<float>(y) + 0.5f;

            const float d_out = sd_rounded_box(px, py, static_cast<float>(cx), static_cast<float>(cy), static_cast<float>(bw), static_cast<float>(bh), 6.0f);
            const float d_in = sd_rounded_box(px, py, static_cast<float>(cx), static_cast<float>(cy), static_cast<float>(bw - 4), static_cast<float>(bh - 4), 4.0f);
            const float d_tip = sd_rounded_box(px, py, static_cast<float>(cx + bw + 8), static_cast<float>(cy), 6.0f, 15.0f, 2.0f);
            const float d_shell = fminf(fmaxf(d_out, -d_in), d_tip);
            const float alpha_shell = 1.0f - smoothstep(-1.0f, 1.0f, d_shell);
            if (alpha_shell > 0.0f) {
                set_px_blend(buf, row + x, Rgb{200, 200, 210}, alpha_shell);
            }

            const float fill_max = (static_cast<float>(cx - bw + 4)) + (2.0f * static_cast<float>(bw - 4) * lvl);
            if (d_in < 0.0f) {
                const float wave = sinf(static_cast<float>(x) * 0.1f + elapsed * 5.0f) * 3.0f;
                if (px < fill_max + wave) {
                    const float gloss = (py - static_cast<float>(cy - bh)) / static_cast<float>(2 * bh);
                    int r = static_cast<int>(col.r * (0.8f + 0.4f * gloss));
                    int g = static_cast<int>(col.g * (0.8f + 0.4f * gloss));
                    int b = static_cast<int>(col.b * (0.8f + 0.4f * gloss));
                    if (((x / 20) * (y / 20) + static_cast<int>(elapsed * 2.0f)) % 13 == 0 &&
                        noise01(x, y, static_cast<int>(elapsed * 100.0f)) < 0.20f) {
                        r = 255; g = 255; b = 255;
                    }
                    set_px_blend(buf, row + x, Rgb{r, g, b}, 1.0f);
                }
            }

            if (lvl < 0.2f && ((static_cast<int>(elapsed * 4.0f) % 2) == 0)) {
                if (fabsf(px - static_cast<float>(cx)) < 10.0f &&
                    fabsf(py - static_cast<float>(cy)) < 20.0f &&
                    fabsf((px - static_cast<float>(cx)) + (py - static_cast<float>(cy)) * 0.4f) < 4.0f) {
                    set_px_blend(buf, row + x, Rgb{255, 255, 255}, 1.0f);
                }
            }
        }
    }
}

static void render_updating(lv_color_t* buf, float elapsed)
{
    fill_screen(buf, BG);
    const int cx = SCREEN_W / 2;
    const int cy = SCREEN_H / 2;
    const int x0 = clampi(cx - 60, 0, SCREEN_W - 1);
    const int x1 = clampi(cx + 60, 0, SCREEN_W - 1);
    const int y0 = clampi(cy - 60, 0, SCREEN_H - 1);
    const int y1 = clampi(cy + 60, 0, SCREEN_H - 1);

    for (int y = y0; y <= y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x <= x1; x++) {
            const float dx = static_cast<float>(x - cx);
            const float dy = static_cast<float>(y - cy);
            const float dist = sqrtf(dx * dx + dy * dy);
            const float angle = atan2f(dy, dx);

            const float a1 = fmodf(angle + elapsed * 2.0f + 2.0f * PI, 2.0f * PI);
            if (fabsf(dist - 50.0f) < 3.0f && a1 > 0.0f && a1 < 4.0f) {
                set_px_blend(buf, row + x, Rgb{0, 255, 100}, 1.0f);
            }

            const float a2 = fmodf(angle - elapsed * 5.0f + 1.5f * 100.0f, 1.5f);
            if (fabsf(dist - 35.0f) < 4.0f && a2 < 1.0f) {
                set_px_blend(buf, row + x, Rgb{0, 200, 255}, 1.0f);
            }

            const float pulse_r = 8.0f + sinf(elapsed * 10.0f) * 2.0f;
            const float alpha_dot = 1.0f - smoothstep(-1.0f, 1.0f, sd_circle(static_cast<float>(x) + 0.5f, static_cast<float>(y) + 0.5f, static_cast<float>(cx), static_cast<float>(cy), pulse_r));
            if (alpha_dot > 0.0f) {
                set_px_blend(buf, row + x, Rgb{255, 255, 255}, alpha_dot);
            }
        }
    }
}

static void render_shutdown(lv_color_t* buf, float elapsed)
{
    fill_screen(buf, Rgb{0, 0, 0});
    float vs = 0.0f;
    float hs = 0.0f;
    float br = 0.0f;
    if (elapsed < 0.4f) {
        vs = 1.0f - (elapsed / 0.4f);
        hs = 1.0f;
        br = 1.0f + elapsed;
    } else if (elapsed < 0.6f) {
        vs = 0.005f;
        hs = 1.0f - ((elapsed - 0.4f) / 0.2f);
        br = 2.0f;
    } else if (elapsed < 0.8f) {
        vs = 0.002f;
        hs = 0.002f;
        br = 1.0f - ((elapsed - 0.6f) / 0.2f);
    } else {
        return;
    }

    const int cx = SCREEN_W / 2;
    const int cy = SCREEN_H / 2;
    int bw = static_cast<int>(SCREEN_W * hs);
    int bh = static_cast<int>(SCREEN_H * vs);
    if (bw < 1) bw = 1;
    if (bh < 1) bh = 1;
    const int r = static_cast<int>(255.0f * fminf(1.0f, br));
    const int g = static_cast<int>(255.0f * fminf(1.0f, br));
    const Rgb col{r, g, 255};

    const int x0 = clampi(cx - bw / 2, 0, SCREEN_W - 1);
    const int x1 = clampi(cx + bw / 2, 0, SCREEN_W - 1);
    const int y0 = clampi(cy - bh / 2, 0, SCREEN_H - 1);
    const int y1 = clampi(cy + bh / 2, 0, SCREEN_H - 1);
    const lv_color_t pixel = rgb_to_color(col);
    for (int y = y0; y <= y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x <= x1; x++) {
            buf[row + x] = pixel;
        }
    }
}

static void apply_scanlines(lv_color_t* buf)
{
    if (!SYSTEM_FX_SCANLINES) {
        return;
    }
    for (int y = 0; y < SCREEN_H; y += 2) {
        const int row = y * SCREEN_W;
        for (int x = 0; x < SCREEN_W; x++) {
            lv_color_t px = buf[row + x];
            px.red = static_cast<uint8_t>((static_cast<uint16_t>(px.red) * 4U) / 5U);
            px.green = static_cast<uint8_t>((static_cast<uint16_t>(px.green) * 4U) / 5U);
            px.blue = static_cast<uint8_t>((static_cast<uint16_t>(px.blue) * 4U) / 5U);
            buf[row + x] = px;
        }
    }
}

static void apply_vignette(lv_color_t* buf)
{
    if (!SYSTEM_FX_VIGNETTE) {
        return;
    }
    const float cx = static_cast<float>(SCREEN_W) * 0.5f;
    const float cy = static_cast<float>(SCREEN_H) * 0.5f;
    const float max_dist = sqrtf(cx * cx + cy * cy);
    for (int y = 0; y < SCREEN_H; y++) {
        const int row = y * SCREEN_W;
        for (int x = 0; x < SCREEN_W; x++) {
            const float dx = static_cast<float>(x) - cx;
            const float dy = static_cast<float>(y) - cy;
            const float dist = sqrtf(dx * dx + dy * dy);
            const float v = 1.0f - smoothstep(max_dist * 0.5f, max_dist, dist);
            lv_color_t px = buf[row + x];
            px.red = static_cast<uint8_t>(clampi(static_cast<int>(px.red * v), 0, 255));
            px.green = static_cast<uint8_t>(clampi(static_cast<int>(px.green * v), 0, 255));
            px.blue = static_cast<uint8_t>(clampi(static_cast<int>(px.blue * v), 0, 255));
            buf[row + x] = px;
        }
    }
}

}  // namespace

void render_system_overlay_v2(lv_color_t* buf, const FaceState& fs, float now_seconds)
{
    if (!buf || fs.system.mode == SystemMode::NONE) {
        return;
    }
    const float elapsed = fmaxf(0.0f, now_seconds - fs.system.timer);
    switch (fs.system.mode) {
    case SystemMode::BOOTING:
        render_booting(buf, elapsed);
        break;
    case SystemMode::ERROR_DISPLAY:
        render_error(buf, elapsed);
        break;
    case SystemMode::LOW_BATTERY:
        render_battery(buf, fs, elapsed);
        break;
    case SystemMode::UPDATING:
        render_updating(buf, elapsed);
        break;
    case SystemMode::SHUTTING_DOWN:
        render_shutdown(buf, elapsed);
        break;
    case SystemMode::NONE:
        break;
    }
    apply_scanlines(buf);
    apply_vignette(buf);
}
