#include "range_ultrasonic.h"
#include "config.h"
#include "pin_map.h"
#include "shared_state.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "driver/rmt_rx.h"

#include <cstring>

static const char* TAG = "range";

// ---- RMT receive channel ----
static rmt_channel_handle_t s_rx_chan = nullptr;
static rmt_symbol_word_t    s_rx_symbols[64];

// Queue to receive RMT done event
static QueueHandle_t s_rx_queue = nullptr;

// RMT resolution: 1 MHz → 1 tick = 1 µs
static constexpr uint32_t RMT_RESOLUTION_HZ = 1000000;

// Speed of sound: ~343 m/s → round-trip: 1 mm ≈ 5.83 µs → distance = ticks / 58
static constexpr float US_PER_MM_ROUNDTRIP = 5.83f;

// ---- RMT receive-done callback ----

static bool IRAM_ATTR rmt_rx_done_cb(rmt_channel_handle_t channel,
                                      const rmt_rx_done_event_data_t* edata,
                                      void* user_ctx)
{
    BaseType_t wake = pdFALSE;
    // Send the received symbol count to the task queue
    xQueueSendFromISR(static_cast<QueueHandle_t>(user_ctx), edata, &wake);
    return wake == pdTRUE;
}

// ---- Init ----

bool range_init()
{
    // Configure TRIG pin as output (initially low)
    gpio_config_t trig_cfg = {};
    trig_cfg.pin_bit_mask = 1ULL << PIN_RANGE_TRIG;
    trig_cfg.mode = GPIO_MODE_OUTPUT;
    trig_cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    trig_cfg.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio_config(&trig_cfg);
    gpio_set_level(PIN_RANGE_TRIG, 0);

    // Configure RMT RX channel on ECHO pin
    rmt_rx_channel_config_t rx_cfg = {};
    rx_cfg.gpio_num = PIN_RANGE_ECHO;
    rx_cfg.clk_src = RMT_CLK_SRC_DEFAULT;
    rx_cfg.resolution_hz = RMT_RESOLUTION_HZ;
    rx_cfg.mem_block_symbols = 64;

    esp_err_t err = rmt_new_rx_channel(&rx_cfg, &s_rx_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "rmt_new_rx_channel failed: %s", esp_err_to_name(err));
        return false;
    }

    // Create queue for RX done events
    s_rx_queue = xQueueCreate(1, sizeof(rmt_rx_done_event_data_t));
    if (!s_rx_queue) {
        ESP_LOGE(TAG, "failed to create RX queue");
        return false;
    }

    // Register callback
    rmt_rx_event_callbacks_t cbs = {};
    cbs.on_recv_done = rmt_rx_done_cb;
    rmt_rx_register_event_callbacks(s_rx_chan, &cbs, s_rx_queue);

    // Enable the channel
    rmt_enable(s_rx_chan);

    ESP_LOGI(TAG, "range sensor initialized (TRIG=GPIO%d, ECHO=GPIO%d)",
             PIN_RANGE_TRIG, PIN_RANGE_ECHO);
    return true;
}

// ---- Single measurement ----

static void do_measurement(uint32_t timeout_us)
{
    uint32_t now = static_cast<uint32_t>(esp_timer_get_time());

    // Start RMT receive (arms the capture before we trigger)
    rmt_receive_config_t rx_cfg = {};
    rx_cfg.signal_range_min_ns = 1000;          // ignore pulses < 1 µs (noise)
    rx_cfg.signal_range_max_ns = timeout_us * 1000; // max echo duration

    esp_err_t err = rmt_receive(s_rx_chan, s_rx_symbols,
                                 sizeof(s_rx_symbols), &rx_cfg);
    if (err != ESP_OK) {
        RangeSample* ws = g_range.write_slot();
        ws->range_mm = 0;
        ws->status = RangeStatus::TIMEOUT;
        ws->timestamp_us = now;
        g_range.publish();
        return;
    }

    // Send 10 µs trigger pulse
    gpio_set_level(PIN_RANGE_TRIG, 1);
    esp_rom_delay_us(10);
    gpio_set_level(PIN_RANGE_TRIG, 0);

    // Wait for RMT capture to complete (with timeout)
    rmt_rx_done_event_data_t rx_data;
    TickType_t wait_ticks = pdMS_TO_TICKS(timeout_us / 1000 + 10);
    if (wait_ticks < 2) wait_ticks = 2;

    RangeSample* ws = g_range.write_slot();
    ws->timestamp_us = now;

    if (xQueueReceive(s_rx_queue, &rx_data, wait_ticks) != pdTRUE) {
        // No echo received
        ws->range_mm = 0;
        ws->status = RangeStatus::TIMEOUT;
        g_range.publish();
        return;
    }

    // Parse RMT symbols — look for the first high-level pulse (echo)
    if (rx_data.num_symbols == 0) {
        ws->range_mm = 0;
        ws->status = RangeStatus::TIMEOUT;
        g_range.publish();
        return;
    }

    // The echo pin goes high for the duration proportional to distance.
    // RMT captures both the high and low portions of the signal.
    // We want the duration of the first high pulse.
    uint32_t echo_us = 0;
    for (size_t i = 0; i < rx_data.num_symbols; i++) {
        rmt_symbol_word_t sym = rx_data.received_symbols[i];
        // level0 is the first half of the symbol
        if (sym.level0 == 1) {
            echo_us = sym.duration0;
            break;
        }
        // level1 is the second half
        if (sym.level1 == 1) {
            echo_us = sym.duration1;
            break;
        }
    }

    if (echo_us == 0) {
        ws->range_mm = 0;
        ws->status = RangeStatus::TIMEOUT;
        g_range.publish();
        return;
    }

    // Convert echo duration to distance in mm
    uint16_t range_mm = static_cast<uint16_t>(echo_us / US_PER_MM_ROUNDTRIP);

    if (echo_us >= timeout_us) {
        ws->range_mm = range_mm;
        ws->status = RangeStatus::OUT_OF_RANGE;
    } else {
        ws->range_mm = range_mm;
        ws->status = RangeStatus::OK;
    }

    g_range.publish();
}

// ---- Task ----

void range_task(void* arg)
{
    ESP_LOGI(TAG, "range_task started @ %u Hz", g_cfg.range_hz);

    TickType_t period = pdMS_TO_TICKS(1000 / g_cfg.range_hz);
    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, period);
        do_measurement(g_cfg.range_timeout_us);
    }
}
