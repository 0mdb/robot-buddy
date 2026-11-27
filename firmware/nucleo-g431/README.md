# nucleo-g431: phase 0 bench firmware

Rust + Embassy bring-up for the shared STM32G431 core (`~/kicad-libs/docs/shared-mcu-core.md`),
on a NUCLEO-G431RB.

```sh
cargo run --release              # blink: LD2 (PA5) + defmt/RTT, proves build -> flash -> log
cargo run --release --bin selftest  # COMP1 -> TIM1 break with no driver: jumper A2 -> A1
cargo run --release --bin stall  # phase 0 gate: DRV8876 CS -> COMP1 -> TIM1 break stall cutoff
```

## Self-test (`src/bin/selftest.rs`), no carrier needed

One jumper from **A2 (PA4, DAC1_OUT1) to A1 (PA1, COMP1_INP)**; nothing else on A1. The DAC stands
in for the CS pin. For each comparator threshold (¼, ½, ¾, 1 × VREFINT) it sweeps the DAC up
until COMP1 trips, checks the break fired (BIF set, MOE cleared, PA8 forced low from 100 % duty),
sweeps down to the release point, and times threshold + 100 mV step → PA8 low with the DWT cycle
counter (an upper bound: includes DAC settling and the ~1.5 µs break filter). Pass: trip within
25 mV of the fraction of the factory-calibrated VREFINT, release below trip, break seen, latency
under 10 µs. Ends with `SELFTEST PASS` / `FAIL`.

Needs: `rustup target add thumbv7em-none-eabihf`, `cargo install probe-rs-tools --locked`.
probe-rs cannot auto-detect the chip; the runner passes `--chip STM32G431RBTx`.

## Native Ubuntu (dev box)

Once: `sudo cp 69-stlink.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger`,
then replug the Nucleo (`ben` is already in `plugdev`). `probe-rs list` should no longer say
"inaccessible".

## Stall gate (`src/bin/stall.rs`)

Pololu 4036 DRV8876 carrier + a TT motor, motor supply 5 V from a bench supply limited to ~2 A.

| Carrier | Nucleo | Notes |
|---|---|---|
| EN/IN1 | D7 (PA8, TIM1_CH1) | PWM 20 kHz; the break forces it low (brake) |
| PH/IN2 | D2 (PA10) | direction |
| SLEEP | D4 (PB5) | driven high at start; also feeds VREF through 10 k, so ITRIP ≈ 1.3 A at 3.3 V |
| PMODE | **GND** | must be tied: the carrier leaves it floating = independent half-bridge mode |
| FAULT | D3 (PB3) | open drain, internal pull-up |
| CS | A1 (PA1) | COMP1 INP + ADC1; 2.49 k on the carrier = 2.5 V/A |
| GND | GND | common ground with the motor supply |
| VIN / OUT1 / OUT2 | bench 5 V / motor | |

The trip threshold is ¾ VREFINT = 0.91 V ≈ 365 mA (`THRESHOLD` in the source). TT notes from
2026-11-20: running ≈ 0.4 V CS (160 mA), stall 1.2-1.7 V. B1 (blue button) steps the modes; each
soft-starts the motor over 200 ms at 60 % duty and logs a line every 20 ms:

1. **MEASURE** (break off): running and hand-stall CS current, start-up peak. Confirms the threshold
   sits between running and stall with margin.
2. **LATCH** (break on, AOE=0): does the soft start trip? Stall the shaft by hand: the trip line
   should appear at once and the motor stays braked; firmware re-arms 2 s later.
3. **CYCLE** (break on, AOE=1): the break ends each PWM cycle early = cycle-by-cycle limit.
   Firmware declares a stall after 300 ms of continuous limiting and turns the bridge off.
4. **IDLE**.

Gate passes when LATCH cuts a hand stall without firmware in the path and running never trips.
Open question for the bench (unverified): IPROPI may sense only the drive-phase (high-side)
current, reading ~0 while EN is low (brake). Check the DRV8876 datasheet and a scope on CS
before trusting the CYCLE-mode numbers.

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
