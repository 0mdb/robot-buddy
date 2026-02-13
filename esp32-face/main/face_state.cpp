#include "face_state.h"
#include "esp_timer.h"
#include <cmath>
#include <cstdlib>

// ---- Time helper ----

static float now_s()
{
    return static_cast<float>(esp_timer_get_time()) / 1'000'000.0f;
}

static float randf() { return static_cast<float>(rand()) / RAND_MAX; }
static float randf_range(float lo, float hi) { return lo + randf() * (hi - lo); }
static int   randi_range(int lo, int hi) { return lo + rand() % (hi - lo + 1); }

// ---- Tweening ----

static float tween(float current, float target, float speed = 0.5f)
{
    return current + (target - current) * speed;
}

// ---- Boot-up sequence ----

static void update_boot(FaceState& fs)
{
    float now = now_s();
    float elapsed = now - fs.fx.boot_timer;

    if (fs.fx.boot_phase == 0) {
        float progress = fminf(1.0f, elapsed / 1.0f);
        float eased = 1.0f - (1.0f - progress) * (1.0f - progress);
        fs.eye_l.openness = eased;
        fs.eye_r.openness = eased;
        fs.eye_l.openness_target = eased;
        fs.eye_r.openness_target = eased;
        if (progress >= 1.0f) {
            fs.fx.boot_phase = 1;
            fs.fx.boot_timer = now;
        }
    } else if (fs.fx.boot_phase == 1) {
        if (elapsed < 0.3f) {
            float t = elapsed / 0.3f;
            fs.eye_l.openness = 1.0f - t;
            fs.eye_r.openness = 1.0f - t;
        } else if (elapsed < 0.5f) {
            fs.eye_l.openness = 0.0f;
            fs.eye_r.openness = 0.0f;
        } else if (elapsed < 0.9f) {
            float t = (elapsed - 0.5f) / 0.4f;
            fs.eye_l.openness = t;
            fs.eye_r.openness = t;
        } else {
            fs.eye_l.openness = 1.0f;
            fs.eye_r.openness = 1.0f;
            fs.eye_l.openness_target = 1.0f;
            fs.eye_r.openness_target = 1.0f;
            fs.fx.boot_phase = 2;
            fs.fx.boot_timer = now;
        }
    } else if (fs.fx.boot_phase == 2) {
        float gx;
        if (elapsed < 0.5f) {
            gx = -2.0f * (elapsed / 0.5f);
        } else if (elapsed < 1.2f) {
            gx = -2.0f + 4.0f * ((elapsed - 0.5f) / 0.7f);
        } else if (elapsed < 1.8f) {
            gx = 2.0f * (1.0f - (elapsed - 1.2f) / 0.6f);
        } else {
            gx = 0.0f;
            fs.fx.boot_active = false;
        }
        for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
            eye->gaze_x = gx;
            eye->gaze_x_target = gx;
            eye->gaze_y = 0.0f;
            eye->gaze_y_target = 0.0f;
        }
    }
}

// ---- Effects helpers ----

static void update_breathing(FaceState& fs)
{
    if (!fs.fx.breathing) return;
    fs.fx.breath_phase += BREATH_SPEED / static_cast<float>(ANIM_FPS);
    if (fs.fx.breath_phase > 2.0f * M_PI)
        fs.fx.breath_phase -= 2.0f * M_PI;
}

static void update_sparkle(FaceState& fs)
{
    if (!fs.fx.sparkle) { fs.fx.sparkle_count = 0; return; }

    // Age existing
    int kept = 0;
    for (int i = 0; i < fs.fx.sparkle_count; i++) {
        if (fs.fx.sparkle_pixels[i].life > 1) {
            fs.fx.sparkle_pixels[kept] = fs.fx.sparkle_pixels[i];
            fs.fx.sparkle_pixels[kept].life--;
            kept++;
        }
    }
    fs.fx.sparkle_count = kept;

    // Maybe spawn
    if (randf() < fs.fx.sparkle_chance && fs.fx.sparkle_count < 8) {
        auto& sp = fs.fx.sparkle_pixels[fs.fx.sparkle_count++];
        sp.x = randi_range(0, GRID_W - 1);
        sp.y = randi_range(0, GRID_H - 1);
        sp.life = randi_range(4, 12);
    }
}

