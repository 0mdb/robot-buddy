#include "touch.h"
#include "config.h"
#include "pin_map.h"
#include "shared_state.h"

#include "driver/i2c_master.h"
#include "esp_lcd_touch.h"
#include "esp_lcd_touch_ft5x06.h"
#include "esp_lvgl_port.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char* TAG = "touch";

static i2c_master_bus_handle_t i2c_bus = nullptr;
static esp_lcd_touch_handle_t  s_touch_handle = nullptr;
static std::size_t             s_transform_index = 0;

static constexpr TouchTransformPreset kTransformPresets[] = {
    {"v2_current", 320, 240, true, true, false},        {"portrait_raw", 240, 320, false, false, false},
    {"portrait_swap", 240, 320, true, false, false},    {"portrait_swap_mx", 240, 320, true, true, false},
    {"portrait_swap_my", 240, 320, true, false, true},  {"portrait_swap_mxy", 240, 320, true, true, true},
    {"landscape_raw", 320, 240, false, false, false},   {"landscape_swap", 320, 240, true, false, false},
    {"landscape_swap_my", 320, 240, true, false, true}, {"landscape_swap_mxy", 320, 240, true, true, true},
};

std::size_t touch_transform_preset_count()
{
    return sizeof(kTransformPresets) / sizeof(kTransformPresets[0]);
}

const TouchTransformPreset* touch_transform_preset_get(std::size_t index)
{
    if (touch_transform_preset_count() == 0) {
        return nullptr;
    }
    return &kTransformPresets[index % touch_transform_preset_count()];
}

std::size_t touch_transform_preset_index()
{
    return s_transform_index;
}

bool touch_transform_apply(std::size_t index)
{
    if (!s_touch_handle || touch_transform_preset_count() == 0) {
        return false;
    }
    const TouchTransformPreset* preset = touch_transform_preset_get(index);
    if (!preset) {
        return false;
    }

    s_transform_index = index % touch_transform_preset_count();
    s_touch_handle->config.x_max = preset->x_max;
    s_touch_handle->config.y_max = preset->y_max;

    esp_err_t err = ESP_OK;
    err = esp_lcd_touch_set_swap_xy(s_touch_handle, preset->swap_xy);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "set_swap_xy failed: %s", esp_err_to_name(err));
    }
    err = esp_lcd_touch_set_mirror_x(s_touch_handle, preset->mirror_x);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "set_mirror_x failed: %s", esp_err_to_name(err));
    }
    err = esp_lcd_touch_set_mirror_y(s_touch_handle, preset->mirror_y);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "set_mirror_y failed: %s", esp_err_to_name(err));
    }

    ESP_LOGI(TAG, "touch transform[%u] %s: x_max=%u y_max=%u swap=%d mx=%d my=%d",
             static_cast<unsigned>(s_transform_index), preset->name, static_cast<unsigned>(preset->x_max),
             static_cast<unsigned>(preset->y_max), preset->swap_xy ? 1 : 0, preset->mirror_x ? 1 : 0,
             preset->mirror_y ? 1 : 0);
    return true;
}

void touch_init(lv_display_t* disp)
{
    ESP_LOGI(TAG, "initializing I2C + touch");

    // 1. I2C master bus
    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.i2c_port = I2C_NUM_0;
    bus_cfg.sda_io_num = PIN_TOUCH_SDA;
    bus_cfg.scl_io_num = PIN_TOUCH_SCL;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &i2c_bus));

    // 2. Touch panel IO
    esp_lcd_panel_io_handle_t     tp_io_handle = nullptr;
    esp_lcd_panel_io_i2c_config_t tp_io_cfg = ESP_LCD_TOUCH_IO_I2C_FT5x06_CONFIG();
    tp_io_cfg.scl_speed_hz = 400000; // Required by new i2c_master API (must be > 0)
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(i2c_bus, &tp_io_cfg, &tp_io_handle));

    // 3. Touch controller
    esp_lcd_touch_handle_t      touch_handle = nullptr;
    const TouchTransformPreset* initial = touch_transform_preset_get(CALIB_TOUCH_DEFAULT_INDEX);
    if (!initial) {
        ESP_LOGE(TAG, "no touch transform presets configured");
        return;
    }
    esp_lcd_touch_config_t tp_cfg = {
        .x_max = initial->x_max,
        .y_max = initial->y_max,
        .rst_gpio_num = PIN_TOUCH_RST,
        .int_gpio_num = PIN_TOUCH_INT,
        .levels =
            {
                .reset = 0,
                .interrupt = 0,
            },
        .flags =
            {
                .swap_xy = initial->swap_xy,
                .mirror_x = initial->mirror_x,
                .mirror_y = initial->mirror_y,
            },
    };
    ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_ft5x06(tp_io_handle, &tp_cfg, &touch_handle));
    s_touch_handle = touch_handle;
    s_transform_index = CALIB_TOUCH_DEFAULT_INDEX % touch_transform_preset_count();
    touch_transform_apply(s_transform_index);

    // 4. Register with LVGL
    const lvgl_port_touch_cfg_t touch_cfg = {
        .disp = disp,
        .handle = touch_handle,
    };
    lvgl_port_add_touch(&touch_cfg);

    ESP_LOGI(TAG, "touch initialized (FT6336)");
}
