#include "audio.h"
#include "pin_map.h"

#include "driver/gpio.h"
#include "esp_log.h"

static const char* TAG = "audio";

void audio_init(void)
{
    // Keep amplifier disabled (active LOW, so set HIGH to disable)
    gpio_config_t amp_cfg = {};
    amp_cfg.pin_bit_mask = 1ULL << PIN_AMP_EN;
    amp_cfg.mode = GPIO_MODE_OUTPUT;
    gpio_config(&amp_cfg);
    gpio_set_level(PIN_AMP_EN, 1);  // HIGH = amplifier disabled

    // TODO: Initialize ES8311 codec via I2C (shared bus with touch controller)
    //   - Reset codec: write 0x1F → 0x00 → 0x80 to register 0x00
    //   - Configure clocks for 16kHz sample rate, MCLK = 4.096 MHz
    //   - Set I2S format: 16-bit, slave mode
    //   - Power up ADC/DAC analog blocks
    //   - Set mic gain (+24dB) and DAC volume (85%)

    // TODO: Initialize I2S peripheral (I2S_NUM_0)
    //   - Standard Philips mode, 16kHz, 16-bit, mono
    //   - Pins: MCK=4, BCK=5, WS=7, DOUT=8, DIN=6

    ESP_LOGI(TAG, "audio stub initialized (codec not configured, amp disabled)");
}

void audio_play_pcm(const int16_t* samples, size_t num_samples)
{
    ESP_LOGW(TAG, "audio_play_pcm: not implemented (%zu samples)", num_samples);
}

void audio_stop(void)
{
    ESP_LOGW(TAG, "audio_stop: not implemented");
}

void audio_mic_start(void)
{
    ESP_LOGW(TAG, "audio_mic_start: not implemented");
}

void audio_mic_stop(void)
{
    ESP_LOGW(TAG, "audio_mic_stop: not implemented");
}

bool audio_is_playing(void)
{
    return false;
}
