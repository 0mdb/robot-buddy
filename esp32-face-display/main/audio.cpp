#include "audio.h"
#include "pin_map.h"
#include "touch.h"

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>

static const char* TAG = "audio";

namespace {

constexpr uint8_t ES8311_ADDR = 0x18;
constexpr int AUDIO_SAMPLE_RATE_HZ = 16000;
constexpr int AUDIO_VOLUME_PERCENT = 100;
constexpr uint8_t ES8311_MIC_GAIN_24DB = 4;
constexpr uint32_t DEFAULT_TONE_MS = 1000;
constexpr uint32_t DEFAULT_MIC_PROBE_MS = 2000;
constexpr double MIC_ACTIVITY_RMS_THRESHOLD = 300.0;
constexpr bool MIC_PROBE_RESULT_TONE = true;  // Temporary diagnostics aid.
constexpr uint32_t MIC_PROBE_PASS_TONE_HZ = 1600;
constexpr uint32_t MIC_PROBE_FAIL_TONE_HZ = 320;
constexpr uint32_t MIC_PROBE_RESULT_TONE_MS = 140;
constexpr int16_t MIC_PROBE_RESULT_TONE_AMP = 10000;
constexpr uint32_t DIAG_TONE_FREQ_HZ = 1000;
constexpr int16_t DIAG_TONE_AMP = 28000;
constexpr uint32_t BOOT_TONE_FREQ_HZ = 660;
constexpr int16_t BOOT_TONE_AMP = 12000;
constexpr uint32_t TONE_EDGE_FADE_MS = 15;
constexpr uint32_t I2C_TIMEOUT_MS = 100;
constexpr uint32_t I2S_TIMEOUT_MS = 1000;
constexpr bool KEEP_AMP_ENABLED_BETWEEN_PLAYS = false;  // Normal behavior: gate amp outside playback.
constexpr uint32_t AMP_WAKE_DELAY_MS = 40;
constexpr bool FORCE_SYNC_DIAGNOSTICS = false;  // Keep false for normal async behavior.
constexpr uint32_t AUDIO_WORKER_STACK_BYTES = 8192;  // 4k was unstable in async diagnostics.
constexpr BaseType_t AUDIO_WORKER_CORE = 0;  // Keep heavy audio work off USB/TinyUSB core.
constexpr UBaseType_t AUDIO_WORKER_PRIORITY = 5;  // Below face_ui(6), above default LVGL task(4).

constexpr uint8_t REG00 = 0x00;
constexpr uint8_t REG01 = 0x01;
constexpr uint8_t REG02 = 0x02;
constexpr uint8_t REG03 = 0x03;
constexpr uint8_t REG04 = 0x04;
constexpr uint8_t REG05 = 0x05;
constexpr uint8_t REG06 = 0x06;
constexpr uint8_t REG07 = 0x07;
constexpr uint8_t REG08 = 0x08;
constexpr uint8_t REG09 = 0x09;
constexpr uint8_t REG0A = 0x0A;
constexpr uint8_t REG0D = 0x0D;
constexpr uint8_t REG0E = 0x0E;
constexpr uint8_t REG12 = 0x12;
constexpr uint8_t REG13 = 0x13;
constexpr uint8_t REG14 = 0x14;
constexpr uint8_t REG15 = 0x15;
constexpr uint8_t REG16 = 0x16;
constexpr uint8_t REG17 = 0x17;
constexpr uint8_t REG1C = 0x1C;
constexpr uint8_t REG31 = 0x31;
constexpr uint8_t REG32 = 0x32;
constexpr uint8_t REG37 = 0x37;

enum class AudioCmdType : uint8_t {
    TONE_1KHZ = 0,
    MIC_PROBE = 1,
    STOP = 2,
};

struct AudioCmd {
    AudioCmdType type;
    uint32_t duration_ms;
};

i2c_master_dev_handle_t s_codec_dev = nullptr;
i2s_chan_handle_t s_tx = nullptr;
i2s_chan_handle_t s_rx = nullptr;
QueueHandle_t s_cmd_queue = nullptr;
TaskHandle_t s_worker_task = nullptr;
std::atomic<bool> s_ready{false};
std::atomic<bool> s_playing{false};
std::atomic<bool> s_abort{false};
std::atomic<bool> s_mic_activity{false};
std::atomic<uint32_t> s_probe_seq{0};
std::atomic<uint32_t> s_probe_duration_ms{0};
std::atomic<uint32_t> s_probe_sample_count{0};
std::atomic<uint32_t> s_probe_read_timeouts{0};
std::atomic<uint32_t> s_probe_read_errors{0};
std::atomic<uint32_t> s_probe_selected_rms_x10{0};
std::atomic<uint32_t> s_probe_selected_peak{0};
std::atomic<int32_t> s_probe_selected_dbfs_x10{-1200};
std::atomic<uint8_t> s_probe_selected_channel{0};  // 0=mono, 1=left, 2=right

struct ProbeStats {
    uint64_t sum_sq = 0;
    int32_t peak = 0;
    uint32_t sample_count = 0;
};

void probe_stats_add_sample(ProbeStats* stats, int16_t sample)
{
    if (stats == nullptr) {
        return;
    }
    const int32_t s = static_cast<int32_t>(sample);
    const int32_t a = (s < 0) ? -s : s;
    stats->peak = std::max(stats->peak, a);
    stats->sum_sq += static_cast<uint64_t>(s * s);
    stats->sample_count++;
}

double probe_stats_rms(const ProbeStats& stats)
{
    if (stats.sample_count == 0) {
        return 0.0;
    }
    return std::sqrt(static_cast<double>(stats.sum_sq) / static_cast<double>(stats.sample_count));
}

double rms_to_dbfs(double rms)
{
    return (rms > 0.0) ? (20.0 * std::log10(rms / 32768.0)) : -120.0;
}

uint32_t clamp_u32(double v)
{
    if (v <= 0.0) {
        return 0;
    }
    const double max_v = static_cast<double>(UINT32_MAX);
    if (v >= max_v) {
        return UINT32_MAX;
    }
    return static_cast<uint32_t>(std::lround(v));
}

void publish_mic_probe_stats(uint32_t duration_ms,
                             uint32_t sample_count,
                             uint32_t read_timeouts,
                             uint32_t read_errors,
                             double selected_rms,
                             int32_t selected_peak,
                             double selected_dbfs,
                             uint8_t selected_channel,
                             bool active)
{
    s_probe_duration_ms.store(duration_ms, std::memory_order_relaxed);
    s_probe_sample_count.store(sample_count, std::memory_order_relaxed);
    s_probe_read_timeouts.store(read_timeouts, std::memory_order_relaxed);
    s_probe_read_errors.store(read_errors, std::memory_order_relaxed);
    s_probe_selected_rms_x10.store(clamp_u32(selected_rms * 10.0), std::memory_order_relaxed);
    s_probe_selected_peak.store(clamp_u32(static_cast<double>(selected_peak)), std::memory_order_relaxed);
    s_probe_selected_dbfs_x10.store(static_cast<int32_t>(std::lround(selected_dbfs * 10.0)), std::memory_order_relaxed);
    s_probe_selected_channel.store(selected_channel, std::memory_order_relaxed);
    s_mic_activity.store(active, std::memory_order_release);
    s_probe_seq.fetch_add(1, std::memory_order_release);
}

void set_amp_enabled(bool enabled)
{
    // Freenove reference board: AP_ENABLE (GPIO1) is active LOW.
    gpio_set_level(PIN_AMP_EN, enabled ? 0 : 1);
}

esp_err_t codec_write(uint8_t reg, uint8_t val)
{
    if (s_codec_dev == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(s_codec_dev, buf, sizeof(buf), I2C_TIMEOUT_MS);
}

esp_err_t codec_read(uint8_t reg, uint8_t* out)
{
    if (s_codec_dev == nullptr || out == nullptr) {
        return ESP_ERR_INVALID_ARG;
    }
    return i2c_master_transmit_receive(s_codec_dev, &reg, 1, out, 1, I2C_TIMEOUT_MS);
}

struct Es8311CoeffDiv {
    uint8_t pre_div;
    uint8_t pre_multi;
    uint8_t adc_div;
    uint8_t dac_div;
    uint8_t fs_mode;
    uint8_t lrck_h;
    uint8_t lrck_l;
    uint8_t bclk_div;
    uint8_t adc_osr;
    uint8_t dac_osr;
};

// Matches Freenove ES8311 settings for MCLK=4.096MHz and Fs=16kHz.
constexpr Es8311CoeffDiv kCoeff16k_4096k = {
    .pre_div = 0x01,
    .pre_multi = 0x00,
    .adc_div = 0x01,
    .dac_div = 0x01,
    .fs_mode = 0x00,
    .lrck_h = 0x00,
    .lrck_l = 0xFF,
    .bclk_div = 0x04,
    .adc_osr = 0x10,
    .dac_osr = 0x10,
};

esp_err_t codec_sample_frequency_config(int mclk_hz, int sample_hz)
{
    ESP_RETURN_ON_FALSE(mclk_hz == 4096000 && sample_hz == AUDIO_SAMPLE_RATE_HZ,
                        ESP_ERR_INVALID_ARG, TAG,
                        "unsupported clock tuple mclk=%d fs=%d", mclk_hz, sample_hz);

    const Es8311CoeffDiv& c = kCoeff16k_4096k;
    uint8_t regv = 0;

    // REG02: preserve low 3 bits, set pre-divider and multiplier.
    ESP_RETURN_ON_ERROR(codec_read(REG02, &regv), TAG, "codec REG02 read failed");
    regv &= 0x07;
    regv |= static_cast<uint8_t>((c.pre_div - 1u) << 5);
    regv |= static_cast<uint8_t>(c.pre_multi << 3);
    ESP_RETURN_ON_ERROR(codec_write(REG02, regv), TAG, "codec REG02 write failed");

    // REG03/REG04: ADC/DAC oversampling and fs mode.
    ESP_RETURN_ON_ERROR(codec_write(REG03, static_cast<uint8_t>((c.fs_mode << 6) | c.adc_osr)), TAG, "codec REG03 failed");
    ESP_RETURN_ON_ERROR(codec_write(REG04, c.dac_osr), TAG, "codec REG04 failed");

    // REG05: adc/dac divider.
    ESP_RETURN_ON_ERROR(codec_write(REG05, static_cast<uint8_t>(((c.adc_div - 1u) << 4) | (c.dac_div - 1u))), TAG, "codec REG05 failed");

    // REG06: preserve top 3 bits, set bclk divider field.
    ESP_RETURN_ON_ERROR(codec_read(REG06, &regv), TAG, "codec REG06 read failed");
    regv &= 0xE0;
    regv |= static_cast<uint8_t>((c.bclk_div < 19u) ? (c.bclk_div - 1u) : c.bclk_div);
    ESP_RETURN_ON_ERROR(codec_write(REG06, regv), TAG, "codec REG06 failed");

    // REG07/REG08: lrck divider.
    ESP_RETURN_ON_ERROR(codec_read(REG07, &regv), TAG, "codec REG07 read failed");
    regv &= 0xC0;
    regv |= c.lrck_h;
    ESP_RETURN_ON_ERROR(codec_write(REG07, regv), TAG, "codec REG07 failed");
    ESP_RETURN_ON_ERROR(codec_write(REG08, c.lrck_l), TAG, "codec REG08 failed");

    return ESP_OK;
}

esp_err_t codec_resolution_config(uint8_t* reg, int bits)
{
    ESP_RETURN_ON_FALSE(reg != nullptr, ESP_ERR_INVALID_ARG, TAG, "null resolution reg");
    switch (bits) {
    case 16:
        *reg |= (3u << 2);
        break;
    case 18:
        *reg |= (2u << 2);
        break;
    case 20:
        *reg |= (1u << 2);
        break;
    case 24:
        *reg |= (0u << 2);
        break;
    case 32:
        *reg |= (4u << 2);
        break;
    default:
        return ESP_ERR_INVALID_ARG;
    }
    return ESP_OK;
}

esp_err_t codec_fmt_config(int bits_in, int bits_out)
{
    uint8_t reg09 = 0;  // SDP In
    uint8_t reg0a = 0;  // SDP Out
    uint8_t reg00 = 0;

    // Slave serial port mode.
    ESP_RETURN_ON_ERROR(codec_read(REG00, &reg00), TAG, "codec REG00 read failed");
    reg00 &= static_cast<uint8_t>(~(1u << 6));
    ESP_RETURN_ON_ERROR(codec_write(REG00, reg00), TAG, "codec REG00 slave mode failed");

    ESP_RETURN_ON_ERROR(codec_resolution_config(&reg09, bits_in), TAG, "codec resolution in failed");
    ESP_RETURN_ON_ERROR(codec_resolution_config(&reg0a, bits_out), TAG, "codec resolution out failed");
    ESP_RETURN_ON_ERROR(codec_write(REG09, reg09), TAG, "codec REG09 failed");
    ESP_RETURN_ON_ERROR(codec_write(REG0A, reg0a), TAG, "codec REG0A failed");
    return ESP_OK;
}

esp_err_t codec_clock_config(bool mclk_from_pin, bool mclk_inverted, bool sclk_inverted, int sample_hz)
{
    uint8_t reg01 = 0x3F;  // enable all clocks
    uint8_t reg06 = 0;
    int mclk_hz = 0;

    if (mclk_from_pin) {
        mclk_hz = sample_hz * 256;  // 4.096MHz @16k
    } else {
        // SCLK-derived mode (not used on this board).
        mclk_hz = sample_hz * 16 * 2;
        reg01 |= (1u << 7);
    }
    if (mclk_inverted) {
        reg01 |= (1u << 6);
    }
    ESP_RETURN_ON_ERROR(codec_write(REG01, reg01), TAG, "codec REG01 failed");

    ESP_RETURN_ON_ERROR(codec_read(REG06, &reg06), TAG, "codec REG06 read failed");
    if (sclk_inverted) {
        reg06 |= (1u << 5);
    } else {
        reg06 &= static_cast<uint8_t>(~(1u << 5));
    }
    ESP_RETURN_ON_ERROR(codec_write(REG06, reg06), TAG, "codec REG06 sclk inv failed");

    return codec_sample_frequency_config(mclk_hz, sample_hz);
}

esp_err_t codec_voice_volume_set(int volume_percent)
{
    int v = volume_percent;
    if (v < 0) v = 0;
    if (v > 100) v = 100;

    const int reg32 = (v == 0) ? 0 : ((v * 256 / 100) - 1);
    return codec_write(REG32, static_cast<uint8_t>(reg32));
}

esp_err_t codec_voice_mute(bool mute)
{
    uint8_t reg31 = 0;
    ESP_RETURN_ON_ERROR(codec_read(REG31, &reg31), TAG, "codec REG31 read failed");
    if (mute) {
        reg31 |= static_cast<uint8_t>((1u << 6) | (1u << 5));
    } else {
        reg31 &= static_cast<uint8_t>(~((1u << 6) | (1u << 5)));
    }
    return codec_write(REG31, reg31);
}

esp_err_t codec_microphone_config(bool digital_mic)
{
    uint8_t reg14 = 0x1A;  // enable analog MIC and max PGA gain
    if (digital_mic) {
        reg14 |= (1u << 6);
    }
    ESP_RETURN_ON_ERROR(codec_write(REG17, 0xC8), TAG, "codec REG17 failed");
    return codec_write(REG14, reg14);
}

esp_err_t codec_init_fixed_16k(void)
{
    // Reset sequence.
    ESP_RETURN_ON_ERROR(codec_write(REG00, 0x1F), TAG, "codec reset step1 failed");
    vTaskDelay(pdMS_TO_TICKS(20));
    ESP_RETURN_ON_ERROR(codec_write(REG00, 0x00), TAG, "codec reset step2 failed");
    ESP_RETURN_ON_ERROR(codec_write(REG00, 0x80), TAG, "codec power-on failed");

    // Match the Freenove ES8311 init flow (clock + data format).
    ESP_RETURN_ON_ERROR(codec_clock_config(true, false, false, AUDIO_SAMPLE_RATE_HZ), TAG, "codec clock config failed");
    ESP_RETURN_ON_ERROR(codec_fmt_config(16, 16), TAG, "codec fmt config failed");

    // Power up analog blocks and DAC/ADC paths.
    ESP_RETURN_ON_ERROR(codec_write(REG0D, 0x01), TAG, "codec REG0D failed");
    ESP_RETURN_ON_ERROR(codec_write(REG0E, 0x02), TAG, "codec REG0E failed");
    ESP_RETURN_ON_ERROR(codec_write(REG12, 0x00), TAG, "codec REG12 failed");
    ESP_RETURN_ON_ERROR(codec_write(REG13, 0x10), TAG, "codec REG13 failed");
    ESP_RETURN_ON_ERROR(codec_write(REG1C, 0x6A), TAG, "codec REG1C failed");
    ESP_RETURN_ON_ERROR(codec_write(REG37, 0x08), TAG, "codec REG37 failed");

    // Match Freenove sequence: re-apply sample frequency and configure mic path.
    ESP_RETURN_ON_ERROR(codec_sample_frequency_config(4096000, AUDIO_SAMPLE_RATE_HZ), TAG, "codec sample cfg failed");
    ESP_RETURN_ON_ERROR(codec_microphone_config(false), TAG, "codec microphone config failed");
    ESP_RETURN_ON_ERROR(codec_write(REG16, ES8311_MIC_GAIN_24DB), TAG, "codec mic gain failed");

    ESP_RETURN_ON_ERROR(codec_voice_volume_set(AUDIO_VOLUME_PERCENT), TAG, "codec volume failed");
    ESP_RETURN_ON_ERROR(codec_voice_mute(false), TAG, "codec unmute failed");

    // Set default fade.
    ESP_RETURN_ON_ERROR(codec_write(REG15, 0x00), TAG, "codec mic fade failed");

    return ESP_OK;
}

esp_err_t i2s_init(void)
{
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.auto_clear = true;
    ESP_RETURN_ON_ERROR(i2s_new_channel(&chan_cfg, &s_tx, &s_rx), TAG, "i2s_new_channel failed");

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE_HZ),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = PIN_I2S_MCK,
            .bclk = PIN_I2S_BCK,
            .ws = PIN_I2S_WS,
            .dout = PIN_I2S_DOUT,
            .din = PIN_I2S_DIN,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };
    // Match Freenove's working echo setup: mono stream on LEFT slot.
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;
    std_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;

    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(s_tx, &std_cfg), TAG, "i2s tx init failed");
    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(s_rx, &std_cfg), TAG, "i2s rx init failed");
    ESP_RETURN_ON_ERROR(i2s_channel_enable(s_tx), TAG, "i2s tx enable failed");
    ESP_RETURN_ON_ERROR(i2s_channel_enable(s_rx), TAG, "i2s rx enable failed");
    return ESP_OK;
}

