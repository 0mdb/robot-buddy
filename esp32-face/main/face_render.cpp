#include "face_render.h"
#include "config.h"
#include "face_state.h"

#include "esp_timer.h"
#include <cmath>
#include <cstring>
#include <algorithm>

// ── Colour palette ──────────────────────────────────────────────────

static constexpr uint8_t EYE_COLOR[3]   = {255, 255, 255};
static constexpr uint8_t PUPIL_COLOR[3] = {30, 100, 220};

// ── Geometry helpers ────────────────────────────────────────────────

static bool in_rounded_rect(float px, float py,
                            float cx, float cy,
                            float hw, float hh,
                            float r)
{
    if (hw <= 0.0f || hh <= 0.0f) return false;
    r = std::min(r, std::min(hw, hh));
    float dx = std::fabs(px - cx);
    float dy = std::fabs(py - cy);
    if (dx > hw || dy > hh) return false;
    if (dx <= hw - r || dy <= hh - r) return true;
    float cdx = dx - (hw - r);
    float cdy = dy - (hh - r);
    return (cdx * cdx + cdy * cdy) <= r * r;
}

static bool in_circle(float px, float py, float cx, float cy, float r)
{
    float dx = px - cx;
    float dy = py - cy;
    return (dx * dx + dy * dy) <= r * r;
}

static float dist_to_edge(float px, float py,
                           float cx, float cy,
                           float hw, float hh)
{
    float dx = hw - std::fabs(px - cx);
    float dy = hh - std::fabs(py - cy);
    return std::max(0.0f, std::min(dx, dy));
}

// ── Special shape helpers ───────────────────────────────────────────

static bool in_heart(float px, float py, float cx, float cy, float size)
{
    float x = (px - cx) / size;
    float y = (cy - py) / size + 0.3f;
    float x2 = x * x;
    float y2 = y * y;
    float t = x2 + y2 - 1.0f;
    return (t * t * t) - x2 * (y * y2) <= 0.0f;
}

static bool in_x_shape(float px, float py, float cx, float cy,
                        float size, float thickness = 0.8f)
{
    float dx = std::fabs(px - cx);
    float dy = std::fabs(py - cy);
    if (dx > size || dy > size) return false;
    return std::fabs(dx - dy) < thickness;
}

// ── Eyelid mask helpers ─────────────────────────────────────────────

static bool tired_mask(float px, float py, float cx, float top_y,
                       float hw, float amount)
{
    if (amount < 0.01f) return false;
    float max_droop = 2.6f * amount;
    float dist = std::fabs(px - cx);
    float droop = max_droop * (dist / std::max(hw, 0.01f));
    return py < top_y + droop;
}

static bool angry_mask_left(float px, float py, float cx, float top_y,
                             float hw, float amount)
{
    if (amount < 0.01f) return false;
    float max_droop = 2.6f * amount;
    float t = (px - (cx - hw)) / std::max(2.0f * hw, 0.01f);
    float droop = max_droop * t;
    return py < top_y + droop;
}

static bool angry_mask_right(float px, float py, float cx, float top_y,
                              float hw, float amount)
{
    if (amount < 0.01f) return false;
    float max_droop = 2.6f * amount;
    float t = (px - (cx - hw)) / std::max(2.0f * hw, 0.01f);
    float droop = max_droop * (1.0f - t);
    return py < top_y + droop;
}

static bool happy_mask(float py, float bottom_y, float amount)
{
    if (amount < 0.01f) return false;
    float cutoff = bottom_y - 2.2f * amount;
    return py > cutoff;
}

// ── Pixel helpers ───────────────────────────────────────────────────

static inline void set_pixel(PixelGrid grid, int x, int y,
                              uint8_t r, uint8_t g, uint8_t b)
{
    grid[y][x][0] = r;
    grid[y][x][1] = g;
    grid[y][x][2] = b;
}

static inline void set_pixel_scaled(PixelGrid grid, int x, int y,
                                     float r, float g, float b, float br)
{
    grid[y][x][0] = static_cast<uint8_t>(std::min(255.0f, r * br));
    grid[y][x][1] = static_cast<uint8_t>(std::min(255.0f, g * br));
    grid[y][x][2] = static_cast<uint8_t>(std::min(255.0f, b * br));
}

