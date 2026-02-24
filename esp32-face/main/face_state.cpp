#include "face_state.h"

#include "esp_timer.h"

#include <cmath>
#include <cstdlib>
#include <initializer_list>

static float now_s()
{
    return static_cast<float>(esp_timer_get_time()) / 1'000'000.0f;
}

static float randf()
{
    return static_cast<float>(rand()) / static_cast<float>(RAND_MAX);
}

static float randf_range(float lo, float hi)
{
    return lo + randf() * (hi - lo);
}

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float tween(float current, float target, float speed)
{
    return current + (target - current) * speed;
}

static float spring_step(float current, float target, float& vel, float k = 0.25f, float d = 0.65f)
{
    const float force = (target - current) * k;
    vel = (vel + force) * d;
    return current + vel;
}

static void clear_sparkles(FaceState& fs)
{
    for (auto& px : fs.fx.sparkle_pixels) {
        px.active = false;
        px.life = 0;
    }
}

static void clear_fire(FaceState& fs)
{
    for (auto& px : fs.fx.fire_pixels) {
        px.active = false;
        px.life = 0.0f;
    }
}

static void set_active_gesture(FaceState& fs, GestureId gesture, float duration_s, float now)
{
    fs.active_gesture = static_cast<uint8_t>(gesture);
    fs.active_gesture_until = now + clampf(duration_s, 0.08f, 10.0f);
}

