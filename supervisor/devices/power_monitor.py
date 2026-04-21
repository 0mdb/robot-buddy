"""Pi-side power state monitor.

Populates `RobotState.power` at ~1 Hz. Phase 1 shipping two implementations:

- `NullPowerMonitor` — always returns source="unknown". Default on non-Pi
  dev machines and when `--power-monitor=null` is passed.
- `PiPMICMonitor` — reads the Pi 5 PMIC's hwmon voltage channel and the
  `vcgencmd get_throttled` bitmask. Produces rail voltage + undervoltage /
  throttled bits. Cannot derive SoC on its own.

Later phases will add fuel-gauge monitor classes (e.g., Waveshare UPS HAT
B via INA219 on I²C) that compose with `PiPMICMonitor` — PMIC keeps being
the authoritative brownout signal, the fuel gauge fills in SoC/current.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Protocol

from supervisor.core.state import PowerState

log = logging.getLogger(__name__)


class PowerMonitor(Protocol):
    """Async power state poller. `poll()` returns a fresh PowerState.

    Implementations must be non-blocking (or bounded) — poll() is awaited
    from the supervisor's tick loop.
    """

    async def poll(self) -> PowerState: ...
    def label(self) -> str: ...


class NullPowerMonitor:
    """No-op monitor; always returns source='unknown'. Safe dev default."""

    async def poll(self) -> PowerState:
        return PowerState(
            source="unknown",
            t_last_update_ms=time.monotonic() * 1000.0,
        )

    def label(self) -> str:
        return "null"


# Pi `vcgencmd get_throttled` bitmask — see
# https://www.raspberrypi.com/documentation/computers/os.html#get_throttled
_THROTTLED_UNDERVOLTAGE_NOW = 0x1
_THROTTLED_FREQ_CAPPED_NOW = 0x2
_THROTTLED_THROTTLED_NOW = 0x4

# hwmon names the Pi 5 PMIC/ADC may register under. The probe walks
# /sys/class/hwmon and picks the first match with an in*_input file.
# Pi 5 typically exposes "rp1_adc"; older kernels / Pi 4 use
# "raspberrypi_hwmon".
_PMIC_HWMON_NAMES = frozenset({"rp1_adc", "raspberrypi_hwmon"})

# Bounded subprocess timeout for vcgencmd. The binary is fast (< 20 ms in
# practice) but we don't want a misbehaving vcgencmd to stall the tick loop.
_VCGENCMD_TIMEOUT_S = 0.2


class PiPMICMonitor:
    """Reads Pi PMIC state via /sys/class/hwmon + `vcgencmd get_throttled`.

    Constructor probes the hwmon tree for a PMIC-like device and caches the
    voltage file path. Raises FileNotFoundError if no match — caller (the
    factory) falls back to NullPowerMonitor on non-Pi hosts.
    """

    def __init__(self, sysfs_root: Path | str = "/sys/class/hwmon") -> None:
        self._sysfs_root = Path(sysfs_root)
        self._voltage_path: Path | None = None
        self._hwmon_label = ""
        self._init_sysfs()

    def _init_sysfs(self) -> None:
        if not self._sysfs_root.exists():
            raise FileNotFoundError(f"no hwmon root at {self._sysfs_root}")

        for entry in sorted(self._sysfs_root.iterdir()):
            name_file = entry / "name"
            if not name_file.is_file():
                continue
            try:
                name = name_file.read_text().strip()
            except OSError:
                continue
            if name not in _PMIC_HWMON_NAMES:
                continue
            voltage_files = sorted(entry.glob("in*_input"))
            if not voltage_files:
                continue
            self._voltage_path = voltage_files[0]
            self._hwmon_label = name
            log.info("PiPMICMonitor: using %s (name=%s)", self._voltage_path, name)
            return

        raise FileNotFoundError(
            f"no PMIC-like hwmon device found under {self._sysfs_root} "
            f"(looked for names: {sorted(_PMIC_HWMON_NAMES)})"
        )

    def label(self) -> str:
        return f"pi-pmic ({self._hwmon_label})"

    async def poll(self) -> PowerState:
        state = PowerState(
            # PMIC alone can't distinguish USB vs battery. Until a fuel-gauge
            # monitor is layered on, report "usb" as the default when the
            # rail is healthy — most users will plug in power during dev.
            source="usb",
            t_last_update_ms=time.monotonic() * 1000.0,
        )

        if self._voltage_path is not None:
            try:
                raw = self._voltage_path.read_text().strip()
                # hwmon convention: voltage inputs are in millivolts.
                state.voltage_mv = int(raw)
            except (OSError, ValueError) as e:
                log.debug("PiPMICMonitor voltage read failed: %s", e)

        # Throttled bitmask — asynchronous subprocess with bounded timeout.
        try:
            proc = await asyncio.create_subprocess_exec(
                "vcgencmd",
                "get_throttled",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=_VCGENCMD_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                log.debug("PiPMICMonitor: vcgencmd timed out")
            else:
                line = stdout.decode("ascii", errors="replace").strip()
                if line.startswith("throttled="):
                    try:
                        bits = int(line.split("=", 1)[1], 16)
                    except ValueError:
                        bits = 0
                    state.pmic_undervoltage = bool(bits & _THROTTLED_UNDERVOLTAGE_NOW)
                    state.pmic_throttled = bool(
                        bits & (_THROTTLED_FREQ_CAPPED_NOW | _THROTTLED_THROTTLED_NOW)
                    )
        except (OSError, ValueError) as e:
            log.debug("PiPMICMonitor: vcgencmd failed: %s", e)

        return state


def pick_power_monitor(override: str | None = None) -> PowerMonitor:
    """Factory used by supervisor main.

    override:
      - None or "auto": try PiPMICMonitor, fall back to NullPowerMonitor
      - "pmic": force PiPMICMonitor (raises on non-Pi hosts)
      - "null": force NullPowerMonitor (useful for tests / dev)
    """
    mode = (override or "auto").lower()
    if mode == "null":
        return NullPowerMonitor()
    if mode == "pmic":
        return PiPMICMonitor()

    try:
        return PiPMICMonitor()
    except (FileNotFoundError, OSError) as e:
        log.info("PiPMICMonitor not available (%s) — using NullPowerMonitor", e)
        return NullPowerMonitor()
