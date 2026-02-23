#pragma once
// RGB565 pixel helpers for direct-buffer rendering.
// Format: RRRRRGGGGGGBBBBB (5-6-5 bit layout within uint16_t)

#include <cstdint>

using pixel_t = uint16_t;

// ---- Encode / Decode --------------------------------------------------------

inline pixel_t px_rgb(uint8_t r, uint8_t g, uint8_t b)
{
    return static_cast<pixel_t>(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
}

inline uint8_t px_r(pixel_t p)
{
    const uint8_t r5 = static_cast<uint8_t>((p >> 11) & 0x1F);
    return static_cast<uint8_t>((r5 << 3) | (r5 >> 2));
}

inline uint8_t px_g(pixel_t p)
{
    const uint8_t g6 = static_cast<uint8_t>((p >> 5) & 0x3F);
    return static_cast<uint8_t>((g6 << 2) | (g6 >> 4));
}

inline uint8_t px_b(pixel_t p)
{
    const uint8_t b5 = static_cast<uint8_t>(p & 0x1F);
    return static_cast<uint8_t>((b5 << 3) | (b5 >> 2));
}

// ---- Arithmetic -------------------------------------------------------------

inline pixel_t px_scale(pixel_t p, uint8_t num, uint8_t den)
{
    const uint16_t r = static_cast<uint16_t>(((p >> 11) & 0x1F) * num / den);
    const uint16_t g = static_cast<uint16_t>(((p >> 5) & 0x3F) * num / den);
    const uint16_t b = static_cast<uint16_t>((p & 0x1F) * num / den);
    return static_cast<pixel_t>((r << 11) | (g << 5) | b);
}

inline pixel_t px_blend(pixel_t bg, uint8_t r, uint8_t g, uint8_t b, float alpha)
{
    if (alpha >= 0.999f) return px_rgb(r, g, b);
    const uint8_t bg_r = px_r(bg);
    const uint8_t bg_g = px_g(bg);
    const uint8_t bg_b = px_b(bg);
    return px_rgb(static_cast<uint8_t>(bg_r + static_cast<int>((r - bg_r) * alpha)),
                  static_cast<uint8_t>(bg_g + static_cast<int>((g - bg_g) * alpha)),
                  static_cast<uint8_t>(bg_b + static_cast<int>((b - bg_b) * alpha)));
}
