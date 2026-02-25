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
    if (alpha <= 0.001f) return bg;
    const uint8_t bg_r = px_r(bg);
    const uint8_t bg_g = px_g(bg);
    const uint8_t bg_b = px_b(bg);
    return px_rgb(static_cast<uint8_t>(bg_r + static_cast<int>((r - bg_r) * alpha)),
                  static_cast<uint8_t>(bg_g + static_cast<int>((g - bg_g) * alpha)),
                  static_cast<uint8_t>(bg_b + static_cast<int>((b - bg_b) * alpha)));
}

// Experimental fixed-point blend for post-baseline A/B profiling.
// Keep disabled for baseline fidelity; enable only when callsites are explicitly
// migrated to pass alpha in 0..255 space.
//
// inline pixel_t px_scale_255(pixel_t p, uint8_t scale_255)
// {
//     if (scale_255 == 255) return p;
//     if (scale_255 == 0) return 0;
//
//     const uint16_t r = (((p >> 11) & 0x1F) * scale_255) >> 8;
//     const uint16_t g = (((p >> 5) & 0x3F) * scale_255) >> 8;
//     const uint16_t b = ((p & 0x1F) * scale_255) >> 8;
//
//     return static_cast<pixel_t>((r << 11) | (g << 5) | b);
// }
//
// inline pixel_t px_blend_u8(pixel_t bg, uint8_t r, uint8_t g, uint8_t b, uint8_t alpha)
// {
//     if (alpha == 255) return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
//     if (alpha == 0) return bg;
//
//     const uint8_t bg_r = (bg >> 8) & 0xF8;
//     const uint8_t bg_g = (bg >> 3) & 0xFC;
//     const uint8_t bg_b = (bg << 3) & 0xF8;
//
//     const uint8_t out_r = bg_r + (((r - bg_r) * alpha) >> 8);
//     const uint8_t out_g = bg_g + (((g - bg_g) * alpha) >> 8);
//     const uint8_t out_b = bg_b + (((b - bg_b) * alpha) >> 8);
//
//     return ((out_r & 0xF8) << 8) | ((out_g & 0xFC) << 3) | (out_b >> 3);
// }
