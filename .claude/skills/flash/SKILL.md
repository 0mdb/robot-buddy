---
name: flash
description: Build and flash ESP32 firmware to a target MCU. Only invoke manually.
argument-hint: "[reflex|face]"
disable-model-invocation: true
allowed-tools: Bash(idf.py:*), Bash(source:*), Bash(ls:*), Read, Grep, Glob
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
