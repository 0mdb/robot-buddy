# Face MCU: USB-CDC → UART0 transport (evaluation)

**Status:** evaluated, not implemented. Decision pending.

## Why

The Face MCU is a Freenove FNK0104 (ESP32-S3 + 2.8" display). Its USB-C port is
on the *side* of the module, which makes for awkward cable routing. The board
breaks out a **UART connector (P2) on the back** carrying 5 V + GND + TXD0 +
RXD0, so a single 4-wire JST off the back could both power the board and carry
the link — replacing the side USB cable. This requires moving the face protocol
transport from USB-CDC to hardware UART0.

## FNK0104 back-connector pinout (from Freenove schematic)

`Schematic/2.8inch_ESP32-S3_Display_Schematic.pdf` in
`github.com/Freenove/Freenove_ESP32_S3_Display`.

| Connector | Silkscreen | Pin 1 | Pin 2 | Pin 3 | Pin 4 |
|-----------|-----------|-------|-------|-------|-------|
| **UART**  | P2 | +5V   | GND   | TXD0  | RXD0  |
| **Expanded IO** | P3 | IO2 | IO3 | IO14 | IO21 |
| **IIC** (I2C) | P4 | 3V3 | GND | SCL | SDA |
| BAT | — | MX1.25 lithium + / − | | | |
| Speaker | — | PH1.25 | | | |

- P2 TXD0/RXD0 = **UART0** (GPIO43/44), 3.3 V logic, 100 Ω series Rs (R38/R39) on board.
- P2 pin 1 is **+5 V (VBUS net)** → powers the board through its onboard 3.3 V LDO, same path as USB.
- P3 pins are the "Expanded IO" GPIO breakout (spare pins). Silkscreen reads `IO2/IO3/IO14/IO21`.

## Firmware scope (`esp32-face/`)

Transport is cleanly abstracted behind two functions in
`main/usb_composite.cpp`:

- `usb_cdc_read(buf, max, timeout)` → `tinyusb_cdcacm_read()`
- `usb_cdc_write(data, len)` → `tinyusb_cdcacm_write_queue/flush()`

Everything above them is transport-agnostic and unchanged: COBS + CRC16 framing
(`main/protocol.cpp`), the 0x00-delimited frame sync (`main/usb_rx.cpp`),
telemetry (`main/telemetry.cpp`).

Plan:

1. **Add `main/uart_transport.cpp`** implementing the same two signatures over
   `driver/uart.h`: `uart_driver_install()` on `UART_NUM_0`, pins 43/44, RX ring
   buffer ~2 KB; `uart_read_bytes()` with the existing 50 ms timeout;
   `uart_write_bytes()` (buffers internally → the retry/flush loop simplifies).
2. **Swap the init call** in `main/app_main.cpp:52`
   (`usb_composite_init()` → `uart_transport_init()`) + include. RX task and
   telemetry call sites are unchanged.
3. **Build switch** — a Kconfig / compile flag (`FACE_TRANSPORT_UART` vs `_USB`)
   so USB-CDC stays available for bench dev; select UART for production.
4. **Trim CDC-only diagnostics** — heartbeat carries `usb_dtr/usb_rts/
   usb_line_state` (`main/telemetry.cpp:145`). Drop or repurpose. Cosmetic.

Console is already `CONFIG_ESP_CONSOLE_NONE=y`, so app logs won't corrupt the
link. **Caveat:** the ROM + 2nd-stage bootloader still print on UART0 at 115200
on every reset — harmless noise (fails CRC, dropped by COBS resync), but the
Pi parser must tolerate junk before the first valid frame (it already does).

## Pi side — config only, no code

Supervisor (`supervisor/io/serial_transport.py`) is port-agnostic pyserial.
Both MCUs are device paths (`/dev/robot_reflex`, `/dev/robot_face`) at 115200,
overridable via `--face-port` / YAML (`supervisor/config.py:13-16`).

| | A. Pi GPIO UART (recommended) | B. USB-UART dongle |
|---|---|---|
| Wiring | 4 wires P2 → Pi header (5V, GND, TX↔RX cross) | P2 TX/RX → adapter → Pi USB; 5V separate |
| Pi `/dev` | `/dev/ttyAMA*` (Pi 5 has spare PL011s via `dtoverlay`) | `/dev/ttyUSB0` |
| Pi setup | enable a UART overlay, free it from console | none |
| Off-the-back | fully clean | relocates cable but keeps a dongle |
| Code change | none — point `--face-port` at the device | none |

Both ESP32 and Pi GPIO UART are 3.3 V → **direct connection, no level shifter**.
Consider bumping baud to **460800–921600** (config-only, both ends) for latency
margin; peak protocol is ~2 KB/s so even 115200 is fine.

## Risks / gotchas

- **No flashing over P2** — no DTR/RTS → no auto-bootloader reset. Keep flashing
  via USB-C (still works; USB isn't disabled, just unused for the protocol).
- **Don't dual-power** — P2 +5 V *and* USB-C plugged simultaneously back-feeds
  VBUS unless the board ORs them. Rule until verified: bench = USB-C,
  production = P2, not both.
- **Pi UART contention** — confirm the chosen `/dev/ttyAMA*` isn't the serial
  console; reflex stays on USB so no conflict there.
- **No hardware flow control** on P2 (no CTS/RTS), but throughput headroom makes
  it a non-issue.

## Effort

- Firmware: ~½–1 day (new transport file + flag + bench test).
- Pi: ~1 hr (config.txt overlay, udev symlink, point `--face-port`).
- Hardware: 4-pin JST-to-Pi-header harness + rear mount.

Reversible: USB-CDC stays behind the build flag.

## Open decisions before building

1. Pi GPIO UART (A) vs USB-UART dongle (B).
2. Confirm the P2 +5 V path doesn't back-feed VBUS when USB-C is also connected
   (check schematic for ORing/diode).
