"""Tests for the XVF3800 USB control client (fake transport, no hardware)."""

from __future__ import annotations

import math
import struct

import pytest

from supervisor.devices.xvf3800 import (
    PARAMS,
    STATUS_RETRY,
    FakeTransport,
    Xvf3800,
    XvfError,
    decode,
    encode,
    reply_length,
    signed_deg,
    to_robot_deg,
)


class _RecordingTransport:
    """Records raw control requests and answers with a canned reply."""

    def __init__(self, reply: bytes = b"") -> None:
        self.reply = reply
        self.ins: list[tuple[int, int, int]] = []
        self.outs: list[tuple[int, int, bytes]] = []

    def ctrl_in(self, wvalue: int, windex: int, length: int) -> bytes:
        self.ins.append((wvalue, windex, length))
        return self.reply

    def ctrl_out(self, wvalue: int, windex: int, data: bytes) -> None:
        self.outs.append((wvalue, windex, data))

    def close(self) -> None:
        pass


class TestWireFormat:
    def test_read_request_sets_read_bit_and_resid(self):
        t = _RecordingTransport(bytes([0, 2, 1, 0]))
        assert Xvf3800(t).read("VERSION") == (2, 1, 0)
        # VERSION = resid 48, cmdid 0: wValue 0x80 | 0, wIndex 48, 3 bytes + status
        assert t.ins == [(0x80, 48, 4)]

    def test_write_request_has_no_read_bit(self):
        t = _RecordingTransport()
        Xvf3800(t).write("PP_AGCMAXGAIN", [30.0])
        assert t.outs == [(11, 17, struct.pack("<f", 30.0))]

    def test_reply_lengths(self):
        assert reply_length(PARAMS["AEC_SPENERGY_VALUES"]) == 1 + 4 * 4
        assert reply_length(PARAMS["DOA_VALUE"]) == 1 + 2 * 2
        assert reply_length(PARAMS["VERSION"]) == 1 + 3

    def test_encode_decode_round_trip(self):
        p = PARAMS["AEC_FIXEDBEAMSAZIMUTH_VALUES"]
        vals = decode(p, encode(p, [0.5, -1.25]))
        assert vals == pytest.approx((0.5, -1.25))

    def test_encode_wrong_count(self):
        with pytest.raises(XvfError):
            encode(PARAMS["AUDIO_MGR_OP_L"], [1])

    def test_short_reply(self):
        with pytest.raises(XvfError):
            decode(PARAMS["AEC_SPENERGY_VALUES"], b"\x00" * 8)


class TestDevice:
    def test_retry_then_ok(self):
        t = FakeTransport({"VERSION": [2, 1, 0]})
        t.busy = 3
        assert Xvf3800(t).version() == "2.1.0"

    def test_error_status_raises(self):
        t = FakeTransport()
        t.status = 7
        with pytest.raises(XvfError, match="status 7"):
            Xvf3800(t).read("VERSION")

    def test_busy_forever_raises(self, monkeypatch):
        monkeypatch.setattr("supervisor.devices.xvf3800._RETRY_SLEEP_S", 0.0)
        t = _RecordingTransport(bytes([STATUS_RETRY, 0, 0, 0]))
        with pytest.raises(XvfError, match="busy"):
            Xvf3800(t).read("VERSION")

    def test_access_checks(self):
        x = Xvf3800(FakeTransport())
        with pytest.raises(XvfError):
            x.write("VERSION", [1, 2, 3])
        with pytest.raises(XvfError):
            x.read("SAVE_CONFIGURATION")
        with pytest.raises(XvfError):
            x.read("NOT_A_PARAM")

    def test_write_then_read_back(self):
        t = FakeTransport()
        x = Xvf3800(t)
        x.write("PP_MIN_NS", [0.3])
        assert x.read("PP_MIN_NS")[0] == pytest.approx(0.3)

    def test_save_configuration(self):
        t = FakeTransport()
        Xvf3800(t).save_configuration()
        assert t.writes == [("SAVE_CONFIGURATION", (1,))]

    def test_voice_direction_speech(self):
        t = FakeTransport(
            {
                "AUDIO_MGR_SELECTED_AZIMUTHS": [math.radians(90.0), math.radians(80.0)],
                "AEC_SPENERGY_VALUES": [0.0, 0.0, 0.1, 2.5],
            }
        )
        vd = Xvf3800(t).voice_direction()
        assert vd.speech is True
        assert vd.azimuth_deg == pytest.approx(90.0, abs=1e-3)
        assert vd.energy == pytest.approx(2.5)
        assert len(vd.beam_energy) == 4

    def test_voice_direction_no_speech_is_nan(self):
        t = FakeTransport(
            {
                "AUDIO_MGR_SELECTED_AZIMUTHS": [float("nan"), 1.0],
                "AEC_SPENERGY_VALUES": [0.0, 0.0, 0.0, 0.0],
            }
        )
        vd = Xvf3800(t).voice_direction()
        assert vd.speech is False
        assert vd.azimuth_deg is None

    def test_negative_azimuth_wraps(self):
        t = FakeTransport(
            {
                "AUDIO_MGR_SELECTED_AZIMUTHS": [math.radians(-30.0), 0.0],
                "AEC_SPENERGY_VALUES": [0, 0, 0, 1],
            }
        )
        assert Xvf3800(t).voice_direction().azimuth_deg == pytest.approx(
            330.0, abs=1e-3
        )


class TestFrames:
    def test_robot_frame(self):
        assert to_robot_deg(10.0, offset_deg=-90.0) == pytest.approx(280.0)
        assert to_robot_deg(10.0, offset_deg=0.0, sign=-1) == pytest.approx(350.0)

    def test_signed(self):
        assert signed_deg(350.0) == pytest.approx(-10.0)
        assert signed_deg(10.0) == pytest.approx(10.0)
        assert signed_deg(180.0) == pytest.approx(-180.0)
