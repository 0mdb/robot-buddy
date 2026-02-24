// System face animations — ported from tools/face_sim_v3/render/face.py.
// Each system mode drives Buddy's face features (eyes, mouth, eyelids, color)
// instead of abstract full-screen overlays, making system states feel "alive."

#include "system_face.h"

#include "config.h"

#include <cmath>
#include <cstdint>

namespace
{

constexpr float PI = 3.14159265358979323846f;

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static void set_color(FaceState& fs, int r, int g, int b)
{
    fs.color_override_active = true;
    fs.color_override_r = static_cast<uint8_t>(clampf(static_cast<float>(r), 0.0f, 255.0f));
    fs.color_override_g = static_cast<uint8_t>(clampf(static_cast<float>(g), 0.0f, 255.0f));
    fs.color_override_b = static_cast<uint8_t>(clampf(static_cast<float>(b), 0.0f, 255.0f));
}

// ══════════════════════════════════════════════════════════════════════
// BOOTING — "Waking up": eyes open from sleepy slits, yawn, settle
// ══════════════════════════════════════════════════════════════════════

static void sys_booting(FaceState& fs, float elapsed)
{
    constexpr float BOOT_DUR = 3.0f;
    const float     t = clampf(elapsed / BOOT_DUR, 0.0f, 1.0f);

    if (t < 0.4f) {
        // Phase 1: Sleepy slits slowly opening
        const float p = t / 0.4f;
        const float droop = 0.6f * (1.0f - p);
        fs.eyelids.top_l = droop;
        fs.eyelids.top_r = droop;
        fs.eye_l.height_scale = 0.7f + 0.15f * p;
        fs.eye_r.height_scale = 0.7f + 0.15f * p;
        fs.eyelids.slope = -0.2f * (1.0f - p);
        // Color: navy → transitioning
        set_color(fs, static_cast<int>(70 + (50 - 70) * p), static_cast<int>(90 + (150 - 90) * p),
                  static_cast<int>(140 + (255 - 140) * p));
    } else if (t < 0.65f) {
        // Phase 2: Yawn — mouth opens wide, eyes squeeze slightly
        const float p = (t - 0.4f) / 0.25f;
        const float yawn = sinf(p * PI);
        fs.mouth_open = 0.6f * yawn;
        fs.mouth_width = 1.0f + 0.2f * yawn;
        fs.mouth_curve = -0.1f * yawn;
        fs.eyelids.top_l = 0.15f * yawn;
        fs.eyelids.top_r = 0.15f * yawn;
        fs.eye_l.height_scale = 0.85f - 0.1f * yawn;
        fs.eye_r.height_scale = 0.85f - 0.1f * yawn;
        set_color(fs, 50, 150, 255);
    } else if (t < 0.85f) {
        // Phase 3: Eyes open fully, quick blink at 75%
        const float p = (t - 0.65f) / 0.2f;
        const float blink_p = fabsf(p - 0.5f) * 2.0f;
        fs.eyelids.top_l = (p > 0.4f && p < 0.6f) ? 0.7f * (1.0f - blink_p) : 0.0f;
        fs.eyelids.top_r = fs.eyelids.top_l;
        fs.eye_l.height_scale = 1.0f;
        fs.eye_r.height_scale = 1.0f;
        set_color(fs, 50, 150, 255);
    } else {
        // Phase 4: Happy bounce settle
        const float p = (t - 0.85f) / 0.15f;
        const float bounce = sinf(p * PI) * 0.05f;
        fs.eye_l.height_scale = 1.0f + bounce;
        fs.eye_r.height_scale = 1.0f + bounce;
        fs.mouth_curve = 0.3f * sinf(p * PI);
        set_color(fs, static_cast<int>(50 + (0 - 50) * p), static_cast<int>(150 + (255 - 150) * p),
                  static_cast<int>(255 + (200 - 255) * p));
    }

    // Breathing ramps in over last 30%
    fs.fx.breathing = t > 0.7f;
}

// ══════════════════════════════════════════════════════════════════════
// ERROR — "Confused Buddy": worried expression + slow headshake
// ══════════════════════════════════════════════════════════════════════

static void sys_error(FaceState& fs, float elapsed)
{
    // Confused expression: asymmetric mouth, inner brow furrow
    fs.eyelids.slope = 0.2f;
    fs.eyelids.top_l = 0.1f;
    fs.eyelids.top_r = 0.1f;
    fs.mouth_curve = -0.2f;
    fs.mouth_offset_x = 2.0f * sinf(elapsed * 3.0f);

    // Slow headshake
    const float shake = sinf(elapsed * 4.0f) * 3.0f;
    fs.eye_l.gaze_x = shake;
    fs.eye_r.gaze_x = shake;

    // Warm orange/amber color
    set_color(fs, 220, 160, 60);
    fs.expression_intensity = 0.7f;
}

// ══════════════════════════════════════════════════════════════════════
// LOW_BATTERY — "Sleepy Buddy": heavy eyelids, slow blinks, drowsy
// ══════════════════════════════════════════════════════════════════════

static void sys_battery(FaceState& fs, float elapsed)
{
    const float lvl = clampf(fs.system.param, 0.0f, 1.0f);

    // Sleepy expression — more droop at lower battery
    const float droop = 0.4f + 0.2f * (1.0f - lvl);
    fs.eyelids.top_l = droop;
    fs.eyelids.top_r = droop;
    fs.eyelids.slope = -0.2f;
    fs.eye_l.height_scale = 0.75f;
    fs.eye_r.height_scale = 0.75f;

    // Periodic yawns at very low battery
    if (lvl < 0.2f) {
        const float yawn_cycle = fmodf(elapsed, 6.0f);
        if (yawn_cycle < 1.5f) {
            const float yawn = sinf(yawn_cycle / 1.5f * PI);
            fs.mouth_open = 0.5f * yawn;
            fs.mouth_width = 1.0f + 0.1f * yawn;
            fs.eyelids.top_l = fminf(0.8f, droop + 0.2f * yawn);
            fs.eyelids.top_r = fminf(0.8f, droop + 0.2f * yawn);
        }
    }

    // Slow breathing
    fs.fx.breathing = true;

    // Navy/deep blue color, dimmer at lower battery
    const float dim = 0.6f + 0.4f * lvl;
    set_color(fs, static_cast<int>(70.0f * dim), static_cast<int>(90.0f * dim), static_cast<int>(140.0f * dim));
    fs.brightness = 0.7f + 0.3f * lvl;
}

// ══════════════════════════════════════════════════════════════════════
// UPDATING — "Thinking hard": gaze drifts up-right, brow furrow
// ══════════════════════════════════════════════════════════════════════

static void sys_updating(FaceState& fs, float elapsed)
{
    // Thinking expression
    fs.eyelids.slope = 0.4f;
    fs.eyelids.top_l = 0.2f;
    fs.eyelids.top_r = 0.2f;
    fs.mouth_curve = -0.1f;
    fs.mouth_offset_x = 1.5f;

    // Gaze drifts up-right with slow wander
    constexpr float base_gx = 6.0f;
    constexpr float base_gy = -4.0f;
    const float     drift_x = sinf(elapsed * 0.8f) * 2.0f;
    const float     drift_y = cosf(elapsed * 0.6f) * 1.5f;
    fs.eye_l.gaze_x = base_gx + drift_x;
    fs.eye_r.gaze_x = base_gx + drift_x;
    fs.eye_l.gaze_y = base_gy + drift_y;
    fs.eye_r.gaze_y = base_gy + drift_y;

    // Blue-violet color
    set_color(fs, 80, 135, 220);
    fs.expression_intensity = 0.6f;
}

// ══════════════════════════════════════════════════════════════════════
// SHUTTING_DOWN — "Going to sleep": yawn, droop, close eyes, fade
// ══════════════════════════════════════════════════════════════════════

static void sys_shutdown(FaceState& fs, float elapsed)
{
    constexpr float SHUT_DUR = 2.5f;
    const float     t = clampf(elapsed / SHUT_DUR, 0.0f, 1.0f);

    if (t < 0.3f) {
        // Phase 1: Yawn
        const float p = t / 0.3f;
        const float yawn = sinf(p * PI);
        fs.mouth_open = 0.5f * yawn;
        fs.mouth_width = 1.0f + 0.15f * yawn;
        fs.eyelids.top_l = 0.1f * yawn;
        fs.eyelids.top_r = 0.1f * yawn;
        fs.eye_l.height_scale = 1.0f - 0.1f * yawn;
        fs.eye_r.height_scale = 1.0f - 0.1f * yawn;
    } else if (t < 0.6f) {
        // Phase 2: Eyes droop, gaze sways, color darkens
        const float p = (t - 0.3f) / 0.3f;
        const float droop = 0.15f + 0.35f * p;
        fs.eyelids.top_l = droop;
        fs.eyelids.top_r = droop;
        fs.eye_l.height_scale = 0.9f - 0.15f * p;
        fs.eye_r.height_scale = 0.9f - 0.15f * p;
        fs.eyelids.slope = -0.2f * p;
        // Gentle side-to-side sway, slowing down
        const float sway_amp = 3.0f * (1.0f - p);
        const float sway = sinf(elapsed * 2.0f) * sway_amp;
        fs.eye_l.gaze_x = sway;
        fs.eye_r.gaze_x = sway;
    } else if (t < 0.85f) {
        // Phase 3: Eyes close with small smile
        const float p = (t - 0.6f) / 0.25f;
        fs.eyelids.top_l = 0.5f + 0.5f * p;
        fs.eyelids.top_r = 0.5f + 0.5f * p;
        fs.eye_l.height_scale = 0.75f - 0.35f * p;
        fs.eye_r.height_scale = 0.75f - 0.35f * p;
        fs.eyelids.slope = -0.2f;
        // Content smile as eyes close
        fs.mouth_curve = 0.3f * p;
    } else {
        // Phase 4: Fully closed, fade brightness
        const float p = (t - 0.85f) / 0.15f;
        fs.eyelids.top_l = 1.0f;
        fs.eyelids.top_r = 1.0f;
        fs.eye_l.height_scale = 0.4f;
        fs.eye_r.height_scale = 0.4f;
        fs.mouth_curve = 0.3f;
        fs.brightness = 1.0f - p;
    }

    // Color fades from cyan to navy to black
    if (t < 0.6f) {
        const float frac = t / 0.6f;
        set_color(fs, static_cast<int>(50 * (1.0f - frac) + 70 * frac),
                  static_cast<int>(150 * (1.0f - frac) + 90 * frac),
                  static_cast<int>(255 * (1.0f - frac) + 140 * frac));
    } else {
        const float frac = (t - 0.6f) / 0.4f;
        set_color(fs, static_cast<int>(70 * (1.0f - frac)), static_cast<int>(90 * (1.0f - frac)),
                  static_cast<int>(140 * (1.0f - frac)));
    }

    fs.fx.breathing = t < 0.5f;
}

// ══════════════════════════════════════════════════════════════════════
// Icon rendering helpers (SDF-based, same math as sim)
// ══════════════════════════════════════════════════════════════════════

static float sd_circle(float px, float py, float cx, float cy, float r)
{
    const float dx = px - cx, dy = py - cy;
    return sqrtf(dx * dx + dy * dy) - r;
}

static float sd_rounded_box(float px, float py, float cx, float cy, float hw, float hh, float r)
{
    const float dx = fabsf(px - cx) - hw + r;
    const float dy = fabsf(py - cy) - hh + r;
    const float mx = fmaxf(dx, 0.0f);
    const float my = fmaxf(dy, 0.0f);
    return fminf(fmaxf(dx, dy), 0.0f) + sqrtf(mx * mx + my * my) - r;
}

static float sd_equilateral_triangle(float px, float py, float cx, float cy, float r)
{
    // Centered equilateral triangle, point-up
    const float     x = fabsf(px - cx);
    const float     y = py - cy;
    constexpr float k = 1.73205f; // sqrt(3)
    float           bx = x - fminf(x, r * 0.5f);
    if (bx < 0.0f) bx = 0.0f;
    float by = y + r * 0.5f;
    float ax = x;
    float ay = y;
    // rotate into triangle space
    ax = ax - r * 0.5f;
    ay = ay + r * k * 0.5f;
    ax = fmaxf(ax, 0.0f);
    // simplified SDF
    float d = fmaxf(-(px - cx) * 0.5f - (py - cy) * k * 0.5f, (px - cx) * 0.5f - (py - cy) * k * 0.5f);
    d = fmaxf(d, py - cy - r * 0.25f);
    (void)bx;
    (void)by;
    (void)ax;
    (void)ay;
    return d;
}

static float smoothstep(float edge0, float edge1, float x)
{
    const float t = clampf((x - edge0) / (edge1 - edge0), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

static void blend_pixel(pixel_t* buf, int idx, int r, int g, int b, float alpha)
{
    if (alpha < 0.01f) return;
    const uint16_t c = buf[idx];
    const int      old_r = (c >> 11) << 3;
    const int      old_g = ((c >> 5) & 0x3F) << 2;
    const int      old_b = (c & 0x1F) << 3;
    const int      nr = static_cast<int>(old_r + (r - old_r) * alpha);
    const int      ng = static_cast<int>(old_g + (g - old_g) * alpha);
    const int      nb = static_cast<int>(old_b + (b - old_b) * alpha);
    buf[idx] = static_cast<pixel_t>(((nr >> 3) << 11) | ((ng >> 2) << 5) | (nb >> 3));
}

} // namespace

// ══════════════════════════════════════════════════════════════════════
// Public API
// ══════════════════════════════════════════════════════════════════════

void system_face_apply(FaceState& fs, float now_s)
{
    const float elapsed = now_s - fs.system.timer;

    // Reset per-frame overrides
    fs.color_override_active = false;

    switch (fs.system.mode) {
    case SystemMode::BOOTING:
        sys_booting(fs, elapsed);
        break;
    case SystemMode::ERROR_DISPLAY:
        sys_error(fs, elapsed);
        break;
    case SystemMode::LOW_BATTERY:
        sys_battery(fs, elapsed);
        break;
    case SystemMode::UPDATING:
        sys_updating(fs, elapsed);
        break;
    case SystemMode::SHUTTING_DOWN:
        sys_shutdown(fs, elapsed);
        break;
    default:
        break;
    }
}

void system_face_render_error_icon(pixel_t* buf)
{
    // Tiny warning icon in lower-right corner (triangle + exclamation)
    constexpr int   icon_cx = SCREEN_W - 22;
    constexpr int   icon_cy = SCREEN_H - 22;
    constexpr float icon_r = 10.0f;

    constexpr int x0 = icon_cx - 14 > 0 ? icon_cx - 14 : 0;
    constexpr int x1 = icon_cx + 14 < SCREEN_W ? icon_cx + 14 : SCREEN_W;
    constexpr int y0 = icon_cy - 14 > 0 ? icon_cy - 14 : 0;
    constexpr int y1 = icon_cy + 14 < SCREEN_H ? icon_cy + 14 : SCREEN_H;

    for (int y = y0; y < y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x < x1; x++) {
            const float px = x + 0.5f, py = y + 0.5f;

            // Triangle
            const float d_tri = sd_equilateral_triangle(px, py, icon_cx, icon_cy, icon_r);
            const float alpha = 1.0f - smoothstep(0.0f, 1.5f, d_tri);
            blend_pixel(buf, row + x, 255, 180, 50, alpha);

            // Exclamation: bar + dot
            const float d_bar = sd_rounded_box(px, py, icon_cx, icon_cy - 2, 1.5f, 4.0f, 0.5f);
            const float d_dot = sd_circle(px, py, icon_cx, icon_cy + 4.5f, 1.5f);
            const float d_mark = fminf(d_bar, d_dot);
            const float alpha_m = 1.0f - smoothstep(0.0f, 1.0f, d_mark);
            blend_pixel(buf, row + x, 0, 0, 0, alpha_m);
        }
    }
}

void system_face_render_battery_icon(pixel_t* buf, float level)
{
    // Tiny battery icon in lower-right corner
    constexpr int   bx = SCREEN_W - 24;
    constexpr int   by = SCREEN_H - 18;
    constexpr float bw = 16.0f, bh = 10.0f;
    const float     lvl = clampf(level, 0.0f, 1.0f);

    int cr, cg, cb;
    if (lvl > 0.5f) {
        cr = 0;
        cg = 220;
        cb = 100;
    } else if (lvl > 0.2f) {
        cr = 220;
        cg = 180;
        cb = 0;
    } else {
        cr = 220;
        cg = 40;
        cb = 40;
    }

    constexpr int x0 = bx - 12 > 0 ? bx - 12 : 0;
    constexpr int x1 = bx + 18 < SCREEN_W ? bx + 18 : SCREEN_W;
    constexpr int y0 = by - 8 > 0 ? by - 8 : 0;
    constexpr int y1 = by + 8 < SCREEN_H ? by + 8 : SCREEN_H;

    for (int y = y0; y < y1; y++) {
        const int row = y * SCREEN_W;
        for (int x = x0; x < x1; x++) {
            const float px = x + 0.5f, py = y + 0.5f;

            // Battery shell (outline)
            const float d_out = sd_rounded_box(px, py, bx, by, bw / 2, bh / 2, 1.5f);
            const float d_in = sd_rounded_box(px, py, bx, by, bw / 2 - 1.5f, bh / 2 - 1.5f, 0.5f);
            const float d_tip = sd_rounded_box(px, py, bx + bw / 2 + 2, by, 1.5f, 3.0f, 0.5f);
            const float d_shell = fminf(fmaxf(d_out, -d_in), d_tip);
            const float alpha_s = 1.0f - smoothstep(0.0f, 1.0f, d_shell);
            blend_pixel(buf, row + x, 180, 180, 190, alpha_s);

            // Fill level
            const float fill_right = (bx - bw / 2 + 1.5f) + (bw - 3.0f) * lvl;
            if (d_in < 0 && px < fill_right) {
                blend_pixel(buf, row + x, cr, cg, cb, 0.9f);
            }
        }
    }
}

void system_face_render_updating_bar(pixel_t* buf, float progress)
{
    // Thin progress bar at bottom of screen
    constexpr int bar_y = SCREEN_H - 4;
    constexpr int bar_h = 2;
    constexpr int bar_x0 = 20;
    constexpr int bar_x1 = SCREEN_W - 20;
    const int     fill_x = bar_x0 + static_cast<int>((bar_x1 - bar_x0) * clampf(progress, 0.0f, 1.0f));

    for (int y = bar_y; y < bar_y + bar_h && y < SCREEN_H; y++) {
        const int row = y * SCREEN_W;
        for (int x = bar_x0; x < bar_x1; x++) {
            if (x < fill_x) {
                blend_pixel(buf, row + x, 80, 135, 220, 0.8f);
            } else {
                blend_pixel(buf, row + x, 30, 40, 60, 0.8f);
            }
        }
    }
}
