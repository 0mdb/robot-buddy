"""Tests for vision params → worker config / safety wiring."""

from __future__ import annotations

from unittest.mock import patch

from supervisor import main as supervisor_main
from supervisor.api.param_registry import create_default_registry


def test_build_vision_worker_config_has_expected_shapes() -> None:
    reg = create_default_registry()

    updates = {
        # Floor HSV
        "vision.floor_hsv_h_low": 1,
        "vision.floor_hsv_s_low": 2,
        "vision.floor_hsv_v_low": 3,
        "vision.floor_hsv_h_high": 4,
        "vision.floor_hsv_s_high": 5,
        "vision.floor_hsv_v_high": 6,
        # Ball HSV
        "vision.ball_hsv_h_low": 171,
        "vision.ball_hsv_s_low": 81,
        "vision.ball_hsv_v_low": 41,
        "vision.ball_hsv_h_high": 14,
        "vision.ball_hsv_s_high": 254,
        "vision.ball_hsv_v_high": 253,
        # Other
        "vision.min_ball_radius_px": 12,
    }

    for name, value in updates.items():
        ok, reason = reg.set(name, value)
        assert ok, reason

    cfg = supervisor_main._build_vision_worker_config(reg)

    assert "mjpeg_enabled" not in cfg

    assert cfg["floor_hsv_low"] == [1, 2, 3]
    assert cfg["floor_hsv_high"] == [4, 5, 6]
    assert cfg["ball_hsv_low"] == [171, 81, 41]
    assert cfg["ball_hsv_high"] == [14, 254, 253]
    assert cfg["min_ball_radius"] == 12

    for k in ("floor_hsv_low", "floor_hsv_high", "ball_hsv_low", "ball_hsv_high"):
        v = cfg[k]
        assert isinstance(v, list)
        assert len(v) == 3
        assert all(isinstance(x, int) for x in v)

    assert isinstance(cfg["min_ball_radius"], int)


def test_configure_vision_policy_from_registry_calls_configure() -> None:
    reg = create_default_registry()

    ok, reason = reg.set("vision.stale_ms", 650.0)
    assert ok, reason
    ok, reason = reg.set("vision.clear_low", 0.12)
    assert ok, reason
    ok, reason = reg.set("vision.clear_high", 0.78)
    assert ok, reason

    with patch("supervisor.core.safety.configure_vision_policy") as mock_cfg:
        supervisor_main._configure_vision_policy_from_registry(reg)

    mock_cfg.assert_called_once_with(stale_ms=650.0, clear_low=0.12, clear_high=0.78)
