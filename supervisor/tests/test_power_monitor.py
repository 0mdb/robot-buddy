"""Unit tests for supervisor.devices.power_monitor."""

from __future__ import annotations

import asyncio

import pytest

from supervisor.devices import power_monitor
from supervisor.devices.power_monitor import (
    NullPowerMonitor,
    PiPMICMonitor,
    WaveshareUpsBMonitor,
    _voltage_to_soc,
    pick_power_monitor,
)


def _make_hwmon(tmp_path, name: str, voltage_mv: int, file_name: str = "in1_input"):
    """Build a fake /sys/class/hwmon with one device."""
    root = tmp_path / "hwmon"
    dev = root / "hwmon0"
    dev.mkdir(parents=True)
    (dev / "name").write_text(name + "\n")
    (dev / file_name).write_text(f"{voltage_mv}\n")
    return root


class TestNullPowerMonitor:
    @pytest.mark.asyncio
    async def test_returns_unknown(self):
        mon = NullPowerMonitor()
        state = await mon.poll()
        assert state.source == "unknown"
        assert state.voltage_mv == 0
        assert state.soc_pct == -1
        assert state.pmic_undervoltage is False
        assert state.t_last_update_ms > 0

    def test_label(self):
        assert NullPowerMonitor().label() == "null"


