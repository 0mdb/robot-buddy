#pragma once
// Cross-task shared state for face commands and touch/button telemetry.

#include <atomic>
#include <cstdint>
#include "face_state.h"

// ---- Latched face command channels (writer: usb_rx_task, reader: face_ui_task) ----
// State/system/talking are last-value channels so high-rate talking updates do not
// erase mood/system state updates.

extern std::atomic<uint8_t>  g_cmd_state_mood;
extern std::atomic<uint8_t>  g_cmd_state_intensity;
extern std::atomic<int8_t>   g_cmd_state_gaze_x;
extern std::atomic<int8_t>   g_cmd_state_gaze_y;
extern std::atomic<uint8_t>  g_cmd_state_brightness;
extern std::atomic<uint32_t> g_cmd_state_us;

extern std::atomic<uint8_t>  g_cmd_system_mode;
extern std::atomic<uint8_t>  g_cmd_system_param;
extern std::atomic<uint32_t> g_cmd_system_us;

extern std::atomic<uint8_t>  g_cmd_talking;
extern std::atomic<uint8_t>  g_cmd_talking_energy;
extern std::atomic<uint32_t> g_cmd_talking_us;

extern std::atomic<uint8_t>  g_cmd_flags;
extern std::atomic<uint32_t> g_cmd_flags_us;

extern std::atomic<uint8_t>  g_cmd_conv_state;
extern std::atomic<uint32_t> g_cmd_conv_state_us;

// ---- Gesture queue (SPSC: writer usb_rx_task, reader face_ui_task) ----

struct GestureEvent {
    uint8_t  gesture_id = 0;
    uint16_t duration_ms = 0;
    uint32_t timestamp_us = 0;
};

// Lock-free single-producer / single-consumer ring. Only the producer moves
// head and only the consumer moves tail, so neither side ever writes the
// other's index. Holds CAP-1 items; push() drops the new item when full.
template <typename T, uint8_t CAP> struct SpscQueue {
    T                    buf[CAP]{};
    std::atomic<uint8_t> head{0}; // next write index (producer only)
    std::atomic<uint8_t> tail{0}; // next read index (consumer only)

    bool push(const T& item)
    {
        const uint8_t h = head.load(std::memory_order_relaxed);
        const uint8_t n = static_cast<uint8_t>((h + 1) % CAP);
        const uint8_t t = tail.load(std::memory_order_acquire);
        if (n == t) {
            return false; // full
        }
        buf[h] = item;
        head.store(n, std::memory_order_release);
        return true;
    }

    // Copy the oldest item without removing it.
    bool peek(T* out) const
    {
        const uint8_t t = tail.load(std::memory_order_relaxed);
        const uint8_t h = head.load(std::memory_order_acquire);
        if (t == h) {
            return false; // empty
        }
        if (out) {
            *out = buf[t];
        }
        return true;
    }

    // Remove the oldest item (call after a successful peek()).
    void drop()
    {
        const uint8_t t = tail.load(std::memory_order_relaxed);
        if (t != head.load(std::memory_order_acquire)) {
            tail.store(static_cast<uint8_t>((t + 1) % CAP), std::memory_order_release);
        }
    }

    bool pop(T* out)
    {
        if (!peek(out)) {
            return false;
        }
        drop();
        return true;
    }
};

using GestureQueue = SpscQueue<GestureEvent, 16>;

extern GestureQueue g_gesture_queue;

// ---- Touch event queue (writer: LVGL context, reader: telemetry_task) ----

struct TouchSample {
    uint8_t  event_type = 0xFF; // 0xFF = no event
    uint16_t x = 0;
    uint16_t y = 0;
    uint32_t timestamp_us = 0;
};

// Touch samples are queued, not latched, so PRESS/RELEASE are never overwritten
// by the PRESSING stream. When full, new samples are dropped.
using TouchQueue = SpscQueue<TouchSample, 32>;

// ---- Button event queue (writer: LVGL context, reader: telemetry_task) ----

struct ButtonEventSample {
    uint8_t  button_id = 0xFF;  // 0xFF = no event
    uint8_t  event_type = 0xFF; // 0xFF = no event
    uint8_t  state = 0;         // toggle state for PTT
    uint32_t timestamp_us = 0;
};

// Queued so RELEASE + TOGGLE/CLICK published back to back all reach the host.
using ButtonEventQueue = SpscQueue<ButtonEventSample, 16>;

// ---- Face perf snapshot buffer (writer: face_ui_task, reader: telemetry_task) ----

struct FacePerfSnapshot {
    uint32_t window_frames = 0;
    uint32_t frame_us_avg = 0;
    uint32_t frame_us_max = 0;
    uint32_t render_us_avg = 0;
    uint32_t render_us_max = 0;
    uint32_t eyes_us_avg = 0;
    uint32_t mouth_us_avg = 0;
    uint32_t border_us_avg = 0;
    uint32_t effects_us_avg = 0;
    uint32_t overlay_us_avg = 0;
    uint32_t dirty_px_avg = 0;
    uint32_t spi_bytes_per_s = 0;
    uint32_t cmd_rx_to_apply_us_avg = 0;
    uint16_t perf_sample_div = 0;
    uint8_t  dirty_rect_enabled = 0;
    uint8_t  afterglow_downsample = 0;
};

struct FacePerfBuffer {
    FacePerfSnapshot               buf[2]{};
    std::atomic<FacePerfSnapshot*> current{&buf[0]};
    uint8_t                        write_idx = 0;

    FacePerfSnapshot* write_slot()
    {
        return &buf[write_idx];
    }
    void publish()
    {
        current.store(&buf[write_idx], std::memory_order_release);
        write_idx ^= 1;
    }
    const FacePerfSnapshot* read() const
    {
        return current.load(std::memory_order_acquire);
    }
};

// ---- Globals ----
extern TouchQueue        g_touch;
extern ButtonEventQueue  g_button;
extern FacePerfBuffer    g_face_perf;
extern std::atomic<bool> g_touch_active;
extern std::atomic<bool> g_talking_active;
// Mirror of host conversation state (true while conv_state == PTT). Written only
// by face_ui_task when SET_CONV_STATE is applied; the host owns PTT state.
extern std::atomic<bool> g_ptt_listening;

// Boot diagnostics (app_main) and host-link state (face_ui_task), for HEARTBEAT.
extern std::atomic<uint8_t>  g_reset_reason; // esp_reset_reason_t
extern std::atomic<uint32_t> g_boot_count;   // boots since last power-on (1 = clean power-on)
extern std::atomic<bool>     g_host_link_lost;
extern std::atomic<uint32_t> g_last_host_rx_us; // any packet from the host (usb_rx_task)

// Current face state (read by telemetry task for status reporting)
extern std::atomic<uint8_t> g_current_mood;
extern std::atomic<uint8_t> g_active_gesture; // 0xFF = none
extern std::atomic<uint8_t> g_system_mode;

// v2 command causality tracking (writer: usb_rx for seq, face_ui for applied_us)
extern std::atomic<uint32_t> g_cmd_seq_last;   // last received cmd seq (from v2 envelope)
extern std::atomic<uint32_t> g_cmd_applied_us; // when display buffer was committed