static void update_fire(FaceState& fs)
{
    if (!fs.anim.rage) { fs.fx.fire_count = 0; return; }

    // Age existing
    int kept = 0;
    for (int i = 0; i < fs.fx.fire_count; i++) {
        auto& fp = fs.fx.fire_pixels[i];
        if (fp.life > 1 && fp.y > 0.0f) {
            fs.fx.fire_pixels[kept] = fp;
            fs.fx.fire_pixels[kept].x += randf_range(-0.3f, 0.3f);
            fs.fx.fire_pixels[kept].y -= 0.5f;
            fs.fx.fire_pixels[kept].life--;
            fs.fx.fire_pixels[kept].heat *= 0.9f;
            kept++;
        }
    }
    fs.fx.fire_count = kept;

    // Spawn new along top of each eye
    for (int i = 0; i < 3 && fs.fx.fire_count < 24; i++) {
        if (randf() < 0.7f && fs.fx.fire_count < 24) {
            auto& fp = fs.fx.fire_pixels[fs.fx.fire_count++];
            fp.x = randf_range(1.0f, 7.0f);
            fp.y = randf_range(1.0f, 3.5f);
            fp.life = randi_range(4, 10);
            fp.heat = randf_range(0.7f, 1.0f);
        }
        if (randf() < 0.7f && fs.fx.fire_count < 24) {
            auto& fp = fs.fx.fire_pixels[fs.fx.fire_count++];
            fp.x = randf_range(9.0f, 15.0f);
            fp.y = randf_range(1.0f, 3.5f);
            fp.life = randi_range(4, 10);
            fp.heat = randf_range(0.7f, 1.0f);
        }
    }
}

// ---- System mode update ----

static bool update_system(FaceState& fs)
{
    if (fs.system.mode == SystemMode::NONE) return false;

    float elapsed = now_s() - fs.system.timer;

    if (fs.system.mode == SystemMode::BOOTING) {
        if (elapsed >= 3.0f) {
            fs.system.mode = SystemMode::NONE;
            return false;
        }
    }
    // ERROR, LOW_BATTERY, UPDATING persist until cleared
    // SHUTTING_DOWN rendering handled in renderer
    return true;
}

// ---- Main state update ----

