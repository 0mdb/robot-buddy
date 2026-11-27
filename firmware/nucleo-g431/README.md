# nucleo-g431: phase 0 bench firmware

Rust + Embassy bring-up for the shared STM32G431 core (`~/kicad-libs/docs/shared-mcu-core.md`),
on a NUCLEO-G431RB. Today: blink LD2 (PA5) and log over defmt/RTT. Next: the phase 0 gate,
DRV8876 CS → COMP → TIM1 break stall cutoff.

```sh
cargo run --release      # build, flash over the on-board ST-LINK V3, stream defmt logs
```

Needs: `rustup target add thumbv7em-none-eabihf`, `cargo install probe-rs-tools --locked`.
probe-rs cannot auto-detect the chip; the runner passes `--chip STM32G431RBTx`.

## WSL2 (Windows dev box)

The ST-LINK enumerates on Windows (0483:374e, VCP on COM11). Pass it through with usbipd-win:

```powershell
usbipd bind --busid <BUSID>                 # once, admin PowerShell
```
```sh
"/mnt/c/Program Files/usbipd-win/usbipd.exe" attach --wsl --busid <BUSID>   # every replug
```

This distro runs without systemd, so nothing applies udev rules. After each WSL start
(rules file: ST-LINK V2/V3 → `plugdev`, mode 0660):

```sh
sudo sh -c 'cp 69-stlink.rules /etc/udev/rules.d/ && modprobe cdc_acm && /lib/systemd/systemd-udevd --daemon && udevadm trigger'
```

The VCP then shows up as `/dev/ttyACM0`. `systemd=true` in `/etc/wsl.conf` makes this permanent.

## Chip seen on the bench (2026-11-27)

DEV_ID 0x468 (G431/G441), 128 KB flash, REV_ID 0x2003. Revision letter: check ES0431
before relying on COMP behaviour (its offset erratum is rev Z/Y only).
