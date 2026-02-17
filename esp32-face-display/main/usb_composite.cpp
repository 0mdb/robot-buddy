#include "usb_composite.h"
#include "esp_log.h"
#include "tinyusb.h"
#include "tusb_cdc_acm.h"

static const char* TAG = "usb_composite";

void usb_composite_init(void)
{
    ESP_LOGI(TAG, "initializing TinyUSB composite device");

    const tinyusb_config_t tusb_cfg = {
        .device_descriptor = nullptr,         // use default
        .string_descriptor = nullptr,         // use default
        .string_descriptor_count = 0,
        .external_phy = false,
        .configuration_descriptor = nullptr,  // use default
        .self_powered = false,
        .vbus_monitor_io = -1,  // no VBUS monitoring GPIO (0 = boot button conflict)
    };
    ESP_ERROR_CHECK(tinyusb_driver_install(&tusb_cfg));

    // CDC ACM for serial commands
    tinyusb_config_cdcacm_t acm_cfg = {
        .usb_dev = TINYUSB_USBDEV_0,
        .cdc_port = TINYUSB_CDC_ACM_0,
        .rx_unread_buf_sz = 512,
        .callback_rx = nullptr,
        .callback_rx_wanted_char = nullptr,
        .callback_line_state_changed = nullptr,
        .callback_line_coding_changed = nullptr,
    };
    ESP_ERROR_CHECK(tusb_cdc_acm_init(&acm_cfg));

    // UAC (audio) — scaffold only. TinyUSB UAC class requires custom
    // descriptors and callbacks that will be implemented when audio
    // streaming is built out. For now, CDC is the only active interface.
    ESP_LOGI(TAG, "TinyUSB CDC initialized (UAC scaffold pending)");
}

void usb_cdc_write(const uint8_t* data, size_t len)
{
    if (len == 0) return;
    tinyusb_cdcacm_write_queue(TINYUSB_CDC_ACM_0, data, len);
    tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0, 0);
}

int usb_cdc_read(uint8_t* buf, size_t max_len, uint32_t timeout_ms)
{
    size_t rx_size = 0;
    esp_err_t ret = tinyusb_cdcacm_read(TINYUSB_CDC_ACM_0, buf, max_len, &rx_size);
    if (ret != ESP_OK) return 0;
    return static_cast<int>(rx_size);
}
