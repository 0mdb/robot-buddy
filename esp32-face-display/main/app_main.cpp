#include "display.h"
#include "touch.h"
#include "led.h"
#include "audio.h"
#include "usb_composite.h"
#include "usb_rx.h"
#include "telemetry.h"
#include "face_ui.h"

#include "esp_lvgl_port.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char* TAG = "face-display";
static constexpr uint32_t AUDIO_BOOT_SELFTEST_MS = 350;

extern "C" void app_main(void)
{
    ESP_LOGI(TAG, "Face-Display MCU booting...");

    // 1. Display (SPI + ILI9341 + LVGL)
    lv_display_t* disp = display_init();

    // 2. Touch (I2C + FT6336 + LVGL input)
    touch_init(disp);

    // 3. WS2812B status LED
    led_init();
    led_set_rgb(0, 0, 40);  // blue = booting

    // 4. Audio codec
    audio_init();
    if (audio_is_ready()) {
        ESP_LOGI(TAG, "audio boot self-test: %u ms gentle tone", static_cast<unsigned>(AUDIO_BOOT_SELFTEST_MS));
        audio_boot_tone_sync(AUDIO_BOOT_SELFTEST_MS);
    } else {
        ESP_LOGW(TAG, "audio boot self-test skipped: audio not ready");
    }

    // 5. USB composite device (CDC for serial)
    usb_composite_init();

    // 6. Create face UI (LVGL objects)
    if (lvgl_port_lock(1000)) {
        face_ui_create(lv_scr_act());
        lvgl_port_unlock();
    }

    // 7. Start FreeRTOS tasks
    xTaskCreatePinnedToCore(usb_rx_task,    "usb_rx",  4096,
                            nullptr, 4, nullptr, 1);     // APP core
    xTaskCreatePinnedToCore(telemetry_task, "telem",   4096,
                            nullptr, 3, nullptr, 1);     // APP core
    xTaskCreatePinnedToCore(face_ui_task,   "face_ui", 8192,
                            nullptr, 6, nullptr, 0);     // PRO core

    // 8. Status LED green = running
    led_set_rgb(0, 40, 0);

    ESP_LOGI(TAG, "all tasks started");
}
