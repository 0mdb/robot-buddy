#include "config.h"

#include "esp_log.h"

#include <cstring>

static const char* TAG = "config";

// Mutable runtime config — initialized from CFG_DEFAULTS in app_main.
ReflexConfig g_cfg = CFG_DEFAULTS;

// Helper: read a little-endian float from raw bytes.
static float read_float(const uint8_t* b)
{
    float v;
    memcpy(&v, b, sizeof(v));
    return v;
}

// Helper: read a little-endian u32 from raw bytes.
static uint32_t read_u32(const uint8_t* b)
{
    uint32_t v;
    memcpy(&v, b, sizeof(v));
    return v;
}

// Helper: read a little-endian i32 from raw bytes.
static int32_t read_i32(const uint8_t* b)
{
    int32_t v;
    memcpy(&v, b, sizeof(v));
    return v;
}

bool config_apply(uint8_t param_id, const uint8_t* value_bytes)
{
    switch (static_cast<ConfigParam>(param_id)) {

    // FF + PI gains
    case ConfigParam::KV:
        g_cfg.kV = read_float(value_bytes);
        ESP_LOGI(TAG, "kV = %.3f", g_cfg.kV);
        return true;
    case ConfigParam::KS:
        g_cfg.kS = read_float(value_bytes);
        ESP_LOGI(TAG, "kS = %.3f", g_cfg.kS);
        return true;
    case ConfigParam::KP:
        g_cfg.Kp = read_float(value_bytes);
        ESP_LOGI(TAG, "Kp = %.3f", g_cfg.Kp);
        return true;
    case ConfigParam::KI:
        g_cfg.Ki = read_float(value_bytes);
        ESP_LOGI(TAG, "Ki = %.3f", g_cfg.Ki);
        return true;
    case ConfigParam::MIN_PWM:
        g_cfg.min_pwm = static_cast<uint16_t>(read_u32(value_bytes));
        ESP_LOGI(TAG, "min_pwm = %u", g_cfg.min_pwm);
        return true;
    case ConfigParam::MAX_PWM:
        g_cfg.max_pwm = static_cast<uint16_t>(read_u32(value_bytes));
        ESP_LOGI(TAG, "max_pwm = %u", g_cfg.max_pwm);
        return true;

    // Rate limits
    case ConfigParam::MAX_V_MM_S:
        g_cfg.max_v_mm_s = static_cast<int16_t>(read_i32(value_bytes));
        ESP_LOGI(TAG, "max_v_mm_s = %d", g_cfg.max_v_mm_s);
        return true;
    case ConfigParam::MAX_A_MM_S2:
        g_cfg.max_a_mm_s2 = static_cast<int16_t>(read_i32(value_bytes));
        ESP_LOGI(TAG, "max_a_mm_s2 = %d", g_cfg.max_a_mm_s2);
        return true;
    case ConfigParam::MAX_W_MRAD_S:
        g_cfg.max_w_mrad_s = static_cast<int16_t>(read_i32(value_bytes));
        ESP_LOGI(TAG, "max_w_mrad_s = %d", g_cfg.max_w_mrad_s);
        return true;
    case ConfigParam::MAX_AW_MRAD_S2:
        g_cfg.max_aw_mrad_s2 = static_cast<int16_t>(read_i32(value_bytes));
        ESP_LOGI(TAG, "max_aw_mrad_s2 = %d", g_cfg.max_aw_mrad_s2);
        return true;

    // Yaw damping
    case ConfigParam::K_YAW:
        g_cfg.K_yaw = read_float(value_bytes);
        ESP_LOGI(TAG, "K_yaw = %.3f", g_cfg.K_yaw);
        return true;

    // Safety
    case ConfigParam::CMD_TIMEOUT_MS:
        g_cfg.cmd_timeout_ms = read_u32(value_bytes);
        ESP_LOGI(TAG, "cmd_timeout_ms = %lu", (unsigned long)g_cfg.cmd_timeout_ms);
        return true;
    case ConfigParam::SOFT_STOP_RAMP_MS:
        g_cfg.soft_stop_ramp_ms = read_u32(value_bytes);
        ESP_LOGI(TAG, "soft_stop_ramp_ms = %lu", (unsigned long)g_cfg.soft_stop_ramp_ms);
        return true;
    case ConfigParam::TILT_THRESH_DEG:
        g_cfg.tilt_thresh_deg = read_float(value_bytes);
        ESP_LOGI(TAG, "tilt_thresh_deg = %.1f", g_cfg.tilt_thresh_deg);
        return true;
    case ConfigParam::TILT_HOLD_MS:
        g_cfg.tilt_hold_ms = read_u32(value_bytes);
        ESP_LOGI(TAG, "tilt_hold_ms = %lu", (unsigned long)g_cfg.tilt_hold_ms);
        return true;
    case ConfigParam::STALL_THRESH_MS:
        g_cfg.stall_thresh_ms = read_u32(value_bytes);
        ESP_LOGI(TAG, "stall_thresh_ms = %lu", (unsigned long)g_cfg.stall_thresh_ms);
        return true;
    case ConfigParam::STALL_SPEED_THRESH:
        g_cfg.stall_speed_thresh = static_cast<int16_t>(read_i32(value_bytes));
        ESP_LOGI(TAG, "stall_speed_thresh = %d", g_cfg.stall_speed_thresh);
        return true;

    // Range sensor
    case ConfigParam::RANGE_STOP_MM:
        g_cfg.range_stop_mm = static_cast<uint16_t>(read_u32(value_bytes));
        ESP_LOGI(TAG, "range_stop_mm = %u", g_cfg.range_stop_mm);
        return true;
    case ConfigParam::RANGE_RELEASE_MM:
        g_cfg.range_release_mm = static_cast<uint16_t>(read_u32(value_bytes));
        ESP_LOGI(TAG, "range_release_mm = %u", g_cfg.range_release_mm);
        return true;

    default:
        ESP_LOGW(TAG, "unknown config param 0x%02X", param_id);
        return false;
    }
}
