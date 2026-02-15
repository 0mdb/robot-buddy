#include "imu.h"
#include "bmi270_config.h"
#include "config.h"
#include "pin_map.h"
#include "shared_state.h"

#include "driver/i2c_master.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rom/ets_sys.h"

#include <cmath>
#include <cstring>

static const char* TAG = "imu";

// ---- BMI270 register map ----
static constexpr uint8_t BMI270_ADDR          = 0x68;  // SDO/SA0 to GND (0x69 if SDO→VDDIO)
static constexpr uint8_t REG_CHIP_ID          = 0x00;
static constexpr uint8_t BMI270_CHIP_ID_VAL   = 0x24;

static constexpr uint8_t REG_STATUS           = 0x03;
static constexpr uint8_t REG_ACC_DATA_X_LSB   = 0x0C;  // accel data: 6 bytes (0x0C–0x11)
static constexpr uint8_t REG_GYR_DATA_X_LSB   = 0x12;  // gyro data:  6 bytes (0x12–0x17)
static constexpr uint8_t REG_INTERNAL_STATUS  = 0x21;

static constexpr uint8_t REG_ACC_CONF         = 0x40;
static constexpr uint8_t REG_ACC_RANGE        = 0x41;
static constexpr uint8_t REG_GYR_CONF         = 0x42;
static constexpr uint8_t REG_GYR_RANGE        = 0x43;

static constexpr uint8_t REG_INIT_CTRL        = 0x59;
static constexpr uint8_t REG_INIT_DATA        = 0x5E;

static constexpr uint8_t REG_PWR_CONF         = 0x7C;
static constexpr uint8_t REG_PWR_CTRL         = 0x7D;
static constexpr uint8_t REG_CMD              = 0x7E;

// ---- ACC_CONF register: [7] acc_filter_perf | [6:4] acc_bwp | [3:0] acc_odr ----
// ODR encoding (acc_odr field):
//   0x05=25Hz, 0x06=25Hz, 0x07=50Hz, 0x08=100Hz,
//   0x09=200Hz, 0x0A=400Hz, 0x0B=800Hz, 0x0C=1600Hz
// BWP: 0x02=normal, 0x01=OSR2, 0x00=OSR4
// filter_perf: 1=high perf (recommended when ODR>=100Hz)
static constexpr uint8_t ACC_ODR_200HZ  = 0x09;
static constexpr uint8_t ACC_ODR_400HZ  = 0x0A;
static constexpr uint8_t ACC_ODR_800HZ  = 0x0B;
static constexpr uint8_t ACC_BWP_NORM   = 0x02;
static constexpr uint8_t ACC_FILTER_HP  = 0x01;  // bit 7

// ---- ACC_RANGE register [1:0] ----
static constexpr uint8_t ACC_RANGE_2G   = 0x00;
static constexpr uint8_t ACC_RANGE_4G   = 0x01;
static constexpr uint8_t ACC_RANGE_8G   = 0x02;
static constexpr uint8_t ACC_RANGE_16G  = 0x03;

// ---- GYR_CONF register: [7] gyr_filter_perf | [6] gyr_noise_perf | [5:4] gyr_bwp | [3:0] gyr_odr ----
// ODR encoding (same as accel): 0x09=200Hz, 0x0A=400Hz, 0x0B=800Hz, ...
static constexpr uint8_t GYR_ODR_200HZ  = 0x09;
static constexpr uint8_t GYR_ODR_400HZ  = 0x0A;
static constexpr uint8_t GYR_ODR_800HZ  = 0x0B;
static constexpr uint8_t GYR_BWP_NORM   = 0x02;
static constexpr uint8_t GYR_NOISE_HP   = 0x01;  // bit 6
static constexpr uint8_t GYR_FILTER_HP  = 0x01;  // bit 7

// ---- GYR_RANGE register [2:0] ----
static constexpr uint8_t GYR_RANGE_2000 = 0x00;  // ±2000 dps
static constexpr uint8_t GYR_RANGE_1000 = 0x01;  // ±1000 dps
static constexpr uint8_t GYR_RANGE_500  = 0x02;  // ±500 dps
static constexpr uint8_t GYR_RANGE_250  = 0x03;  // ±250 dps
static constexpr uint8_t GYR_RANGE_125  = 0x04;  // ±125 dps

