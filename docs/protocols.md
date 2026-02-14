# Protocols

## Transport
USB serial between Raspberry Pi 5 and each ESP32.

## Face MCU protocol (v0)
Binary fixed-size packets.

### SET_STATE (cmd=0x01)
Fields:
- emotion_id (u8): 0 happy, 1 curious, 2 scared, 3 sleepy, 4 angry, 5 sad
- intensity (u8): 0..255
- gaze_x (i8): -4..+4
- gaze_y (i8): -4..+4
- brightness_cap (u8): 0..255

### GESTURE (cmd=0x02)
- gesture_id (u8): blink, winkL, winkR, surprise, etc.
- duration_ms (u16)

## Reflex MCU protocol (v0)
### SET_TWIST (cmd=0x10)
- v_mm_s (i16)
- w_mrad_s (i16)

### STOP (cmd=0x11)
- reason (u8)

### STATE (cmd=0x12)
- wheel_speed_l (i16)
- wheel_speed_r (i16)
- battery_mv (u16)
- fault_flags (u16)
- (future) odom x/y/theta
