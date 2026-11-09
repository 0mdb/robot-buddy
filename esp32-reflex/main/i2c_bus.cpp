#include "i2c_bus.h"
#include "pin_map.h"

#include "driver/gpio.h"
#include "esp_log.h"
#include "rom/ets_sys.h"

static const char* TAG = "i2c_bus";

static i2c_master_bus_handle_t s_bus = nullptr;

static constexpr int RECOVERY_CLK_PULSES = 9;
static constexpr int RECOVERY_HALF_PERIOD_US = 5; // ~100 kHz

// Bit-bang recovery for the case where the driver could not even be created
// (SDA held low at boot). Once the bus exists, i2c_master_bus_reset() does this.
static void bitbang_recover()
{
    ESP_LOGW(TAG, "bit-bang bus recovery");

    gpio_config_t cfg = {};
    cfg.pin_bit_mask = (1ULL << PIN_I2C_SCL) | (1ULL << PIN_I2C_SDA);
    cfg.mode = GPIO_MODE_INPUT_OUTPUT_OD;
    cfg.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&cfg);

    gpio_set_level(PIN_I2C_SDA, 1);
    for (int i = 0; i < RECOVERY_CLK_PULSES; i++) {
        gpio_set_level(PIN_I2C_SCL, 0);
        ets_delay_us(RECOVERY_HALF_PERIOD_US);
        gpio_set_level(PIN_I2C_SCL, 1);
        ets_delay_us(RECOVERY_HALF_PERIOD_US);
        if (gpio_get_level(PIN_I2C_SDA) == 1) {
            ESP_LOGI(TAG, "SDA released after %d clocks", i + 1);
            break;
        }
    }
    // STOP: SDA low -> SCL high -> SDA high
    gpio_set_level(PIN_I2C_SDA, 0);
    ets_delay_us(RECOVERY_HALF_PERIOD_US);
    gpio_set_level(PIN_I2C_SCL, 1);
    ets_delay_us(RECOVERY_HALF_PERIOD_US);
    gpio_set_level(PIN_I2C_SDA, 1);
    ets_delay_us(RECOVERY_HALF_PERIOD_US);

    gpio_reset_pin(PIN_I2C_SCL);
    gpio_reset_pin(PIN_I2C_SDA);
}

static bool create_bus()
{
    i2c_master_bus_config_t cfg = {};
    cfg.i2c_port = I2C_NUM_1;
    cfg.sda_io_num = PIN_I2C_SDA;
    cfg.scl_io_num = PIN_I2C_SCL;
    cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    cfg.glitch_ignore_cnt = 7;
    // The board has 4.7k pull-ups (R16/R17); the internal ones are harmless in parallel.
    cfg.flags.enable_internal_pullup = true;

    esp_err_t err = i2c_new_master_bus(&cfg, &s_bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_new_master_bus failed: %s", esp_err_to_name(err));
        s_bus = nullptr;
        return false;
    }
    return true;
}

bool i2c_bus_init()
{
    if (s_bus) return true;
    ESP_LOGI(TAG, "I²C bus: SDA=GPIO%d SCL=GPIO%d", PIN_I2C_SDA, PIN_I2C_SCL);
    if (create_bus()) return true;
    bitbang_recover();
    return create_bus();
}

i2c_master_bus_handle_t i2c_bus_handle()
{
    return s_bus;
}

bool i2c_bus_recover()
{
    if (!s_bus) return i2c_bus_init();
    esp_err_t err = i2c_master_bus_reset(s_bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_master_bus_reset failed: %s", esp_err_to_name(err));
        return false;
    }
    return true;
}
