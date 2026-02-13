#include "encoder.h"
#include "pin_map.h"
#include "config.h"

#include "driver/pulse_cnt.h"
#include "esp_log.h"

#include <cmath>

static const char* TAG = "encoder";

// PCNT unit handles
static pcnt_unit_handle_t s_units[2] = {};

// Accumulated counts (PCNT hardware counter is 16-bit with overflow watch;
// we use the high-limit/low-limit watch + ISR-free accumulator approach
// provided by the new PCNT driver).
// However, for simplicity in v1 we rely on frequent sampling (100+ Hz)
// so the 16-bit counter won't overflow between reads.
// We track the "last read" and compute deltas in the control loop.

static void init_one(EncoderSide side, gpio_num_t pin_a, gpio_num_t pin_b)
{
    int idx = static_cast<int>(side);

    pcnt_unit_config_t unit_cfg = {};
    unit_cfg.high_limit = INT16_MAX;
    unit_cfg.low_limit  = INT16_MIN;
    ESP_ERROR_CHECK(pcnt_new_unit(&unit_cfg, &s_units[idx]));

    // Channel A: counts on A edges, direction from B level
    pcnt_chan_config_t chan_a_cfg = {};
    chan_a_cfg.edge_gpio_num  = pin_a;
    chan_a_cfg.level_gpio_num = pin_b;
    pcnt_channel_handle_t chan_a = nullptr;
    ESP_ERROR_CHECK(pcnt_new_channel(s_units[idx], &chan_a_cfg, &chan_a));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(chan_a,
        PCNT_CHANNEL_EDGE_ACTION_DECREASE, PCNT_CHANNEL_EDGE_ACTION_INCREASE));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(chan_a,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE));

    // Channel B: counts on B edges, direction from A level (full quadrature)
    pcnt_chan_config_t chan_b_cfg = {};
    chan_b_cfg.edge_gpio_num  = pin_b;
    chan_b_cfg.level_gpio_num = pin_a;
    pcnt_channel_handle_t chan_b = nullptr;
    ESP_ERROR_CHECK(pcnt_new_channel(s_units[idx], &chan_b_cfg, &chan_b));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(chan_b,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_DECREASE));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(chan_b,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP, PCNT_CHANNEL_LEVEL_ACTION_INVERSE));

    // Glitch filter: reject pulses shorter than 1 µs
    pcnt_glitch_filter_config_t filt = {};
    filt.max_glitch_ns = 1000;
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(s_units[idx], &filt));

    ESP_ERROR_CHECK(pcnt_unit_enable(s_units[idx]));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(s_units[idx]));
    ESP_ERROR_CHECK(pcnt_unit_start(s_units[idx]));

    ESP_LOGI(TAG, "%s encoder initialized (A=%d, B=%d)",
             side == EncoderSide::LEFT ? "LEFT" : "RIGHT",
             static_cast<int>(pin_a), static_cast<int>(pin_b));
}

void encoder_init()
{
    init_one(EncoderSide::LEFT,  PIN_ENC_L_A, PIN_ENC_L_B);
    init_one(EncoderSide::RIGHT, PIN_ENC_R_A, PIN_ENC_R_B);
}

int32_t encoder_get_count(EncoderSide side)
{
    int count = 0;
    pcnt_unit_get_count(s_units[static_cast<int>(side)], &count);
    return static_cast<int32_t>(count);
}

void encoder_snapshot(int32_t* out_left, int32_t* out_right)
{
    // Read as close together as possible. No perfect simultaneity
    // but at 100 Hz sampling this is fine.
    int l = 0, r = 0;
    pcnt_unit_get_count(s_units[0], &l);
    pcnt_unit_get_count(s_units[1], &r);
    *out_left  = static_cast<int32_t>(l);
    *out_right = static_cast<int32_t>(r);
}

float encoder_delta_to_mm_s(int32_t delta_counts, uint32_t dt_us)
{
    if (dt_us == 0) return 0.0f;
    // wheel circumference / counts_per_rev = mm per count
    const float mm_per_count = (g_cfg.wheel_diameter_mm * M_PI) / g_cfg.counts_per_rev;
    const float dt_s = static_cast<float>(dt_us) / 1'000'000.0f;
    return (static_cast<float>(delta_counts) * mm_per_count) / dt_s;
}