void face_state_update(FaceState& fs)
{
    float now = now_s();

    // System mode takes priority
    if (update_system(fs)) return;

    // Boot sequence
    if (fs.fx.boot_active) {
        if (fs.fx.boot_timer == 0.0f) fs.fx.boot_timer = now;
        update_boot(fs);
        update_breathing(fs);
        update_sparkle(fs);
        return;
    }

    // ---- Mood → eyelid targets ----
    fs.eyelids.tired_target = (fs.mood == Mood::TIRED) ? 1.0f : 0.0f;
    fs.eyelids.angry_target = (fs.mood == Mood::ANGRY) ? 1.0f : 0.0f;
    fs.eyelids.happy_target = (fs.mood == Mood::HAPPY) ? 1.0f : 0.0f;

    // ---- Mood → mouth targets ----
    if (fs.mood == Mood::HAPPY)       fs.mouth_curve_target = 0.8f;
    else if (fs.mood == Mood::ANGRY)  fs.mouth_curve_target = -0.6f;
    else if (fs.mood == Mood::TIRED)  fs.mouth_curve_target = -0.3f;
    else                              fs.mouth_curve_target = 0.2f;

    // ---- Auto-blink ----
    if (fs.anim.autoblink && now >= fs.anim.next_blink) {
        face_blink(fs);
        fs.anim.next_blink = now + BLINK_INTERVAL + randf() * BLINK_VARIATION;
    }

    // ---- Re-open eyes after blink ----
    for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
        if (eye->is_open && eye->openness < 0.05f)
            eye->openness_target = 1.0f;
        if (!eye->is_open)
            eye->openness_target = 0.0f;
    }

    // ---- Idle gaze wander ----
    if (fs.anim.idle && now >= fs.anim.next_idle) {
        float gx = randf_range(-MAX_GAZE, MAX_GAZE);
        float gy = randf_range(-MAX_GAZE * 0.6f, MAX_GAZE * 0.6f);
        for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
            eye->gaze_x_target = gx;
            eye->gaze_y_target = gy;
        }
        fs.anim.next_idle = now + IDLE_INTERVAL + randf() * IDLE_VARIATION;
    }

    // ---- Confused (horizontal shake) ----
    if (fs.anim.confused) {
        if (fs.anim.confused_toggle) {
            fs.anim.h_flicker = true;
            fs.anim.h_flicker_amp = 1.5f;
            fs.anim.confused_timer = now;
            fs.anim.confused_toggle = false;
        } else if (now >= fs.anim.confused_timer + 0.5f) {
            fs.anim.h_flicker = false;
            fs.anim.confused_toggle = true;
            fs.anim.confused = false;
        }
    }

    // ---- Laugh (vertical shake) ----
    if (fs.anim.laugh) {
        if (fs.anim.laugh_toggle) {
            fs.anim.v_flicker = true;
            fs.anim.v_flicker_amp = 1.5f;
            fs.anim.laugh_timer = now;
            fs.anim.laugh_toggle = false;
        } else if (now >= fs.anim.laugh_timer + 0.5f) {
            fs.anim.v_flicker = false;
            fs.anim.laugh_toggle = true;
            fs.anim.laugh = false;
        }
    }

    // ---- Surprise ----
    if (fs.anim.surprise) {
        float elapsed = now - fs.anim.surprise_timer;
        if (elapsed < 0.15f) {
            for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
                eye->width_scale_target = 1.3f;
                eye->height_scale_target = 1.25f;
            }
        } else if (elapsed < 0.8f) {
            for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
                eye->width_scale_target = 1.0f;
                eye->height_scale_target = 1.0f;
            }
        } else {
            for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
                eye->width_scale_target = 1.0f;
                eye->height_scale_target = 1.0f;
            }
            fs.anim.surprise = false;
        }
    }

    // ---- Heart ----
    if (fs.anim.heart && now >= fs.anim.heart_timer + 2.0f)
        fs.anim.heart = false;

    // ---- X eyes ----
    if (fs.anim.x_eyes && now >= fs.anim.x_eyes_timer + 1.5f)
        fs.anim.x_eyes = false;

    // ---- Rage ----
    if (fs.anim.rage) {
        float elapsed = now - fs.anim.rage_timer;
        if (elapsed < 3.0f) {
            fs.eyelids.angry_target = 1.0f;
            float shake = sinf(elapsed * 30.0f) * 0.4f;
            for (auto* eye : {&fs.eye_l, &fs.eye_r})
                eye->gaze_x_target = shake;
        } else {
            fs.eyelids.angry_target = 0.0f;
            fs.anim.rage = false;
            fs.fx.fire_count = 0;
        }
    }

    // ---- Sleepy ----
    if (fs.anim.sleepy) {
        float elapsed = now - fs.anim.sleepy_timer;
        if (elapsed < 3.0f) {
            float droop = fminf(1.0f, elapsed / 1.5f);
            fs.eyelids.tired_target = droop;
            float sway = sinf(elapsed * 2.0f) * 1.5f;
            for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
                eye->gaze_x_target = sway;
                eye->gaze_y_target = droop;
            }
        } else {
            fs.eyelids.tired_target = 0.0f;
            fs.anim.sleepy = false;
        }
    }

    // ---- Gesture → mouth overrides ----
    fs.mouth_wave_target = 0.0f;
    fs.mouth_offset_x_target = 0.0f;
    fs.mouth_width_target = 1.0f;

    if (fs.anim.surprise) {
        fs.mouth_curve_target = 0.0f;
        fs.mouth_open_target = 0.8f;
        fs.mouth_width_target = 0.5f;
    } else if (fs.anim.laugh) {
        fs.mouth_curve_target = 1.0f;
        float elapsed = now - fs.anim.laugh_timer;
        float chatter = 0.2f + 0.3f * fmaxf(0.0f, sinf(elapsed * 50.0f));
        fs.mouth_open = chatter;
        fs.mouth_open_target = chatter;
    } else if (fs.anim.heart) {
        fs.mouth_curve_target = 1.0f;
        fs.mouth_open_target = 0.0f;
    } else if (fs.anim.rage) {
        fs.mouth_curve_target = -1.0f;
        fs.mouth_open_target = 0.3f;
        fs.mouth_wave_target = 0.7f;
    } else if (fs.anim.x_eyes) {
        fs.mouth_curve_target = 0.0f;
        fs.mouth_open_target = 0.8f;
        fs.mouth_width_target = 0.5f;
    } else if (fs.anim.sleepy) {
        float elapsed = now - fs.anim.sleepy_timer;
        float dur = 3.0f;
        float ys = dur * 0.2f, yp = dur * 0.4f, ye = dur * 0.7f;
        if (elapsed < ys) {
            fs.mouth_open_target = 0.0f;
        } else if (elapsed < yp) {
            fs.mouth_open_target = (elapsed - ys) / (yp - ys);
            fs.mouth_curve_target = 0.0f;
            fs.mouth_width_target = 0.7f;
        } else if (elapsed < ye) {
            fs.mouth_open_target = 1.0f;
            fs.mouth_curve_target = 0.0f;
            fs.mouth_width_target = 0.7f;
        } else {
            float t = (elapsed - ye) / (dur - ye);
            fs.mouth_open_target = fmaxf(0.0f, 1.0f - t * 1.5f);
        }
    } else if (fs.anim.confused) {
        float elapsed = now - fs.anim.confused_timer;
        fs.mouth_offset_x_target = 1.5f * sinf(elapsed * 12.0f);
        fs.mouth_curve_target = -0.2f;
        fs.mouth_open_target = 0.0f;
    } else {
        fs.mouth_open_target = 0.0f;
    }

    // ---- Squash & stretch on blink ----
    for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
        if (eye->openness_target < 0.1f && eye->openness > 0.3f) {
            eye->width_scale_target = 1.15f;
            eye->height_scale_target = 0.85f;
        } else if (eye->openness_target > 0.9f && eye->openness < 0.7f) {
            eye->width_scale_target = 0.9f;
            eye->height_scale_target = 1.1f;
        } else if (eye->openness > 0.9f) {
            eye->width_scale_target = 1.0f;
            eye->height_scale_target = 1.0f;
        }
    }

    // ---- Tween all continuous values ----
    for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
        eye->openness     = tween(eye->openness,     eye->openness_target);
        eye->gaze_x       = tween(eye->gaze_x,       eye->gaze_x_target,       0.35f);
        eye->gaze_y       = tween(eye->gaze_y,       eye->gaze_y_target,       0.35f);
        eye->width_scale  = tween(eye->width_scale,  eye->width_scale_target,  0.3f);
        eye->height_scale = tween(eye->height_scale, eye->height_scale_target, 0.3f);
    }

    fs.eyelids.tired = tween(fs.eyelids.tired, fs.eyelids.tired_target);
    fs.eyelids.angry = tween(fs.eyelids.angry, fs.eyelids.angry_target);
    fs.eyelids.happy = tween(fs.eyelids.happy, fs.eyelids.happy_target);

    fs.mouth_curve    = tween(fs.mouth_curve,    fs.mouth_curve_target,    0.25f);
    fs.mouth_open     = tween(fs.mouth_open,     fs.mouth_open_target,    0.3f);
    fs.mouth_wave     = tween(fs.mouth_wave,     fs.mouth_wave_target,    0.3f);
    fs.mouth_offset_x = tween(fs.mouth_offset_x, fs.mouth_offset_x_target, 0.25f);
    fs.mouth_width    = tween(fs.mouth_width,    fs.mouth_width_target,   0.25f);

    // ---- Flicker offsets ----
    if (fs.anim.h_flicker) {
        float dx = fs.anim.h_flicker_alt ? fs.anim.h_flicker_amp : -fs.anim.h_flicker_amp;
        fs.eye_l.gaze_x += dx;
        fs.eye_r.gaze_x += dx;
        fs.anim.h_flicker_alt = !fs.anim.h_flicker_alt;
    }
    if (fs.anim.v_flicker) {
        float dy = fs.anim.v_flicker_alt ? fs.anim.v_flicker_amp : -fs.anim.v_flicker_amp;
        fs.eye_l.gaze_y += dy;
        fs.eye_r.gaze_y += dy;
        fs.anim.v_flicker_alt = !fs.anim.v_flicker_alt;
    }

    // ---- Effects ----
    update_breathing(fs);
    update_sparkle(fs);
    update_fire(fs);
}