static void update_boot(FaceState& fs)
{
    const float now = now_s();
    const float elapsed = now - fs.fx.boot_timer;

    if (fs.fx.boot_phase == 0) {
        const float progress = fminf(1.0f, elapsed / 1.0f);
        const float eased = 1.0f - (1.0f - progress) * (1.0f - progress);
        fs.eye_l.openness = eased;
        fs.eye_r.openness = eased;
        fs.eye_l.openness_target = eased;
        fs.eye_r.openness_target = eased;
        if (progress >= 1.0f) {
            fs.fx.boot_phase = 1;
            fs.fx.boot_timer = now;
        }
        return;
    }

    if (fs.fx.boot_phase == 1) {
        if (elapsed < 0.3f) {
            const float t = elapsed / 0.3f;
            fs.eye_l.openness = 1.0f - t;
            fs.eye_r.openness = 1.0f - t;
        } else if (elapsed < 0.5f) {
            fs.eye_l.openness = 0.0f;
            fs.eye_r.openness = 0.0f;
        } else if (elapsed < 0.9f) {
            const float t = (elapsed - 0.5f) / 0.4f;
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
        return;
    }

    if (fs.fx.boot_phase == 2) {
        float gx = 0.0f;
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
        fs.eye_l.gaze_x = gx;
        fs.eye_l.gaze_x_target = gx;
        fs.eye_l.gaze_y = 0.0f;
        fs.eye_l.gaze_y_target = 0.0f;
        fs.eye_r.gaze_x = gx;
        fs.eye_r.gaze_x_target = gx;
        fs.eye_r.gaze_y = 0.0f;
        fs.eye_r.gaze_y_target = 0.0f;
    }
}

static void update_breathing(FaceState& fs)
{
    if (!fs.fx.breathing) {
        return;
    }
    fs.fx.breath_phase += fs.fx.breath_speed / static_cast<float>(ANIM_FPS);
    const float two_pi = 2.0f * static_cast<float>(M_PI);
    if (fs.fx.breath_phase > two_pi) {
        fs.fx.breath_phase -= two_pi;
    }
}

static void update_sparkle(FaceState& fs)
{
    if (!fs.fx.sparkle) {
        clear_sparkles(fs);
        return;
    }

    for (auto& px : fs.fx.sparkle_pixels) {
        if (!px.active) {
            continue;
        }
        if (px.life > 0) {
            px.life--;
        }
        if (px.life == 0) {
            px.active = false;
        }
    }

    if (randf() >= fs.fx.sparkle_chance) {
        return;
    }

    for (auto& px : fs.fx.sparkle_pixels) {
        if (px.active) {
            continue;
        }
        px.active = true;
        px.x = static_cast<int16_t>(rand() % SCREEN_W);
        px.y = static_cast<int16_t>(rand() % SCREEN_H);
        px.life = static_cast<uint8_t>(5 + (rand() % 11));
        break;
    }
}

static void update_fire(FaceState& fs)
{
    if (!fs.anim.rage) {
        clear_fire(fs);
        return;
    }

    for (auto& px : fs.fx.fire_pixels) {
        if (!px.active) {
            continue;
        }
        px.x += randf_range(-1.5f, 1.5f);
        px.y -= 3.0f;
        px.life -= 1.0f;
        px.heat *= 0.9f;
        if (px.life <= 1.0f || px.y < 0.0f) {
            px.active = false;
        }
    }

    if (randf() >= 0.3f) {
        return;
    }

    for (float cx : {LEFT_EYE_CX, RIGHT_EYE_CX}) {
        for (auto& px : fs.fx.fire_pixels) {
            if (px.active) {
                continue;
            }
            px.active = true;
            px.x = cx + randf_range(-20.0f, 20.0f);
            px.y = LEFT_EYE_CY - 30.0f;
            px.life = static_cast<float>(5 + (rand() % 11));
            px.heat = 1.0f;
            break;
        }
    }
}

static bool update_system(FaceState& fs)
{
    return fs.system.mode != SystemMode::NONE;
}

void face_state_update(FaceState& fs)
{
    const float now = now_s();
    const float dt = 1.0f / static_cast<float>(ANIM_FPS);

    if (update_system(fs)) {
        update_breathing(fs);
        update_sparkle(fs);
        update_fire(fs);
        if (fs.active_gesture != 0xFF && now > fs.active_gesture_until) {
            fs.active_gesture = 0xFF;
        }
        return;
    }

    if (fs.fx.boot_active) {
        if (fs.fx.boot_timer == 0.0f) {
            fs.fx.boot_timer = now;
        }
        update_boot(fs);
        update_breathing(fs);
        update_sparkle(fs);
        update_fire(fs);
        if (fs.active_gesture != 0xFF && now > fs.active_gesture_until) {
            fs.active_gesture = 0xFF;
        }
        return;
    }

    float t_curve = 0.1f;
    float t_width = 1.0f;
    float t_open = 0.0f;
    float t_lid_slope = 0.0f;
    float t_lid_top = 0.0f;
    float t_lid_bot = 0.0f;

    switch (fs.mood) {
    case Mood::NEUTRAL:
        t_curve = 0.1f;
        break;
    case Mood::HAPPY:
        t_curve = 0.8f;
        t_lid_bot = 0.4f;
        t_width = 1.1f;
        break;
    case Mood::EXCITED:
        t_curve = 0.9f;
        t_open = 0.2f;
        t_lid_bot = 0.3f;
        t_width = 1.2f;
        break;
    case Mood::CURIOUS:
        t_curve = 0.0f;
        t_open = 0.1f;
        t_width = 0.9f;
        break;
    case Mood::SAD:
        t_curve = -0.5f;
        t_lid_slope = -0.6f;
        t_lid_top = 0.3f;
        break;
    case Mood::SCARED:
        t_curve = -0.3f;
        t_open = 0.3f;
        t_width = 0.8f;
        break;
    case Mood::ANGRY:
        t_curve = -0.6f;
        t_lid_slope = 0.8f;
        t_lid_top = 0.4f;
        break;
    case Mood::SURPRISED:
        t_curve = 0.0f;
        t_open = 0.6f;
        t_width = 0.4f;
        break;
    case Mood::SLEEPY:
        t_curve = 0.0f;
        t_lid_top = 0.6f;
        t_lid_slope = -0.2f;
        break;
    case Mood::LOVE:
        t_curve = 0.6f;
        t_lid_bot = 0.3f;
        break;
    case Mood::SILLY:
        t_curve = 0.5f;
        t_width = 1.1f;
        break;
    case Mood::THINKING:
        t_curve = -0.1f;
        t_lid_slope = 0.4f;
        t_lid_top = 0.2f;
        break;
    case Mood::CONFUSED:
        t_curve = -0.2f;
        t_lid_slope = 0.2f;
        t_lid_top = 0.1f;
        break;
    }

    const float intensity = clampf(fs.expression_intensity, 0.0f, 1.0f);
    auto        blend_target = [intensity](float neutral_value, float target_value) -> float {
        return neutral_value + (target_value - neutral_value) * intensity;
    };
    t_curve = blend_target(0.1f, t_curve);
    t_width = blend_target(1.0f, t_width);
    t_open = blend_target(0.0f, t_open);
    t_lid_slope = blend_target(0.0f, t_lid_slope);
    t_lid_top = blend_target(0.0f, t_lid_top);
    t_lid_bot = blend_target(0.0f, t_lid_bot);

    // Per-mood eye scale (V3 sim MOOD_EYE_SCALE — intensity-blended)
    float ws = 1.0f, hs = 1.0f;
    switch (fs.mood) {
    case Mood::HAPPY:
        ws = 1.05f;
        hs = 0.9f;
        break;
    case Mood::EXCITED:
        ws = 1.15f;
        hs = 1.1f;
        break;
    case Mood::CURIOUS:
        ws = 1.05f;
        hs = 1.15f;
        break;
    case Mood::SAD:
        ws = 0.95f;
        hs = 0.85f;
        break;
    case Mood::SCARED:
        ws = 0.9f;
        hs = 1.15f;
        break;
    case Mood::ANGRY:
        ws = 1.1f;
        hs = 0.65f;
        break;
    case Mood::SURPRISED:
        ws = 1.2f;
        hs = 1.2f;
        break;
    case Mood::SLEEPY:
        ws = 0.95f;
        hs = 0.7f;
        break;
    case Mood::LOVE:
        ws = 1.05f;
        hs = 1.05f;
        break;
    case Mood::SILLY:
        ws = 1.1f;
        hs = 1.0f;
        break;
    case Mood::CONFUSED:
        ws = 1.0f;
        hs = 1.05f;
        break;
    default:
        break;
    }
    ws = 1.0f + (ws - 1.0f) * intensity;
    hs = 1.0f + (hs - 1.0f) * intensity;
    fs.eye_l.width_scale_target = ws;
    fs.eye_r.width_scale_target = ws;
    fs.eye_l.height_scale_target = hs;
    fs.eye_r.height_scale_target = hs;

    fs.mouth_curve_target = t_curve;
    fs.mouth_width_target = t_width;
    fs.mouth_open_target = t_open;
    fs.mouth_wave_target = 0.0f;
    fs.mouth_offset_x_target = 0.0f;
    fs.eyelids.slope_target = t_lid_slope;

    if (fs.mood == Mood::THINKING) {
        fs.mouth_offset_x_target = 1.5f;
        fs.eye_l.gaze_x_target = 6.0f;
        fs.eye_l.gaze_y_target = -4.0f;
        fs.eye_r.gaze_x_target = 6.0f;
        fs.eye_r.gaze_y_target = -4.0f;
    }

    // Confused: persistent asymmetric mouth (puzzled look)
    if (fs.mood == Mood::CONFUSED) {
        fs.mouth_offset_x_target = 2.0f;
    }

    // Love: mild pupil convergence (soft focus / adoring gaze)
    if (fs.mood == Mood::LOVE) {
        const float li = clampf(fs.expression_intensity, 0.0f, 1.0f);
        fs.eye_l.gaze_x_target = 2.5f * li;
        fs.eye_r.gaze_x_target = -2.5f * li;
    }

    if (fs.anim.surprise) {
        const float elapsed = now - fs.anim.surprise_timer;
        if (elapsed < 0.15f) {
            fs.eye_l.width_scale_target = 1.3f;
            fs.eye_l.height_scale_target = 1.25f;
            fs.eye_r.width_scale_target = 1.3f;
            fs.eye_r.height_scale_target = 1.25f;
        }
        fs.mouth_curve_target = 0.0f;
        fs.mouth_open_target = 0.6f;
        fs.mouth_width_target = 0.5f;
    }

    if (fs.anim.laugh) {
        fs.mouth_curve_target = 1.0f;
        const float elapsed = now - fs.anim.laugh_timer;
        const float chatter = 0.2f + 0.3f * fmaxf(0.0f, sinf(elapsed * 50.0f));
        fs.mouth_open_target = fmaxf(fs.mouth_open_target, chatter);
    }

    if (fs.anim.rage) {
        const float elapsed = now - fs.anim.rage_timer;
        fs.eyelids.slope_target = 0.9f;
        t_lid_top = fmaxf(t_lid_top, 0.4f);
        const float shake = sinf(elapsed * 30.0f) * 0.4f;
        fs.eye_l.gaze_x_target = shake;
        fs.eye_r.gaze_x_target = shake;
        fs.mouth_curve_target = -1.0f;
        fs.mouth_open_target = 0.3f;
        fs.mouth_wave_target = 0.7f;
    }

    if (fs.anim.x_eyes) {
        fs.mouth_curve_target = 0.0f;
        fs.mouth_open_target = 0.8f;
        fs.mouth_width_target = 0.5f;
    }

    if (fs.anim.heart) {
        fs.mouth_curve_target = 1.0f;
        fs.mouth_open_target = 0.0f;
    }

    if (fs.anim.sleepy) {
        const float elapsed = now - fs.anim.sleepy_timer;
        const float droop = fminf(1.0f, elapsed / fmaxf(0.15f, fs.anim.sleepy_duration * 0.5f));
        t_lid_top = fmaxf(t_lid_top, droop * 0.6f);
        fs.eyelids.slope_target = -0.2f;
        const float sway = sinf(elapsed * 2.0f) * 6.0f;
        fs.eye_l.gaze_x_target = sway;
        fs.eye_r.gaze_x_target = sway;
        fs.eye_l.gaze_y_target = droop * 3.0f;
        fs.eye_r.gaze_y_target = droop * 3.0f;

        const float dur = fmaxf(0.2f, fs.anim.sleepy_duration);
        const float ys = dur * 0.2f;
        const float yp = dur * 0.4f;
        const float ye = dur * 0.7f;
        if (elapsed < ys) {
            // no-op
        } else if (elapsed < yp) {
            fs.mouth_open_target = (elapsed - ys) / (yp - ys);
            fs.mouth_curve_target = 0.0f;
            fs.mouth_width_target = 0.7f;
        } else if (elapsed < ye) {
            fs.mouth_open_target = 1.0f;
            fs.mouth_curve_target = 0.0f;
            fs.mouth_width_target = 0.7f;
        } else {
            const float t2 = (elapsed - ye) / fmaxf(0.001f, (dur - ye));
            fs.mouth_open_target = fmaxf(0.0f, 1.0f - t2 * 1.5f);
        }
    }

    if (fs.anim.confused) {
        const float elapsed = now - fs.anim.confused_timer;
        fs.mouth_offset_x_target = 1.5f * sinf(elapsed * 12.0f);
        fs.mouth_curve_target = -0.2f;
        fs.mouth_open_target = 0.0f;
    }

    // NOD: slight lid droop follows vertical gaze (pre-spring, tweened)
    if (fs.anim.nod) {
        const float elapsed = now - fs.anim.nod_timer;
        const float lid_offset = 0.15f * fmaxf(0.0f, sinf(elapsed * 12.0f));
        t_lid_top = fmaxf(t_lid_top, lid_offset);
    }

    // HEADSHAKE: slight frown (pre-spring, tweened)
    if (fs.anim.headshake) {
        fs.mouth_curve_target = -0.2f;
    }

    if (fs.anim.heart && now > fs.anim.heart_timer + fs.anim.heart_duration) {
        fs.anim.heart = false;
    }
    if (fs.anim.x_eyes && now > fs.anim.x_eyes_timer + fs.anim.x_eyes_duration) {
        fs.anim.x_eyes = false;
    }
    if (fs.anim.rage && now > fs.anim.rage_timer + fs.anim.rage_duration) {
        fs.anim.rage = false;
        clear_fire(fs);
    }
    if (fs.anim.surprise && now > fs.anim.surprise_timer + fs.anim.surprise_duration) {
        fs.anim.surprise = false;
    }
    if (fs.anim.sleepy && now > fs.anim.sleepy_timer + fs.anim.sleepy_duration) {
        fs.anim.sleepy = false;
    }
    if (fs.anim.nod && now > fs.anim.nod_timer + fs.anim.nod_duration) {
        fs.anim.nod = false;
    }
    if (fs.anim.headshake && now > fs.anim.headshake_timer + fs.anim.headshake_duration) {
        fs.anim.headshake = false;
    }

    if (fs.anim.confused) {
        if (fs.anim.confused_toggle) {
            fs.anim.h_flicker = true;
            fs.anim.h_flicker_amp = 1.5f;
            fs.anim.confused_toggle = false;
        }
        if (now > fs.anim.confused_timer + fs.anim.confused_duration) {
            fs.anim.confused = false;
            fs.anim.h_flicker = false;
            fs.anim.confused_toggle = true;
        }
    }

    if (fs.anim.laugh) {
        if (fs.anim.laugh_toggle) {
            fs.anim.v_flicker = true;
            fs.anim.v_flicker_amp = 1.5f;
            fs.anim.laugh_toggle = false;
        }
        if (now > fs.anim.laugh_timer + fs.anim.laugh_duration) {
            fs.anim.laugh = false;
            fs.anim.v_flicker = false;
            fs.anim.laugh_toggle = true;
        }
    }

    if (fs.anim.autoblink && now >= fs.anim.next_blink) {
        face_blink(fs);
        fs.anim.next_blink = now + BLINK_INTERVAL + randf() * BLINK_VARIATION;
    }

    if (!fs.eye_l.is_open && fs.eyelids.top_l > 0.95f) {
        fs.eye_l.is_open = true;
    }
    if (!fs.eye_r.is_open && fs.eyelids.top_r > 0.95f) {
        fs.eye_r.is_open = true;
    }

    const float closure_l = fs.eye_l.is_open ? 0.0f : 1.0f;
    const float closure_r = fs.eye_r.is_open ? 0.0f : 1.0f;
    const float final_top_l = fmaxf(t_lid_top, closure_l);
    float       final_top_r = fmaxf(t_lid_top, closure_r);

    // Curious: asymmetric brow — right eye slightly hooded, left appears "raised"
    if (fs.mood == Mood::CURIOUS) {
        const float ci = clampf(fs.expression_intensity, 0.0f, 1.0f);
        final_top_r = fmaxf(final_top_r, 0.25f * ci);
    }

    const float speed_l = (final_top_l > fs.eyelids.top_l) ? 0.6f : 0.4f;
    const float speed_r = (final_top_r > fs.eyelids.top_r) ? 0.6f : 0.4f;

    fs.eyelids.top_l = tween(fs.eyelids.top_l, final_top_l, speed_l);
    fs.eyelids.top_r = tween(fs.eyelids.top_r, final_top_r, speed_r);
    fs.eyelids.bottom_l = tween(fs.eyelids.bottom_l, t_lid_bot, 0.3f);
    fs.eyelids.bottom_r = tween(fs.eyelids.bottom_r, t_lid_bot, 0.3f);
    fs.eyelids.slope = tween(fs.eyelids.slope, fs.eyelids.slope_target, 0.3f);

    if (fs.anim.idle && now >= fs.anim.next_idle) {
        const float target_x = randf_range(-MAX_GAZE, MAX_GAZE);
        const float target_y = randf_range(-MAX_GAZE * 0.6f, MAX_GAZE * 0.6f);

        if (fs.mood == Mood::SILLY) {
            if (randf() < 0.5f) {
                fs.eye_l.gaze_x_target = 8.0f;
                fs.eye_r.gaze_x_target = -8.0f;
            } else {
                fs.eye_l.gaze_x_target = -6.0f;
                fs.eye_r.gaze_x_target = 6.0f;
            }
        } else if (fs.mood == Mood::LOVE) {
            // Reduced wander amplitude + convergence maintained (still, adoring)
            const float li = clampf(fs.expression_intensity, 0.0f, 1.0f);
            fs.eye_l.gaze_x_target = target_x * 0.4f + 2.5f * li;
            fs.eye_r.gaze_x_target = target_x * 0.4f - 2.5f * li;
        } else {
            fs.eye_l.gaze_x_target = target_x;
            fs.eye_r.gaze_x_target = target_x;
        }

        if (fs.mood == Mood::LOVE) {
            fs.eye_l.gaze_y_target = target_y * 0.4f;
            fs.eye_r.gaze_y_target = target_y * 0.4f;
            fs.anim.next_idle = now + 2.5f + randf() * 3.0f;
        } else {
            fs.eye_l.gaze_y_target = target_y;
            fs.eye_r.gaze_y_target = target_y;
            fs.anim.next_idle = now + 1.0f + randf() * 2.0f;
        }
    }

    if (now > fs.anim.next_saccade) {
        const float jitter_x = randf_range(-0.5f, 0.5f);
        const float jitter_y = randf_range(-0.5f, 0.5f);
        fs.eye_l.gaze_x += jitter_x;
        fs.eye_r.gaze_x += jitter_x;
        fs.eye_l.gaze_y += jitter_y;
        fs.eye_r.gaze_y += jitter_y;
        fs.anim.next_saccade = now + randf_range(0.1f, 0.4f);
    }

    if (fs.talking) {
        fs.talking_phase += 15.0f * dt;
        const float e = clampf(fs.talking_energy, 0.0f, 1.0f);
        const float noise_open = sinf(fs.talking_phase) + sinf(fs.talking_phase * 2.3f);
        const float noise_width = cosf(fs.talking_phase * 0.7f);

        const float base_open = 0.2f + 0.5f * e;
        const float mod_open = fabsf(noise_open) * 0.6f * e;
        const float base_width = 1.0f;
        const float mod_width = noise_width * 0.3f * e;

        fs.mouth_open_target = fmaxf(fs.mouth_open_target, base_open + mod_open);
        fs.mouth_width_target = base_width + mod_width;

        const float bounce = fabsf(sinf(fs.talking_phase)) * 0.05f * e;
        fs.eye_l.height_scale_target += bounce;
        fs.eye_r.height_scale_target += bounce;
    }

    fs.eye_l.gaze_x = spring_step(fs.eye_l.gaze_x, fs.eye_l.gaze_x_target, fs.eye_l.vx);
    fs.eye_l.gaze_y = spring_step(fs.eye_l.gaze_y, fs.eye_l.gaze_y_target, fs.eye_l.vy);
    fs.eye_r.gaze_x = spring_step(fs.eye_r.gaze_x, fs.eye_r.gaze_x_target, fs.eye_r.vx);
    fs.eye_r.gaze_y = spring_step(fs.eye_r.gaze_y, fs.eye_r.gaze_y_target, fs.eye_r.vy);

    for (EyeState* eye : {&fs.eye_l, &fs.eye_r}) {
        eye->width_scale = tween(eye->width_scale, eye->width_scale_target, 0.2f);
        eye->height_scale = tween(eye->height_scale, eye->height_scale_target, 0.2f);
        eye->openness_target = eye->is_open ? 1.0f : 0.0f;
        eye->openness = tween(eye->openness, eye->openness_target, 0.4f);
        eye->width_scale_target = 1.0f;
        eye->height_scale_target = 1.0f;
    }

    fs.mouth_curve = tween(fs.mouth_curve, fs.mouth_curve_target, 0.2f);
    fs.mouth_open = tween(fs.mouth_open, fs.mouth_open_target, 0.4f);
    fs.mouth_width = tween(fs.mouth_width, fs.mouth_width_target, 0.2f);
    fs.mouth_offset_x = tween(fs.mouth_offset_x, fs.mouth_offset_x_target, 0.2f);
    fs.mouth_wave = tween(fs.mouth_wave, fs.mouth_wave_target, 0.1f);

    if (fs.anim.h_flicker) {
        const float dx = fs.anim.h_flicker_alt ? fs.anim.h_flicker_amp : -fs.anim.h_flicker_amp;
        fs.eye_l.gaze_x += dx;
        fs.eye_r.gaze_x += dx;
        fs.anim.h_flicker_alt = !fs.anim.h_flicker_alt;
    }

    if (fs.anim.v_flicker) {
        const float dy = fs.anim.v_flicker_alt ? fs.anim.v_flicker_amp : -fs.anim.v_flicker_amp;
        fs.eye_l.gaze_y += dy;
        fs.eye_r.gaze_y += dy;
        fs.anim.v_flicker_alt = !fs.anim.v_flicker_alt;
    }

    // NOD/HEADSHAKE post-spring gaze overrides (bypass spring for crisp kinematics)
    if (fs.anim.nod) {
        const float elapsed = now - fs.anim.nod_timer;
        const float gy = 4.0f * sinf(elapsed * 12.0f);
        fs.eye_l.gaze_y = gy;
        fs.eye_r.gaze_y = gy;
    }
    if (fs.anim.headshake) {
        const float elapsed = now - fs.anim.headshake_timer;
        const float gx = 5.0f * sinf(elapsed * 14.0f);
        fs.eye_l.gaze_x = gx;
        fs.eye_r.gaze_x = gx;
    }

    update_breathing(fs);
    update_sparkle(fs);
    update_fire(fs);

    if (fs.active_gesture != 0xFF && now > fs.active_gesture_until) {
        fs.active_gesture = 0xFF;
    }
}

float face_get_breath_scale(const FaceState& fs)
{
    if (!fs.fx.breathing) {
        return 1.0f;
    }
    return 1.0f + sinf(fs.fx.breath_phase) * fs.fx.breath_amount;
}

void face_get_emotion_color(const FaceState& fs, uint8_t& r, uint8_t& g, uint8_t& b)
{
    // System face color override takes priority (set by system_face_apply)
    if (fs.color_override_active) {
        r = fs.color_override_r;
        g = fs.color_override_g;
        b = fs.color_override_b;
        return;
    }

    int rr = 50;
    int gg = 150;
    int bb = 255;

    if (fs.anim.rage) {
        rr = 255;
        gg = 30;
        bb = 0;
    } else if (fs.anim.heart) {
        rr = 255;
        gg = 105;
        bb = 180;
    } else if (fs.anim.x_eyes) {
        rr = 200;
        gg = 40;
        bb = 40;
    } else {
        switch (fs.mood) {
        case Mood::HAPPY:
            rr = 0;
            gg = 255;
            bb = 200;
            break;
        case Mood::EXCITED:
            rr = 100;
            gg = 255;
            bb = 100;
            break;
        case Mood::CURIOUS:
            rr = 255;
            gg = 180;
            bb = 50;
            break;
        case Mood::SAD:
            rr = 70;
            gg = 110;
            bb = 210;
            break;
        case Mood::SCARED:
            rr = 180;
            gg = 50;
            bb = 255;
            break;
        case Mood::ANGRY:
            rr = 255;
            gg = 0;
            bb = 0;
            break;
        case Mood::SURPRISED:
            rr = 255;
            gg = 255;
            bb = 200;
            break;
        case Mood::SLEEPY:
            rr = 70;
            gg = 90;
            bb = 140;
            break;
        case Mood::LOVE:
            rr = 255;
            gg = 100;
            bb = 150;
            break;
        case Mood::SILLY:
            rr = 200;
            gg = 255;
            bb = 50;
            break;
        case Mood::THINKING:
            rr = 80;
            gg = 135;
            bb = 220;
            break;
        case Mood::CONFUSED:
            rr = 200;
            gg = 160;
            bb = 80;
            break;
        default:
            rr = 50;
            gg = 150;
            bb = 255;
            break;
        }
    }

    const float intensity = clampf(fs.expression_intensity, 0.0f, 1.0f);
    const int   nr = 50;
    const int   ng = 150;
    const int   nb = 255;

    rr = static_cast<int>(nr + (rr - nr) * intensity);
    gg = static_cast<int>(ng + (gg - ng) * intensity);
    bb = static_cast<int>(nb + (bb - nb) * intensity);

    rr = static_cast<int>(clampf(static_cast<float>(rr), 0.0f, 255.0f));
    gg = static_cast<int>(clampf(static_cast<float>(gg), 0.0f, 255.0f));
    bb = static_cast<int>(clampf(static_cast<float>(bb), 0.0f, 255.0f));

    r = static_cast<uint8_t>(rr);
    g = static_cast<uint8_t>(gg);
    b = static_cast<uint8_t>(bb);
}

void face_blink(FaceState& fs)
{
    fs.eye_l.is_open = false;
    fs.eye_r.is_open = false;
    fs.eye_l.openness_target = 0.0f;
    fs.eye_r.openness_target = 0.0f;
    set_active_gesture(fs, GestureId::BLINK, 0.18f, now_s());
}

void face_wink_left(FaceState& fs)
{
    fs.eye_l.is_open = false;
    fs.eye_l.openness_target = 0.0f;
    set_active_gesture(fs, GestureId::WINK_L, 0.20f, now_s());
}

void face_wink_right(FaceState& fs)
{
    fs.eye_r.is_open = false;
    fs.eye_r.openness_target = 0.0f;
    set_active_gesture(fs, GestureId::WINK_R, 0.20f, now_s());
}

void face_set_gaze(FaceState& fs, float x, float y)
{
    fs.eye_l.gaze_x_target = clampf(x, -MAX_GAZE, MAX_GAZE);
    fs.eye_l.gaze_y_target = clampf(y, -MAX_GAZE, MAX_GAZE);
    fs.eye_r.gaze_x_target = clampf(x, -MAX_GAZE, MAX_GAZE);
    fs.eye_r.gaze_y_target = clampf(y, -MAX_GAZE, MAX_GAZE);
}

void face_set_mood(FaceState& fs, Mood mood)
{
    fs.mood = mood;
}

void face_set_expression_intensity(FaceState& fs, float intensity)
{
    fs.expression_intensity = clampf(intensity, 0.0f, 1.0f);
}

void face_trigger_gesture(FaceState& fs, GestureId gesture, uint16_t duration_ms)
{
    const float now = now_s();
    auto        dur_s = [duration_ms](float fallback) -> float {
        if (duration_ms == 0) {
            return fallback;
        }
        return fmaxf(0.08f, static_cast<float>(duration_ms) / 1000.0f);
    };

    switch (gesture) {
    case GestureId::BLINK:
        face_blink(fs);
        set_active_gesture(fs, gesture, dur_s(0.18f), now);
        break;
    case GestureId::WINK_L:
        face_wink_left(fs);
        set_active_gesture(fs, gesture, dur_s(0.20f), now);
        break;
    case GestureId::WINK_R:
        face_wink_right(fs);
        set_active_gesture(fs, gesture, dur_s(0.20f), now);
        break;
    case GestureId::NOD:
        fs.anim.nod = true;
        fs.anim.nod_timer = now;
        fs.anim.nod_duration = dur_s(0.35f);
        set_active_gesture(fs, gesture, fs.anim.nod_duration, now);
        break;
    case GestureId::HEADSHAKE:
        fs.anim.headshake = true;
        fs.anim.headshake_timer = now;
        fs.anim.headshake_duration = dur_s(0.35f);
        set_active_gesture(fs, gesture, fs.anim.headshake_duration, now);
        break;
    case GestureId::WIGGLE:
        fs.anim.confused = true;
        fs.anim.confused_timer = now;
        fs.anim.confused_toggle = true;
        fs.anim.confused_duration = dur_s(0.60f);
        fs.anim.laugh = true;
        fs.anim.laugh_timer = now;
        fs.anim.laugh_toggle = true;
        fs.anim.laugh_duration = dur_s(0.60f);
        set_active_gesture(fs, gesture, dur_s(0.60f), now);
        break;
    case GestureId::LAUGH:
        fs.anim.laugh = true;
        fs.anim.laugh_timer = now;
        fs.anim.laugh_toggle = true;
        fs.anim.laugh_duration = dur_s(0.50f);
        set_active_gesture(fs, gesture, fs.anim.laugh_duration, now);
        break;
    case GestureId::CONFUSED:
        fs.anim.confused = true;
        fs.anim.confused_timer = now;
        fs.anim.confused_toggle = true;
        fs.anim.confused_duration = dur_s(0.50f);
        set_active_gesture(fs, gesture, fs.anim.confused_duration, now);
        break;
    case GestureId::RAGE:
        fs.anim.rage = true;
        fs.anim.rage_timer = now;
        fs.anim.rage_duration = dur_s(3.0f);
        set_active_gesture(fs, gesture, fs.anim.rage_duration, now);
        break;
    case GestureId::HEART:
        fs.anim.heart = true;
        fs.anim.heart_timer = now;
        fs.anim.heart_duration = dur_s(2.0f);
        set_active_gesture(fs, gesture, fs.anim.heart_duration, now);
        break;
    case GestureId::X_EYES:
        fs.anim.x_eyes = true;
        fs.anim.x_eyes_timer = now;
        fs.anim.x_eyes_duration = dur_s(2.5f);
        set_active_gesture(fs, gesture, fs.anim.x_eyes_duration, now);
        break;
    case GestureId::SLEEPY:
        fs.anim.sleepy = true;
        fs.anim.sleepy_timer = now;
        fs.anim.sleepy_duration = dur_s(3.0f);
        set_active_gesture(fs, gesture, fs.anim.sleepy_duration, now);
        break;
    case GestureId::SURPRISE:
        fs.anim.surprise = true;
        fs.anim.surprise_timer = now;
        fs.anim.surprise_duration = dur_s(0.8f);
        set_active_gesture(fs, gesture, fs.anim.surprise_duration, now);
        break;
    }
}

void face_set_system_mode(FaceState& fs, SystemMode mode, float param)
{
    if (fs.system.mode == mode) {
        fs.system.param = param;
        return;
    }
    fs.system.mode = mode;
    fs.system.timer = now_s();
    fs.system.phase = 0;
    fs.system.param = param;
}
