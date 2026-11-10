#pragma once
// Minimal LVGL stand-in for host-side render tests (test/render_harness.cpp).
#include <cstdint>
struct lv_obj_t {
    int dummy;
};
struct lv_event_t {
    int code;
};
struct lv_indev_t {
    int dummy;
};
struct lv_display_t {
    int dummy;
};
struct lv_point_t {
    int32_t x, y;
};
struct lv_area_t {
    int32_t x1, y1, x2, y2;
};
struct lv_color_t {
    uint8_t r, g, b;
};
typedef int lv_event_code_t;
typedef int lv_color_format_t;
enum { LV_EVENT_PRESSED = 1, LV_EVENT_PRESSING = 2, LV_EVENT_RELEASED = 3 };
enum { LV_COLOR_FORMAT_RGB565 = 0x12 };
enum { LV_ALIGN_TOP_LEFT = 1, LV_ALIGN_TOP_MID = 2 };
enum { LV_OBJ_FLAG_CLICKABLE = 1 };
enum { LV_PART_MAIN = 0 };
enum { LV_OPA_COVER = 255, LV_OPA_70 = 178 };
inline lv_obj_t* stub_obj()
{
    static lv_obj_t o;
    return &o;
}
inline lv_obj_t* lv_canvas_create(lv_obj_t*)
{
    return stub_obj();
}
inline void       lv_canvas_set_buffer(lv_obj_t*, void*, int, int, int) {}
inline void       lv_canvas_fill_bg(lv_obj_t*, lv_color_t, int) {}
inline lv_color_t lv_color_black()
{
    return {0, 0, 0};
}
inline lv_color_t lv_color_hex(uint32_t)
{
    return {0, 0, 0};
}
inline void      lv_obj_align(lv_obj_t*, int, int, int) {}
inline void      lv_obj_add_flag(lv_obj_t*, int) {}
inline void      lv_obj_add_event_cb(lv_obj_t*, void (*)(lv_event_t*), int, void*) {}
inline lv_obj_t* lv_obj_create(lv_obj_t*)
{
    return stub_obj();
}
inline lv_obj_t* lv_label_create(lv_obj_t*)
{
    return stub_obj();
}
inline void            lv_label_set_text(lv_obj_t*, const char*) {}
inline void            lv_obj_set_size(lv_obj_t*, int, int) {}
inline void            lv_obj_set_style_radius(lv_obj_t*, int, int) {}
inline void            lv_obj_set_style_border_width(lv_obj_t*, int, int) {}
inline void            lv_obj_set_style_bg_color(lv_obj_t*, lv_color_t, int) {}
inline void            lv_obj_set_style_bg_opa(lv_obj_t*, int, int) {}
inline void            lv_obj_set_style_pad_all(lv_obj_t*, int, int) {}
inline void            lv_obj_set_style_text_color(lv_obj_t*, lv_color_t, int) {}
inline void            lv_obj_move_foreground(lv_obj_t*) {}
inline void            lv_obj_invalidate(lv_obj_t*) {}
inline void            lv_obj_invalidate_area(lv_obj_t*, const lv_area_t*) {}
inline lv_event_code_t lv_event_get_code(lv_event_t* e)
{
    return e->code;
}
inline lv_indev_t* lv_indev_get_act()
{
    return nullptr;
}
inline void lv_indev_get_point(lv_indev_t*, lv_point_t* p)
{
    p->x = 0;
    p->y = 0;
}
inline lv_obj_t* lv_scr_act()
{
    return stub_obj();
}