// ---- Public helpers ----

float face_get_breath_scale(const FaceState& fs)
{
    if (!fs.fx.breathing) return 1.0f;
    return 1.0f + sinf(fs.fx.breath_phase) * BREATH_AMOUNT;
}

void face_get_emotion_color(const FaceState& fs, uint8_t& r, uint8_t& g, uint8_t& b)
{
    if (fs.anim.rage) {
        int flicker = randi_range(-20, 20);
        r = static_cast<uint8_t>(fminf(255, fmaxf(0, 230 + flicker)));
        g = static_cast<uint8_t>(fminf(255, fmaxf(0, 30 + flicker)));
        b = 0;
        return;
    }
    if (fs.anim.heart)   { r = 255; g = 60;  b = 140; return; }
    if (fs.anim.x_eyes)  { r = 200; g = 40;  b = 40;  return; }
    if (fs.anim.surprise) {
        float elapsed = now_s() - fs.anim.surprise_timer;
        if (elapsed < 0.15f) { r = 200; g = 220; b = 255; return; }
    }
    if (fs.mood == Mood::HAPPY)  { r = 50;  g = 180; b = 255; return; }
    if (fs.mood == Mood::TIRED)  { r = 20;  g = 60;  b = 160; return; }
    if (fs.mood == Mood::ANGRY)  { r = 60;  g = 80;  b = 220; return; }
    r = 30; g = 120; b = 255;  // default blue
}

