#include "usb_composite.h"
#include "esp_log.h"
#include "tinyusb.h"
#include "tusb_cdc_acm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <atomic>

static const char* TAG = "usb_composite";
static std::atomic<uint32_t> g_tx_calls{0};
static std::atomic<uint32_t> g_tx_bytes_requested{0};
static std::atomic<uint32_t> g_tx_bytes_queued{0};
static std::atomic<uint32_t> g_tx_short_writes{0};
static std::atomic<uint32_t> g_tx_flush_ok{0};
static std::atomic<uint32_t> g_tx_flush_not_finished{0};
static std::atomic<uint32_t> g_tx_flush_timeout{0};
static std::atomic<uint32_t> g_tx_flush_error{0};
static std::atomic<uint32_t> g_rx_calls{0};
static std::atomic<uint32_t> g_rx_bytes{0};
static std::atomic<uint32_t> g_rx_errors{0};
static std::atomic<uint32_t> g_line_state_events{0};
static std::atomic<uint8_t> g_line_dtr{0};
static std::atomic<uint8_t> g_line_rts{0};

static void record_flush_result(esp_err_t flush_ret)
{
    switch (flush_ret) {
    case ESP_OK:
        g_tx_flush_ok.fetch_add(1, std::memory_order_relaxed);
        break;
    case ESP_ERR_NOT_FINISHED:
        g_tx_flush_not_finished.fetch_add(1, std::memory_order_relaxed);
        break;
    case ESP_ERR_TIMEOUT:
        g_tx_flush_timeout.fetch_add(1, std::memory_order_relaxed);
        break;
    default:
        g_tx_flush_error.fetch_add(1, std::memory_order_relaxed);
        break;
    }
}

static void cdc_line_state_changed_cb(int itf, cdcacm_event_t* event)
{
    if (event == nullptr || event->type != CDC_EVENT_LINE_STATE_CHANGED) {
        return;
    }
    const uint8_t dtr = event->line_state_changed_data.dtr ? 1 : 0;
    const uint8_t rts = event->line_state_changed_data.rts ? 1 : 0;
    g_line_state_events.fetch_add(1, std::memory_order_relaxed);
    g_line_dtr.store(dtr, std::memory_order_relaxed);
    g_line_rts.store(rts, std::memory_order_relaxed);
    ESP_LOGI(TAG, "cdc line-state itf=%d dtr=%u rts=%u", itf, dtr, rts);
}

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
        .vbus_monitor_io = 0,  // boot button pin doubles as VBUS sense on this board
    };
    ESP_ERROR_CHECK(tinyusb_driver_install(&tusb_cfg));

    // CDC ACM for serial commands
    tinyusb_config_cdcacm_t acm_cfg = {
        .usb_dev = TINYUSB_USBDEV_0,
        .cdc_port = TINYUSB_CDC_ACM_0,
        .rx_unread_buf_sz = 512,
        .callback_rx = nullptr,
        .callback_rx_wanted_char = nullptr,
        .callback_line_state_changed = cdc_line_state_changed_cb,
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

    static constexpr uint32_t FLUSH_TIMEOUT_TICKS = 2;
    static constexpr int MAX_WRITE_ATTEMPTS = 6;

    g_tx_calls.fetch_add(1, std::memory_order_relaxed);
    g_tx_bytes_requested.fetch_add(static_cast<uint32_t>(len), std::memory_order_relaxed);

    size_t written = 0;
    for (int attempt = 0; attempt < MAX_WRITE_ATTEMPTS && written < len; ++attempt) {
        const size_t queued = tinyusb_cdcacm_write_queue(
            TINYUSB_CDC_ACM_0, data + written, len - written);
        g_tx_bytes_queued.fetch_add(static_cast<uint32_t>(queued), std::memory_order_relaxed);
        if (queued < (len - written)) {
            g_tx_short_writes.fetch_add(1, std::memory_order_relaxed);
        }
        written += queued;

        const esp_err_t flush_ret =
            tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0, FLUSH_TIMEOUT_TICKS);
        record_flush_result(flush_ret);

        if (written >= len || flush_ret == ESP_OK) {
            if (written >= len) {
                break;
            }
        }
        if (flush_ret == ESP_ERR_TIMEOUT) {
            break;
        }
        if (queued == 0) {
            // Give TinyUSB task a chance to run and free CDC TX buffer space.
            vTaskDelay(1);
        }
    }
}

int usb_cdc_read(uint8_t* buf, size_t max_len, uint32_t timeout_ms)
{
    (void)timeout_ms;
    g_rx_calls.fetch_add(1, std::memory_order_relaxed);

    size_t rx_size = 0;
    esp_err_t ret = tinyusb_cdcacm_read(TINYUSB_CDC_ACM_0, buf, max_len, &rx_size);
    if (ret != ESP_OK) {
        g_rx_errors.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    if (rx_size > 0) {
        g_rx_bytes.fetch_add(static_cast<uint32_t>(rx_size), std::memory_order_relaxed);
    }
    return static_cast<int>(rx_size);
}

UsbCdcDiagSnapshot usb_cdc_diag_snapshot(void)
{
    UsbCdcDiagSnapshot out = {};
    out.tx_calls = g_tx_calls.load(std::memory_order_relaxed);
    out.tx_bytes_requested = g_tx_bytes_requested.load(std::memory_order_relaxed);
    out.tx_bytes_queued = g_tx_bytes_queued.load(std::memory_order_relaxed);
    out.tx_short_writes = g_tx_short_writes.load(std::memory_order_relaxed);
    out.tx_flush_ok = g_tx_flush_ok.load(std::memory_order_relaxed);
    out.tx_flush_not_finished = g_tx_flush_not_finished.load(std::memory_order_relaxed);
    out.tx_flush_timeout = g_tx_flush_timeout.load(std::memory_order_relaxed);
    out.tx_flush_error = g_tx_flush_error.load(std::memory_order_relaxed);
    out.rx_calls = g_rx_calls.load(std::memory_order_relaxed);
    out.rx_bytes = g_rx_bytes.load(std::memory_order_relaxed);
    out.rx_errors = g_rx_errors.load(std::memory_order_relaxed);
    out.line_state_events = g_line_state_events.load(std::memory_order_relaxed);
    out.dtr = g_line_dtr.load(std::memory_order_relaxed);
    out.rts = g_line_rts.load(std::memory_order_relaxed);
    return out;
}
