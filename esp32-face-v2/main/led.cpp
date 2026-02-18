#include "led.h"
#include "pin_map.h"

#include "led_strip.h"
#include "esp_log.h"

static const char* TAG = "led";
static led_strip_handle_t strip = nullptr;

void led_init(void)
{
    led_strip_config_t strip_cfg = {
        .strip_gpio_num = PIN_LED_DATA,
        .max_leds = 1,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_WS2812,
        .flags = { .invert_out = false },
    };

    led_strip_rmt_config_t rmt_cfg = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10'000'000,  // 10 MHz
        .mem_block_symbols = 64,
        .flags = { .with_dma = false },
    };

    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_cfg, &rmt_cfg, &strip));
    led_off();
    ESP_LOGI(TAG, "WS2812B LED initialized on GPIO %d", PIN_LED_DATA);
}

void led_set_rgb(uint8_t r, uint8_t g, uint8_t b)
{
    if (!strip) return;
    led_strip_set_pixel(strip, 0, r, g, b);
    led_strip_refresh(strip);
}

void led_off(void)
{
    if (!strip) return;
    led_strip_clear(strip);
    led_strip_refresh(strip);
}
