#include "display.h"
#include "pin_map.h"
#include "config.h"

#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_ili9341.h"
#include "esp_lvgl_port.h"
#include "driver/ledc.h"
#include "driver/spi_master.h"
#include "esp_log.h"

static const char* TAG = "display";

static esp_lcd_panel_io_handle_t s_io = nullptr;

// ILI9341 drive presets for row-crosstalk tuning (see PANEL_TUNE_MODE in config.h).
// Each preset sets all four registers so presets are independent of each other.
//   0xC5 VCOM control 1 (VCOMH, VCOML), 0xC7 VCOM offset, 0xB4 display inversion
//   control (bit set = frame inversion, clear = line inversion; bit2 = normal mode),
//   0xB1 frame rate (DIVA, RTNA: 0x1B = 70 Hz, 0x1F = 61 Hz, 0x13 = 100 Hz).
struct PanelPreset {
    const char* name;
    uint8_t     vcom1[2];
    uint8_t     vcom_offset;
    uint8_t     inversion;
    uint8_t     frame_rate;
};
static constexpr PanelPreset PANEL_PRESETS[] = {
    {"vendor default", {0x43, 0x4C}, 0xA0, 0x02, 0x1B}, {"frame inversion", {0x43, 0x4C}, 0xA0, 0x07, 0x1B},
    {"vcom offset -", {0x43, 0x4C}, 0x90, 0x02, 0x1B},  {"vcom offset +", {0x43, 0x4C}, 0xB0, 0x02, 0x1B},
    {"alt vcom", {0x3E, 0x28}, 0x86, 0x02, 0x1B},       {"alt vcom + frame inv", {0x3E, 0x28}, 0x86, 0x07, 0x1B},
    {"61 Hz refresh", {0x43, 0x4C}, 0xA0, 0x02, 0x1F},  {"100 Hz refresh", {0x43, 0x4C}, 0xA0, 0x02, 0x13},
};

int display_panel_preset_count(void)
{
    return static_cast<int>(sizeof(PANEL_PRESETS) / sizeof(PANEL_PRESETS[0]));
}

void display_apply_panel_preset(int index)
{
    if (!s_io || index < 0 || index >= display_panel_preset_count()) return;
    const PanelPreset& p = PANEL_PRESETS[index];
    const uint8_t      b1[2] = {0x00, p.frame_rate};
    // tx_param waits for in-flight pixel transfers, so this is safe between flushes.
    esp_lcd_panel_io_tx_param(s_io, 0xC5, p.vcom1, 2);
    esp_lcd_panel_io_tx_param(s_io, 0xC7, &p.vcom_offset, 1);
    esp_lcd_panel_io_tx_param(s_io, 0xB4, &p.inversion, 1);
    esp_lcd_panel_io_tx_param(s_io, 0xB1, b1, 2);
    ESP_LOGI(TAG, "panel preset %d: %s", index, p.name);
}

// Backlight via LEDC
static void backlight_init(void)
{
    ledc_timer_config_t timer_cfg = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_cfg));

    ledc_channel_config_t ch_cfg = {
        .gpio_num = PIN_TFT_BL,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = DEFAULT_BRIGHTNESS,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&ch_cfg));
}

void display_set_backlight(uint8_t brightness)
{
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, brightness);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

lv_display_t* display_init(void)
{
    ESP_LOGI(TAG, "initializing display");

    // 1. Backlight
    backlight_init();

    // 2. SPI bus
    spi_bus_config_t bus_cfg = {};
    bus_cfg.mosi_io_num = PIN_TFT_MOSI;
    bus_cfg.miso_io_num = PIN_TFT_MISO;
    bus_cfg.sclk_io_num = PIN_TFT_SCLK;
    bus_cfg.quadwp_io_num = -1;
    bus_cfg.quadhd_io_num = -1;
    bus_cfg.max_transfer_sz = SCREEN_W * 80 * 2; // DMA-friendly chunk
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus_cfg, SPI_DMA_CH_AUTO));

    // 3. LCD panel IO (SPI)
    esp_lcd_panel_io_handle_t     io_handle = nullptr;
    esp_lcd_panel_io_spi_config_t io_cfg = {};
    io_cfg.dc_gpio_num = PIN_TFT_DC;
    io_cfg.cs_gpio_num = PIN_TFT_CS;
    io_cfg.pclk_hz = SPI_FREQ_HZ;
    io_cfg.lcd_cmd_bits = 8;
    io_cfg.lcd_param_bits = 8;
    io_cfg.spi_mode = 0;
    io_cfg.trans_queue_depth = 10;
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI2_HOST, &io_cfg, &io_handle));

    // 4. LCD panel (ILI9341)
    esp_lcd_panel_handle_t     panel_handle = nullptr;
    esp_lcd_panel_dev_config_t panel_cfg = {};
    panel_cfg.reset_gpio_num = -1; // RST tied to board reset
    panel_cfg.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_BGR;
    panel_cfg.bits_per_pixel = 16;
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(io_handle, &panel_cfg, &panel_handle));

    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_handle, true));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));
    s_io = io_handle;
    if (PANEL_PRESET >= 0) {
        display_apply_panel_preset(PANEL_PRESET);
    }

    // 5. LVGL port
    lvgl_port_cfg_t lvgl_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    lvgl_cfg.task_affinity = 0; // keep LVGL engine with UI rendering on core 0
    ESP_ERROR_CHECK(lvgl_port_init(&lvgl_cfg));

    // 6. Add display to LVGL
    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = io_handle,
        .panel_handle = panel_handle,
        .control_handle = nullptr,
        .buffer_size = SCREEN_W * 30,
        .double_buffer = true,
        .trans_size = 0,
        .hres = SCREEN_W,
        .vres = SCREEN_H,
        .monochrome = false,
        .rotation =
            {
                .swap_xy = true,
                .mirror_x = false,
                .mirror_y = false,
            },
        .rounder_cb = nullptr,
        .color_format = LV_COLOR_FORMAT_RGB565,
        .flags =
            {
                .buff_dma = true,
                .buff_spiram = false,
                .sw_rotate = false,
                .swap_bytes = true,
                .full_refresh = false,
                .direct_mode = false,
            },
    };
    lv_display_t* disp = lvgl_port_add_disp(&disp_cfg);

    ESP_LOGI(TAG, "display initialized: %dx%d", SCREEN_W, SCREEN_H);
    return disp;
}
