// Host-side render regression test: runs the real face_ui.cpp drawing code and
// checks that the incremental (dirty-rect) canvas matches a full-clear reference
// render every frame. Run: just test-face-render
#include "esp_heap_caps.h"

#include "../main/face_ui.cpp" // NOLINT: include the TU to reach its static render state

#include <cstdio>
#include <vector>

int64_t g_fake_time_us = 1'000'000;

// ---- Platform stubs for symbols face_ui.cpp links against ----
void        display_set_backlight(uint8_t) {}
void        led_set_rgb(uint8_t, uint8_t, uint8_t) {}
std::size_t touch_transform_preset_count()
{
    return 0;
}
const TouchTransformPreset* touch_transform_preset_get(std::size_t)
{
    return nullptr;
}
std::size_t touch_transform_preset_index()
{
    return 0;
}
bool touch_transform_apply(std::size_t)
{
    return true;
}

// Full-clear reference: same draw calls as face_ui_update(), on a fresh buffer.
static void render_reference(pixel_t* buf, const FaceState& fs, uint32_t now_ms)
{
    std::fill_n(buf, SCREEN_W * SCREEN_H, rgb_to_color(BG_R, BG_G, BG_B));
    render_eye(buf, fs.eye_l, fs, true, LEFT_EYE_CX, LEFT_EYE_CY);
    render_eye(buf, fs.eye_r, fs, false, RIGHT_EYE_CX, RIGHT_EYE_CY);
    render_mouth(buf, fs);
    if (fs.anim.rage) render_fire_effect(buf, fs);
    render_sparkles(buf, fs);
    if (fs.system.mode == SystemMode::NONE) {
        conv_border_render(buf);
        render_touch_ring(buf, fs, now_ms);
    }
}

struct Diff {
    int count = 0;
    int x0 = SCREEN_W, y0 = SCREEN_H, x1 = -1, y1 = -1;
};

static Diff compare(const pixel_t* a, const pixel_t* b)
{
    Diff d;
    for (int y = 0; y < SCREEN_H; y++) {
        for (int x = 0; x < SCREEN_W; x++) {
            if (a[y * SCREEN_W + x] != b[y * SCREEN_W + x]) {
                d.count++;
                d.x0 = std::min(d.x0, x);
                d.y0 = std::min(d.y0, y);
                d.x1 = std::max(d.x1, x);
                d.y1 = std::max(d.y1, y);
            }
        }
    }
    return d;
}

static void write_ppm(const char* path, const pixel_t* buf)
{
    FILE* f = std::fopen(path, "wb");
    if (!f) return;
    std::fprintf(f, "P6\n%d %d\n255\n", SCREEN_W, SCREEN_H);
    for (int i = 0; i < SCREEN_W * SCREEN_H; i++) {
        const pixel_t c = buf[i];
        const uint8_t rgb[3] = {static_cast<uint8_t>((c >> 11) << 3), static_cast<uint8_t>(((c >> 5) & 0x3F) << 2),
                                static_cast<uint8_t>((c & 0x1F) << 3)};
        std::fwrite(rgb, 1, 3, f);
    }
    std::fclose(f);
}

struct Scenario {
    const char* name;
    uint8_t     flags;
    uint8_t     conv_state;
    bool        talking;
};

static int run(const Scenario& sc, int frames, const char* dump_dir)
{
    FaceState fs;
    s_prev_bounds = {};
    std::memset(canvas_buf, 0, CANVAS_BYTES); // device: lv_canvas_fill_bg() at create
    apply_face_flags(fs, sc.flags);
    if (!afterglow_buf) fs.fx.afterglow = false;
    conv_border_set_state(sc.conv_state);
    std::vector<pixel_t> ref(SCREEN_W * SCREEN_H);
    int                  bad_frames = 0;

    for (int f = 0; f < frames; f++) {
        g_fake_time_us += 33'333;
        // Sweep gaze left/right and up/down so eyes cross the mouth's columns.
        const float t = static_cast<float>(f) / 30.0f;
        face_set_gaze(fs, 12.0f * sinf(t * 1.3f), 6.0f * sinf(t * 0.7f));
        fs.talking = sc.talking;
        fs.talking_energy = sc.talking ? 0.5f + 0.5f * sinf(t * 9.0f) : 0.0f;
        conv_border_update(1.0f / ANIM_FPS);
        face_state_update(fs);

        s_collect_render_perf = false;
        face_ui_update(fs);
        const uint32_t now_ms = touch_now_ms();
        render_reference(ref.data(), fs, now_ms);

        if (dump_dir && (f == 40 || f == 120)) {
            char p[512];
            std::snprintf(p, sizeof(p), "%s/%s_f%03d.ppm", dump_dir, sc.name, f);
            write_ppm(p, canvas_buf);
        }
        const Diff d = compare(canvas_buf, ref.data());
        if (d.count > 0) {
            if (bad_frames < 3) {
                std::fprintf(stderr, "  %s frame %d: %d px differ, bbox x[%d..%d] y[%d..%d]\n", sc.name, f, d.count,
                             d.x0, d.x1, d.y0, d.y1);
                if (dump_dir && bad_frames == 0) {
                    char p[512];
                    std::snprintf(p, sizeof(p), "%s/%s_incremental.ppm", dump_dir, sc.name);
                    write_ppm(p, canvas_buf);
                    std::snprintf(p, sizeof(p), "%s/%s_reference.ppm", dump_dir, sc.name);
                    write_ppm(p, ref.data());
                }
            }
            bad_frames++;
        }
    }
    std::printf("%-22s %s (%d/%d frames differ)\n", sc.name, bad_frames ? "FAIL" : "ok", bad_frames, frames);
    return bad_frames ? 1 : 0;
}