static inline void add_pixel(PixelGrid grid, int x, int y,
                              int r, int g, int b)
{
    grid[y][x][0] = static_cast<uint8_t>(std::min(255, grid[y][x][0] + r));
    grid[y][x][1] = static_cast<uint8_t>(std::min(255, grid[y][x][1] + g));
    grid[y][x][2] = static_cast<uint8_t>(std::min(255, grid[y][x][2] + b));
}

static inline bool is_black(const PixelGrid grid, int x, int y)
{
    return grid[y][x][0] == 0 && grid[y][x][1] == 0 && grid[y][x][2] == 0;
}

// ── Single-eye renderer ─────────────────────────────────────────────

static void render_eye(PixelGrid grid, const FaceState& fs, bool is_left)
{
    const EyeState& eye = is_left ? fs.eye_l : fs.eye_r;
    float base_cx = is_left ? LEFT_EYE_CX : RIGHT_EYE_CX;
    float base_cy = is_left ? LEFT_EYE_CY : RIGHT_EYE_CY;

    uint8_t cr, cg, cb;
    face_get_emotion_color(fs, cr, cg, cb);
    float solid_r = cr, solid_g = cg, solid_b = cb;

    float breath = face_get_breath_scale(fs);
    float open_frac = std::max(0.0f, std::min(1.0f, eye.openness));

    float w_scale = eye.width_scale * breath;
    float h_scale = eye.height_scale * breath;

    float half_w = (EYE_WIDTH / 2.0f) * w_scale;
    float half_h = (EYE_HEIGHT / 2.0f) * open_frac * h_scale;
    float corner_r = EYE_CORNER_R * std::min(1.0f, open_frac * 2.0f);

    float cx = base_cx + eye.gaze_x * GAZE_EYE_SHIFT;
    float cy = base_cy + eye.gaze_y * GAZE_EYE_SHIFT;
    float pupil_cx = base_cx + eye.gaze_x * GAZE_PUPIL_SHIFT;
    float pupil_cy = base_cy + eye.gaze_y * GAZE_PUPIL_SHIFT;

    float top_y = cy - half_h;
    float bottom_y = cy + half_h;
    float br = std::max(0.0f, std::min(1.0f, fs.brightness));

    bool do_edge_glow = fs.fx.edge_glow;
    float edge_falloff = fs.fx.edge_glow_falloff;

    // Heart eyes override
    if (fs.anim.heart) {
        float heart_size = 2.2f * breath;
        for (int y = 0; y < GRID_H; y++) {
            for (int x = 0; x < GRID_W; x++) {
                float px = x + 0.5f;
                float py = y + 0.5f;
                if (in_heart(px, py, base_cx, base_cy, heart_size)) {
                    set_pixel_scaled(grid, x, y, solid_r, solid_g, solid_b, br);
                }
            }
        }
        return;
    }

    // X eyes override
    if (fs.anim.x_eyes) {
        for (int y = 0; y < GRID_H; y++) {
            for (int x = 0; x < GRID_W; x++) {
                float px = x + 0.5f;
                float py = y + 0.5f;
                if (in_x_shape(px, py, base_cx, base_cy, 2.8f)) {
                    set_pixel_scaled(grid, x, y, solid_r, solid_g, solid_b, br);
                }
            }
        }
        return;
    }

    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            float px = x + 0.5f;
            float py = y + 0.5f;

            if (!in_rounded_rect(px, py, cx, cy, half_w, half_h, corner_r))
                continue;

            // Eyelid masks
            if (is_left) {
                if (angry_mask_left(px, py, cx, top_y, half_w, fs.eyelids.angry))
                    continue;
            } else {
                if (angry_mask_right(px, py, cx, top_y, half_w, fs.eyelids.angry))
                    continue;
            }
            if (tired_mask(px, py, cx, top_y, half_w, fs.eyelids.tired))
                continue;
            if (happy_mask(py, bottom_y, fs.eyelids.happy))
                continue;

            float pr, pg, pb;
            if (fs.solid_eye) {
                pr = solid_r; pg = solid_g; pb = solid_b;
            } else if (in_circle(px, py, pupil_cx, pupil_cy, PUPIL_R)) {
                pr = PUPIL_COLOR[0]; pg = PUPIL_COLOR[1]; pb = PUPIL_COLOR[2];
            } else {
                pr = EYE_COLOR[0]; pg = EYE_COLOR[1]; pb = EYE_COLOR[2];
            }

            // Edge glow: dim pixels near the edges
            if (do_edge_glow) {
                float dist = dist_to_edge(px, py, cx, cy, half_w, half_h);
                float max_dist = std::min(half_w, half_h);
                if (max_dist > 0.0f) {
                    float glow = 1.0f - edge_falloff * (1.0f - std::min(dist / max_dist, 1.0f));
                    pr *= glow;
                    pg *= glow;
                    pb *= glow;
                }
            }

            set_pixel_scaled(grid, x, y, pr, pg, pb, br);
        }
    }
}

