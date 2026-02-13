#include "motor.h"
#include "pin_map.h"
#include "config.h"

#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char* TAG = "motor";

// LEDC channel mapping
static constexpr ledc_channel_t CH_LEFT  = LEDC_CHANNEL_0;
static constexpr ledc_channel_t CH_RIGHT = LEDC_CHANNEL_1;
static constexpr ledc_timer_t   PWM_TIMER = LEDC_TIMER_0;
static constexpr ledc_mode_t    PWM_MODE  = LEDC_LOW_SPEED_MODE;

// Direction pin pairs [side][0=fwd, 1=rev]
static constexpr gpio_num_t DIR_PINS[2][2] = {
    {PIN_AIN1, PIN_AIN2},  // LEFT
    {PIN_BIN1, PIN_BIN2},  // RIGHT
};

static constexpr gpio_num_t PWM_PINS[2] = {PIN_PWMA, PIN_PWMB};
static constexpr ledc_channel_t PWM_CHS[2] = {CH_LEFT, CH_RIGHT};

static void init_direction_gpios()
{
    const gpio_num_t pins[] = {PIN_AIN1, PIN_AIN2, PIN_BIN1, PIN_BIN2, PIN_STBY};
    for (auto pin : pins) {
        gpio_config_t cfg = {};
        cfg.pin_bit_mask = 1ULL << pin;
        cfg.mode = GPIO_MODE_OUTPUT;
        cfg.pull_up_en = GPIO_PULLUP_DISABLE;
        cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
        cfg.intr_type = GPIO_INTR_DISABLE;
        gpio_config(&cfg);
        gpio_set_level(pin, 0);
    }
    ESP_LOGI(TAG, "direction GPIOs + STBY initialized (all LOW)");
}

static void init_pwm()
{
    ledc_timer_config_t timer_cfg = {};
    timer_cfg.speed_mode = PWM_MODE;
    timer_cfg.timer_num = PWM_TIMER;
    timer_cfg.duty_resolution = static_cast<ledc_timer_bit_t>(PWM_RESOLUTION_BITS);
    timer_cfg.freq_hz = g_cfg.pwm_freq_hz;
    timer_cfg.clk_cfg = LEDC_AUTO_CLK;
    ESP_ERROR_CHECK(ledc_timer_config(&timer_cfg));

    for (int i = 0; i < 2; i++) {
        ledc_channel_config_t ch_cfg = {};
        ch_cfg.speed_mode = PWM_MODE;
        ch_cfg.channel = PWM_CHS[i];
        ch_cfg.timer_sel = PWM_TIMER;
        ch_cfg.gpio_num = PWM_PINS[i];
        ch_cfg.duty = 0;
        ch_cfg.hpoint = 0;
        ESP_ERROR_CHECK(ledc_channel_config(&ch_cfg));
    }
    ESP_LOGI(TAG, "LEDC PWM initialized @ %u Hz, %u-bit",
             g_cfg.pwm_freq_hz, PWM_RESOLUTION_BITS);
}

void motor_init()
{
    init_direction_gpios();
    init_pwm();
}

void motor_enable()
{
    gpio_set_level(PIN_STBY, 1);
    ESP_LOGI(TAG, "motors ENABLED (STBY HIGH)");
}

void motor_set_output(MotorSide side, uint16_t duty, bool forward)
{
    int s = static_cast<int>(side);
    if (duty > g_cfg.max_pwm) duty = g_cfg.max_pwm;

    // TB6612 truth table: IN1=H IN2=L → forward, IN1=L IN2=H → reverse
    gpio_set_level(DIR_PINS[s][0], forward ? 1 : 0);
    gpio_set_level(DIR_PINS[s][1], forward ? 0 : 1);
    ledc_set_duty(PWM_MODE, PWM_CHS[s], duty);
    ledc_update_duty(PWM_MODE, PWM_CHS[s]);
}

void motor_brake()
{
    for (int s = 0; s < 2; s++) {
        // Short-brake: IN1=H, IN2=H (TB6612 shorts motor leads)
        gpio_set_level(DIR_PINS[s][0], 1);
        gpio_set_level(DIR_PINS[s][1], 1);
        ledc_set_duty(PWM_MODE, PWM_CHS[s], 0);
        ledc_update_duty(PWM_MODE, PWM_CHS[s]);
    }
}

void motor_hard_kill()
{
    // PWM off + brake direction first, then STBY low
    motor_brake();
    gpio_set_level(PIN_STBY, 0);
    ESP_LOGW(TAG, "HARD KILL — STBY LOW");
}

bool motor_is_enabled()
{
    return gpio_get_level(PIN_STBY) == 1;
}
