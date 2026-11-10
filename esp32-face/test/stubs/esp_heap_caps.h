#pragma once
#include <cstdlib>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_INTERNAL 2
inline void* heap_caps_malloc(std::size_t n, int)
{
    return std::malloc(n);
}
inline std::size_t heap_caps_get_minimum_free_size(int)
{
    return 0;
}
