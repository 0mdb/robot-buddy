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
static constexpr BaseType_t CORE_UI = 0;
static constexpr BaseType_t CORE_IO = 1;

static constexpr UBaseType_t PRIO_FACE_UI = 6;
static constexpr UBaseType_t PRIO_USB_RX = 4;
static constexpr UBaseType_t PRIO_TELEM = 3;

static constexpr uint32_t STACK_FACE_UI = 8192;
static constexpr uint32_t STACK_USB_RX = 4096;
static constexpr uint32_t STACK_TELEM = 4096;

static bool start_task(TaskFunction_t fn,
                       const char* name,
                       uint32_t stack_bytes,
                       UBaseType_t priority,
                       BaseType_t core)
{
    const BaseType_t ok = xTaskCreatePinnedToCore(
        fn, name, stack_bytes, nullptr, priority, nullptr, core);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "failed to start task '%s' (prio=%u, core=%d, stack=%u)",
                 name,
                 static_cast<unsigned>(priority),
                 static_cast<int>(core),
                 static_cast<unsigned>(stack_bytes));
        return false;
    }
    return true;
}

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

    // 7. Start FreeRTOS tasks.
    // Keep USB I/O isolated on core 1 and render/UI on core 0.
    const bool started =
        start_task(usb_rx_task, "usb_rx", STACK_USB_RX, PRIO_USB_RX, CORE_IO) &&
        start_task(telemetry_task, "telem", STACK_TELEM, PRIO_TELEM, CORE_IO) &&
        start_task(face_ui_task, "face_ui", STACK_FACE_UI, PRIO_FACE_UI, CORE_UI);

    if (!started) {
        led_set_rgb(40, 0, 0);  // red = startup task failure
        ESP_LOGE(TAG, "task startup failed; halting app_main");
        return;
    }

    // 8. Status LED green = running
    led_set_rgb(0, 40, 0);

    ESP_LOGI(TAG, "all tasks started");
}
