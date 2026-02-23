"""NDJSON envelope codec for Core ↔ Worker messages.

Wire format (PROTOCOL.md §3.1): one JSON line per message, newline-terminated.
Payload fields are inline — not nested in a ``payload`` object (§1.8).

Example::

    {"v": 2, "type": "tts.event.energy", "src": "tts", "seq": 11, "t_ns": 0, "energy": 180}
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 2


@dataclass(slots=True)
class Envelope:
    """Parsed NDJSON message envelope."""

    type: str
    src: str
    seq: int
    t_ns: int
    v: int = SCHEMA_VERSION
    # Payload fields stored as a flat dict — merged with header on serialise.
    payload: dict[str, Any] = field(default_factory=dict)

    # Optional header fields (present on some message types).
    ref_seq: int | None = None
    ref_type: str | None = None
    session_id: str | None = None
    err: str | None = None

    # ── Serialisation ────────────────────────────────────────────

    def to_line(self) -> bytes:
        """Serialise to a single NDJSON line (bytes, newline-terminated)."""
        d: dict[str, Any] = {
            "v": self.v,
            "type": self.type,
            "src": self.src,
            "seq": self.seq,
            "t_ns": self.t_ns,
        }
        if self.ref_seq is not None:
            d["ref_seq"] = self.ref_seq
        if self.ref_type is not None:
            d["ref_type"] = self.ref_type
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.err is not None:
            d["err"] = self.err
        d.update(self.payload)
        return json.dumps(d, separators=(",", ":")).encode() + b"\n"

    # ── Deserialisation ──────────────────────────────────────────

    @classmethod
    def from_line(cls, line: bytes | str) -> Envelope:
        """Parse a single NDJSON line into an Envelope.

        Raises ``ValueError`` on malformed input.
        """
        if isinstance(line, bytes):
            line = line.decode()
        line = line.strip()
        if not line:
            raise ValueError("empty line")
        d = json.loads(line)
        if not isinstance(d, dict):
            raise ValueError("expected JSON object")

        # Required fields
        try:
            msg_type = d.pop("type")
            src = d.pop("src")
            seq = d.pop("seq")
            t_ns = d.pop("t_ns")
        except KeyError as e:
            raise ValueError(f"missing required field: {e}") from None

        v = d.pop("v", SCHEMA_VERSION)

        # Optional header fields
        ref_seq = d.pop("ref_seq", None)
        ref_type = d.pop("ref_type", None)
        session_id = d.pop("session_id", None)
        err = d.pop("err", None)

        # Everything remaining is payload
        return cls(
            type=msg_type,
            src=src,
            seq=seq,
            t_ns=t_ns,
            v=v,
            payload=d,
            ref_seq=ref_seq,
            ref_type=ref_type,
            session_id=session_id,
            err=err,
        )


class SeqCounter:
    """Per-source monotonically increasing sequence counter."""

    __slots__ = ("_value",)

    def __init__(self, start: int = 0) -> None:
        self._value = start

    def next(self) -> int:
        v = self._value
        self._value += 1
        return v

    @property
    def value(self) -> int:
        return self._value


def make_envelope(
    msg_type: str,
    src: str,
    seq: int,
    payload: dict[str, Any] | None = None,
    *,
    t_ns: int | None = None,
    ref_seq: int | None = None,
    session_id: str | None = None,
) -> Envelope:
    """Convenience builder for outbound envelopes."""
    return Envelope(
        type=msg_type,
        src=src,
        seq=seq,
        t_ns=t_ns if t_ns is not None else time.monotonic_ns(),
        payload=payload or {},
        ref_seq=ref_seq,
        session_id=session_id,
    )
