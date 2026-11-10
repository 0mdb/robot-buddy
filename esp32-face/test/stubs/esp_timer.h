#pragma once
#include <cstdint>
// Controllable fake clock for host tests.
extern int64_t g_fake_time_us;
inline int64_t esp_timer_get_time()
{
    return g_fake_time_us;
}
