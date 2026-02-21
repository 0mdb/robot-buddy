#pragma once
// Cross-task shared state for face commands and touch/button telemetry.

#include <atomic>
#include <cstdint>
#include "face_state.h"

// ---- Latched face command channels (writer: usb_rx_task, reader: face_ui_task) ----
// State/system/talking are last-value channels so high-rate talking updates do not
// erase mood/system state updates.

extern std::atomic<uint8_t> g_cmd_state_mood;
extern std::atomic<uint8_t> g_cmd_state_intensity;
extern std::atomic<int8_t>  g_cmd_state_gaze_x;
extern std::atomic<int8_t>  g_cmd_state_gaze_y;
extern std::atomic<uint8_t> g_cmd_state_brightness;
extern std::atomic<uint32_t> g_cmd_state_us;

extern std::atomic<uint8_t> g_cmd_system_mode;
extern std::atomic<uint8_t> g_cmd_system_param;
extern std::atomic<uint32_t> g_cmd_system_us;

extern std::atomic<uint8_t> g_cmd_talking;
extern std::atomic<uint8_t> g_cmd_talking_energy;
extern std::atomic<uint32_t> g_cmd_talking_us;

extern std::atomic<uint8_t> g_cmd_flags;
extern std::atomic<uint32_t> g_cmd_flags_us;

// ---- Gesture queue (SPSC: writer usb_rx_task, reader face_ui_task) ----

struct GestureEvent {
    uint8_t  gesture_id   = 0;
    uint16_t duration_ms  = 0;
    uint32_t timestamp_us = 0;
};

struct GestureQueue {
    static constexpr uint8_t CAP = 16;
    GestureEvent buf[CAP]{};
    std::atomic<uint8_t> head{0};  // next write index
    std::atomic<uint8_t> tail{0};  // next read index

    bool push(const GestureEvent& ev) {
        const uint8_t h = head.load(std::memory_order_relaxed);
        const uint8_t n = static_cast<uint8_t>((h + 1) % CAP);
        const uint8_t t = tail.load(std::memory_order_acquire);
        if (n == t) {
            return false;  // full
        }
        buf[h] = ev;
        head.store(n, std::memory_order_release);
        return true;
    }

    bool pop(GestureEvent* out) {
        const uint8_t t = tail.load(std::memory_order_relaxed);
        const uint8_t h = head.load(std::memory_order_acquire);
        if (t == h) {
            return false;  // empty
        }
        if (out) {
            *out = buf[t];
        }
        tail.store(static_cast<uint8_t>((t + 1) % CAP), std::memory_order_release);
        return true;
    }
};

extern GestureQueue g_gesture_queue;

// ---- Touch event buffer (writer: LVGL context, reader: telemetry_task) ----

struct TouchSample {
    uint8_t  event_type   = 0xFF;  // 0xFF = no event
    uint16_t x            = 0;
    uint16_t y            = 0;
    uint32_t timestamp_us = 0;
};

struct TouchBuffer {
    TouchSample              buf[2]{};
    std::atomic<TouchSample*> current{&buf[0]};
    uint8_t                  write_idx = 0;

    TouchSample* write_slot() { return &buf[write_idx]; }
    void publish() {
        current.store(&buf[write_idx], std::memory_order_release);
        write_idx ^= 1;
    }
    const TouchSample* read() const {
        return current.load(std::memory_order_acquire);
    }
};

// ---- Button event buffer (writer: LVGL context, reader: telemetry_task) ----

struct ButtonEventSample {
    uint8_t  button_id    = 0xFF;  // 0xFF = no event
    uint8_t  event_type   = 0xFF;  // 0xFF = no event
    uint8_t  state        = 0;     // toggle state for PTT
    uint32_t timestamp_us = 0;
};

struct ButtonEventBuffer {
    ButtonEventSample              buf[2]{};
    std::atomic<ButtonEventSample*> current{&buf[0]};
    uint8_t                        write_idx = 0;

    ButtonEventSample* write_slot() { return &buf[write_idx]; }
    void publish() {
        current.store(&buf[write_idx], std::memory_order_release);
        write_idx ^= 1;
    }
    const ButtonEventSample* read() const {
        return current.load(std::memory_order_acquire);
    }
};

// ---- Globals ----
extern TouchBuffer       g_touch;
extern ButtonEventBuffer g_button;
extern std::atomic<bool> g_touch_active;
extern std::atomic<bool> g_talking_active;
extern std::atomic<bool> g_ptt_listening;

// Current face state (read by telemetry task for status reporting)
extern std::atomic<uint8_t> g_current_mood;
extern std::atomic<uint8_t> g_active_gesture;   // 0xFF = none
extern std::atomic<uint8_t> g_system_mode;

// v2 command causality tracking (writer: usb_rx for seq, face_ui for applied_us)
extern std::atomic<uint32_t> g_cmd_seq_last;     // last received cmd seq (from v2 envelope)
extern std::atomic<uint32_t> g_cmd_applied_us;   // when display buffer was committed
