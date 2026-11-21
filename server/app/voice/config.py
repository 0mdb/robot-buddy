"""Voice ID settings, from the environment (VOICE_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# server/app/voice/config.py -> repo root; /data/ there is git-ignored.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    # Save each committed turn's audio + sidecar (kids' voices: opt-in).
    capture: bool = False
    # Embed, match and learn voiceprints; send a "speaker" message per turn.
    voice_id: bool = False
    data_dir: Path = _REPO_ROOT / "data" / "voice"
    keep_days: int = 30
    max_mb: int = 2000
    # Matching (ECAPA cosine). Placeholders until the bake-off on real turns
    # (server/scripts/voice_id_eval.py) sets them.
    match_score: float = 0.45
    match_margin: float = 0.08
    # Learning from the camera: the face's match score, and enough speech to trust.
    enroll_face_score: float = 0.5
    enroll_min_speech_s: float = 1.5
    max_prints_per_member: int = 40
    device: str = "cpu"

    @classmethod
    def from_env(cls) -> VoiceConfig:
        d = cls()
        return cls(
            capture=_bool("VOICE_CAPTURE", d.capture),
            voice_id=_bool("VOICE_ID", d.voice_id),
            data_dir=Path(os.environ.get("VOICE_DATA_DIR", "") or d.data_dir),
            keep_days=int(os.environ.get("VOICE_CAPTURE_DAYS", d.keep_days)),
            max_mb=int(os.environ.get("VOICE_CAPTURE_MAX_MB", d.max_mb)),
            match_score=float(os.environ.get("VOICE_MATCH_SCORE", d.match_score)),
            match_margin=float(os.environ.get("VOICE_MATCH_MARGIN", d.match_margin)),
            enroll_face_score=float(
                os.environ.get("VOICE_ENROLL_FACE_SCORE", d.enroll_face_score)
            ),
            enroll_min_speech_s=float(
                os.environ.get("VOICE_ENROLL_MIN_SPEECH_S", d.enroll_min_speech_s)
            ),
            device=os.environ.get("VOICE_DEVICE", d.device),
        )

    @property
    def enabled(self) -> bool:
        return self.capture or self.voice_id