// ---- PWR_CTRL bits ----
static constexpr uint8_t PWR_CTRL_AUX_EN  = 0x01;
static constexpr uint8_t PWR_CTRL_GYR_EN  = 0x02;
static constexpr uint8_t PWR_CTRL_ACC_EN  = 0x04;
static constexpr uint8_t PWR_CTRL_TEMP_EN = 0x08;

// ---- Sensitivity lookup tables (LSB/unit) ----
// Accelerometer: LSB/g for each range setting
static constexpr float ACCEL_SENS_TABLE[] = {
    // ACC_RANGE_2G  → 16384 LSB/g  → 0.0000610 g/LSB
    // ACC_RANGE_4G  → 8192  LSB/g  → 0.000122  g/LSB
    // ACC_RANGE_8G  → 4096  LSB/g  → 0.000244  g/LSB
    // ACC_RANGE_16G → 2048  LSB/g  → 0.000488  g/LSB
    1.0f / 16384.0f,  // ±2g
    1.0f / 8192.0f,   // ±4g
    1.0f / 4096.0f,   // ±8g
    1.0f / 2048.0f,   // ±16g
};

// Gyroscope: (dps/LSB) for each range setting
static constexpr float GYRO_SENS_DPS_TABLE[] = {
    // GYR_RANGE_2000 → 16.4 LSB/dps  → 0.061035 dps/LSB
    // GYR_RANGE_1000 → 32.8 LSB/dps  → 0.030518 dps/LSB
    // GYR_RANGE_500  → 65.5 LSB/dps  → 0.015267 dps/LSB
    // GYR_RANGE_250  → 131.1 LSB/dps → 0.007630 dps/LSB
    // GYR_RANGE_125  → 262.1 LSB/dps → 0.003815 dps/LSB
    1.0f / 16.4f,    // ±2000 dps
    1.0f / 32.8f,    // ±1000 dps
    1.0f / 65.5f,    // ±500 dps
    1.0f / 131.1f,   // ±250 dps
    1.0f / 262.1f,   // ±125 dps
};

// Runtime sensitivity values — set during configure() from g_cfg range selections
static float s_accel_sens_g  = ACCEL_SENS_TABLE[ACC_RANGE_2G];
static float s_gyro_sens_rad = GYRO_SENS_DPS_TABLE[GYR_RANGE_500] * (M_PI / 180.0f);

// ---- I²C driver state ----
static i2c_master_bus_handle_t s_bus = nullptr;
static i2c_master_dev_handle_t s_dev = nullptr;

// ---- I²C bus recovery ----
// If SDA is stuck low (slave holding it), bit-bang SCL to clock out the
// stuck slave, then issue a STOP condition, then re-init the driver.

static constexpr int RECOVERY_CLK_PULSES    = 9;
static constexpr int RECOVERY_HALF_PERIOD_US = 5;  // ~100 kHz

static void i2c_bus_recover()
{
    ESP_LOGW(TAG, "attempting I²C bus recovery...");

    if (s_dev) {
        i2c_master_bus_rm_device(s_dev);
        s_dev = nullptr;
    }
    if (s_bus) {
        i2c_del_master_bus(s_bus);
        s_bus = nullptr;
    }

    gpio_config_t scl_cfg = {};
    scl_cfg.pin_bit_mask = 1ULL << PIN_IMU_SCL;
    scl_cfg.mode = GPIO_MODE_INPUT_OUTPUT_OD;
    scl_cfg.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&scl_cfg);

    gpio_config_t sda_cfg = {};
    sda_cfg.pin_bit_mask = 1ULL << PIN_IMU_SDA;
    sda_cfg.mode = GPIO_MODE_INPUT_OUTPUT_OD;
    sda_cfg.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&sda_cfg);

    gpio_set_level(PIN_IMU_SDA, 1);

    for (int i = 0; i < RECOVERY_CLK_PULSES; i++) {
        gpio_set_level(PIN_IMU_SCL, 0);
        ets_delay_us(RECOVERY_HALF_PERIOD_US);
        gpio_set_level(PIN_IMU_SCL, 1);
        ets_delay_us(RECOVERY_HALF_PERIOD_US);

        if (gpio_get_level(PIN_IMU_SDA) == 1) {
            ESP_LOGI(TAG, "SDA released after %d clocks", i + 1);
            break;
        }
    }

    // Generate STOP: SDA low → SCL high → SDA high
    gpio_set_level(PIN_IMU_SDA, 0);
    ets_delay_us(RECOVERY_HALF_PERIOD_US);
    gpio_set_level(PIN_IMU_SCL, 1);
    ets_delay_us(RECOVERY_HALF_PERIOD_US);
    gpio_set_level(PIN_IMU_SDA, 1);
    ets_delay_us(RECOVERY_HALF_PERIOD_US);

    gpio_reset_pin(PIN_IMU_SCL);
    gpio_reset_pin(PIN_IMU_SDA);

    ESP_LOGI(TAG, "bus recovery complete, will re-init driver");
}

