"""Tests for face telemetry payload parsing (v1/v2 and optional perf tail)."""

from __future__ import annotations

import struct

from supervisor.api.protocol_capture import _decode_fields
from supervisor.devices.protocol import FaceHeartbeatPayload, FaceStatusPayload


def test_face_status_payload_v1_unpack() -> None:
    payload = struct.pack("<BBBB", 3, 6, 2, 0x07)
    status = FaceStatusPayload.unpack(payload)
    assert status.mood_id == 3
    assert status.active_gesture == 6
    assert status.system_mode == 2
    assert status.flags == 0x07
    assert status.cmd_seq_last_applied is None
    assert status.t_state_applied_us is None


def test_face_status_payload_v2_unpack() -> None:
    payload = struct.pack("<BBBBII", 4, 9, 1, 0x05, 1234, 5678)
    status = FaceStatusPayload.unpack(payload)
    assert status.mood_id == 4
    assert status.active_gesture == 9
    assert status.system_mode == 1
    assert status.flags == 0x05
    assert status.cmd_seq_last_applied == 1234
    assert status.t_state_applied_us == 5678


def _heartbeat_payload(with_perf: bool) -> bytes:
    base = struct.pack("<IIII", 1000, 10, 11, 12)
    usb = struct.pack(
        "<IIIIIIIIIIII",
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
    )
    tail = struct.pack("<BBBB", 1, 0, 1, 0)
    payload = base + usb + tail
    if not with_perf:
        return payload
    perf = struct.pack(
        "<IIIIIIIIIIIIIHBB",
        33,  # window_frames
        34000,  # frame_us_avg
        42000,  # frame_us_max
        21000,  # render_us_avg
        26000,  # render_us_max
        2500,  # eyes_us_avg
        2400,  # mouth_us_avg
        6000,  # border_us_avg
        5000,  # effects_us_avg
        3000,  # overlay_us_avg
        12345,  # dirty_px_avg
        987654,  # spi_bytes_per_s
        16000,  # cmd_rx_to_apply_us_avg
        8,  # sample_div
        1,  # dirty_rect_enabled
        2,  # afterglow_downsample
    )
    return payload + perf


def test_face_heartbeat_payload_without_perf_tail() -> None:
    hb = FaceHeartbeatPayload.unpack(_heartbeat_payload(with_perf=False))
    assert hb.uptime_ms == 1000
    assert hb.status_tx_count == 10
    assert hb.touch_tx_count == 11
    assert hb.button_tx_count == 12
    assert hb.usb_tx_calls == 20
    assert hb.usb_line_state_events == 31
    assert hb.usb_dtr == 1
    assert hb.ptt_listening == 1
    assert hb.perf_window_frames == 0
    assert hb.perf_frame_us_avg == 0


def test_face_heartbeat_payload_with_perf_tail() -> None:
    hb = FaceHeartbeatPayload.unpack(_heartbeat_payload(with_perf=True))
    assert hb.perf_window_frames == 33
    assert hb.perf_frame_us_avg == 34000
    assert hb.perf_frame_us_max == 42000
    assert hb.perf_spi_bytes_per_s == 987654
    assert hb.perf_cmd_rx_to_apply_us_avg == 16000
    assert hb.perf_sample_div == 8
    assert hb.perf_dirty_rect_enabled == 1
    assert hb.perf_afterglow_downsample == 2


def test_protocol_capture_decode_face_status_v2_fields() -> None:
    payload = struct.pack("<BBBBII", 1, 2, 3, 4, 55, 123456)
    decoded = _decode_fields(0x90, payload)
    assert decoded["mood"] == 1
    assert decoded["gesture"] == 2
    assert decoded["system_mode"] == 3
    assert decoded["flags"] == "0x04"
    assert decoded["cmd_seq_last_applied"] == 55
    assert decoded["t_state_applied_us"] == 123456


def test_protocol_capture_decode_heartbeat_perf_tail() -> None:
    decoded = _decode_fields(0x93, _heartbeat_payload(with_perf=True))
    assert decoded["uptime_ms"] == 1000
    assert decoded["status_tx"] == 10
    assert "perf" in decoded
    assert decoded["perf"]["window_frames"] == 33
    assert decoded["perf"]["sample_div"] == 8
    assert decoded["perf"]["dirty_rect_enabled"] is True
