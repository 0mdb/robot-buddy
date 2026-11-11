// Host-side unit tests for pure firmware logic (no ESP-IDF needed).
// Run: just test-face-host
#include "shared_state.h"
#include "touch_gesture.h"

#include <cstdio>
#include <cstdlib>
#include <thread>

static int g_failures = 0;
#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                       \
            g_failures++;                                                                                              \
        }                                                                                                              \
    } while (0)

static const TouchGestureConfig CFG = {300, 700, 200, 24, 160};
using E = TouchGestureEvent;

static void test_tap()
{
    TouchGesture g(CFG);
    g.press(100, 100, 1000);
    CHECK(g.tick(1100) == E::NONE);
    g.move(110, 105, 1150); // within tolerance
    CHECK(g.release(110, 105, 1299) == E::TAP);
    CHECK(!g.down());
}

static void test_wrap_safe_tap()
{
    TouchGesture g(CFG);
    g.press(10, 10, 0xFFFFFF00u);                    // timer about to wrap
    CHECK(g.release(10, 10, 0x00000010u) == E::TAP); // 272 ms later, across the wrap
}

static void test_slow_release_is_nothing()
{
    TouchGesture g(CFG);
    g.press(50, 50, 0);
    CHECK(g.tick(500) == E::NONE);
    CHECK(g.release(50, 50, 500) == E::NONE); // between tap max and long-press
}

static void test_long_press_fires_once_while_held()
{
    TouchGesture g(CFG);
    g.press(50, 50, 0);
    CHECK(g.tick(699) == E::NONE);
    CHECK(g.tick(700) == E::LONG_PRESS);
    CHECK(g.tick(800) == E::NONE);
    CHECK(g.release(50, 50, 900) == E::NONE); // release after firing reports nothing
    CHECK(g.long_fired());
}

static void test_long_press_detected_at_release_if_no_tick()
{
    TouchGesture g(CFG);
    g.press(50, 50, 0);
    CHECK(g.release(50, 50, 750) == E::LONG_PRESS);
}

static void test_stroke_is_pet_once()
{
    TouchGesture g(CFG);
    g.press(40, 120, 0);
    int x = 40;
    int pets = 0;
    for (int i = 1; i <= 40; i++) { // back-and-forth stroke, 20 px per sample
        x += (i / 6) % 2 ? -20 : 20;
        g.move(x, 120, i * 30);
        if (g.tick(i * 30) == E::PET) pets++;
        if (i == 7) CHECK(!g.petting()); // path 140 px: not yet
        if (i == 8) CHECK(g.petting());  // path 160 px: stroking
    }
    CHECK(pets == 1);
    CHECK(g.petting());
    CHECK(g.release(x, 120, 2000) == E::NONE);
    CHECK(!g.petting());

    TouchGesture shortdrag(CFG); // a single swipe under the path threshold is not a pet
    shortdrag.press(0, 0, 0);
    shortdrag.move(100, 0, 50);
    CHECK(shortdrag.tick(60) == E::NONE);
    CHECK(!shortdrag.petting());
}

static void test_drag_cancels_everything()
{
    TouchGesture g(CFG);
    g.press(50, 50, 0);
    g.move(80, 50, 50); // 30 px > 24
    CHECK(g.cancelled());
    CHECK(g.tick(1000) == E::NONE);
    CHECK(g.release(50, 50, 1100) == E::NONE);

    TouchGesture t(CFG);
    t.press(50, 50, 0);
    t.move(80, 50, 50);
    t.move(50, 50, 60); // coming back does not un-cancel
    CHECK(t.release(50, 50, 100) == E::NONE);
}

static void test_ring_progress()
{
    TouchGesture g(CFG);
    CHECK(g.ring_progress(0) < 0.0f);
    g.press(50, 50, 0);
    CHECK(g.ring_progress(199) < 0.0f); // hidden before ring_show_ms
    CHECK(g.ring_progress(200) == 0.0f);
    const float mid = g.ring_progress(450);
    CHECK(mid > 0.49f && mid < 0.51f);
    g.tick(700);
    CHECK(g.ring_progress(750) == 1.0f);
    CHECK(g.ms_since_long_fire(850) == 150);
    g.move(200, 200, 760); // dragging after fire does not cancel the fired press
    CHECK(!g.cancelled());
}

static void test_reset()
{
    TouchGesture g(CFG);
    g.press(50, 50, 0);
    g.reset();
    CHECK(!g.down());
    CHECK(g.tick(1000) == E::NONE);
    CHECK(g.release(50, 50, 100) == E::NONE);
}

static void test_spsc_basic()
{
    SpscQueue<int, 4> q; // holds 3
    int               v = 0;
    CHECK(!q.pop(&v));
    CHECK(q.push(1) && q.push(2) && q.push(3));
    CHECK(!q.push(4)); // full: new item dropped
    CHECK(q.peek(&v) && v == 1);
    CHECK(q.peek(&v) && v == 1); // peek does not consume
    q.drop();
    CHECK(q.pop(&v) && v == 2);
    CHECK(q.pop(&v) && v == 3);
    CHECK(!q.pop(&v));
    q.drop(); // drop on empty is a no-op
    CHECK(q.push(5) && q.pop(&v) && v == 5);
}

static void test_spsc_threads()
{
    // One producer, one consumer: every item arrives exactly once, in order.
    SpscQueue<uint32_t, 16> q;
    constexpr uint32_t      N = 200000;
    std::thread             prod([&] {
        for (uint32_t i = 1; i <= N;) {
            if (q.push(i)) i++;
        }
    });
    uint32_t                expect = 1;
    uint32_t                v = 0;
    while (expect <= N) {
        if (q.pop(&v)) {
            if (v != expect) {
                CHECK(v == expect);
                break;
            }
            expect++;
        }
    }
    prod.join();
    CHECK(expect == N + 1);
}

int main()
{
    test_tap();
    test_wrap_safe_tap();
    test_slow_release_is_nothing();
    test_long_press_fires_once_while_held();
    test_long_press_detected_at_release_if_no_tick();
    test_stroke_is_pet_once();
    test_drag_cancels_everything();
    test_ring_progress();
    test_reset();
    test_spsc_basic();
    test_spsc_threads();
    if (g_failures) {
        std::fprintf(stderr, "%d failure(s)\n", g_failures);
        return 1;
    }
    std::printf("face host tests: all passed\n");
    return 0;
}