esp_err_t codec_i2c_attach(void)
{
    i2c_master_bus_handle_t bus = touch_get_i2c_bus();
    ESP_RETURN_ON_FALSE(bus != nullptr, ESP_ERR_INVALID_STATE, TAG, "touch I2C bus unavailable");

    ESP_RETURN_ON_ERROR(i2c_master_probe(bus, ES8311_ADDR, I2C_TIMEOUT_MS), TAG, "ES8311 probe failed at 0x%02X", ES8311_ADDR);

    i2c_device_config_t dev_cfg = {};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = ES8311_ADDR;
    dev_cfg.scl_speed_hz = 400000;
    ESP_RETURN_ON_ERROR(i2c_master_bus_add_device(bus, &dev_cfg, &s_codec_dev), TAG, "codec add device failed");
    return ESP_OK;
}

void run_tone(uint32_t duration_ms, uint32_t freq_hz, int16_t amp)
{
    if (!s_ready.load(std::memory_order_acquire)) {
        ESP_LOGW(TAG, "tone skipped: audio not ready");
        return;
    }

    if (duration_ms == 0) {
        duration_ms = DEFAULT_TONE_MS;
    }

    constexpr size_t kChunkFrames = 256;
    constexpr double kPi = 3.14159265358979323846;
    int16_t out[kChunkFrames];
    size_t bytes_written = 0;
    double phase = 0.0;
    const double phase_step = 2.0 * kPi * static_cast<double>(freq_hz) / static_cast<double>(AUDIO_SAMPLE_RATE_HZ);
    uint32_t frames_left = static_cast<uint32_t>((static_cast<uint64_t>(duration_ms) * AUDIO_SAMPLE_RATE_HZ) / 1000ULL);
    const uint32_t frames_total = frames_left;
    uint32_t frames_written = 0;
    const uint32_t fade_frames = std::max<uint32_t>(1, (AUDIO_SAMPLE_RATE_HZ * TONE_EDGE_FADE_MS) / 1000U);

    ESP_LOGI(TAG, "tone start: duration_ms=%u frames=%u freq=%u amp=%d",
             static_cast<unsigned>(duration_ms),
             static_cast<unsigned>(frames_total),
             static_cast<unsigned>(freq_hz),
             static_cast<int>(amp));
    set_amp_enabled(true);
    vTaskDelay(pdMS_TO_TICKS(AMP_WAKE_DELAY_MS));
    s_playing.store(true, std::memory_order_release);

    while (frames_left > 0 && !s_abort.load(std::memory_order_acquire)) {
        const size_t frames = std::min<size_t>(kChunkFrames, frames_left);
        for (size_t i = 0; i < frames; i++) {
            const uint32_t sample_idx = frames_written + static_cast<uint32_t>(i);
            const uint32_t frames_remaining = (frames_total > sample_idx) ? (frames_total - sample_idx) : 0;
            const float attack = (sample_idx < fade_frames) ? (static_cast<float>(sample_idx) / static_cast<float>(fade_frames)) : 1.0f;
            const float release = (frames_remaining < fade_frames) ? (static_cast<float>(frames_remaining) / static_cast<float>(fade_frames)) : 1.0f;
            const float env = std::min(attack, release);
            const int16_t v = static_cast<int16_t>(std::sin(phase) * static_cast<double>(amp) * static_cast<double>(env));
            out[i] = v;
            phase += phase_step;
            if (phase >= 2.0 * kPi) {
                phase -= 2.0 * kPi;
            }
        }

        esp_err_t err = i2s_channel_write(s_tx, out, frames * sizeof(int16_t), &bytes_written, I2S_TIMEOUT_MS);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "tone write failed: %s", esp_err_to_name(err));
            break;
        }
        const size_t frames_committed = bytes_written / sizeof(int16_t);
        if (frames_committed < frames) {
            ESP_LOGW(TAG, "tone short write: committed=%u requested=%u",
                     static_cast<unsigned>(frames_committed),
                     static_cast<unsigned>(frames));
        }
        // Keep streaming even on short writes to avoid over-constraining playback.
        frames_left -= static_cast<uint32_t>(frames);
        frames_written += static_cast<uint32_t>(frames);
    }

    s_playing.store(false, std::memory_order_release);
    if (!KEEP_AMP_ENABLED_BETWEEN_PLAYS) {
        set_amp_enabled(false);
    }
    ESP_LOGI(TAG, "tone done: frames_written=%u/%u abort=%d", static_cast<unsigned>(frames_written), static_cast<unsigned>(frames_total), s_abort.load(std::memory_order_acquire) ? 1 : 0);
}

