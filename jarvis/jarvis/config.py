"""Settings from the environment.

Jarvis keeps its own env file, outside the repo, so its credentials never sit
next to Buddy's: ``~/.config/jarvis/jarvis.env`` (override with JARVIS_ENV_FILE).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

IDENTITY_RE = re.compile(r"^[a-z0-9_-]{1,32}$")

DEFAULT_ENV_FILE = Path.home() / ".config" / "jarvis" / "jarvis.env"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "jarvis"

# Read tier: entity domains whose state Jarvis may read. person/device_tracker
# (where family members are) and camera are left out on purpose.
DEFAULT_HA_DOMAINS = (
    "light,switch,sensor,binary_sensor,climate,cover,lock,media_player,fan,weather"
)


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def parse_device_tokens(raw: str) -> dict[str, str]:
    """``"buddy=tok1,cli=tok2"`` -> ``{"tok1": "buddy", "tok2": "cli"}``."""
    tokens: dict[str, str] = {}
    for item in _csv(raw):
        device, sep, token = item.partition("=")
        device, token = device.strip(), token.strip()
        if not sep or not device or len(token) < 16:
            raise ValueError(
                f"JARVIS_DEVICE_TOKENS entry {device or item!r} needs the form "
                "name=<token of 16+ chars>"
            )
        tokens[token] = device
    return tokens


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8200
    data_dir: Path = DEFAULT_DATA_DIR
    # token -> device name. Empty = every call is refused.
    device_tokens: dict[str, str] = field(default_factory=dict)
    # Identities allowed to use Jarvis. Empty = every call is refused.
    owners: tuple[str, ...] = ()

    ollama_url: str = "http://127.0.0.1:11435"
    model: str = "gemma4:26b-a4b-it-qat"
    ollama_think: bool = False
    llm_timeout_s: float = 60.0
    max_tool_rounds: int = 4

    ha_url: str = ""
    ha_token: str = ""
    ha_domains: tuple[str, ...] = _csv(DEFAULT_HA_DOMAINS)
    ha_timeout_s: float = 5.0

    history_turns: int = 6
    history_window_s: float = 30 * 60

    @property
    def ha_enabled(self) -> bool:
        return bool(self.ha_url and self.ha_token)


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    path = Path(env_file or os.environ.get("JARVIS_ENV_FILE", DEFAULT_ENV_FILE))
    if path.is_file():
        load_dotenv(path, override=False)
    env = os.environ.get

    owners = _csv(env("JARVIS_OWNERS", "").lower())
    for owner in owners:
        if not IDENTITY_RE.match(owner):
            raise ValueError(f"JARVIS_OWNERS: bad identity {owner!r}")

    return Settings(
        host=env("JARVIS_HOST", "127.0.0.1"),
        port=int(env("JARVIS_PORT", "8200")),
        data_dir=Path(env("JARVIS_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser(),
        device_tokens=parse_device_tokens(env("JARVIS_DEVICE_TOKENS", "")),
        owners=owners,
        ollama_url=env("JARVIS_OLLAMA_URL", "http://127.0.0.1:11435").rstrip("/"),
        model=env("JARVIS_MODEL", "gemma4:26b-a4b-it-qat"),
        ollama_think=env("JARVIS_OLLAMA_THINK", "0").lower() in ("1", "true", "yes"),
        llm_timeout_s=float(env("JARVIS_LLM_TIMEOUT_S", "60")),
        max_tool_rounds=int(env("JARVIS_MAX_TOOL_ROUNDS", "4")),
        ha_url=env("JARVIS_HA_URL", "").rstrip("/"),
        ha_token=env("JARVIS_HA_TOKEN", ""),
        ha_domains=_csv(env("JARVIS_HA_DOMAINS", DEFAULT_HA_DOMAINS)),
        ha_timeout_s=float(env("JARVIS_HA_TIMEOUT_S", "5")),
        history_turns=int(env("JARVIS_HISTORY_TURNS", "6")),
        history_window_s=float(env("JARVIS_HISTORY_WINDOW_S", str(30 * 60))),
    )
