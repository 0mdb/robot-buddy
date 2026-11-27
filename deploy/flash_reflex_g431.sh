#!/usr/bin/env bash
# Flash the reflex v3 STM32G431 from the Pi over the host UART (ST system bootloader on USART1,
# AN2606 sec. 52). Runs ON THE PI. Manual-only, like every flash-* action.
#
#   REFLEX_NRST_GPIO=<n> REFLEX_BOOT0_GPIO=<n> deploy/flash_reflex_g431.sh buddy-reflex.bin
#
# J11 on the v3 board brings the core's NRST NPN and BOOT0 series R to two Pi GPIOs (idle low).
# Which Pi GPIOs they are is not fixed yet, so both must be given. The supervisor holds the UART:
# stop it first (systemctl stop robot-buddy-supervisor) and start it afterwards.
# The BOOT0 pin is only honoured with option byte nSWBOOT0 = 1 (factory default; check with
# STM32CubeProgrammer if the bootloader never answers). The first flash of a blank chip is SWD.
# Needs: stm32flash (apt install stm32flash), pinctrl (Pi 5 raspi-utils).
set -euo pipefail

BIN=${1:?usage: $0 firmware.bin}
PORT=${REFLEX_PORT:-/dev/ttyAMA0}
NRST=${REFLEX_NRST_GPIO:?set REFLEX_NRST_GPIO (Pi GPIO driving the v3 NRST NPN, high = reset)}
BOOT0=${REFLEX_BOOT0_GPIO:?set REFLEX_BOOT0_GPIO (Pi GPIO driving v3 BOOT0, high = bootloader)}

reset_into() { # $1 = BOOT0 level (dh/dl)
    pinctrl set "$BOOT0" op "$1"
    pinctrl set "$NRST" op dh # NPN on: NRST low
    sleep 0.05
    pinctrl set "$NRST" op dl
    sleep 0.1
}

trap 'pinctrl set "$BOOT0" op dl; pinctrl set "$NRST" op dl' EXIT
echo "reset into the bootloader (BOOT0 high)"
reset_into dh
# 8E1 is the bootloader's framing; stm32flash sets it. -v verify, -R reset after (not used: we
# reset with BOOT0 low ourselves so the application starts).
stm32flash -b 115200 -w "$BIN" -v "$PORT"
echo "reset into the application (BOOT0 low)"
reset_into dl
echo "done"