// ---- Convenience triggers ----

void face_blink(FaceState& fs)
{
    fs.eye_l.openness_target = 0.0f;
    fs.eye_r.openness_target = 0.0f;
    fs.eye_l.is_open = true;
    fs.eye_r.is_open = true;
}

void face_wink_left(FaceState& fs)
{
    fs.eye_l.openness_target = 0.0f;
    fs.eye_l.is_open = true;
}

void face_wink_right(FaceState& fs)
{
    fs.eye_r.openness_target = 0.0f;
    fs.eye_r.is_open = true;
}

void face_set_gaze(FaceState& fs, float x, float y)
{
    x = fmaxf(-MAX_GAZE, fminf(MAX_GAZE, x));
    y = fmaxf(-MAX_GAZE, fminf(MAX_GAZE, y));
    for (auto* eye : {&fs.eye_l, &fs.eye_r}) {
        eye->gaze_x_target = x;
        eye->gaze_y_target = y;
    }
}

void face_set_mood(FaceState& fs, Mood mood) { fs.mood = mood; }

void face_trigger_gesture(FaceState& fs, GestureId gesture)
{
    float now = now_s();
    switch (gesture) {
    case GestureId::BLINK:    face_blink(fs);           break;
    case GestureId::WINK_L:   face_wink_left(fs);       break;
    case GestureId::WINK_R:   face_wink_right(fs);      break;
    case GestureId::CONFUSED: fs.anim.confused = true;   break;
    case GestureId::LAUGH:    fs.anim.laugh = true;      break;
    case GestureId::SURPRISE:
        fs.anim.surprise = true;
        fs.anim.surprise_timer = now;
        break;
    case GestureId::HEART:
        fs.anim.heart = true;
        fs.anim.heart_timer = now;
        break;
    case GestureId::X_EYES:
        fs.anim.x_eyes = true;
        fs.anim.x_eyes_timer = now;
        break;
    case GestureId::SLEEPY:
        fs.anim.sleepy = true;
        fs.anim.sleepy_timer = now;
        break;
    case GestureId::RAGE:
        fs.anim.rage = true;
        fs.anim.rage_timer = now;
        break;
    }
}

void face_set_system_mode(FaceState& fs, SystemMode mode, float param)
{
    fs.system.mode  = mode;
    fs.system.timer = now_s();
    fs.system.phase = 0;
    fs.system.param = param;
}
