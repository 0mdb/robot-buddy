---
name: flash
description: Build and flash ESP32 firmware to a target MCU. Only invoke manually.
---

Build and flash ESP32 firmware. Parse `$ARGUMENTS` to determine target.

## Argument parsing

- `reflex` → esp32-reflex (motion control MCU)
- `face` → esp32-face-v2 (face display MCU)
- No argument → ask which target

## Environment

ESP-IDF must be sourced first. Check if `$IDF_PATH` is set, and if not:
```bash
source ~/esp/esp-idf/export.sh
```

## Targets

### esp32-reflex
- **Directory:** `/home/ben/robot-buddy/esp32-reflex`
- **Target chip:** ESP32-S3
- **Console:** USB CDC (native USB)
- **Serial port:** `/dev/robot_reflex` or `/dev/ttyACM*`
- **Key config:** `sdkconfig.defaults` — dual-core, watchdog 3s

### esp32-face-v2
- **Directory:** `/home/ben/robot-buddy/esp32-face-v2`
- **Target chip:** ESP32-S3
- **Console:** TinyUSB CDC (composite device: CDC + UAC)
- **Serial port:** `/dev/robot_face` or `/dev/ttyACM*`
- **Key config:** `sdkconfig.defaults` — dual-core, watchdog 5s, 8MB PSRAM

## Steps

1. Confirm the target with the user if ambiguous.
2. Source ESP-IDF environment if needed.
3. Build:
```bash
cd /home/ben/robot-buddy/esp32-<target> && idf.py build
```
4. If build succeeds, ask user to confirm flash (device must be connected).
5. Flash:
```bash
cd /home/ben/robot-buddy/esp32-<target> && idf.py flash
```
6. Optionally start monitor:
```bash
cd /home/ben/robot-buddy/esp32-<target> && idf.py monitor
```

## Rules

1. ALWAYS confirm before flashing — this writes to hardware.
2. If build fails, read the error and suggest fixes before retrying.
3. Never flash without a successful build first.
4. If the serial port can't be found, suggest checking USB connection and `ls /dev/ttyACM*`.

## Human Checkpoints (esp32-face-v2)

The face MCU may require manual intervention:

1. **Download Mode**: Ask operator to put device into download mode before flashing. Wait for explicit confirmation.
2. **Post-Flash Reboot**: Ask operator to reset device after flash. Wait for confirmation before validation.

## Port Re-Enumeration

Device path can change after reset/reenumeration. Always recheck:
```bash
ls -l /dev/serial/by-id 2>/dev/null || true
ls -l /dev/ttyACM* 2>/dev/null || true
```

## Validation

Prefer supervisor-facing telemetry over `idf.py monitor` for face MCU — the binary protocol makes monitor output unreadable. Validate via:
1. Start supervisor with face MCU connected
2. Confirm `rx_face_status_packets` and `rx_heartbeat_packets` increasing
3. Send `SET_STATE`, `GESTURE`, `SET_TALKING` and verify telemetry reflects changes

## Common Issues

- `by-id` path changes after reboot — re-enumerate every flash cycle
- Monitor command may fail without TTY — rerun with PTY
- Serial `Errno 13` — check device permissions
- `idf.py monitor` output is binary gibberish for face MCU — this is normal
