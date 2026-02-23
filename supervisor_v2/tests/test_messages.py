"""Tests for NDJSON envelope codec and message types."""

from __future__ import annotations

import json

from supervisor_v2.messages.envelope import Envelope, SeqCounter, make_envelope
from supervisor_v2.messages import types as T


class TestEnvelopeRoundTrip:
    """Verify serialise → deserialise identity."""

    def test_minimal(self):
        env = Envelope(
            type="tts.event.energy", src="tts", seq=11, t_ns=0, payload={"energy": 180}
        )
        line = env.to_line()
        assert line.endswith(b"\n")
        parsed = Envelope.from_line(line)
        assert parsed.type == "tts.event.energy"
        assert parsed.src == "tts"
        assert parsed.seq == 11
        assert parsed.t_ns == 0
        assert parsed.payload == {"energy": 180}

    def test_with_optional_fields(self):
        env = Envelope(
            type="tts.event.started",
            src="tts",
            seq=10,
            t_ns=1234,
            payload={"text": "Hello friend!"},
            ref_seq=5,
            session_id="sess-abc",
        )
        line = env.to_line()
        parsed = Envelope.from_line(line)
        assert parsed.ref_seq == 5
        assert parsed.session_id == "sess-abc"
        assert parsed.payload == {"text": "Hello friend!"}

    def test_empty_payload(self):
        env = Envelope(type="tts.cmd.cancel", src="core", seq=7, t_ns=0)
        line = env.to_line()
        parsed = Envelope.from_line(line)
        assert parsed.payload == {}

    def test_inline_payload_format(self):
        """Wire format must have payload fields inline, not nested (§1.8)."""
        env = Envelope(
            type="tts.event.energy", src="tts", seq=11, t_ns=0, payload={"energy": 180}
        )
        d = json.loads(env.to_line())
        assert "energy" in d
        assert "payload" not in d

    def test_version_field(self):
        env = make_envelope("tts.cmd.cancel", "core", 1)
        d = json.loads(env.to_line())
        assert d["v"] == 2


class TestEnvelopeErrors:
    def test_empty_line_raises(self):
        try:
            Envelope.from_line(b"")
            assert False, "should raise"
        except ValueError:
            pass

    def test_missing_required_field(self):
        try:
            Envelope.from_line(b'{"v": 2, "type": "x"}')
            assert False, "should raise"
        except ValueError as e:
            assert "missing required field" in str(e)

    def test_non_object_raises(self):
        try:
            Envelope.from_line(b'"just a string"')
            assert False, "should raise"
        except ValueError:
            pass


class TestSeqCounter:
    def test_monotonic(self):
        c = SeqCounter()
        assert c.next() == 0
        assert c.next() == 1
        assert c.next() == 2
        assert c.value == 3

    def test_custom_start(self):
        c = SeqCounter(start=100)
        assert c.next() == 100


class TestMakeEnvelope:
    def test_auto_timestamp(self):
        env = make_envelope("tts.cmd.cancel", "core", 1)
        assert env.t_ns > 0

    def test_explicit_timestamp(self):
        env = make_envelope("tts.cmd.cancel", "core", 1, t_ns=42)
        assert env.t_ns == 42


class TestMessageTypes:
    """Sanity check that type constants follow the dotted convention."""

    def test_dotted_format(self):
        for name in dir(T):
            if name.startswith("_") or name.startswith("SRC_"):
                continue
            val = getattr(T, name)
            if isinstance(val, str) and "." in val:
                parts = val.split(".")
                assert len(parts) == 3, f"{name}={val} should be domain.entity.verb"
