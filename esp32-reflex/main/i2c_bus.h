#pragma once
// The reflex board's single I²C bus (SDA GPIO7, SCL GPIO8): BMI270 IMU + TCA9554A
// expander. One owner so neither device can tear the bus down under the other.
// The ESP-IDF i2c_master driver serialises transactions across tasks on one bus.

#include "driver/i2c_master.h"

// Create the bus (idempotent). On failure, bit-bangs a recovery and retries once.
bool i2c_bus_init();

// The bus handle, or nullptr if i2c_bus_init() never succeeded.
i2c_master_bus_handle_t i2c_bus_handle();

// Clear a stuck bus (clock out a slave holding SDA) WITHOUT deleting it: devices
// added by other modules stay valid. Returns true on success.
bool i2c_bus_recover();
