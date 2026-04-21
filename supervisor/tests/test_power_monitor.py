"""Unit tests for supervisor.devices.power_monitor."""

from __future__ import annotations

import asyncio

import pytest

from supervisor.devices import power_monitor
from supervisor.devices.power_monitor import (
    NullPowerMonitor,
    PiPMICMonitor,
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
    async def test_poll_reads_voltage(self, tmp_path, monkeypatch):
        root = _make_hwmon(tmp_path, name="rp1_adc", voltage_mv=5012)
        mon = PiPMICMonitor(sysfs_root=root)

        # Stub vcgencmd to return an all-clear bitmask.
        async def fake_exec(*args, **kwargs):
            return _FakeProc(b"throttled=0x0\n")

        monkeypatch.setattr(power_monitor.asyncio, "create_subprocess_exec", fake_exec)

        state = await mon.poll()
        assert state.source == "usb"
        assert state.voltage_mv == 5012
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
        # Voltage still read; throttled fields stay at defaults.
        assert state.voltage_mv == 5010
        assert state.pmic_undervoltage is False


class TestPickPowerMonitor:
    def test_null_override(self):
        mon = pick_power_monitor("null")
        assert isinstance(mon, NullPowerMonitor)

    def test_auto_falls_back_to_null_when_no_hwmon(self, monkeypatch, tmp_path):
        def explode(self, sysfs_root="/sys/class/hwmon"):
            raise FileNotFoundError("no pmic")

        monkeypatch.setattr(PiPMICMonitor, "__init__", explode)
        mon = pick_power_monitor(None)
        assert isinstance(mon, NullPowerMonitor)

    def test_pmic_override_raises_when_unavailable(self, monkeypatch):
        def explode(self, sysfs_root="/sys/class/hwmon"):
            raise FileNotFoundError("no pmic")

        monkeypatch.setattr(PiPMICMonitor, "__init__", explode)
        with pytest.raises(FileNotFoundError):
            pick_power_monitor("pmic")


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