void run_mic_probe(uint32_t duration_ms)
{
    if (!s_ready.load(std::memory_order_acquire)) {
        ESP_LOGW(TAG, "mic probe skipped: audio not ready");
        return;
    }
    if (duration_ms == 0) {
        duration_ms = DEFAULT_MIC_PROBE_MS;
    }

    constexpr size_t kChunkBytes = 1024;
    int16_t in[kChunkBytes / sizeof(int16_t)];
    ProbeStats left = {};
    ProbeStats right = {};
    ProbeStats mono = {};
    uint32_t read_timeouts = 0;
    uint32_t read_errors = 0;
    const int64_t deadline_us = esp_timer_get_time() + static_cast<int64_t>(duration_ms) * 1000;

    while (esp_timer_get_time() < deadline_us && !s_abort.load(std::memory_order_acquire)) {
        size_t bytes_read = 0;
        esp_err_t err = i2s_channel_read(s_rx, in, sizeof(in), &bytes_read, 200);
        if (err != ESP_OK) {
            read_errors++;
            continue;
        }
        if (bytes_read == 0) {
            read_timeouts++;
            continue;
        }

        const size_t n = bytes_read / sizeof(int16_t);
        for (size_t i = 0; i < n; i++) {
            const int16_t sample = in[i];
            probe_stats_add_sample(&mono, sample);
            if ((i & 1u) == 0u) {
                probe_stats_add_sample(&left, sample);
            } else {
                probe_stats_add_sample(&right, sample);
            }
        }
    }

    if (mono.sample_count == 0) {
        publish_mic_probe_stats(
            duration_ms,
            0,
            read_timeouts,
            read_errors,
            0.0,
            0,
            -120.0,
            0,   // mono
            false);
        ESP_LOGW(TAG, "mic probe: no samples read (duration_ms=%u, read_timeouts=%u, read_errors=%u)",
                 static_cast<unsigned>(duration_ms),
                 static_cast<unsigned>(read_timeouts),
                 static_cast<unsigned>(read_errors));
        if (MIC_PROBE_RESULT_TONE) {
            // Two low beeps means RX path produced no samples.
            run_tone(MIC_PROBE_RESULT_TONE_MS, MIC_PROBE_FAIL_TONE_HZ, MIC_PROBE_RESULT_TONE_AMP);
            vTaskDelay(pdMS_TO_TICKS(60));
            run_tone(MIC_PROBE_RESULT_TONE_MS, MIC_PROBE_FAIL_TONE_HZ, MIC_PROBE_RESULT_TONE_AMP);
        }
        return;
    }

    const double rms_left = probe_stats_rms(left);
    const double rms_right = probe_stats_rms(right);
    const double rms_mono = probe_stats_rms(mono);

    const bool left_valid = left.sample_count > 0;
    const bool right_valid = right.sample_count > 0;
    double active_rms = rms_mono;
    int32_t active_peak = mono.peak;
    const char* active_slot = "mono";
    if (left_valid || right_valid) {
        if (right_valid && (!left_valid || rms_right > rms_left)) {
            active_rms = rms_right;
            active_peak = right.peak;
            active_slot = "right";
        } else {
            active_rms = rms_left;
            active_peak = left.peak;
            active_slot = "left";
        }
    }

    // Use the strongest slot to avoid false negatives when wiring/slot layout differs.
    const bool active = active_rms >= MIC_ACTIVITY_RMS_THRESHOLD;
    const double active_dbfs = rms_to_dbfs(active_rms);
    uint8_t selected_channel = 0;  // mono
    if (left_valid || right_valid) {
        selected_channel = (active_slot[0] == 'r') ? 2 : 1;
    }
    publish_mic_probe_stats(
        duration_ms,
        mono.sample_count,
        read_timeouts,
        read_errors,
        active_rms,
        active_peak,
        active_dbfs,
        selected_channel,
        active);
    ESP_LOGI(TAG,
             "mic probe: duration_ms=%u samples=%u to=%u err=%u "
             "left(rms=%.1f peak=%d n=%u) right(rms=%.1f peak=%d n=%u) "
             "selected=%s rms=%.1f peak=%d dbfs=%.1f",
             static_cast<unsigned>(duration_ms),
             static_cast<unsigned>(mono.sample_count),
             static_cast<unsigned>(read_timeouts),
             static_cast<unsigned>(read_errors),
             rms_left,
             static_cast<int>(left.peak),
             static_cast<unsigned>(left.sample_count),
             rms_right,
             static_cast<int>(right.peak),
             static_cast<unsigned>(right.sample_count),
             active_slot,
             active_rms,
             static_cast<int>(active_peak),
             active_dbfs);
    if (MIC_PROBE_RESULT_TONE) {
        run_tone(MIC_PROBE_RESULT_TONE_MS,
                 active ? MIC_PROBE_PASS_TONE_HZ : MIC_PROBE_FAIL_TONE_HZ,
                 MIC_PROBE_RESULT_TONE_AMP);
    }
}

