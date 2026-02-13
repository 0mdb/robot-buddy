#include "imu.h"
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

// ---- LSM6DSV16X register map (subset) ----
static constexpr uint8_t LSM6_ADDR        = 0x6A;  // SDO/SA0 to GND
static constexpr uint8_t REG_WHO_AM_I     = 0x0F;
static constexpr uint8_t WHO_AM_I_VALUE   = 0x70;

static constexpr uint8_t REG_CTRL1        = 0x10;  // accel ODR + FS
static constexpr uint8_t REG_CTRL2        = 0x11;  // gyro ODR + FS
static constexpr uint8_t REG_CTRL3        = 0x12;  // BDU, IF_INC, SW_RESET
static constexpr uint8_t REG_STATUS       = 0x1E;

static constexpr uint8_t REG_OUTX_L_G     = 0x22;  // gyro data starts here (6 bytes)
static constexpr uint8_t REG_OUTX_L_A     = 0x28;  // accel data starts here (6 bytes)

// CTRL1: accel ODR + FS
// ODR bits [7:4], FS bits [3:2]
// ODR=0110 → 240 Hz, FS=00 → ±2g
static constexpr uint8_t CTRL1_VAL = 0x60;  // 240 Hz, ±2g

// CTRL2: gyro ODR + FS
// ODR bits [7:4], FS bits [3:0]
// ODR=0110 → 240 Hz, FS=0010 → ±500 dps
static constexpr uint8_t CTRL2_VAL = 0x62;  // 240 Hz, ±500 dps

// CTRL3: BDU=1 (block data update), IF_INC=1 (auto-increment address)
static constexpr uint8_t CTRL3_VAL = 0x44;

// Sensitivity constants
static constexpr float GYRO_SENSITIVITY_DPS  = 17.50f / 1000.0f;   // ±500 dps: 17.50 mdps/LSB → dps/LSB
static constexpr float GYRO_SENSITIVITY_RAD  = GYRO_SENSITIVITY_DPS * (M_PI / 180.0f);
static constexpr float ACCEL_SENSITIVITY_G   = 0.061f / 1000.0f;    // ±2g: 0.061 mg/LSB → g/LSB

// ---- I²C driver state ----
static i2c_master_bus_handle_t s_bus = nullptr;
static i2c_master_dev_handle_t s_dev = nullptr;

// ---- I²C bus recovery ----
// If SDA is stuck low (slave holding it), bit-bang SCL to clock out the
// stuck slave, then issue a STOP condition, then re-init the driver.

static constexpr int    RECOVERY_CLK_PULSES = 9;
static constexpr int    RECOVERY_HALF_PERIOD_US = 5;  // ~100 kHz

