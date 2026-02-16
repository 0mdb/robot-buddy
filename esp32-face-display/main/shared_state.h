#pragma once
// Double-buffered cross-task state for face commands and touch events.
// Writer publishes atomically; reader gets latest snapshot.

#include <atomic>
#include <cstdint>
#include "face_state.h"

// ---- Face command buffer (writer: usb_rx_task, reader: face_ui_task) ----

struct FaceCommand {
    uint8_t  mood_id      = 0;
    uint8_t  intensity    = 255;
    int8_t   gaze_x       = 0;
    int8_t   gaze_y       = 0;
    uint8_t  brightness   = 200;
    bool     has_gesture   = false;
    uint8_t  gesture_id   = 0;
    uint16_t gesture_dur  = 0;
    bool     has_system    = false;
    uint8_t  system_mode  = 0;
    uint8_t  system_param = 0;
};

struct FaceCommandBuffer {
    FaceCommand              buf[2]{};
    std::atomic<FaceCommand*> current{&buf[0]};
    std::atomic<uint32_t>    last_cmd_us{0};
    uint8_t                  write_idx = 0;

    FaceCommand* write_slot() { return &buf[write_idx]; }
    void publish(uint32_t now_us) {
        current.store(&buf[write_idx], std::memory_order_release);
        last_cmd_us.store(now_us, std::memory_order_release);
        write_idx ^= 1;
    }
    const FaceCommand* read() const {
        return current.load(std::memory_order_acquire);
    }
};

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

// ---- Globals ----

extern FaceCommandBuffer g_face_cmd;
extern TouchBuffer       g_touch;
extern std::atomic<bool> g_touch_active;

// Current face state (read by telemetry task for status reporting)
extern std::atomic<uint8_t> g_current_mood;
extern std::atomic<uint8_t> g_active_gesture;   // 0xFF = none
extern std::atomic<uint8_t> g_system_mode;