void audio_worker_task(void* arg)
{
    ESP_LOGI(TAG, "audio worker started, stack HWM=%u words",
             static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)));
    AudioCmd cmd = {};
    while (true) {
        if (xQueueReceive(s_cmd_queue, &cmd, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        ESP_LOGD(TAG, "audio worker cmd=%u stack HWM=%u words",
                 static_cast<unsigned>(cmd.type),
                 static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)));
        switch (cmd.type) {
        case AudioCmdType::TONE_1KHZ:
            s_abort.store(false, std::memory_order_release);
            run_tone(cmd.duration_ms, DIAG_TONE_FREQ_HZ, DIAG_TONE_AMP);
            break;
        case AudioCmdType::MIC_PROBE:
            s_abort.store(false, std::memory_order_release);
            run_mic_probe(cmd.duration_ms);
            break;
        case AudioCmdType::STOP:
            s_abort.store(true, std::memory_order_release);
            if (!KEEP_AMP_ENABLED_BETWEEN_PLAYS) {
                set_amp_enabled(false);
            }
            s_playing.store(false, std::memory_order_release);
            break;
        }
    }
}

bool enqueue_cmd(AudioCmdType type, uint32_t duration_ms)
{
    if (s_cmd_queue == nullptr || s_worker_task == nullptr) {
        return false;
    }
    eTaskState state = eTaskGetState(s_worker_task);
    if (state == eDeleted || state == eInvalid) {
        ESP_LOGW(TAG, "audio worker not alive (state=%d), forcing sync fallback", static_cast<int>(state));
        s_worker_task = nullptr;
        return false;
    }
    const AudioCmd cmd = {
        .type = type,
        .duration_ms = duration_ms,
    };
    if (xQueueSend(s_cmd_queue, &cmd, pdMS_TO_TICKS(10)) != pdTRUE) {
        ESP_LOGW(TAG, "audio cmd queue full, forcing sync fallback");
        return false;
    }
    return true;
}

