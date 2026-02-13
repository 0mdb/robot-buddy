#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "esp32-face";

void app_main(void)
{
    ESP_LOGI(TAG, "Face MCU stub booted.");

    // TODO: init led_strip (RMT)
    // TODO: init USB serial (CDC) or UART over USB-Serial bridge
    // TODO: start animation task @ 60 FPS
    // TODO: parse protocol packets and update shared state

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        ESP_LOGI(TAG, "tick");
    }
}