// ── Sparkle overlay ─────────────────────────────────────────────────

static void apply_sparkle(PixelGrid grid, const FaceState& fs)
{
    if (!fs.fx.sparkle) return;
    for (int i = 0; i < fs.fx.sparkle_count; i++) {
        const SparklePixel& sp = fs.fx.sparkle_pixels[i];
        if (sp.x < 0 || sp.x >= GRID_W || sp.y < 0 || sp.y >= GRID_H)
            continue;
        if (is_black(grid, sp.x, sp.y))
            continue;
        float intensity = std::min(1.0f, sp.life / 6.0f);
        int boost = static_cast<int>(80.0f * intensity);
        add_pixel(grid, sp.x, sp.y, boost, boost, boost);
    }
}

// ── Fire particles ──────────────────────────────────────────────────

static void apply_fire(PixelGrid grid, const FaceState& fs)
{
    if (!fs.anim.rage) return;
    for (int i = 0; i < fs.fx.fire_count; i++) {
        const FirePixel& fp = fs.fx.fire_pixels[i];
        int ix = static_cast<int>(fp.x);
        int iy = static_cast<int>(fp.y);
        if (ix < 0 || ix >= GRID_W || iy < 0 || iy >= GRID_H)
            continue;

        int fr, fg, fb;
        if (fp.heat > 0.85f) {
            fr = 255; fg = 220; fb = 120;
        } else if (fp.heat > 0.65f) {
            fr = 255; fg = 140; fb = 20;
        } else if (fp.heat > 0.4f) {
            fr = 220; fg = 50; fb = 0;
        } else {
            fr = 130; fg = 20; fb = 0;
        }

        float fade = std::min(1.0f, fp.life / 5.0f);
        // Max-blend with existing pixel
        grid[iy][ix][0] = static_cast<uint8_t>(std::min(255, std::max((int)grid[iy][ix][0], (int)(fr * fade))));
        grid[iy][ix][1] = static_cast<uint8_t>(std::min(255, std::max((int)grid[iy][ix][1], (int)(fg * fade))));
        grid[iy][ix][2] = static_cast<uint8_t>(std::min(255, std::max((int)grid[iy][ix][2], (int)(fb * fade))));
    }
}

// ── Afterglow ───────────────────────────────────────────────────────

static void apply_afterglow(PixelGrid grid, const FaceState& fs)
{
    if (!fs.fx.afterglow || !fs.fx.afterglow_valid) return;
    constexpr float decay = 0.4f;
    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            if (is_black(grid, x, y)) {
                uint8_t pr = fs.fx.afterglow_buf[y][x][0];
                uint8_t pg = fs.fx.afterglow_buf[y][x][1];
                uint8_t pb = fs.fx.afterglow_buf[y][x][2];
                if (pr > 0 || pg > 0 || pb > 0) {
                    grid[y][x][0] = static_cast<uint8_t>(pr * decay);
                    grid[y][x][1] = static_cast<uint8_t>(pg * decay);
                    grid[y][x][2] = static_cast<uint8_t>(pb * decay);
                }
            }
        }
    }
}

// Store current frame into afterglow buffer (call after all rendering).
// This mutates fs.fx, so we take a non-const ref via a helper.
static void store_afterglow(PixelGrid grid, EffectsState& fx)
{
    if (!fx.afterglow) return;
    std::memcpy(fx.afterglow_buf, grid, sizeof(fx.afterglow_buf));
    fx.afterglow_valid = true;
}

