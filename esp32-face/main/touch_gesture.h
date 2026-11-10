#pragma once
// Whole-screen touch gesture classifier (spec §9.5).
//
// Pure C++ with no ESP-IDF/LVGL dependencies so it can be unit tested on the
// host (esp32-face/test/). Times are wrap-safe uint32 milliseconds.
//
//   tap        : released < tap_max_ms after touch-down, never moved > move_tol_px
//   long-press : held >= long_press_ms, never moved > move_tol_px; fires once at the
//                threshold while still held (release afterwards reports nothing)
//   drag / pet : moved > move_tol_px at any point -> no gesture for this touch
//   in-between : released between tap_max_ms and long_press_ms -> no gesture

#include <cstdint>

struct TouchGestureConfig {
    uint32_t tap_max_ms;
    uint32_t long_press_ms;
    uint32_t ring_show_ms;
    int      move_tol_px;
};

enum class TouchGestureEvent : uint8_t {
    NONE = 0,
    TAP = 1,
    LONG_PRESS = 2,
};

class TouchGesture
{
  public:
    explicit TouchGesture(const TouchGestureConfig& cfg) : cfg_(cfg) {}

    void              press(int x, int y, uint32_t now_ms);
    void              move(int x, int y, uint32_t now_ms); // may cancel; call tick() to fire long-press
    TouchGestureEvent release(int x, int y, uint32_t now_ms);
    TouchGestureEvent tick(uint32_t now_ms); // returns LONG_PRESS exactly once at the threshold
    void              reset();               // drop the current touch (e.g. system overlay shown)

    bool down() const
    {
        return down_;
    }
    bool cancelled() const
    {
        return cancelled_;
    }
    bool long_fired() const
    {
        return long_fired_;
    }
    int x() const
    {
        return x_;
    }
    int y() const
    {
        return y_;
    }
    int press_x() const
    {
        return x0_;
    }
    int press_y() const
    {
        return y0_;
    }

    // Long-press ring fill: <0 = hidden, else 0..1 between ring_show_ms and long_press_ms.
    float ring_progress(uint32_t now_ms) const;

    // Milliseconds since the long-press fired (UINT32_MAX if it has not fired).
    uint32_t ms_since_long_fire(uint32_t now_ms) const;

  private:
    static uint32_t elapsed(uint32_t now_ms, uint32_t since_ms)
    {
        return now_ms - since_ms;
    }

    TouchGestureConfig cfg_;
    bool               down_ = false;
    bool               cancelled_ = false;
    bool               long_fired_ = false;
    int                x0_ = 0;
    int                y0_ = 0;
    int                x_ = 0;
    int                y_ = 0;
    uint32_t           t0_ms_ = 0;
    uint32_t           fire_ms_ = 0;
};
