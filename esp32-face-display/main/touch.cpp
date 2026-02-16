#include "touch.h"
#include "pin_map.h"
#include "shared_state.h"

#include "driver/i2c_master.h"
#include "esp_lcd_touch_ft5x06.h"
#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char* TAG = "touch";

// Shared I2C bus handle (also used by audio/ES8311)
static i2c_master_bus_handle_t i2c_bus = nullptr;

i2c_master_bus_handle_t touch_get_i2c_bus(void) { return i2c_bus; }

void touch_init(lv_display_t* disp)
{
    ESP_LOGI(TAG, "initializing I2C + touch");

    // 1. I2C master bus (shared with ES8311 codec)
    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.i2c_port = I2C_NUM_0;
    bus_cfg.sda_io_num = PIN_TOUCH_SDA;
    bus_cfg.scl_io_num = PIN_TOUCH_SCL;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &i2c_bus));

    // 2. Touch panel IO
    esp_lcd_panel_io_handle_t tp_io_handle = nullptr;
    esp_lcd_panel_io_i2c_config_t tp_io_cfg =
        ESP_LCD_TOUCH_IO_I2C_FT5x06_CONFIG();
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(i2c_bus, &tp_io_cfg, &tp_io_handle));

    // 3. Touch controller
    esp_lcd_touch_handle_t touch_handle = nullptr;
    esp_lcd_touch_config_t tp_cfg = {
        .x_max = 240,
        .y_max = 320,
        .rst_gpio_num = PIN_TOUCH_RST,
        .int_gpio_num = PIN_TOUCH_INT,
        .levels = {
            .reset = 0,
            .interrupt = 0,
        },
        .flags = {
            .swap_xy = 0,
            .mirror_x = 0,
            .mirror_y = 0,
        },
    };
    ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_ft5x06(tp_io_handle, &tp_cfg, &touch_handle));

    // 4. Register with LVGL
    const lvgl_port_touch_cfg_t touch_cfg = {
        .disp = disp,
        .handle = touch_handle,
    };
    lvgl_port_add_touch(&touch_cfg);

    ESP_LOGI(TAG, "touch initialized (FT6336)");
}
