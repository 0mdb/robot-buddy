#include "face_ui.h"
#include "config.h"
#include "shared_state.h"
#include "display.h"
#include "led.h"
#include "protocol.h"

#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <cmath>
#include <cstring>

static const char* TAG = "face_ui";
static constexpr uint32_t TALKING_CMD_TIMEOUT_MS = 450;
static constexpr int BTN_BAR_H = 54;
static constexpr int BTN_W = 138;
static constexpr int BTN_H = 42;

static float now_s();

// ---- LVGL objects ----
static lv_obj_t* canvas_obj = nullptr;
static lv_color_t* canvas_buf = nullptr;
static lv_obj_t* ptt_btn = nullptr;
static lv_obj_t* ptt_label = nullptr;
static lv_obj_t* action_btn = nullptr;

static void publish_touch_sample(uint8_t event_type, int x, int y);
static void publish_button_event(FaceButtonId button_id, FaceButtonEventType event_type, uint8_t state);
static void update_ptt_button_visual(bool listening);
static void root_touch_event_cb(lv_event_t* e);
static void ptt_button_event_cb(lv_event_t* e);
static void action_button_event_cb(lv_event_t* e);

// ---- Drawing helpers ----

static lv_color_t rgb_to_color(uint8_t r, uint8_t g, uint8_t b)
{
    return lv_color_make(r, g, b);
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

static void render_eye(lv_color_t* buf, const EyeState& eye, const FaceState& fs,
                       float center_x, float center_y)
{
    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);
    lv_color_t eye_color = rgb_to_color(r, g, b);
    lv_color_t black = rgb_to_color(0, 0, 0);

    float breath = face_get_breath_scale(fs);

    // Eye dimensions with scale and breathing
    float ew = EYE_WIDTH * eye.width_scale * breath;
    float eh = EYE_HEIGHT * eye.height_scale * eye.openness * breath;

    if (eh < 2.0f) return;  // eye closed

    // Eye position offset by gaze
    float ex = center_x + eye.gaze_x * GAZE_EYE_SHIFT - ew / 2.0f;
    float ey = center_y + eye.gaze_y * GAZE_EYE_SHIFT - eh / 2.0f;

    int corner = static_cast<int>(EYE_CORNER_R * fminf(eye.width_scale, eye.height_scale));

    // Draw eye body
    draw_filled_rounded_rect(buf, (int)ex, (int)ey, (int)ew, (int)eh, corner, eye_color);

    // Draw pupil (darker circle) if not solid_eye mode
    if (!fs.solid_eye) {
        float px = center_x + eye.gaze_x * GAZE_PUPIL_SHIFT;
        float py = center_y + eye.gaze_y * GAZE_PUPIL_SHIFT;
        int pr = static_cast<int>(PUPIL_R * eye.openness);
        if (pr > 1) {
            draw_filled_circle(buf, (int)px, (int)py, pr, rgb_to_color(10, 20, 50));
        }
    }

    // ---- Eyelid overlays (draw black rects to mask parts of the eye) ----

    // Tired: droop from top
    if (fs.eyelids.tired > 0.01f) {
        int lid_h = static_cast<int>(eh * 0.5f * fs.eyelids.tired);
        draw_filled_rect(buf, (int)ex, (int)ey, (int)ew, lid_h, black);
    }

    // Angry: diagonal slant from inner corner
    if (fs.eyelids.angry > 0.01f) {
        int lid_h = static_cast<int>(eh * 0.4f * fs.eyelids.angry);
        // Simplified: draw a triangle-ish shape using stacked rects
        bool is_left = (center_x < SCREEN_W / 2);
        for (int row = 0; row < lid_h; row++) {
            float frac = static_cast<float>(row) / fmaxf(1.0f, static_cast<float>(lid_h));
            int w;
            int lx;
            if (is_left) {
                // Left eye: wider on right (inner) side
                w = static_cast<int>(ew * (1.0f - frac));
                lx = static_cast<int>(ex + ew - w);
            } else {
                // Right eye: wider on left (inner) side
                w = static_cast<int>(ew * (1.0f - frac));
                lx = static_cast<int>(ex);
            }
            int py = static_cast<int>(ey) + row;
            if (py >= 0 && py < SCREEN_H && w > 0) {
                draw_filled_rect(buf, lx, py, w, 1, black);
            }
        }
    }

    // Happy: mask bottom portion (uplifted)
    if (fs.eyelids.happy > 0.01f) {
        int lid_h = static_cast<int>(eh * 0.4f * fs.eyelids.happy);
        int ly = static_cast<int>(ey + eh - lid_h);
        draw_filled_rect(buf, (int)ex, ly, (int)ew, lid_h, black);
    }
}

