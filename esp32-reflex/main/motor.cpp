#include "motor.h"
#include "config.h"
#include "expander.h"
#include "pin_map.h"
#include "shared_state.h"

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include <atomic>

static const char* TAG = "motor";

// LEDC channel mapping
static constexpr ledc_channel_t CH_LEFT = LEDC_CHANNEL_0;
static constexpr ledc_channel_t CH_RIGHT = LEDC_CHANNEL_1;
static constexpr ledc_timer_t   PWM_TIMER = LEDC_TIMER_0;
static constexpr ledc_mode_t    PWM_MODE = LEDC_LOW_SPEED_MODE;

static constexpr gpio_num_t     PWM_PINS[2] = {PIN_PWMA, PIN_PWMB};
static constexpr ledc_channel_t PWM_CHS[2] = {CH_LEFT, CH_RIGHT};

// Expander bits per side: [side][0 = IN1 (fwd), 1 = IN2 (rev)]
static constexpr uint8_t DIR_BITS[2][2] = {
    {EXP_BIT_AIN1, EXP_BIT_AIN2}, // LEFT
    {EXP_BIT_BIN1, EXP_BIT_BIN2}, // RIGHT
};

// Direction latch as last confirmed by readback. Guarded by s_lock (control_task and
// safety_task both call in).
static SemaphoreHandle_t s_lock = nullptr;
static uint8_t           s_dir_bits = 0;
static std::atomic<bool> s_enabled{false};

static void set_duty(int s, uint16_t duty)
{
    ledc_set_duty(PWM_MODE, PWM_CHS[s], duty);
    ledc_update_duty(PWM_MODE, PWM_CHS[s]);
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
    ESP_LOGI(TAG, "LEDC PWM initialized @ %u Hz, %u-bit", g_cfg.pwm_freq_hz, PWM_RESOLUTION_BITS);
}

static void init_estop_inputs()
{
    // Both lines have external pull-downs (R4, R18): no internal pulls.
    gpio_config_t cfg = {};
    cfg.pin_bit_mask = (1ULL << PIN_ESTOP_N) | (1ULL << PIN_ESTOP_LOOP);
    cfg.mode = GPIO_MODE_INPUT;
    cfg.pull_up_en = GPIO_PULLUP_DISABLE;
    cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    cfg.intr_type = GPIO_INTR_DISABLE;
    gpio_config(&cfg);
}

void motor_init()
{
    s_lock = xSemaphoreCreateMutex();
    init_pwm(); // PWM 0 first: whatever the direction lines do, the bridge is braked
    init_estop_inputs();
    if (!expander_init()) {
        // Lines stay low on their pull-downs; motors cannot be driven. Report it.
        ESP_LOGE(TAG, "direction expander missing — motors unavailable");
        g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::MOTOR_DRV), std::memory_order_relaxed);
    }
    s_dir_bits = 0;
}

void motor_enable()
{
    s_enabled.store(true, std::memory_order_relaxed);
    ESP_LOGI(TAG, "motors ENABLED (software)");
}

void motor_set_output(MotorSide side, uint16_t duty, bool forward)
{
    if (!s_enabled.load(std::memory_order_relaxed)) return;
    const int s = static_cast<int>(side);
    if (duty > g_cfg.max_pwm) duty = g_cfg.max_pwm;

    // TB6612: IN1=H IN2=L forward, IN1=L IN2=H reverse.
    const uint8_t side_mask = DIR_BITS[s][0] | DIR_BITS[s][1];
    const uint8_t want_side = forward ? DIR_BITS[s][0] : DIR_BITS[s][1];

    xSemaphoreTake(s_lock, portMAX_DELAY);
    const bool change = (s_dir_bits & side_mask) != want_side;
    if (change && duty == 0) {
        // Nothing to drive: leave the latch alone. Saves an I²C write every time the
        // controller output dithers through zero.
        set_duty(s, 0);
        xSemaphoreGive(s_lock);
        return;
    }
    if (change) {
        // PWM -> 0 BEFORE touching IN1/IN2: with PWM low the bridge is in short-brake,
        // so the expander write can't walk it through a driven invalid state.
        set_duty(s, 0);
        const uint8_t next = static_cast<uint8_t>((s_dir_bits & ~side_mask) | want_side);
        if (!expander_write_dir(next)) {
            xSemaphoreGive(s_lock);
            g_fault_flags.fetch_or(static_cast<uint16_t>(Fault::MOTOR_DRV), std::memory_order_relaxed);
            ESP_LOGE(TAG, "direction write/readback failed (side %d) — holding PWM 0", s);
            return;
        }
        s_dir_bits = next;
    }
    set_duty(s, duty);
    xSemaphoreGive(s_lock);
}

void motor_brake()
{
    // PWM low = short-brake whatever IN1/IN2 are (other than both low, which coasts).
    // LEDC only, so a brake never queues behind an I²C transaction.
    for (int s = 0; s < 2; s++)
        set_duty(s, 0);
}

void motor_hard_kill()
{
    s_enabled.store(false, std::memory_order_relaxed);
    motor_brake();
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(20)) == pdTRUE) {
        if (expander_write_dir(0)) s_dir_bits = 0;
        xSemaphoreGive(s_lock);
    }
    ESP_LOGW(TAG, "HARD KILL — PWM 0, direction lines low, disabled");
}

bool motor_estop_ok()
{
    return gpio_get_level(PIN_ESTOP_N) == 1;
}

bool motor_estop_cable_present()
{
    return gpio_get_level(PIN_ESTOP_LOOP) == 1;
}

bool motor_is_enabled()
{
    return s_enabled.load(std::memory_order_relaxed) && motor_estop_ok();
}