void dump_codec_regs_impl(void)
{
    if (s_codec_dev == nullptr) {
        ESP_LOGW(TAG, "reg dump: codec not attached");
        return;
    }
    // ES8311 register map: 0x00-0x17, 0x1C, 0x31-0x32, 0x37, 0x44-0x45, 0xFD-0xFF
    static constexpr uint8_t ranges[][2] = {
        {0x00, 0x17}, {0x1C, 0x1C}, {0x31, 0x32}, {0x37, 0x37}, {0x44, 0x45}, {0xFD, 0xFF},
    };
    ESP_LOGI(TAG, "--- ES8311 register dump ---");
    for (const auto& r : ranges) {
        for (uint8_t addr = r[0]; addr <= r[1]; addr++) {
            uint8_t val = 0;
            esp_err_t err = codec_read(addr, &val);
            if (err == ESP_OK) {
                ESP_LOGI(TAG, "  REG[0x%02X] = 0x%02X", addr, val);
            } else {
                ESP_LOGW(TAG, "  REG[0x%02X] = READ_ERR (%s)", addr, esp_err_to_name(err));
            }
        }
    }
    ESP_LOGI(TAG, "--- end register dump ---");
}

}  // namespace

void audio_init(void)
{
    gpio_config_t amp_cfg = {};
    amp_cfg.pin_bit_mask = 1ULL << PIN_AMP_EN;
    amp_cfg.mode = GPIO_MODE_OUTPUT;
    ESP_ERROR_CHECK(gpio_config(&amp_cfg));
    // Keep amp enabled by default (vendor examples do this) to avoid missing
    // short diagnostics due to power-gate timing.
    set_amp_enabled(true);

    esp_err_t err = i2s_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s init failed: %s", esp_err_to_name(err));
        return;
    }

    err = codec_i2c_attach();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "codec i2c attach failed: %s", esp_err_to_name(err));
        return;
    }

    err = codec_init_fixed_16k();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "codec init failed: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "codec init OK");

    s_cmd_queue = xQueueCreate(4, sizeof(AudioCmd));
    if (s_cmd_queue == nullptr) {
        ESP_LOGW(TAG, "audio cmd queue allocation failed; using sync diagnostics path");
    } else {
        BaseType_t task_ok = xTaskCreatePinnedToCore(audio_worker_task,
                                                     "audio_diag",
                                                     AUDIO_WORKER_STACK_BYTES,
                                                     nullptr,
                                                     AUDIO_WORKER_PRIORITY,
                                                     &s_worker_task,
                                                     AUDIO_WORKER_CORE);
        if (task_ok != pdPASS) {
            ESP_LOGW(TAG, "audio worker task create failed; using sync diagnostics path");
            vQueueDelete(s_cmd_queue);
            s_cmd_queue = nullptr;
            s_worker_task = nullptr;
        }
    }

    s_ready.store(true, std::memory_order_release);
    ESP_LOGI(TAG, "audio initialized: ES8311 + I2S @%dHz (%s)",
             AUDIO_SAMPLE_RATE_HZ,
             (s_worker_task != nullptr) ? "async worker" : "sync fallback");
}

