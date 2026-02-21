#pragma once
// Shared state between tasks. All structures follow single-writer rules.

#include <atomic>
#include <cstdint>

// ---- Fault flags (bitfield) ----
// Written by safety_task (PRO core), read by telemetry_task (APP core).

enum class Fault : uint16_t {
    NONE = 0,
    CMD_TIMEOUT = 1 << 0,
    ESTOP = 1 << 1,
    TILT = 1 << 2,
    STALL = 1 << 3,
    IMU_FAIL = 1 << 4,
    BROWNOUT = 1 << 5,
    OBSTACLE = 1 << 6,
};

inline uint16_t operator|(Fault a, Fault b)
{
    return static_cast<uint16_t>(a) | static_cast<uint16_t>(b);
}
inline uint16_t operator|(uint16_t a, Fault b)
{
    return a | static_cast<uint16_t>(b);
}
inline uint16_t operator&(uint16_t a, Fault b)
{
    return a & static_cast<uint16_t>(b);
}

// ---- IMU sample (double-buffered) ----
// Writer: imu_task (PRO core). Reader: control_task (PRO core).

struct ImuSample {
    float    gyro_z_rad_s = 0.0f; // yaw rate
    float    accel_x_g = 0.0f;    // forward/back (for tilt detection)
    float    accel_y_g = 0.0f;
    float    accel_z_g = 0.0f; // should be ~1g when upright
    uint32_t timestamp_us = 0;
};

struct ImuBuffer {
    ImuSample               buf[2]{};
    std::atomic<ImuSample*> current{&buf[0]}; // reader uses this
    uint8_t                 write_idx = 0;    // writer-private

    // Writer: fill buf[write_idx], then swap.
    ImuSample* write_slot()
    {
        return &buf[write_idx];
    }
    void publish()
    {
        current.store(&buf[write_idx], std::memory_order_release);
        write_idx ^= 1;
    }

    // Reader: get latest published sample (treat as immutable).
    const ImuSample* read() const
    {
        return current.load(std::memory_order_acquire);
    }
};

// ---- Command buffer (ping-pong, double-buffered) ----
// Writer: usb_rx_task (APP core). Reader: control_task (PRO core).

struct Command {
    int16_t v_mm_s = 0;
    int16_t w_mrad_s = 0;
};

struct CommandBuffer {
    Command               buf[2]{};
    std::atomic<Command*> current{&buf[0]}; // PRO reads via this pointer
    std::atomic<uint32_t> last_cmd_us{0};   // timestamp of last valid command
    uint8_t               write_idx = 0;    // APP-private

    // Writer (APP core): fill buf[write_idx], swap pointer, update timestamp.
    Command* write_slot()
    {
        return &buf[write_idx];
    }
    void publish(uint32_t now_us)
    {
        current.store(&buf[write_idx], std::memory_order_release);
        last_cmd_us.store(now_us, std::memory_order_release);
        write_idx ^= 1;
    }

    // Reader (PRO core): get latest command (treat as immutable).
    const Command* read() const
    {
        return current.load(std::memory_order_acquire);
    }
};

// ---- Telemetry state ----
// Writer: control_task (PRO core). Reader: telemetry_task (APP core).
// Uses a sequence counter (seqlock pattern) for tear detection.

struct TelemetryState {
    int16_t  speed_l_mm_s = 0;
    int16_t  speed_r_mm_s = 0;
    int16_t  gyro_z_mrad_s = 0;
    uint16_t battery_mv = 0;
    uint16_t fault_flags = 0;
    uint32_t timestamp_us = 0;

    // Seqlock: writer increments to odd before write, even after.
    // Reader spins if odd or if seq changed during read.
    std::atomic<uint32_t> seq{0};
};

// ---- Range sensor sample (double-buffered) ----
// Writer: range_task (APP core). Reader: safety_task (PRO core), telemetry_task (APP core).

enum class RangeStatus : uint8_t {
    OK = 0,
    TIMEOUT = 1,      // no echo received within timeout
    OUT_OF_RANGE = 2, // echo received but beyond max range
    NOT_READY = 3,    // no measurement taken yet
};

struct RangeSample {
    uint16_t    range_mm = 0;
    RangeStatus status = RangeStatus::NOT_READY;
    uint32_t    timestamp_us = 0;
};

struct RangeBuffer {
    RangeSample               buf[2]{};
    std::atomic<RangeSample*> current{&buf[0]};
    uint8_t                   write_idx = 0; // writer-private

    RangeSample* write_slot()
    {
        return &buf[write_idx];
    }
    void publish()
    {
        current.store(&buf[write_idx], std::memory_order_release);
        write_idx ^= 1;
    }

    const RangeSample* read() const
    {
        return current.load(std::memory_order_acquire);
    }
};

// ---- Global shared state ----
// Defined in app_main.cpp, extern'd here.

extern ImuBuffer             g_imu;
extern CommandBuffer         g_cmd;
extern RangeBuffer           g_range;
extern TelemetryState        g_telemetry;
extern std::atomic<uint16_t> g_fault_flags;
