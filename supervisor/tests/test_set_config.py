"""Tests for SET_CONFIG protocol and param registry wiring."""

import struct

import pytest

from supervisor.devices.protocol import (
    CmdType,
    build_set_config,
    parse_frame,
)
from supervisor.devices.reflex_client import REFLEX_PARAM_IDS
from supervisor.api.param_registry import (
    ParamDef,
    ParamRegistry,
    create_default_registry,
)


class TestBuildSetConfig:
    def test_round_trip_float(self):
        value_bytes = struct.pack("<f", 2.5)
        pkt = build_set_config(seq=1, param_id=0x01, value_bytes=value_bytes)
        assert pkt[-1:] == b"\x00"
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == CmdType.SET_CONFIG
        assert parsed.seq == 1
        assert parsed.payload[0] == 0x01  # param_id
        assert struct.unpack("<f", parsed.payload[1:5])[0] == pytest.approx(2.5)

    def test_round_trip_int(self):
        value_bytes = struct.pack("<i", 500)
        pkt = build_set_config(seq=7, param_id=0x10, value_bytes=value_bytes)
        parsed = parse_frame(pkt[:-1])
        assert parsed.pkt_type == CmdType.SET_CONFIG
        assert parsed.payload[0] == 0x10
        assert struct.unpack("<i", parsed.payload[1:5])[0] == 500

    def test_wrong_value_length_raises(self):
        with pytest.raises(ValueError, match="4 bytes"):
            build_set_config(seq=0, param_id=0x01, value_bytes=b"\x00\x00")


class TestParamIdMapping:
    def test_all_tunable_params_have_ids(self):
        """Every runtime-mutable reflex param should have a ConfigParam ID."""
        registry = create_default_registry()
        for p_dict in registry.get_all():
            name = p_dict["name"]
            if name.startswith("reflex.") and p_dict["mutable"] == "runtime":
                assert name in REFLEX_PARAM_IDS, f"{name} missing from REFLEX_PARAM_IDS"

    def test_boot_only_params_not_in_ids(self):
        """boot_only params should not appear in REFLEX_PARAM_IDS."""
        registry = create_default_registry()
        boot_only_names = {
            p["name"]
            for p in registry.get_all()
            if p["name"].startswith("reflex.") and p["mutable"] == "boot_only"
        }
        for name in boot_only_names:
            assert name not in REFLEX_PARAM_IDS, (
                f"{name} is boot_only but in REFLEX_PARAM_IDS"
            )

    def test_param_ids_unique(self):
        """All ConfigParam IDs must be unique."""
        ids = list(REFLEX_PARAM_IDS.values())
        assert len(ids) == len(set(ids)), "duplicate param IDs found"


class TestParamRegistryOnChange:
    def test_set_triggers_callback(self):
        reg = ParamRegistry()
        reg.register(
            ParamDef(
                name="test.val",
                type="float",
                min=0.0,
                max=10.0,
                default=1.0,
            )
        )

        changes: list[tuple[str, object]] = []
        reg.on_change(lambda name, val: changes.append((name, val)))

        reg.set("test.val", 5.0)
        assert changes == [("test.val", 5.0)]

    def test_bulk_set_triggers_callbacks(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="a", type="int", min=0, max=100, default=0))
        reg.register(ParamDef(name="b", type="int", min=0, max=100, default=0))

        changes: list[tuple[str, object]] = []
        reg.on_change(lambda name, val: changes.append((name, val)))

        reg.bulk_set({"a": 10, "b": 20})
        assert ("a", 10) in changes
        assert ("b", 20) in changes
        assert len(changes) == 2

    def test_failed_validation_no_callback(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="x", type="int", min=0, max=10, default=5))

        changes: list[tuple[str, object]] = []
        reg.on_change(lambda name, val: changes.append((name, val)))

        ok, _ = reg.set("x", 999)
        assert not ok
        assert changes == []

    def test_boot_only_rejects_set(self):
        reg = ParamRegistry()
        reg.register(
            ParamDef(
                name="hw.thing",
                type="int",
                min=0,
                max=100,
                default=50,
                mutable="boot_only",
            )
        )

        ok, reason = reg.set("hw.thing", 60)
        assert not ok
        assert "boot_only" in reason

    def test_bulk_set_all_fail_if_any_invalid(self):
        reg = ParamRegistry()
        reg.register(ParamDef(name="a", type="int", min=0, max=100, default=0))
        reg.register(ParamDef(name="b", type="int", min=0, max=10, default=0))

        changes: list[tuple[str, object]] = []
        reg.on_change(lambda name, val: changes.append((name, val)))

        results = reg.bulk_set({"a": 5, "b": 999})  # b out of range
        assert not results["b"][0]
        assert changes == []  # nothing applied


class TestDefaultRegistryConsistency:
    def test_all_reflex_runtime_params_are_known(self):
        """Cross-check: every name in REFLEX_PARAM_IDS is registered."""
        registry = create_default_registry()
        for name in REFLEX_PARAM_IDS:
            p = registry.get(name)
            assert p is not None, f"{name} in REFLEX_PARAM_IDS but not in registry"
            assert p.mutable == "runtime", f"{name} should be runtime-mutable"

    def test_reflex_defaults_match_firmware(self):
        """Spot-check a few defaults against config.h values."""
        reg = create_default_registry()
        assert reg.get_value("reflex.kV") == 1.0
        assert reg.get_value("reflex.Kp") == 2.0
        assert reg.get_value("reflex.max_v_mm_s") == 500
        assert reg.get_value("reflex.cmd_timeout_ms") == 400
        assert reg.get_value("reflex.range_stop_mm") == 250