// ---- I²C init / reinit ----

static bool i2c_driver_init()
{
    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.i2c_port = I2C_NUM_1;
    bus_cfg.sda_io_num = PIN_IMU_SDA;
    bus_cfg.scl_io_num = PIN_IMU_SCL;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;

    esp_err_t err = i2c_new_master_bus(&bus_cfg, &s_bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_new_master_bus failed: %s", esp_err_to_name(err));
        return false;
    }

    i2c_device_config_t dev_cfg = {};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = BMI270_ADDR;
    dev_cfg.scl_speed_hz = 400000;  // 400 kHz fast mode

    err = i2c_master_bus_add_device(s_bus, &dev_cfg, &s_dev);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_master_bus_add_device failed: %s", esp_err_to_name(err));
        return false;
    }

    return true;
}

// ---- Register read/write helpers ----

static esp_err_t reg_write(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(s_dev, buf, 2, 50);
}

static esp_err_t reg_read(uint8_t reg, uint8_t* data, size_t len)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, data, len, 50);
}

// Burst write for config file upload. The BMI270 auto-increments the
// write address within INIT_DATA, so we can chunk the upload.
static esp_err_t burst_write(uint8_t reg, const uint8_t* data, size_t len)
{
    // I2C frame: [reg] [data...].  Max ~256 bytes per transaction
    // to avoid hogging the bus.  The ESP-IDF I2C driver handles framing.
    static constexpr size_t CHUNK = 128;

    for (size_t off = 0; off < len; off += CHUNK) {
        size_t n = (len - off > CHUNK) ? CHUNK : (len - off);

        // Build frame: register byte + payload
        uint8_t buf[1 + CHUNK];
        buf[0] = reg;
        memcpy(&buf[1], &data[off], n);

        esp_err_t err = i2c_master_transmit(s_dev, buf, 1 + n, 100);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}

// ---- BMI270 configuration ----

// Map config enum values to ODR register values for ACC_CONF / GYR_CONF
static uint8_t imu_odr_to_reg(uint16_t odr_hz)
{
    if (odr_hz >= 1600) return 0x0C;
    if (odr_hz >= 800)  return 0x0B;
    if (odr_hz >= 400)  return 0x0A;
    if (odr_hz >= 200)  return 0x09;
    if (odr_hz >= 100)  return 0x08;
    if (odr_hz >= 50)   return 0x07;
    return 0x06;  // 25 Hz
}

// Map config gyro range enum to GYR_RANGE register value
static uint8_t gyro_range_dps_to_reg(uint16_t range_dps)
{
    if (range_dps >= 2000) return GYR_RANGE_2000;
    if (range_dps >= 1000) return GYR_RANGE_1000;
    if (range_dps >= 500)  return GYR_RANGE_500;
    if (range_dps >= 250)  return GYR_RANGE_250;
    return GYR_RANGE_125;
}

// Map config accel range enum to ACC_RANGE register value
static uint8_t accel_range_g_to_reg(uint8_t range_g)
{
    if (range_g >= 16) return ACC_RANGE_16G;
    if (range_g >= 8)  return ACC_RANGE_8G;
    if (range_g >= 4)  return ACC_RANGE_4G;
    return ACC_RANGE_2G;
}

static bool bmi270_configure()
{
    // Step 1: Read and verify CHIP_ID
    uint8_t chip_id = 0;
    if (reg_read(REG_CHIP_ID, &chip_id, 1) != ESP_OK || chip_id != BMI270_CHIP_ID_VAL) {
        ESP_LOGE(TAG, "CHIP_ID failed: got 0x%02X, expected 0x%02X", chip_id, BMI270_CHIP_ID_VAL);
        return false;
    }
    ESP_LOGI(TAG, "BMI270 detected (CHIP_ID=0x%02X)", chip_id);

    // Step 2: Soft reset
    esp_err_t err = reg_write(REG_CMD, 0xB6);
    if (err != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(2));  // BMI270 needs ~2 ms after soft reset

    // Re-verify chip ID after reset
    if (reg_read(REG_CHIP_ID, &chip_id, 1) != ESP_OK || chip_id != BMI270_CHIP_ID_VAL) {
        ESP_LOGE(TAG, "CHIP_ID after reset: 0x%02X", chip_id);
        return false;
    }

    // Step 3: Disable advanced power save for config load
    err = reg_write(REG_PWR_CONF, 0x00);
    if (err != ESP_OK) return false;
    ets_delay_us(450);  // datasheet: wait ≥450 µs

    // Step 4: Prepare config load
    err = reg_write(REG_INIT_CTRL, 0x00);
    if (err != ESP_OK) return false;

    // Step 5: Burst-write config file to INIT_DATA
    err = burst_write(REG_INIT_DATA, BMI270_CONFIG_FILE, BMI270_CONFIG_FILE_SIZE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "config file upload failed: %s", esp_err_to_name(err));
        return false;
    }

    // Step 6: Complete config load
    err = reg_write(REG_INIT_CTRL, 0x01);
    if (err != ESP_OK) return false;

    // Step 7: Wait for INTERNAL_STATUS == 0x01 (init OK), up to 20 ms
    vTaskDelay(pdMS_TO_TICKS(20));
    uint8_t status = 0;
    if (reg_read(REG_INTERNAL_STATUS, &status, 1) != ESP_OK || (status & 0x0F) != 0x01) {
        ESP_LOGE(TAG, "INTERNAL_STATUS = 0x%02X (expected 0x01), init failed", status);
        return false;
    }
    ESP_LOGI(TAG, "config file loaded OK (INTERNAL_STATUS=0x%02X)", status);

    // Step 8: Configure accelerometer
    uint8_t acc_range_reg = accel_range_g_to_reg(g_cfg.imu_accel_range_g);
    uint8_t acc_odr_reg   = imu_odr_to_reg(g_cfg.imu_odr_hz);
    uint8_t acc_conf = (ACC_FILTER_HP << 7) | (ACC_BWP_NORM << 4) | acc_odr_reg;

    err = reg_write(REG_ACC_CONF, acc_conf);
    if (err != ESP_OK) return false;
    err = reg_write(REG_ACC_RANGE, acc_range_reg);
    if (err != ESP_OK) return false;

    // Step 9: Configure gyroscope
    uint8_t gyr_range_reg = gyro_range_dps_to_reg(g_cfg.imu_gyro_range_dps);
    uint8_t gyr_odr_reg   = imu_odr_to_reg(g_cfg.imu_odr_hz);
    uint8_t gyr_conf = (GYR_FILTER_HP << 7) | (GYR_NOISE_HP << 6) | (GYR_BWP_NORM << 4) | gyr_odr_reg;

    err = reg_write(REG_GYR_CONF, gyr_conf);
    if (err != ESP_OK) return false;
    err = reg_write(REG_GYR_RANGE, gyr_range_reg);
    if (err != ESP_OK) return false;

    // Step 10: Enable accel + gyro + temp
    err = reg_write(REG_PWR_CTRL, PWR_CTRL_ACC_EN | PWR_CTRL_GYR_EN | PWR_CTRL_TEMP_EN);
    if (err != ESP_OK) return false;

    // Step 11: Set power mode — disable adv_power_save for continuous operation
    err = reg_write(REG_PWR_CONF, 0x02);  // fifo_self_wake=1, adv_power_save=0
    if (err != ESP_OK) return false;

    // Compute runtime sensitivity values from selected ranges
    s_accel_sens_g  = ACCEL_SENS_TABLE[acc_range_reg];
    s_gyro_sens_rad = GYRO_SENS_DPS_TABLE[gyr_range_reg] * (M_PI / 180.0f);

    ESP_LOGI(TAG, "BMI270 configured: ODR %u Hz, gyro ±%u dps, accel ±%u g",
             g_cfg.imu_odr_hz, g_cfg.imu_gyro_range_dps, g_cfg.imu_accel_range_g);
    ESP_LOGI(TAG, "  accel sens: %.6f g/LSB, gyro sens: %.6f rad/s/LSB",
             s_accel_sens_g, s_gyro_sens_rad);

    return true;
}