static void render_mouth(lv_color_t* buf, const FaceState& fs)
{
    if (!fs.show_mouth) return;

    uint8_t r, g, b;
    face_get_emotion_color(fs, r, g, b);
    lv_color_t color = rgb_to_color(r, g, b);

    float cx = MOUTH_CX + fs.mouth_offset_x * 8.0f;
    float cy = MOUTH_CY;
    float hw = MOUTH_HALF_W * fs.mouth_width;
    float curve = fs.mouth_curve;
    float thick = MOUTH_THICKNESS;

    // Draw mouth as a series of horizontal lines forming a curve
    int num_points = static_cast<int>(hw * 2);
    for (int i = 0; i < num_points; i++) {
        float t = static_cast<float>(i) / static_cast<float>(num_points - 1);  // 0..1
        float x_off = -hw + 2.0f * hw * t;

        // Quadratic curve: center dips/rises by curve amount
        float parabola = 1.0f - 4.0f * (t - 0.5f) * (t - 0.5f);
        float y_off = -curve * 30.0f * parabola;

        // Wave distortion (rage)
        if (fs.mouth_wave > 0.01f) {
            y_off += fs.mouth_wave * 5.0f * sinf(t * 12.0f + now_s() * 8.0f);
        }

        int px = static_cast<int>(cx + x_off);
        int py = static_cast<int>(cy + y_off);

        // Draw a thick dot at each point
        int th = static_cast<int>(thick);
        draw_filled_rect(buf, px - th / 2, py - th / 2, th, th, color);

        // Open mouth fill
        if (fs.mouth_open > 0.05f) {
            int open_h = static_cast<int>(fs.mouth_open * 20.0f * parabola);
            if (open_h > 0) {
                draw_filled_rect(buf, px - th / 2, py, th, open_h, color);
            }
        }
    }
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
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(0, p.x, p.y);
    } else if (code == LV_EVENT_PRESSING) {
        g_touch_active.store(true, std::memory_order_relaxed);
        publish_touch_sample(2, p.x, p.y);
    } else if (code == LV_EVENT_RELEASED) {
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

    ESP_LOGI(TAG, "face UI created (%dx%d canvas in PSRAM)", SCREEN_W, SCREEN_H);
}

void face_ui_update(const FaceState& fs)
{
    if (!canvas_buf) return;

    // Clear to black
    memset(canvas_buf, 0, SCREEN_W * SCREEN_H * sizeof(lv_color_t));

    // Render eyes
    render_eye(canvas_buf, fs.eye_l, fs, LEFT_EYE_CX, LEFT_EYE_CY);
    render_eye(canvas_buf, fs.eye_r, fs, RIGHT_EYE_CX, RIGHT_EYE_CY);

    // Render mouth
    render_mouth(canvas_buf, fs);

    // Invalidate canvas to trigger LVGL refresh
    lv_obj_invalidate(canvas_obj);
}

// ---- FreeRTOS task ----

// Global state instances
FaceCommandBuffer g_face_cmd;
TouchBuffer       g_touch;
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
    uint32_t last_cmd_us = 0;
    uint32_t last_talking_cmd_us = 0;
    bool last_led_talking = false;
    bool last_led_listening = false;

    while (true) {
        const uint32_t now_us = static_cast<uint32_t>(esp_timer_get_time());
        // 1. Read latest command (atomic)
        const FaceCommand* cmd = g_face_cmd.read();
        uint32_t cmd_us = g_face_cmd.last_cmd_us.load(std::memory_order_acquire);

        // 2. Apply new commands if updated
        if (cmd_us != last_cmd_us) {
            last_cmd_us = cmd_us;

            if (cmd->has_state) {
                // Apply mood
                if (cmd->mood_id <= static_cast<uint8_t>(Mood::THINKING)) {
                    face_set_mood(fs, static_cast<Mood>(cmd->mood_id));
                }

                // Apply gaze (scale i8 to float: -128..127 → -MAX_GAZE..+MAX_GAZE)
                float gx = static_cast<float>(cmd->gaze_x) / 128.0f * MAX_GAZE;
                float gy = static_cast<float>(cmd->gaze_y) / 128.0f * MAX_GAZE;
                face_set_gaze(fs, gx, gy);

                // Apply brightness
                display_set_backlight(cmd->brightness);
            }

            // Apply gesture (one-shot)
            if (cmd->has_gesture && cmd->gesture_id <= static_cast<uint8_t>(GestureId::WIGGLE)) {
                face_trigger_gesture(fs, static_cast<GestureId>(cmd->gesture_id), cmd->gesture_dur);
            }

            // Apply system mode
            if (cmd->has_system) {
                float param = static_cast<float>(cmd->system_param) / 255.0f;
                face_set_system_mode(fs, static_cast<SystemMode>(cmd->system_mode), param);
            }

            if (cmd->has_talking) {
                fs.talking = cmd->talking;
                fs.talking_energy = static_cast<float>(cmd->talking_energy) / 255.0f;
                if (!fs.talking) {
                    fs.talking_energy = 0.0f;
                }
                last_talking_cmd_us = cmd_us;
            }
        }

        if (fs.talking && last_talking_cmd_us != 0) {
            const uint32_t age_us = now_us - last_talking_cmd_us;
            if (age_us > TALKING_CMD_TIMEOUT_MS * 1000U) {
                fs.talking = false;
                fs.talking_energy = 0.0f;
            }
        }

        // 3. Advance animations
        face_state_update(fs);

        // 4. Update telemetry atomics
        g_current_mood.store(static_cast<uint8_t>(fs.mood), std::memory_order_relaxed);
        g_active_gesture.store(
            fs.anim.heart ? static_cast<uint8_t>(GestureId::HEART) :
            fs.anim.rage ? static_cast<uint8_t>(GestureId::RAGE) :
            fs.anim.surprise ? static_cast<uint8_t>(GestureId::SURPRISE) :
            fs.anim.confused ? static_cast<uint8_t>(GestureId::CONFUSED) :
            fs.anim.laugh ? static_cast<uint8_t>(GestureId::LAUGH) :
            fs.anim.sleepy ? static_cast<uint8_t>(GestureId::SLEEPY) :
            fs.anim.x_eyes ? static_cast<uint8_t>(GestureId::X_EYES) :
            0xFF,
            std::memory_order_relaxed);
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

        // 5. Render under LVGL lock
        if (lvgl_port_lock(100)) {
            face_ui_update(fs);
            lvgl_port_unlock();
        }

        // 6. Sleep for frame period
        vTaskDelay(pdMS_TO_TICKS(1000 / ANIM_FPS));
    }
}
