// Pi link over UART0 on the FNK0104's P2 connector (pin 1 +5V, 2 GND, 3 TXD0, 4 RXD0).
// See docs/face-uart-transport.md. 3.3 V logic, straight to the Pi's GPIO14/15, TX<->RX
// crossed. No flow control and no DTR/RTS, so flashing stays on the USB-C port.

#include "face_link.h"
#include "pin_map.h"
#include "sdkconfig.h"

#include "driver/uart.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

#include <algorithm>
#include <atomic>

static const char* TAG = "uart_link";

static constexpr uart_port_t PORT = UART_NUM_0;
static constexpr int         RX_RING_BYTES = 2048;
static constexpr int         TX_RING_BYTES = 2048; // > the largest frame (MAX_FRAME 768), so writes never split
static constexpr int         EVENT_QUEUE_LEN = 16;

static QueueHandle_t     s_events = nullptr;
static SemaphoreHandle_t s_tx_mutex = nullptr;
static StaticSemaphore_t s_tx_mutex_buf;

static std::atomic<uint32_t> g_tx_calls{0};
static std::atomic<uint32_t> g_tx_bytes_requested{0};
static std::atomic<uint32_t> g_tx_bytes_queued{0};
static std::atomic<uint32_t> g_tx_short_writes{0};
static std::atomic<uint32_t> g_rx_calls{0};
static std::atomic<uint32_t> g_rx_bytes{0};
static std::atomic<uint32_t> g_rx_errors{0};

void face_link_init(void)
{
    const uart_config_t cfg = {
        .baud_rate = CONFIG_FACE_UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .rx_flow_ctrl_thresh = 0,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(PORT, RX_RING_BYTES, TX_RING_BYTES, EVENT_QUEUE_LEN, &s_events, 0));
    ESP_ERROR_CHECK(uart_param_config(PORT, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(PORT, PIN_LINK_TX, PIN_LINK_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    // Hold RX idle-high with the cable unplugged so a floating pin doesn't read as noise.
    gpio_set_pull_mode(PIN_LINK_RX, GPIO_PULLUP_ONLY);
    s_tx_mutex = xSemaphoreCreateMutexStatic(&s_tx_mutex_buf);
    ESP_LOGI(TAG, "UART0 link up: %d baud, TX GPIO%d, RX GPIO%d", CONFIG_FACE_UART_BAUD, static_cast<int>(PIN_LINK_TX),
             static_cast<int>(PIN_LINK_RX));
}

bool face_link_write(const uint8_t* data, size_t len)
{
    if (len == 0) return true;
    g_tx_calls.fetch_add(1, std::memory_order_relaxed);
    g_tx_bytes_requested.fetch_add(static_cast<uint32_t>(len), std::memory_order_relaxed);

    if (len > static_cast<size_t>(TX_RING_BYTES) || !s_tx_mutex ||
        xSemaphoreTake(s_tx_mutex, portMAX_DELAY) != pdTRUE) {
        g_tx_short_writes.fetch_add(1, std::memory_order_relaxed);
        return false;
    }
    // Copies into the TX ring, blocking only while it drains at line rate (no flow
    // control, so the wire always drains). The mutex keeps frames from interleaving.
    const int  written = uart_write_bytes(PORT, data, len);
    const bool ok = written == static_cast<int>(len);
    xSemaphoreGive(s_tx_mutex);

    if (written > 0) {
        g_tx_bytes_queued.fetch_add(static_cast<uint32_t>(written), std::memory_order_relaxed);
    }
    if (!ok) {
        g_tx_short_writes.fetch_add(1, std::memory_order_relaxed);
    }
    return ok;
}

// Count line errors; on overflow drop the input so the COBS parser resyncs on the next 0x00.
static void handle_event(const uart_event_t& ev)
{
    switch (ev.type) {
    case UART_FIFO_OVF:
    case UART_BUFFER_FULL:
        g_rx_errors.fetch_add(1, std::memory_order_relaxed);
        uart_flush_input(PORT);
        xQueueReset(s_events);
        break;
    case UART_FRAME_ERR:
    case UART_PARITY_ERR:
        g_rx_errors.fetch_add(1, std::memory_order_relaxed);
        break;
    default:
        break; // UART_DATA, UART_BREAK, ...: data is read below by length
    }
}

int face_link_read(uint8_t* buf, size_t max_len, uint32_t timeout_ms)
{
    g_rx_calls.fetch_add(1, std::memory_order_relaxed);
    if (!s_events || max_len == 0) return 0;

    // Drain pending events (keeps the queue from filling and counts errors), then, if
    // nothing is buffered, block until the driver signals data or an error.
    uart_event_t ev;
    while (xQueueReceive(s_events, &ev, 0) == pdTRUE) {
        handle_event(ev);
    }
    size_t avail = 0;
    uart_get_buffered_data_len(PORT, &avail);
    if (avail == 0) {
        if (xQueueReceive(s_events, &ev, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
            return 0;
        }
        handle_event(ev);
        uart_get_buffered_data_len(PORT, &avail);
        if (avail == 0) return 0;
    }

    // Read only what is already buffered: uart_read_bytes waits for the full count,
    // so asking for more than is there would add latency.
    const int n = uart_read_bytes(PORT, buf, static_cast<uint32_t>(std::min(avail, max_len)), 0);
    if (n < 0) {
        g_rx_errors.fetch_add(1, std::memory_order_relaxed);
        return 0;
    }
    g_rx_bytes.fetch_add(static_cast<uint32_t>(n), std::memory_order_relaxed);
    return n;
}

FaceLinkDiag face_link_diag_snapshot(void)
{
    FaceLinkDiag out = {};
    out.tx_calls = g_tx_calls.load(std::memory_order_relaxed);
    out.tx_bytes_requested = g_tx_bytes_requested.load(std::memory_order_relaxed);
    out.tx_bytes_queued = g_tx_bytes_queued.load(std::memory_order_relaxed);
    out.tx_short_writes = g_tx_short_writes.load(std::memory_order_relaxed);
    out.rx_calls = g_rx_calls.load(std::memory_order_relaxed);
    out.rx_bytes = g_rx_bytes.load(std::memory_order_relaxed);
    out.rx_errors = g_rx_errors.load(std::memory_order_relaxed);
    return out;
}
