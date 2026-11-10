#include "touch_gesture.h"

#include <climits>

void TouchGesture::press(int x, int y, uint32_t now_ms)
{
    down_ = true;
    cancelled_ = false;
    long_fired_ = false;
    x0_ = x_ = x;
    y0_ = y_ = y;
    t0_ms_ = now_ms;
    fire_ms_ = 0;
}

void TouchGesture::move(int x, int y, uint32_t now_ms)
{
    (void)now_ms;
    if (!down_) {
        return;
    }
    x_ = x;
    y_ = y;
    if (cancelled_ || long_fired_) {
        return;
    }
    const int dx = x - x0_;
    const int dy = y - y0_;
    const int tol = cfg_.move_tol_px;
    if (dx * dx + dy * dy > tol * tol) {
        cancelled_ = true; // drag / pet: no gesture for this touch
    }
}

TouchGestureEvent TouchGesture::tick(uint32_t now_ms)
{
    if (!down_ || cancelled_ || long_fired_) {
        return TouchGestureEvent::NONE;
    }
    if (elapsed(now_ms, t0_ms_) >= cfg_.long_press_ms) {
        long_fired_ = true;
        fire_ms_ = now_ms;
        return TouchGestureEvent::LONG_PRESS;
    }
    return TouchGestureEvent::NONE;
}

TouchGestureEvent TouchGesture::release(int x, int y, uint32_t now_ms)
{
    if (!down_) {
        return TouchGestureEvent::NONE;
    }
    move(x, y, now_ms);
    // A long-press that crossed its threshold between the last tick and release still counts.
    TouchGestureEvent ev = tick(now_ms);
    if (ev == TouchGestureEvent::NONE && !cancelled_ && !long_fired_ && elapsed(now_ms, t0_ms_) < cfg_.tap_max_ms) {
        ev = TouchGestureEvent::TAP;
    }
    down_ = false;
    return ev;
}

void TouchGesture::reset()
{
    down_ = false;
    cancelled_ = false;
    long_fired_ = false;
    fire_ms_ = 0;
}

float TouchGesture::ring_progress(uint32_t now_ms) const
{
    if (!down_ || cancelled_) {
        return -1.0f;
    }
    if (long_fired_) {
        return 1.0f;
    }
    const uint32_t held = elapsed(now_ms, t0_ms_);
    if (held < cfg_.ring_show_ms) {
        return -1.0f;
    }
    const uint32_t span = cfg_.long_press_ms > cfg_.ring_show_ms ? cfg_.long_press_ms - cfg_.ring_show_ms : 1U;
    const float    p = static_cast<float>(held - cfg_.ring_show_ms) / static_cast<float>(span);
    return p > 1.0f ? 1.0f : p;
}

uint32_t TouchGesture::ms_since_long_fire(uint32_t now_ms) const
{
    if (!long_fired_) {
        return UINT32_MAX;
    }
    return elapsed(now_ms, fire_ms_);
}