// ---- Public API ----

bool imu_init()
{
    if (!i2c_driver_init()) {
        ESP_LOGW(TAG, "I²C driver init failed, trying bus recovery...");
        i2c_bus_recover();
        if (!i2c_driver_init()) {
            ESP_LOGE(TAG, "I²C driver init failed after recovery");
            return false;
        }
    }

    if (!bmi270_configure()) {
        ESP_LOGE(TAG, "BMI270 configuration failed");
        return false;
    }

    return true;
}

void imu_task(void* arg)
{
    // Task period derived from configured ODR.
    // Run slightly faster than ODR to avoid missing samples.
    const uint32_t period_ms = (g_cfg.imu_odr_hz >= 400) ? 2 : 4;
    const TickType_t period = pdMS_TO_TICKS(period_ms);
    int consecutive_errors = 0;
    static constexpr int MAX_ERRORS_BEFORE_RECOVERY = 10;

    ESP_LOGI(TAG, "imu_task started (period=%lu ms)", (unsigned long)period_ms);

    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, period);

        // BMI270 data registers: accel at 0x0C (6 bytes), gyro at 0x12 (6 bytes).
        // They are contiguous (0x0C–0x17 = 12 bytes), so read in one burst.
        uint8_t raw[12];
        esp_err_t err = reg_read(REG_ACC_DATA_X_LSB, raw, 12);

        if (err != ESP_OK) {
            consecutive_errors++;
            if (consecutive_errors >= MAX_ERRORS_BEFORE_RECOVERY) {
                ESP_LOGW(TAG, "I²C errors (%d consecutive), attempting recovery",
                         consecutive_errors);
                g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::IMU_FAIL),
                                       std::memory_order_relaxed);
                i2c_bus_recover();
                if (i2c_driver_init() && bmi270_configure()) {
                    ESP_LOGI(TAG, "I²C recovery + reinit succeeded");
                    consecutive_errors = 0;
                } else {
                    ESP_LOGE(TAG, "I²C recovery failed, will retry next cycle");
                }
            }
            continue;
        }

        // Successful read — clear error count and IMU_FAIL fault
        if (consecutive_errors > 0) {
            consecutive_errors = 0;
            g_fault_flags.fetch_and(~static_cast<uint16_t>(Fault::IMU_FAIL),
                                    std::memory_order_relaxed);
        }

        // Parse raw data (little-endian 16-bit two's complement)
        // Accel: raw[0..5] → ax, ay, az
        // Gyro:  raw[6..11] → gx, gy, gz
        int16_t ax = static_cast<int16_t>(raw[0]  | (raw[1]  << 8));
        int16_t ay = static_cast<int16_t>(raw[2]  | (raw[3]  << 8));
        int16_t az = static_cast<int16_t>(raw[4]  | (raw[5]  << 8));
        int16_t gz = static_cast<int16_t>(raw[10] | (raw[11] << 8));

        // Convert and publish
        ImuSample* slot = g_imu.write_slot();
        slot->gyro_z_rad_s = static_cast<float>(gz) * s_gyro_sens_rad;
        slot->accel_x_g    = static_cast<float>(ax) * s_accel_sens_g;
        slot->accel_y_g    = static_cast<float>(ay) * s_accel_sens_g;
        slot->accel_z_g    = static_cast<float>(az) * s_accel_sens_g;
        slot->timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
        g_imu.publish();
    }
}
