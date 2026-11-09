#include "expander.h"
#include "i2c_bus.h"
#include "pin_map.h"

#include "driver/i2c_master.h"
#include "esp_log.h"

static const char* TAG = "expander";

// TCA9554A registers
static constexpr uint8_t REG_INPUT = 0x00;  // pin levels, read-only
static constexpr uint8_t REG_OUTPUT = 0x01; // output latch
static constexpr uint8_t REG_CONFIG = 0x03; // 1 = input (power-up default 0xFF)

static constexpr int I2C_TIMEOUT_MS = 10;

static i2c_master_dev_handle_t s_dev = nullptr;
static bool                    s_ok = false;

static esp_err_t write_reg(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(s_dev, buf, 2, I2C_TIMEOUT_MS);
}

static esp_err_t read_reg(uint8_t reg, uint8_t* val)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, val, 1, I2C_TIMEOUT_MS);
}

bool expander_init()
{
    s_ok = false;
    if (!i2c_bus_init()) return false;
    if (!s_dev) {
        i2c_device_config_t cfg = {};
        cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
        cfg.device_address = EXP_I2C_ADDR;
        cfg.scl_speed_hz = 400000;
        if (i2c_master_bus_add_device(i2c_bus_handle(), &cfg, &s_dev) != ESP_OK) {
            ESP_LOGE(TAG, "add device 0x%02X failed", EXP_I2C_ADDR);
            s_dev = nullptr;
            return false;
        }
    }
    // Latch low first, then switch P0-P3 to outputs (P4-P7 stay inputs).
    if (write_reg(REG_OUTPUT, 0x00) != ESP_OK || write_reg(REG_CONFIG, static_cast<uint8_t>(~EXP_DIR_MASK)) != ESP_OK) {
        ESP_LOGE(TAG, "TCA9554A at 0x%02X not answering", EXP_I2C_ADDR);
        return false;
    }
    uint8_t cfg_rb = 0;
    if (read_reg(REG_CONFIG, &cfg_rb) != ESP_OK || cfg_rb != static_cast<uint8_t>(~EXP_DIR_MASK)) {
        ESP_LOGE(TAG, "config readback 0x%02X", cfg_rb);
        return false;
    }
    s_ok = true;
    ESP_LOGI(TAG, "TCA9554A ready, direction lines low");
    return true;
}

bool expander_write_dir(uint8_t bits)
{
    bits &= EXP_DIR_MASK;
    if (!s_dev) return false;
    if (write_reg(REG_OUTPUT, bits) != ESP_OK) {
        s_ok = false;
        return false;
    }
    uint8_t in = 0;
    if (read_reg(REG_INPUT, &in) != ESP_OK || (in & EXP_DIR_MASK) != bits) {
        s_ok = false;
        return false;
    }
    s_ok = true;
    return true;
}

bool expander_ok()
{
    return s_ok;
}