void audio_play_pcm(const int16_t* samples, size_t num_samples)
{
    if (!audio_is_ready() || samples == nullptr || num_samples == 0) {
        return;
    }

    constexpr size_t kChunkSamples = 256;
    int16_t out[kChunkSamples];
    size_t pos = 0;
    size_t bytes_written = 0;

    set_amp_enabled(true);
    vTaskDelay(pdMS_TO_TICKS(AMP_WAKE_DELAY_MS));
    s_playing.store(true, std::memory_order_release);

    while (pos < num_samples && !s_abort.load(std::memory_order_acquire)) {
        const size_t n = std::min(kChunkSamples, num_samples - pos);
        // TX path is configured MONO+LEFT; write one sample per frame.
        for (size_t i = 0; i < n; i++) {
            out[i] = samples[pos + i];
        }
        esp_err_t err = i2s_channel_write(s_tx, out, n * sizeof(int16_t), &bytes_written, I2S_TIMEOUT_MS);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "pcm write failed: %s", esp_err_to_name(err));
            break;
        }
        const size_t samples_committed = bytes_written / sizeof(int16_t);
        if (samples_committed < n) {
            ESP_LOGW(TAG, "pcm short write: committed=%u requested=%u",
                     static_cast<unsigned>(samples_committed),
                     static_cast<unsigned>(n));
        }
        pos += n;
    }

    s_playing.store(false, std::memory_order_release);
    if (!KEEP_AMP_ENABLED_BETWEEN_PLAYS) {
        set_amp_enabled(false);
    }
}