struct LidOverride {
    bool  on = false;
    float slope = 0, top_l = 0, top_r = 0, bottom = 0, h_l = 1.0f, h_r = 1.0f, curve = 0, offset = 0;
};

// Snapshot mode: settle a mood for ~2 s and dump the frame (for visual review).
// An optional LidOverride replaces lid/mouth values after each update (design mockups).
static void snapshot(const char* dir, const char* name, Mood mood, float intensity, float gx, float gy,
                     uint8_t conv_state, LidOverride ov = {})
{
    FaceState fs;
    s_prev_bounds = {};
    std::memset(canvas_buf, 0, CANVAS_BYTES);
    apply_face_flags(fs, static_cast<uint8_t>(FACE_FLAGS_ALL & ~FACE_FLAG_AFTERGLOW & ~FACE_FLAG_SPARKLE));
    fs.anim.autoblink = false; // keep eyes open for a clean still
    fs.fx.boot_active = false; // skip the ~3 s boot animation
    fs.anim.idle = false;
    conv_border_set_state(conv_state);
    face_set_mood(fs, mood);
    face_set_expression_intensity(fs, intensity);
    face_set_gaze(fs, gx, gy);
    for (int f = 0; f < 60; f++) {
        g_fake_time_us += 33'333;
        conv_border_update(1.0f / ANIM_FPS);
        face_state_update(fs);
        if (ov.on) {
            fs.eyelids.slope = ov.slope;
            fs.eyelids.top_l = ov.top_l;
            fs.eyelids.top_r = ov.top_r;
            fs.eyelids.bottom_l = fs.eyelids.bottom_r = ov.bottom;
            fs.eye_l.height_scale = ov.h_l;
            fs.eye_r.height_scale = ov.h_r;
            fs.mouth_curve = ov.curve;
            fs.mouth_offset_x = ov.offset;
        }
        face_ui_update(fs);
    }
    char p[512];
    std::snprintf(p, sizeof(p), "%s/%s.ppm", dir, name);
    write_ppm(p, canvas_buf);
}

int main(int argc, char** argv)
{
    const char* dump_dir = argc > 1 ? argv[1] : nullptr;
    face_ui_create(nullptr);
    if (!canvas_buf) return 2;
    if (argc > 2 && std::strcmp(argv[2], "moods") == 0) {
        // THINKING as the supervisor sends it in conv THINKING: intensity 0.5, gaze aversion up-right.
        snapshot(dump_dir, "neutral", Mood::NEUTRAL, 1.0f, 0, 0, 0);
        snapshot(dump_dir, "thinking_conv", Mood::THINKING, 0.5f, 0.5f * MAX_GAZE, -0.3f * MAX_GAZE, 4);
        snapshot(dump_dir, "thinking_full", Mood::THINKING, 1.0f, 0, 0, 0);
        snapshot(dump_dir, "angry", Mood::ANGRY, 1.0f, 0, 0, 0);
        snapshot(dump_dir, "confused", Mood::CONFUSED, 1.0f, 0, 0, 0);
        // THINKING mockups (gaze up-right like the conversation THINKING state).
        const float gx = 0.5f * MAX_GAZE, gy = -0.3f * MAX_GAZE;
        LidOverride a; // one brow raised, other hooded, no V
        a.on = true;
        a.slope = 0.0f;
        a.top_l = 0.0f;
        a.top_r = 0.22f;
        a.h_l = 1.08f;
        a.h_r = 1.0f;
        a.curve = -0.05f;
        a.offset = 1.5f;
        snapshot(dump_dir, "mock_A_one_brow", Mood::THINKING, 1.0f, gx, gy, 0, a);
        LidOverride b; // soft squint from below, outer corners slightly down (no V)
        b.on = true;
        b.slope = -0.15f;
        b.top_l = b.top_r = 0.10f;
        b.bottom = 0.18f;
        b.curve = 0.0f;
        b.offset = 1.5f;
        snapshot(dump_dir, "mock_B_soft_squint", Mood::THINKING, 1.0f, gx, gy, 0, b);
        LidOverride c; // plain: neutral lids, just gaze aversion + offset mouth
        c.on = true;
        c.slope = 0.0f;
        c.top_l = c.top_r = 0.0f;
        c.curve = 0.0f;
        c.offset = 1.5f;
        snapshot(dump_dir, "mock_C_gaze_only", Mood::THINKING, 1.0f, gx, gy, 0, c);
        return 0;
    }

    const uint8_t  defaults = static_cast<uint8_t>(FACE_FLAGS_ALL & ~FACE_FLAG_AFTERGLOW);
    const Scenario scenarios[] = {
        {"idle_default_flags", defaults, 0, false},
        {"idle_no_sparkle", static_cast<uint8_t>(defaults & ~FACE_FLAG_SPARKLE), 0, false},
        {"talking", defaults, 5, true},
        {"listening_border", defaults, 2, false},
        {"thinking_border", defaults, 4, false},
    };
    int failures = 0;
    for (const auto& sc : scenarios) {
        failures += run(sc, 300, dump_dir);
    }
    return failures ? 1 : 0;
}