// ── Mouth renderer ──────────────────────────────────────────────────

static void render_mouth(PixelGrid grid, const FaceState& fs)
{
    if (!fs.show_mouth) return;

    float curve    = fs.mouth_curve;
    float openness = fs.mouth_open;
    float wave     = fs.mouth_wave;
    float offset_x = fs.mouth_offset_x;
    float width_sc = fs.mouth_width;
    float br       = std::max(0.0f, std::min(1.0f, fs.brightness));

    uint8_t mr, mg, mb;
    face_get_emotion_color(fs, mr, mg, mb);
    float col_r = mr, col_g = mg, col_b = mb;

    float cx = MOUTH_CX + offset_x;
    float half_w = MOUTH_HALF_W * width_sc;
    float bend = -curve * 2.5f;

    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            float px = x + 0.5f;
            float py = y + 0.5f;

            float dx = px - cx;
            if (std::fabs(dx) > half_w + 0.5f) continue;

            float t = dx / std::max(half_w, 0.1f);
            float curve_y = MOUTH_CY + bend * t * t;

            if (wave > 0.01f) {
                curve_y += wave * 1.2f * std::sin(t * static_cast<float>(M_PI) * 4.0f);
            }

            float dist_to_curve = py - curve_y;

            // Mouth line
            if (std::fabs(dx) <= half_w && std::fabs(dist_to_curve) < MOUTH_THICKNESS) {
                float edge_fade = 1.0f - std::max(0.0f, std::fabs(dx) - half_w + 1.0f);
                edge_fade = std::max(0.0f, std::min(1.0f, edge_fade));
                set_pixel_scaled(grid, x, y,
                                 col_r * edge_fade, col_g * edge_fade, col_b * edge_fade, br);
            }
            // Open mouth fill
            else if (openness > 0.05f && std::fabs(dx) <= half_w) {
                float fill_depth = openness * 3.0f;
                if (dist_to_curve > 0.0f && dist_to_curve < fill_depth) {
                    float fade = 1.0f - dist_to_curve / fill_depth;
                    set_pixel_scaled(grid, x, y,
                                     col_r * 0.3f * fade, col_g * 0.3f * fade,
                                     col_b * 0.3f * fade, br);
                }
            }
        }
    }
}

// ── System mode renderers ───────────────────────────────────────────

static constexpr float CENTER = GRID_W / 2.0f;

static float now_sec()
{
    return static_cast<float>(esp_timer_get_time()) / 1e6f;
}

static void render_system_booting(PixelGrid grid, const FaceState& fs)
{
    float elapsed = now_sec() - fs.system.timer;
    float br = std::max(0.0f, std::min(1.0f, fs.brightness));

    // Three concentric ring waves
    for (int wave = 0; wave < 3; wave++) {
        float wave_start = wave * 0.4f;
        float we = elapsed - wave_start;
        if (we < 0.0f || we > 1.5f) continue;
        float radius = (we / 1.5f) * 12.0f;
        float thickness = 1.5f;
        float alpha = std::max(0.0f, 1.0f - we / 1.5f);

        for (int y = 0; y < GRID_H; y++) {
            for (int x = 0; x < GRID_W; x++) {
                float dx = (x + 0.5f) - CENTER;
                float dy = (y + 0.5f) - CENTER;
                float dist = std::sqrt(dx * dx + dy * dy);
                if (std::fabs(dist - radius) < thickness) {
                    float intensity = alpha * (1.0f - std::fabs(dist - radius) / thickness);
                    int r = static_cast<int>(30.0f * intensity * br);
                    int g = static_cast<int>(140.0f * intensity * br);
                    int b = static_cast<int>(255.0f * intensity * br);
                    add_pixel(grid, x, y, r, g, b);
                }
            }
        }
    }

    // Flash at end
    if (elapsed > 2.4f) {
        float flash_t = std::min(1.0f, (elapsed - 2.4f) / 0.3f);
        float flash_alpha = 1.0f - flash_t;
        for (int y = 0; y < GRID_H; y++) {
            for (int x = 0; x < GRID_W; x++) {
                int r = static_cast<int>(30.0f * flash_alpha * br);
                int g = static_cast<int>(120.0f * flash_alpha * br);
                int b = static_cast<int>(255.0f * flash_alpha * br);
                add_pixel(grid, x, y, r, g, b);
            }
        }
    }
}

