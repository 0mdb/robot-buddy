"""Find an ALSA device by card name instead of card number.

USB cards get their number at enumeration, so ``plughw:2,0`` can point at a
different card after a reboot. A device spec ``match:<text>`` is resolved
against /proc/asound/cards (card id or description, case-insensitive) to
``plughw:CARD=<id>,DEV=0``. Any other spec is passed through unchanged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_CARDS = Path("/proc/asound/cards")
_HEAD = re.compile(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s*(.*)$")


@dataclass(frozen=True)
class AlsaCard:
    index: int
    id: str
    description: str


def parse_cards(text: str) -> list[AlsaCard]:
    cards: list[AlsaCard] = []
    for line in text.splitlines():
        m = _HEAD.match(line)
        if m:
            cards.append(AlsaCard(int(m.group(1)), m.group(2), m.group(3).strip()))
        elif cards and line.strip():
            c = cards[-1]
            cards[-1] = AlsaCard(c.index, c.id, f"{c.description} {line.strip()}")
    return cards


def resolve_alsa_device(spec: str, cards_text: str | None = None) -> str | None:
    """Resolve ``match:<text>``; None if no card matches. Other specs pass through."""
    if not spec.startswith("match:"):
        return spec
    want = spec[len("match:") :].strip().lower()
    if cards_text is None:
        try:
            cards_text = _CARDS.read_text()
        except OSError:
            log.warning("cannot read %s to resolve %r", _CARDS, spec)
            return None
    for c in parse_cards(cards_text):
        if want and (want in c.id.lower() or want in c.description.lower()):
            return f"plughw:CARD={c.id},DEV=0"
    return None
