#pragma once
#include "lvgl.h"
inline bool lvgl_port_lock(int)
{
    return true;
}
inline void lvgl_port_unlock() {}
