"""Pi-side power state monitor.

Populates `RobotState.power` at ~1 Hz. Available implementations:

- `NullPowerMonitor` — always returns source="unknown". Default on non-Pi
  dev machines and when `--power-monitor=null` is passed.
- `PiPMICMonitor` — reads the Pi 5 PMIC: `vcgencmd get_throttled` for
  undervoltage / throttled bits, and `vcgencmd pmic_read_adc` for the
  3V3_SYS_V rail (proxy for overall rail health). Cannot derive SoC.
- `WaveshareUpsBMonitor` — reads the Waveshare UPS HAT (B) INA219 on I²C
  bus 1 @ 0x43 for pack voltage + current, derives SoC from a 2S 18650
  voltage curve, and composes with `PiPMICMonitor` so PMIC undervoltage
  stays the authoritative brownout signal.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Protocol

from supervisor.core.state import PowerState

log = logging.getLogger(__name__)

try:
    from smbus2 import SMBus as _SMBus  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — smbus2 is a runtime dep on the Pi
    _SMBus = None  # type: ignore[assignment]


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

# Rail label we use as the "overall rail health" voltage. Pi 5 exposes many
# rails via `vcgencmd pmic_read_adc`; 3V3_SYS_V is the system 3.3 V rail and
# tracks the input supply with the cleanest signal of the labeled rails.
_PMIC_RAIL_VOLTAGE_HEALTH = "3V3_SYS_V"

# `vcgencmd pmic_read_adc` line shape, e.g.:
#   3V3_SYS_V volt(13)=3.32910450V
#   EXT5V_V   volt(24)=4.95214390V
# Tolerant: we only require the rail label, "=", a numeric value, and a
# trailing "V" (or "A" for current rails — we ignore those).
_PMIC_ADC_LINE = re.compile(r"^\s*(?P<label>\w+)\s+\w+\(\d+\)=(?P<value>[-\d.]+)V\s*$")


async def _run_vcgencmd(*args: str) -> str | None:
    """Run vcgencmd with a bounded timeout. Returns stdout or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "vcgencmd",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as e:
        log.debug("PiPMICMonitor: vcgencmd %s spawn failed: %s", args, e)
        return None
    try:
        stdout, _ = await asyncio.wait_for(
            proc.communicate(), timeout=_VCGENCMD_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.debug("PiPMICMonitor: vcgencmd %s timed out", args)
        return None
    return stdout.decode("ascii", errors="replace")


def _parse_pmic_rail_mv(adc_output: str, rail_label: str) -> int | None:
    """Pull the named rail's voltage (mV) from `vcgencmd pmic_read_adc` output.

    Returns None if the rail isn't present or its value isn't parseable.
    """
    for raw_line in adc_output.splitlines():
        m = _PMIC_ADC_LINE.match(raw_line)
        if m is None or m.group("label") != rail_label:
            continue
        try:
            return int(round(float(m.group("value")) * 1000))
        except ValueError:
            return None
    return None


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
        _ = self._voltage_path  # hwmon channels are internal PMIC rails on Pi 5; voltage_mv comes from pmic_read_adc below.

        throttled_out = await _run_vcgencmd("get_throttled")
        if throttled_out is not None:
            line = throttled_out.strip()
            if line.startswith("throttled="):
                try:
                    bits = int(line.split("=", 1)[1], 16)
                except ValueError:
                    bits = 0
                state.pmic_undervoltage = bool(bits & _THROTTLED_UNDERVOLTAGE_NOW)
                state.pmic_throttled = bool(
                    bits & (_THROTTLED_FREQ_CAPPED_NOW | _THROTTLED_THROTTLED_NOW)
                )

        adc_out = await _run_vcgencmd("pmic_read_adc")
        if adc_out is not None:
            voltage_mv = _parse_pmic_rail_mv(adc_out, _PMIC_RAIL_VOLTAGE_HEALTH)
            if voltage_mv is not None:
                state.voltage_mv = voltage_mv

        return state


# ── Waveshare UPS HAT (B) — INA219 over I²C ─────────────────────────────────

# I²C bus + address for the HAT (B) variant.
_INA219_BUS_DEFAULT = 1
_INA219_ADDR_DEFAULT = 0x43

# INA219 register map (subset we use).
_REG_CONFIG = 0x00
_REG_SHUNT_VOLTAGE = 0x01
_REG_BUS_VOLTAGE = 0x02

# HAT (B) shunt resistance: 0.1 Ω. Shunt LSB: 10 µV.
# current_mA = (shunt_raw × 10 µV) / 0.1 Ω = shunt_raw × 0.1 mA.

# Approximate 2S 18650 discharge curve, monotonically decreasing voltage.
# Linear interpolation between waypoints; refine empirically with a real pack.
_SOC_CURVE: tuple[tuple[int, int], ...] = (
    (8400, 100),
    (8100, 90),
    (7800, 75),
    (7500, 55),
    (7200, 35),
    (6800, 15),
    (6400, 5),
    (6000, 0),
)

# Current threshold (mA) below which we consider the pack "quiescent" — used
# to distinguish float-charge vs active discharge when current is near zero.
_CURRENT_QUIESCENT_MA = 50

# Voltage above which a quiescent pack is assumed to be on float charge
# (USB-C plugged in, charge complete) rather than discharging on battery.
_FLOAT_CHARGE_THRESHOLD_MV = 8300


def _voltage_to_soc(voltage_mv: int) -> int:
    """Piecewise-linear 2S 18650 voltage → SoC %. Returns 0..100."""
    if voltage_mv >= _SOC_CURVE[0][0]:
        return 100
    if voltage_mv <= _SOC_CURVE[-1][0]:
        return 0
    for (v_hi, s_hi), (v_lo, s_lo) in zip(_SOC_CURVE, _SOC_CURVE[1:]):
        if v_lo <= voltage_mv <= v_hi:
            ratio = (voltage_mv - v_lo) / (v_hi - v_lo)
            return int(round(s_lo + ratio * (s_hi - s_lo)))
    return -1  # unreachable


def _read_ina219_blocking(bus_num: int, addr: int) -> tuple[int, int]:
    """Open the I²C bus, read INA219 voltage + current, return (mv, ma).

    Synchronous; wrap in asyncio.to_thread() from the poll loop. Raises
    OSError on bus/device failure.
    """
    if _SMBus is None:
        raise OSError("smbus2 not installed")
    with _SMBus(bus_num) as bus:
        v_hi, v_lo = bus.read_i2c_block_data(addr, _REG_BUS_VOLTAGE, 2)
        # Bus voltage register: 16-bit big-endian, top 13 bits = LSB 4 mV.
        voltage_mv = (((v_hi << 8) | v_lo) >> 3) * 4
        s_hi, s_lo = bus.read_i2c_block_data(addr, _REG_SHUNT_VOLTAGE, 2)
        s_raw = (s_hi << 8) | s_lo
        if s_raw >= 0x8000:
            s_raw -= 0x10000
    # 0.1 Ω shunt → current_mA = s_raw × 0.1.
    current_ma = round(s_raw / 10)
    return voltage_mv, current_ma


def _probe_ina219_present(
    bus_num: int = _INA219_BUS_DEFAULT, addr: int = _INA219_ADDR_DEFAULT
) -> bool:
    """Single-byte read on the config register; True if the device ACKs."""
    if _SMBus is None:
        return False
    try:
        with _SMBus(bus_num) as bus:
            bus.read_byte_data(addr, _REG_CONFIG)
        return True
    except (OSError, FileNotFoundError):
        return False


class WaveshareUpsBMonitor:
    """Waveshare UPS HAT (B) fuel-gauge monitor.

    Composes with an inner PowerMonitor (typically PiPMICMonitor): the
    inner's pmic_undervoltage / pmic_throttled bits stay authoritative,
    while INA219 fills in voltage_mv / current_ma / soc_pct / source /
    charging / ac_present.

    Construction is side-effect-free; the I²C bus is opened lazily inside
    poll(). A transient I²C glitch keeps the inner state and zeros the
    fuel-gauge fields — it does not crash the poll loop.
    """

    def __init__(
        self,
        bus_num: int = _INA219_BUS_DEFAULT,
        addr: int = _INA219_ADDR_DEFAULT,
        inner: PowerMonitor | None = None,
    ) -> None:
        self._bus_num = bus_num
        self._addr = addr
        self._inner = inner

    def label(self) -> str:
        inner = f"+{self._inner.label()}" if self._inner else ""
        return f"waveshare-ups-b (i2c-{self._bus_num} @ 0x{self._addr:02x}){inner}"

    async def poll(self) -> PowerState:
        if self._inner is not None:
            state = await self._inner.poll()
        else:
            state = PowerState()
        state.t_last_update_ms = time.monotonic() * 1000.0

        try:
            voltage_mv, current_ma = await asyncio.to_thread(
                _read_ina219_blocking, self._bus_num, self._addr
            )
        except OSError as e:
            log.debug("WaveshareUpsBMonitor: I²C read failed: %s", e)
            return state

        state.voltage_mv = voltage_mv
        state.current_ma = current_ma
        state.soc_pct = _voltage_to_soc(voltage_mv)

        # Source / charging from current sign. HAT (B) wires + = discharge.
        if current_ma < -_CURRENT_QUIESCENT_MA:
            state.source = "ac_charging"
            state.charging = True
            state.ac_present = True
        elif current_ma > _CURRENT_QUIESCENT_MA:
            state.source = "battery"
            state.charging = False
            state.ac_present = False
        else:
            # Quiescent: float-charge plateau vs idle-on-battery.
            if voltage_mv >= _FLOAT_CHARGE_THRESHOLD_MV:
                state.source = "ac_charging"
                state.ac_present = True
            else:
                state.source = "battery"
                state.ac_present = False
            state.charging = False

        return state


def pick_power_monitor(override: str | None = None) -> PowerMonitor:
    """Factory used by supervisor main.

    override:
      - None or "auto": try Waveshare UPS HAT (B), then PiPMICMonitor, then
        NullPowerMonitor
      - "ups-b": force WaveshareUpsBMonitor wrapping PiPMICMonitor (or
        NullPowerMonitor if PMIC is unavailable). Raises OSError if the
        INA219 bus/device is missing.
      - "pmic": force PiPMICMonitor (raises on non-Pi hosts)
      - "null": force NullPowerMonitor (useful for tests / dev)
    """
    mode = (override or "auto").lower()
    if mode == "null":
        return NullPowerMonitor()
    if mode == "pmic":
        return PiPMICMonitor()
    if mode == "ups-b":
        inner = _try_pmic_else_null()
        # Probe to give a clean OSError up front rather than silent zeros.
        if not _probe_ina219_present():
            raise OSError(
                f"Waveshare UPS HAT (B) INA219 not detected on i2c-"
                f"{_INA219_BUS_DEFAULT} @ 0x{_INA219_ADDR_DEFAULT:02x}"
            )
        return WaveshareUpsBMonitor(inner=inner)

    # auto: try ups-b → pmic → null.
    if _probe_ina219_present():
        inner = _try_pmic_else_null()
        log.info(
            "PowerMonitor: WaveshareUpsBMonitor on i2c-%d @ 0x%02x (inner=%s)",
            _INA219_BUS_DEFAULT,
            _INA219_ADDR_DEFAULT,
            inner.label(),
        )
        return WaveshareUpsBMonitor(inner=inner)
    try:
        return PiPMICMonitor()
    except (FileNotFoundError, OSError) as e:
        log.info("PiPMICMonitor not available (%s) — using NullPowerMonitor", e)
        return NullPowerMonitor()


def _try_pmic_else_null() -> PowerMonitor:
    try:
        return PiPMICMonitor()
    except (FileNotFoundError, OSError) as e:
        log.info(
            "PiPMICMonitor not available (%s) — UPS-B will compose with NullPowerMonitor",
            e,
        )
        return NullPowerMonitor()