void audio_stop(void)
{
    if (enqueue_cmd(AudioCmdType::STOP, 0)) {
        return;
    }
    s_abort.store(true, std::memory_order_release);
    if (!KEEP_AMP_ENABLED_BETWEEN_PLAYS) {
        set_amp_enabled(false);
    }
    s_playing.store(false, std::memory_order_release);
}

void audio_mic_start(void)
{
    audio_run_mic_probe(5000);
}

void audio_mic_stop(void)
{
    audio_stop();
}

void audio_play_test_tone(uint32_t duration_ms)
{
    if (!audio_is_ready()) {
        ESP_LOGW(TAG, "tone command dropped (audio not ready)");
        return;
    }
    if (FORCE_SYNC_DIAGNOSTICS) {
        ESP_LOGI(TAG, "tone sync diagnostics: %u ms", static_cast<unsigned>(duration_ms));
        s_abort.store(false, std::memory_order_release);
        run_tone(duration_ms, DIAG_TONE_FREQ_HZ, DIAG_TONE_AMP);
        return;
    }
    if (enqueue_cmd(AudioCmdType::TONE_1KHZ, duration_ms)) {
        ESP_LOGI(TAG, "tone queued: %u ms", static_cast<unsigned>(duration_ms));
        return;
    }
    // Fallback path: run directly when queue/worker is unavailable.
    ESP_LOGW(TAG, "tone sync fallback: %u ms", static_cast<unsigned>(duration_ms));
    s_abort.store(false, std::memory_order_release);
    run_tone(duration_ms, DIAG_TONE_FREQ_HZ, DIAG_TONE_AMP);
}