static void render_system_error(PixelGrid grid, const FaceState& fs)
{
    float elapsed = now_sec() - fs.system.timer;
    float br = std::max(0.0f, std::min(1.0f, fs.brightness));

    // Flash on/off at ~2Hz
    if (std::sin(elapsed * 4.0f * static_cast<float>(M_PI)) <= -0.3f)
        return;

    // Triangle: barycentric test
    constexpr float ax = 8.0f, ay = 2.0f;
    constexpr float bx = 2.0f, by = 13.0f;
    constexpr float tcx = 14.0f, tcy = 13.0f;
    constexpr float denom = (by - tcy) * (ax - tcx) + (tcx - bx) * (ay - tcy);

    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            float px = x + 0.5f;
            float py = y + 0.5f;
            float u = ((by - tcy) * (px - tcx) + (tcx - bx) * (py - tcy)) / denom;
            float v = ((tcy - ay) * (px - tcx) + (ax - tcx) * (py - tcy)) / denom;
            float w = 1.0f - u - v;
            if (u >= 0.0f && v >= 0.0f && w >= 0.0f) {
                float r = 255.0f, g = 180.0f, b = 0.0f;
                // Exclamation mark
                if (px >= 7.0f && px <= 9.0f) {
                    if ((py >= 5.0f && py <= 9.0f) || (py >= 10.5f && py <= 12.0f)) {
                        r = 40.0f; g = 10.0f; b = 0.0f;
                    }
                }
                set_pixel_scaled(grid, x, y, r, g, b, br);
            }
        }
    }
}

static void render_system_low_battery(PixelGrid grid, const FaceState& fs)
{
    float elapsed = now_sec() - fs.system.timer;
    float br = std::max(0.0f, std::min(1.0f, fs.brightness));
    float level = std::max(0.0f, std::min(1.0f, fs.system.param));

    constexpr int body_l = 3, body_r = 12;
    constexpr int body_t = 4, body_b = 11;
    constexpr int tip_l = 12, tip_r = 14;
    constexpr int tip_t = 6, tip_b = 9;

    float fill_r, fill_g, fill_b;
    if (level > 0.4f) {
        fill_r = 40; fill_g = 200; fill_b = 40;
    } else if (level > 0.15f) {
        fill_r = 255; fill_g = 180; fill_b = 0;
    } else {
        fill_r = 180; fill_g = 0; fill_b = 0;
    }

    constexpr float out_r = 120, out_g = 120, out_b = 130;
    int fill_right = body_l + 1 + std::max(1, static_cast<int>(level * 8));

    bool critical = level <= 0.15f;
    bool bang_visible = critical && (std::fmod(elapsed * 2.0f, 1.0f) < 0.6f);

    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            if (y >= tip_t && y <= tip_b && x >= tip_l && x <= tip_r) {
                set_pixel_scaled(grid, x, y, out_r, out_g, out_b, br);
                continue;
            }
            if (x >= body_l && x <= body_r && y >= body_t && y <= body_b) {
                bool is_outline = (x == body_l || x == body_r ||
                                   y == body_t || y == body_b);
                if (is_outline) {
                    set_pixel_scaled(grid, x, y, out_r, out_g, out_b, br);
                } else {
                    if (bang_visible && (x == 7 || x == 8)) {
                        if ((y >= 5 && y <= 8) || y == 10) {
                            set_pixel_scaled(grid, x, y, 255, 40, 20, br);
                            continue;
                        }
                    }
                    if (x < fill_right) {
                        set_pixel_scaled(grid, x, y, fill_r, fill_g, fill_b, br);
                    }
                }
            }
        }
    }
}

