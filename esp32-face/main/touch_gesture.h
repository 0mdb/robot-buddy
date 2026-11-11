#pragma once
// Whole-screen touch gesture classifier (spec §9.5).
//
// Pure C++ with no ESP-IDF/LVGL dependencies so it can be unit tested on the
// host (esp32-face/test/). Times are wrap-safe uint32 milliseconds.
//
//   tap        : released < tap_max_ms after touch-down, never moved > move_tol_px
//   long-press : held >= long_press_ms, never moved > move_tol_px; fires once at the
//                threshold while still held (release afterwards reports nothing)
//   drag       : moved > move_tol_px at any point -> no tap / long-press for this touch
//   pet        : a drag whose finger path reaches pet_path_px; fires PET once (via tick)
//   in-between : released between tap_max_ms and long_press_ms -> no gesture

#include <cstdint>

struct TouchGestureConfig {
    uint32_t tap_max_ms;
    uint32_t long_press_ms;
    uint32_t ring_show_ms;
    int      move_tol_px;
    int      pet_path_px;
};

enum class TouchGestureEvent : uint8_t {
    NONE = 0,
    TAP = 1,
    LONG_PRESS = 2,
    PET = 3,
};

class TouchGesture
{
  public:
    explicit TouchGesture(const TouchGestureConfig& cfg) : cfg_(cfg) {}

    void              press(int x, int y, uint32_t now_ms);
    void              move(int x, int y, uint32_t now_ms); // may cancel; call tick() to fire long-press
    TouchGestureEvent release(int x, int y, uint32_t now_ms);
    TouchGestureEvent tick(uint32_t now_ms); // LONG_PRESS once at the threshold, or PET once per stroke
    void              reset();               // drop the current touch (e.g. system overlay shown)

    bool down() const
    {
        return down_;
    }
    bool cancelled() const
    {
        return cancelled_;
    }
    bool petting() const // finger down and stroking (PET has fired for this touch)
    {
        return down_ && pet_fired_;
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
    bool               pet_fired_ = false;
    float              path_px_ = 0.0f;
    int                x0_ = 0;
    int                y0_ = 0;
    int                x_ = 0;
    int                y_ = 0;
    uint32_t           t0_ms_ = 0;
    uint32_t           fire_ms_ = 0;
};