void audio_run_mic_probe(uint32_t duration_ms)
{
    if (!audio_is_ready()) {
        ESP_LOGW(TAG, "mic probe command dropped (audio not ready)");
        return;
    }
    if (FORCE_SYNC_DIAGNOSTICS) {
        s_abort.store(false, std::memory_order_release);
        run_mic_probe(duration_ms);
        return;
    }
    if (enqueue_cmd(AudioCmdType::MIC_PROBE, duration_ms)) {
        return;
    }
    s_abort.store(false, std::memory_order_release);
    run_mic_probe(duration_ms);
}

bool audio_is_playing(void)
{
    return s_playing.load(std::memory_order_acquire);
}

bool audio_is_ready(void)
{
    return s_ready.load(std::memory_order_acquire);
}

bool audio_mic_activity_detected(void)
{
    return s_mic_activity.load(std::memory_order_acquire);
}

MicProbeStats audio_get_mic_probe_stats(void)
{
    MicProbeStats stats = {};
    stats.probe_seq = s_probe_seq.load(std::memory_order_acquire);
    stats.duration_ms = s_probe_duration_ms.load(std::memory_order_acquire);
    stats.sample_count = s_probe_sample_count.load(std::memory_order_acquire);
    stats.read_timeouts = s_probe_read_timeouts.load(std::memory_order_acquire);
    stats.read_errors = s_probe_read_errors.load(std::memory_order_acquire);
    stats.selected_rms_x10 = s_probe_selected_rms_x10.load(std::memory_order_acquire);
    stats.selected_peak = s_probe_selected_peak.load(std::memory_order_acquire);
    stats.selected_dbfs_x10 = s_probe_selected_dbfs_x10.load(std::memory_order_acquire);
    stats.selected_channel = s_probe_selected_channel.load(std::memory_order_acquire);
    stats.active = s_mic_activity.load(std::memory_order_acquire);
    return stats;
}

void audio_dump_codec_regs(void)
{
    dump_codec_regs_impl();
}

void audio_boot_tone_sync(uint32_t duration_ms)
{
    if (!s_ready.load(std::memory_order_acquire)) {
        ESP_LOGW(TAG, "boot tone skipped: audio not ready");
        return;
    }
    ESP_LOGI(TAG, "boot tone sync: %u ms (blocking)", static_cast<unsigned>(duration_ms));
    s_abort.store(false, std::memory_order_release);
    run_tone(duration_ms, BOOT_TONE_FREQ_HZ, BOOT_TONE_AMP);
}
