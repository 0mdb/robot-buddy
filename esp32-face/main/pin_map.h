#pragma once
// Freenove FNK0104 (ESP32-S3 2.8" Touch Display) pin assignments.

#include "driver/gpio.h"

// ---- TFT Display (ILI9341 via SPI2_HOST / HSPI) ----
constexpr gpio_num_t PIN_TFT_MOSI = GPIO_NUM_11;
constexpr gpio_num_t PIN_TFT_SCLK = GPIO_NUM_12;
constexpr gpio_num_t PIN_TFT_MISO = GPIO_NUM_13;
constexpr gpio_num_t PIN_TFT_CS = GPIO_NUM_10;
constexpr gpio_num_t PIN_TFT_DC = GPIO_NUM_46;
constexpr gpio_num_t PIN_TFT_BL = GPIO_NUM_45; // backlight (active HIGH)
// RST tied to board reset — no GPIO control

// ---- Touch (FT6336 capacitive, I2C) ----
constexpr gpio_num_t PIN_TOUCH_SDA = GPIO_NUM_16;
constexpr gpio_num_t PIN_TOUCH_SCL = GPIO_NUM_15;
constexpr gpio_num_t PIN_TOUCH_RST = GPIO_NUM_18;
constexpr gpio_num_t PIN_TOUCH_INT = GPIO_NUM_17;

// ---- Pi link on P2 (UART0; 100R series on board) ----
constexpr gpio_num_t PIN_LINK_TX = GPIO_NUM_43; // P2 pin 3 TXD0 -> Pi GPIO15 (pin 10)
constexpr gpio_num_t PIN_LINK_RX = GPIO_NUM_44; // P2 pin 4 RXD0 <- Pi GPIO14 (pin 8)

// ---- WS2812B RGB LED ----
constexpr gpio_num_t PIN_LED_DATA = GPIO_NUM_42;

// ---- SD Card (SDMMC 4-bit) ----
constexpr gpio_num_t PIN_SD_CLK = GPIO_NUM_38;
constexpr gpio_num_t PIN_SD_CMD = GPIO_NUM_40;
constexpr gpio_num_t PIN_SD_D0 = GPIO_NUM_39;
constexpr gpio_num_t PIN_SD_D1 = GPIO_NUM_41;
constexpr gpio_num_t PIN_SD_D2 = GPIO_NUM_48;
constexpr gpio_num_t PIN_SD_D3 = GPIO_NUM_47;

// ---- Button ----
constexpr gpio_num_t PIN_BUTTON = GPIO_NUM_0; // boot button

// ---- Battery ADC ----
constexpr gpio_num_t PIN_VBAT_ADC = GPIO_NUM_9; // voltage divider 2:1