static void i2c_bus_recover()
{
    ESP_LOGW(TAG, "attempting I²C bus recovery...");

    // Tear down driver so we can bit-bang the pins
    if (s_dev) {
        i2c_master_bus_rm_device(s_dev);
        s_dev = nullptr;
    }
    if (s_bus) {
        i2c_del_master_bus(s_bus);
        s_bus = nullptr;
    }

    // Configure SCL as open-drain output, SDA as open-drain input
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

    // Release SDA (high)
    gpio_set_level(PIN_IMU_SDA, 1);

    // Clock SCL 9 times to free a stuck slave
    for (int i = 0; i < RECOVERY_CLK_PULSES; i++) {
        gpio_set_level(PIN_IMU_SCL, 0);
        ets_delay_us(RECOVERY_HALF_PERIOD_US);
        gpio_set_level(PIN_IMU_SCL, 1);
        ets_delay_us(RECOVERY_HALF_PERIOD_US);

        // Check if SDA is released
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

    // Reset GPIO config — i2c_new_master_bus will reconfigure them
    gpio_reset_pin(PIN_IMU_SCL);
    gpio_reset_pin(PIN_IMU_SDA);

    ESP_LOGI(TAG, "bus recovery complete, will re-init driver");
}

// ---- I²C init / reinit ----

static bool i2c_driver_init()
{
    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.i2c_port = I2C_NUM_1;  // dedicated bus for IMU
    bus_cfg.sda_io_num = PIN_IMU_SDA;
    bus_cfg.scl_io_num = PIN_IMU_SCL;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;  // use external pull-ups in production

    esp_err_t err = i2c_new_master_bus(&bus_cfg, &s_bus);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c_new_master_bus failed: %s", esp_err_to_name(err));
        return false;
    }

    i2c_device_config_t dev_cfg = {};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = LSM6_ADDR;
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

// ---- IMU configuration ----

static bool lsm6_configure()
{
    // Check WHO_AM_I
    uint8_t who = 0;
    if (reg_read(REG_WHO_AM_I, &who, 1) != ESP_OK || who != WHO_AM_I_VALUE) {
        ESP_LOGE(TAG, "WHO_AM_I failed: got 0x%02X, expected 0x%02X", who, WHO_AM_I_VALUE);
        return false;
    }
    ESP_LOGI(TAG, "LSM6DSV16X detected (WHO_AM_I=0x%02X)", who);

    // Software reset
    esp_err_t err = reg_write(REG_CTRL3, 0x01);  // SW_RESET bit
    if (err != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(20));  // wait for reset

    // Configure: BDU + IF_INC
    err = reg_write(REG_CTRL3, CTRL3_VAL);
    if (err != ESP_OK) return false;

    // Accel: 240 Hz, ±2g
    err = reg_write(REG_CTRL1, CTRL1_VAL);
    if (err != ESP_OK) return false;

    // Gyro: 240 Hz, ±500 dps
    err = reg_write(REG_CTRL2, CTRL2_VAL);
    if (err != ESP_OK) return false;

    ESP_LOGI(TAG, "LSM6DSV16X configured: gyro 240Hz ±500dps, accel 240Hz ±2g");
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

    if (!lsm6_configure()) {
        ESP_LOGE(TAG, "LSM6DSV16X configuration failed");
        return false;
    }

    return true;
}

void imu_task(void* arg)
{
    // Task runs at ~240 Hz to match IMU ODR
    const TickType_t period = pdMS_TO_TICKS(4);  // ~250 Hz
    int consecutive_errors = 0;
    static constexpr int MAX_ERRORS_BEFORE_RECOVERY = 10;

    ESP_LOGI(TAG, "imu_task started");

    TickType_t last_wake = xTaskGetTickCount();

    while (true) {
        vTaskDelayUntil(&last_wake, period);

        // Read gyro (6 bytes) + accel (6 bytes) in one burst
        // Registers are contiguous: gyro at 0x22, accel at 0x28
        // But there's a gap (0x28 - 0x28 = 0), so read separately.
        // Actually gyro is 0x22-0x27 (6 bytes), then status/temp, then accel 0x28-0x2D.
        // Read them as two separate reads for clarity.

        uint8_t gyro_raw[6];
        uint8_t accel_raw[6];

        esp_err_t err1 = reg_read(REG_OUTX_L_G, gyro_raw, 6);
        esp_err_t err2 = reg_read(REG_OUTX_L_A, accel_raw, 6);

        if (err1 != ESP_OK || err2 != ESP_OK) {
            consecutive_errors++;
            if (consecutive_errors >= MAX_ERRORS_BEFORE_RECOVERY) {
                ESP_LOGW(TAG, "I²C errors (%d consecutive), attempting recovery",
                         consecutive_errors);
                g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::IMU_FAIL),
                                       std::memory_order_relaxed);
                i2c_bus_recover();
                if (i2c_driver_init() && lsm6_configure()) {
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
            // Clear IMU_FAIL if it was set
            g_fault_flags.fetch_and(~static_cast<uint16_t>(Fault::IMU_FAIL),
                                    std::memory_order_relaxed);
        }

        // Parse raw data (little-endian 16-bit signed)
        // Only gz is needed for yaw damping; gx/gy unused in v1.
        int16_t gz = static_cast<int16_t>(gyro_raw[4] | (gyro_raw[5] << 8));

        int16_t ax = static_cast<int16_t>(accel_raw[0] | (accel_raw[1] << 8));
        int16_t ay = static_cast<int16_t>(accel_raw[2] | (accel_raw[3] << 8));
        int16_t az = static_cast<int16_t>(accel_raw[4] | (accel_raw[5] << 8));

        // Convert and publish
        ImuSample* slot = g_imu.write_slot();
        slot->gyro_z_rad_s = static_cast<float>(gz) * GYRO_SENSITIVITY_RAD;
        slot->accel_x_g    = static_cast<float>(ax) * ACCEL_SENSITIVITY_G;
        slot->accel_y_g    = static_cast<float>(ay) * ACCEL_SENSITIVITY_G;
        slot->accel_z_g    = static_cast<float>(az) * ACCEL_SENSITIVITY_G;
        slot->timestamp_us = static_cast<uint32_t>(esp_timer_get_time());
        g_imu.publish();
    }
}