class TestPiPMICMonitor:
    def test_init_raises_when_no_hwmon_root(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PiPMICMonitor(sysfs_root=tmp_path / "missing")

    def test_init_raises_when_no_matching_device(self, tmp_path):
        _make_hwmon(tmp_path, name="nvme_composite", voltage_mv=5000)
        with pytest.raises(FileNotFoundError):
            PiPMICMonitor(sysfs_root=tmp_path / "hwmon")

    def test_init_picks_rp1_adc(self, tmp_path):
        root = _make_hwmon(tmp_path, name="rp1_adc", voltage_mv=5020)
        mon = PiPMICMonitor(sysfs_root=root)
        assert "rp1_adc" in mon.label()

    def test_init_picks_raspberrypi_hwmon(self, tmp_path):
        root = _make_hwmon(tmp_path, name="raspberrypi_hwmon", voltage_mv=4950)
        mon = PiPMICMonitor(sysfs_root=root)
        assert "raspberrypi_hwmon" in mon.label()

    @pytest.mark.asyncio
    async def test_poll_clean_state(self, tmp_path, monkeypatch):
        root = _make_hwmon(tmp_path, name="rp1_adc", voltage_mv=5012)
        mon = PiPMICMonitor(sysfs_root=root)

        # Stub vcgencmd to return an all-clear bitmask.
        async def fake_exec(*args, **kwargs):
            return _FakeProc(b"throttled=0x0\n")

        monkeypatch.setattr(power_monitor.asyncio, "create_subprocess_exec", fake_exec)

        state = await mon.poll()
        assert state.source == "usb"
        # voltage_mv stays 0 on Pi-PMIC-only (hwmon channels aren't the 5V
        # rail; see PiPMICMonitor.poll() for the rationale).
        assert state.voltage_mv == 0
        assert state.pmic_undervoltage is False
        assert state.pmic_throttled is False

    @pytest.mark.asyncio
    async def test_poll_detects_undervoltage_and_throttled(self, tmp_path, monkeypatch):
        root = _make_hwmon(tmp_path, name="rp1_adc", voltage_mv=4700)
        mon = PiPMICMonitor(sysfs_root=root)

        # bit 0 = undervoltage, bit 2 = currently throttled
        async def fake_exec(*args, **kwargs):
            return _FakeProc(b"throttled=0x5\n")

        monkeypatch.setattr(power_monitor.asyncio, "create_subprocess_exec", fake_exec)

        state = await mon.poll()
        assert state.pmic_undervoltage is True
        assert state.pmic_throttled is True

    @pytest.mark.asyncio
    async def test_poll_survives_vcgencmd_missing(self, tmp_path, monkeypatch):
        root = _make_hwmon(tmp_path, name="rp1_adc", voltage_mv=5010)
        mon = PiPMICMonitor(sysfs_root=root)

        async def boom(*args, **kwargs):
            raise FileNotFoundError("vcgencmd not found")

        monkeypatch.setattr(power_monitor.asyncio, "create_subprocess_exec", boom)

        state = await mon.poll()
        # Throttled fields stay at defaults; voltage_mv is 0 by design
        # (see PiPMICMonitor.poll() note — hwmon can't see the 5V input).
        assert state.voltage_mv == 0
        assert state.pmic_undervoltage is False


class TestVoltageToSoc:
    def test_at_or_above_top_returns_100(self):
        assert _voltage_to_soc(8400) == 100
        assert _voltage_to_soc(8500) == 100

    def test_at_or_below_bottom_returns_0(self):
        assert _voltage_to_soc(6000) == 0
        assert _voltage_to_soc(5800) == 0

    def test_interpolates_between_waypoints(self):
        # Halfway between (7800, 75) and (7500, 55) → 7650 mV → 65 %
        assert _voltage_to_soc(7650) == 65

    def test_monotonic_decreasing(self):
        prev = 101
        for mv in range(8400, 5999, -100):
            soc = _voltage_to_soc(mv)
            assert soc <= prev
            prev = soc


class _FakeSMBus:
    """Stand-in for smbus2.SMBus. Use as the module-level _SMBus factory."""

    def __init__(
        self,
        registers: dict[tuple[int, int], int] | None = None,
        fail_open: bool = False,
        fail_read: bool = False,
    ) -> None:
        self._registers = registers or {}
        self._fail_open = fail_open
        self._fail_read = fail_read

    def __call__(self, bus_num: int) -> _FakeSMBus:
        return self

    def __enter__(self) -> _FakeSMBus:
        if self._fail_open:
            raise OSError("simulated bus open failure")
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read_byte_data(self, addr: int, reg: int) -> int:
        if self._fail_read:
            raise OSError("simulated read failure")
        return self._registers.get((addr, reg), 0) & 0xFF

    def read_i2c_block_data(self, addr: int, reg: int, length: int) -> list[int]:
        if self._fail_read:
            raise OSError("simulated read failure")
        word = self._registers.get((addr, reg), 0) & 0xFFFF
        return list(word.to_bytes(length, "big"))


def _ina219_registers(voltage_mv: int, current_ma: int) -> dict[tuple[int, int], int]:
    """Encode bus-voltage + shunt-voltage register values for a fake INA219."""
    # Bus voltage register: top 13 bits = LSB 4 mV, bottom 3 bits are status.
    bus_raw = (voltage_mv // 4) << 3
    # Shunt voltage register (signed): LSB 10 µV, 0.1 Ω shunt → s_raw = ma × 10.
    shunt_raw = current_ma * 10
    if shunt_raw < 0:
        shunt_raw += 0x10000
    return {
        (0x43, 0x00): 0x00,  # config (just needs to ACK)
        (0x43, 0x02): bus_raw,
        (0x43, 0x01): shunt_raw,
    }


class TestWaveshareUpsBMonitor:
    @pytest.mark.asyncio
    async def test_label_includes_inner(self):
        mon = WaveshareUpsBMonitor(inner=NullPowerMonitor())
        assert "waveshare-ups-b" in mon.label()
        assert "null" in mon.label()

    @pytest.mark.asyncio
    async def test_poll_battery_discharge(self, monkeypatch):
        # 7.4 V, 800 mA discharging → battery, no charge, mid-curve SoC.
        fake = _FakeSMBus(_ina219_registers(7400, 800))
        monkeypatch.setattr(power_monitor, "_SMBus", fake)
        mon = WaveshareUpsBMonitor(inner=NullPowerMonitor())
        state = await mon.poll()
        assert state.voltage_mv == 7400
        assert state.current_ma == 800
        assert state.source == "battery"
        assert state.charging is False
        assert state.ac_present is False
        assert 35 <= state.soc_pct <= 55

    @pytest.mark.asyncio
    async def test_poll_charging(self, monkeypatch):
        # 8.2 V, -300 mA (charging current) → ac_charging.
        fake = _FakeSMBus(_ina219_registers(8200, -300))
        monkeypatch.setattr(power_monitor, "_SMBus", fake)
        mon = WaveshareUpsBMonitor(inner=NullPowerMonitor())
        state = await mon.poll()
        assert state.voltage_mv == 8200
        assert state.current_ma == -300
        assert state.source == "ac_charging"
        assert state.charging is True
        assert state.ac_present is True

    @pytest.mark.asyncio
    async def test_poll_quiescent_float(self, monkeypatch):
        # 8.4 V, ~0 mA → AC plugged, charge complete (float plateau).
        fake = _FakeSMBus(_ina219_registers(8400, 10))
        monkeypatch.setattr(power_monitor, "_SMBus", fake)
        mon = WaveshareUpsBMonitor(inner=NullPowerMonitor())
        state = await mon.poll()
        assert state.source == "ac_charging"
        assert state.charging is False
        assert state.ac_present is True
        assert state.soc_pct == 100

    @pytest.mark.asyncio
    async def test_poll_quiescent_idle_battery(self, monkeypatch):
        # 7.6 V, ~0 mA → idle on battery (no current, below float threshold).
        fake = _FakeSMBus(_ina219_registers(7600, -5))
        monkeypatch.setattr(power_monitor, "_SMBus", fake)
        mon = WaveshareUpsBMonitor(inner=NullPowerMonitor())
        state = await mon.poll()
        assert state.source == "battery"
        assert state.charging is False
        assert state.ac_present is False

    @pytest.mark.asyncio
    async def test_poll_passes_through_pmic_undervoltage(self, monkeypatch, tmp_path):
        # PMIC inner reports undervoltage; INA219 layer must preserve it.
        root = _make_hwmon(tmp_path, name="rp1_adc", voltage_mv=4700)
        inner = PiPMICMonitor(sysfs_root=root)

        async def fake_exec(*args, **kwargs):
            return _FakeProc(b"throttled=0x5\n")

        monkeypatch.setattr(power_monitor.asyncio, "create_subprocess_exec", fake_exec)
        fake = _FakeSMBus(_ina219_registers(7400, 800))
        monkeypatch.setattr(power_monitor, "_SMBus", fake)

        mon = WaveshareUpsBMonitor(inner=inner)
        state = await mon.poll()
        assert state.pmic_undervoltage is True
        assert state.pmic_throttled is True
        assert state.voltage_mv == 7400  # INA219 still applied on top

    @pytest.mark.asyncio
    async def test_poll_survives_i2c_failure(self, monkeypatch):
        # Bus fails to open → keep inner state, leave fuel-gauge fields at default.
        fake = _FakeSMBus(fail_open=True)
        monkeypatch.setattr(power_monitor, "_SMBus", fake)
        mon = WaveshareUpsBMonitor(inner=NullPowerMonitor())
        state = await mon.poll()
        assert state.voltage_mv == 0
        assert state.current_ma == 0
        assert state.soc_pct == -1
        assert state.t_last_update_ms > 0


class TestPickPowerMonitor:
    def test_null_override(self):
        mon = pick_power_monitor("null")
        assert isinstance(mon, NullPowerMonitor)

    def test_auto_falls_back_to_null_when_no_hwmon(self, monkeypatch, tmp_path):
        def explode(self, sysfs_root="/sys/class/hwmon"):
            raise FileNotFoundError("no pmic")

        monkeypatch.setattr(PiPMICMonitor, "__init__", explode)
        monkeypatch.setattr(
            power_monitor, "_probe_ina219_present", lambda *a, **k: False
        )
        mon = pick_power_monitor(None)
        assert isinstance(mon, NullPowerMonitor)

    def test_pmic_override_raises_when_unavailable(self, monkeypatch):
        def explode(self, sysfs_root="/sys/class/hwmon"):
            raise FileNotFoundError("no pmic")

        monkeypatch.setattr(PiPMICMonitor, "__init__", explode)
        with pytest.raises(FileNotFoundError):
            pick_power_monitor("pmic")

    def test_auto_picks_ups_b_when_probe_succeeds(self, monkeypatch):
        # Stub PiPMICMonitor.__init__ so we don't need a real hwmon tree.
        # Set the attrs that label() reads so the factory's diagnostic log works.
        def fake_init(self, sysfs_root="/sys/class/hwmon"):
            self._hwmon_label = "test"
            self._voltage_path = None
            self._sysfs_root = None

        monkeypatch.setattr(PiPMICMonitor, "__init__", fake_init)
        monkeypatch.setattr(
            power_monitor, "_probe_ina219_present", lambda *a, **k: True
        )
        mon = pick_power_monitor(None)
        assert isinstance(mon, WaveshareUpsBMonitor)
        assert isinstance(mon._inner, PiPMICMonitor)

    def test_auto_ups_b_falls_back_to_null_inner_when_pmic_missing(self, monkeypatch):
        def explode(self, sysfs_root="/sys/class/hwmon"):
            raise FileNotFoundError("no pmic")

        monkeypatch.setattr(PiPMICMonitor, "__init__", explode)
        monkeypatch.setattr(
            power_monitor, "_probe_ina219_present", lambda *a, **k: True
        )
        mon = pick_power_monitor(None)
        assert isinstance(mon, WaveshareUpsBMonitor)
        assert isinstance(mon._inner, NullPowerMonitor)

    def test_ups_b_override_raises_when_probe_fails(self, monkeypatch):
        monkeypatch.setattr(
            PiPMICMonitor, "__init__", lambda self, sysfs_root="/sys/class/hwmon": None
        )
        monkeypatch.setattr(
            power_monitor, "_probe_ina219_present", lambda *a, **k: False
        )
        with pytest.raises(OSError):
            pick_power_monitor("ups-b")


class _FakeProc:
    """Minimal asyncio subprocess stand-in for the test doubles."""

    def __init__(self, stdout: bytes) -> None:
        self._stdout = stdout

    async def communicate(self):
        return self._stdout, b""

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


@pytest.fixture(autouse=True)
def _event_loop_policy():
    # Keep default policy; pytest-asyncio handles loop lifecycle.
    yield
    # no-op cleanup
    _ = asyncio