static void render_system_updating(PixelGrid grid, const FaceState& fs)
{
    float elapsed = now_sec() - fs.system.timer;
    float br = std::max(0.0f, std::min(1.0f, fs.brightness));

    constexpr float radius = 5.0f;
    constexpr float thickness = 1.6f;
    constexpr float arc_len = static_cast<float>(M_PI) * 0.7f;
    float angle_offset = elapsed * 4.0f * static_cast<float>(M_PI);

    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            float dx = (x + 0.5f) - CENTER;
            float dy = (y + 0.5f) - CENTER;
            float dist = std::sqrt(dx * dx + dy * dy);
            if (std::fabs(dist - radius) > thickness) continue;

            float angle = std::atan2(dy, dx) - angle_offset;
            angle = std::fmod(angle, 2.0f * static_cast<float>(M_PI));
            if (angle < 0.0f) angle += 2.0f * static_cast<float>(M_PI);
            if (angle < arc_len) {
                float t = angle / arc_len;
                float intensity = 1.0f - t * 0.6f;
                set_pixel(grid, x, y,
                          static_cast<uint8_t>(60.0f * intensity * br),
                          static_cast<uint8_t>(160.0f * intensity * br),
                          static_cast<uint8_t>(255.0f * intensity * br));
            }
        }
    }

    // Progress dots
    int dot_count = static_cast<int>(elapsed * 1.5f) % 4;
    int center_i = static_cast<int>(CENTER);
    for (int i = 0; i < dot_count; i++) {
        int px = center_i + i - 1;
        if (px >= 0 && px < GRID_W) {
            set_pixel(grid, px, center_i,
                      static_cast<uint8_t>(100.0f * br),
                      static_cast<uint8_t>(180.0f * br),
                      static_cast<uint8_t>(255.0f * br));
        }
    }
}

static void render_system_shutdown(PixelGrid grid, const FaceState& fs)
{
    float elapsed = now_sec() - fs.system.timer;
    float br = std::max(0.0f, std::min(1.0f, fs.brightness));

    if (elapsed > 2.0f) return;

    float radius, alpha;
    if (elapsed < 1.5f) {
        float t = elapsed / 1.5f;
        radius = 8.0f * (1.0f - t * t);
        alpha = 1.0f;
    } else {
        float t = (elapsed - 1.5f) / 0.5f;
        radius = 0.8f;
        alpha = 1.0f - t;
    }

    constexpr float col_r = 30, col_g = 120, col_b = 255;

    for (int y = 0; y < GRID_H; y++) {
        for (int x = 0; x < GRID_W; x++) {
            float dx = (x + 0.5f) - CENTER;
            float dy = (y + 0.5f) - CENTER;
            float dist = std::sqrt(dx * dx + dy * dy);
            if (dist <= radius) {
                float edge = std::max(0.0f, 1.0f - std::max(0.0f, dist - radius + 1.0f));
                set_pixel(grid, x, y,
                          static_cast<uint8_t>(col_r * alpha * edge * br),
                          static_cast<uint8_t>(col_g * alpha * edge * br),
                          static_cast<uint8_t>(col_b * alpha * edge * br));
            }
        }
    }
}

static bool render_system_mode(PixelGrid grid, const FaceState& fs)
{
    switch (fs.system.mode) {
    case SystemMode::NONE:         return false;
    case SystemMode::BOOTING:      render_system_booting(grid, fs); break;
    case SystemMode::ERROR_DISPLAY: render_system_error(grid, fs); break;
    case SystemMode::LOW_BATTERY:  render_system_low_battery(grid, fs); break;
    case SystemMode::UPDATING:     render_system_updating(grid, fs); break;
    case SystemMode::SHUTTING_DOWN: render_system_shutdown(grid, fs); break;
    }
    return true;
}

// ── Main render function ────────────────────────────────────────────

void face_render(const FaceState& fs, PixelGrid grid)
{
    // Clear grid
    std::memset(grid, 0, sizeof(PixelGrid));

    // System mode takes over the entire grid
    if (render_system_mode(grid, fs))
        return;

    // Eyes + mouth
    render_eye(grid, fs, true);
    render_eye(grid, fs, false);
    render_mouth(grid, fs);

    // Post-processing effects
    apply_afterglow(grid, fs);
    apply_sparkle(grid, fs);
    apply_fire(grid, fs);

    // Store current frame for next frame's afterglow.
    // We cast away const on fs.fx here because afterglow_buf is
    // a render-internal cache, not part of the logical state.
    store_afterglow(grid, const_cast<EffectsState&>(fs.fx));
}
