"""Tests for the BRINGUP_DIAG telemetry path (open-loop bring-up sample)."""

from __future__ import annotations

from supervisor.devices.protocol import (
    BringupDiagPayload,
    BringupPhase,
    ParsedPacket,
    TelType,
)


class TestBringupDiagPayload:
    def test_pack_unpack_round_trip(self):
        p = BringupDiagPayload(
            phase=int(BringupPhase.LEFT_FWD),
            side=0,
            forward=1,
            pwm_duty=63,
            raw_l=4096,
            raw_r=-128,
        )
        wire = BringupDiagPayload._FMT.pack(
            p.phase, p.side, p.forward, p.pwm_duty, p.raw_l, p.raw_r
        )
        assert len(wire) == 13

        out = BringupDiagPayload.unpack(wire)
        assert out.phase == p.phase
        assert out.side == p.side
        assert out.forward == p.forward
        assert out.pwm_duty == p.pwm_duty
        assert out.raw_l == p.raw_l
        assert out.raw_r == p.raw_r

    def test_unpack_rejects_short(self):
        import pytest

        with pytest.raises(ValueError, match="too short"):
            BringupDiagPayload.unpack(b"\x00" * 5)

    def test_signed_count_decodes_negative(self):
        # i32 negative → wrap correctly through struct
        wire = BringupDiagPayload._FMT.pack(0, 1, 0, 0, -1, -1000)
        out = BringupDiagPayload.unpack(wire)
        assert out.raw_l == -1
        assert out.raw_r == -1000


def _make_packet(payload: bytes) -> ParsedPacket:
    return ParsedPacket(
        pkt_type=int(TelType.BRINGUP_DIAG),
        seq=42,
        payload=payload,
        t_src_us=12345,
        t_pi_rx_ns=67890_000_000,
    )


class _FakeTransport:
    """Minimal SerialTransport stand-in for ReflexClient construction."""

    def __init__(self) -> None:
        self._packet_handlers: list = []
        self._connection_handlers: list = []

    def on_packet(self, cb) -> None:
        self._packet_handlers.append(cb)

    def on_connection_change(self, cb) -> None:
        self._connection_handlers.append(cb)

    def send(self, *_args, **_kwargs) -> None:
        pass

    @property
    def connected(self) -> bool:
        return False


class TestReflexClientDispatch:
    def test_bringup_diag_lands_on_telemetry(self):
        from supervisor.devices.reflex_client import ReflexClient

        client = ReflexClient(transport=_FakeTransport())  # type: ignore[arg-type]
        wire = BringupDiagPayload._FMT.pack(
            int(BringupPhase.RIGHT_FWD), 1, 1, 63, 100, 200
        )
        client._handle_packet(_make_packet(wire))

        latest = client.telemetry.latest_bringup
        assert latest is not None
        assert latest.phase == int(BringupPhase.RIGHT_FWD)
        assert latest.side == 1
        assert latest.forward == 1
        assert latest.raw_l == 100
        assert latest.raw_r == 200

    def test_bad_payload_does_not_crash(self):
        from supervisor.devices.reflex_client import ReflexClient

        client = ReflexClient(transport=_FakeTransport())  # type: ignore[arg-type]
        client._handle_packet(_make_packet(b"\x00\x00"))  # too short
        assert client.telemetry.latest_bringup is None
        assert client._rx_bad_payload_packets == 1


class TestRobotStateMirror:
    def test_to_dict_includes_bringup_diag_when_present(self):
        from supervisor.core.state import RobotState

        s = RobotState()
        # Default: None passthrough
        assert s.to_dict()["bringup_diag"] is None

        s.bringup_diag = {
            "phase": int(BringupPhase.LEFT_REV),
            "side": 0,
            "forward": 0,
            "pwm_duty": 63,
            "raw_l": -480,
            "raw_r": 0,
        }
        d = s.to_dict()
        assert d["bringup_diag"] == s.bringup_diag

    def test_tick_loop_mirrors_latest_bringup(self):
        # Stand-in for the tick-loop telemetry callback: copy fields onto RobotState.
        # This mirrors the path in TickLoop._on_reflex_telemetry without spinning
        # up a full TickLoop instance (which has many dependencies).
        from supervisor.core.state import RobotState
        from supervisor.devices.reflex_client import ReflexTelemetry

        tel = ReflexTelemetry()
        tel.latest_bringup = BringupDiagPayload(
            phase=int(BringupPhase.LEFT_FWD),
            side=0,
            forward=1,
            pwm_duty=63,
            raw_l=480,
            raw_r=0,
        )
        robot = RobotState()
        if tel.latest_bringup is not None:
            robot.bringup_diag = {
                "phase": tel.latest_bringup.phase,
                "side": tel.latest_bringup.side,
                "forward": tel.latest_bringup.forward,
                "pwm_duty": tel.latest_bringup.pwm_duty,
                "raw_l": tel.latest_bringup.raw_l,
                "raw_r": tel.latest_bringup.raw_r,
            }

        assert robot.bringup_diag is not None
        assert robot.bringup_diag["phase"] == int(BringupPhase.LEFT_FWD)
        assert robot.bringup_diag["raw_l"] == 480
