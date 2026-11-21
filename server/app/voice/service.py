"""Per-turn voice work: save the clip, embed it, match it, learn from the camera.

Runs beside the turn, never in its way: the embedding starts at end-of-utterance in a
worker thread, and the result waits for the turn to finish. A turn dropped by a late
resume is discarded (its audio comes back merged into the next turn).

**Learning from the camera** is the main way voiceprints are made. A turn's voice is added
to a member's prints only when the robot saw exactly one face, recognised as that member
with a good score, and the clip holds enough speech. The danger is a child talking off
camera while a parent's face is in view, so a sample is refused when the voice clearly
sounds like someone else already known, or (once the member has a few prints) nothing
like the member. The robot's voice direction vs face bearing is logged in the sidecar for
a later agreement check, once the XVF3800 DoA offset is calibrated.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.voice.capture import TurnAudioStore
from app.voice.config import VoiceConfig
from app.voice.embed import Embedder
from app.voice.prints import Match, VoicePrintStore

log = logging.getLogger(__name__)

# Once a member has this many prints, a sample must sound at least a little like them.
_ESTABLISHED = 5
_SELF_FLOOR = 0.25


class VoiceService:
    """App-wide: the stores and the model. One ``VoiceSession`` per connection."""

    def __init__(
        self,
        config: VoiceConfig,
        *,
        embedder: Any | None = None,
        prints: VoicePrintStore | None = None,
        store: TurnAudioStore | None = None,
    ) -> None:
        self.config = config
        root = Path(config.data_dir)
        self.store = store or TurnAudioStore(
            root, keep_days=config.keep_days, max_mb=config.max_mb
        )
        self.prints = prints or VoicePrintStore(
            root / "voiceprints.json", max_per_member=config.max_prints_per_member
        )
        self.embedder = embedder or Embedder(config.device)

    def session(self) -> VoiceSession:
        return VoiceSession(self)

    def forget(self, member_id: str) -> dict[str, Any]:
        had = self.prints.forget(member_id)
        clips = self.store.forget_member(member_id)
        log.info("voice id: forgot %s (prints=%s clips=%d)", member_id, had, clips)
        return {"prints": had, "clips": clips}

    def forget_all(self) -> None:
        self.prints.forget_all()
        self.store.forget_all()
        log.info("voice id: forgot everyone")

    def learn_decision(
        self,
        face: dict[str, Any] | None,
        speech_s: float,
        text: str,
        m: Match,
        own_score: float | None,
    ) -> tuple[str | None, str]:
        """(member to add this sample to, or None; the reason)."""
        cfg = self.config
        if not face or not face.get("member_id"):
            return None, "no face label"
        mid = str(face["member_id"])
        if int(face.get("faces", 1)) != 1:
            return None, "more than one face"
        if float(face.get("score") or 0.0) < cfg.enroll_face_score:
            return None, "face score low"
        if speech_s < cfg.enroll_min_speech_s:
            return None, "short"
        if not text.strip():
            return None, "no words"
        if (
            m.best_id
            and m.best_id != mid
            and m.score >= cfg.match_score
            and m.score - (own_score or 0.0) >= cfg.match_margin
        ):
            return None, f"sounds like {m.best_id}"
        if (
            self.prints.count(mid) >= _ESTABLISHED
            and own_score is not None
            and own_score < _SELF_FLOOR
        ):
            return None, "unlike their prints"
        return mid, "face"


class VoiceSession:
    """One connection's voice state: the face label the robot last sent, and a running
    average of this conversation's voice (short answers like "seven" are too little alone)."""

    def __init__(self, service: VoiceService) -> None:
        self.svc = service
        self.face: dict[str, Any] | None = None
        self._sum: np.ndarray | None = None
        self._weight = 0.0
        self._session_member: str | None = None

    def update_profile(self, profile: dict[str, Any]) -> None:
        face = profile.get("face_speaker")
        self.face = dict(face) if isinstance(face, dict) else None
        ids = profile.get("roster_ids")
        if isinstance(ids, list):
            gone = self.svc.prints.keep_only({str(i) for i in ids})
            for mid in gone:
                self.svc.store.forget_member(mid)
            if gone:
                log.info("voice id: dropped prints of removed members %s", gone)

    def _session_add(self, emb: np.ndarray, w: float, turn: Match) -> None:
        if (
            turn.member_id
            and self._session_member
            and turn.member_id != self._session_member
        ):
            # Someone else is talking now: start the conversation's average over.
            self._sum, self._weight = None, 0.0
        v = emb * w
        self._sum = v if self._sum is None else self._sum + v
        self._weight += w

    def _session_emb(self) -> np.ndarray | None:
        if self._sum is None:
            return None
        return self._sum / (np.linalg.norm(self._sum) + 1e-9)

    async def process(
        self,
        pcm: bytes,
        *,
        turn_task: asyncio.Task[Any] | None,
        turn_meta: dict[str, Any],
        face: dict[str, Any] | None,
        robot_id: str = "",
    ) -> dict[str, Any] | None:
        cfg = self.svc.config
        emb_task = (
            asyncio.create_task(asyncio.to_thread(self.svc.embedder.embed, pcm))
            if cfg.voice_id
            else None
        )
        if turn_task is not None:
            with contextlib.suppress(BaseException):
                await asyncio.shield(turn_task)
            if turn_task.cancelled():
                if emb_task is not None:
                    emb_task.cancel()
                return None  # dropped by a late resume; its audio is in the next turn
        emb: np.ndarray | None = None
        speech_s = 0.0
        if emb_task is not None:
            try:
                emb, speech_s = await emb_task
            except Exception:
                log.exception("voice id: embedding failed")
        text = str(turn_meta.get("text") or "")
        turn_id = str(turn_meta.get("turn_id") or "")
        msg: dict[str, Any] | None = None
        sidecar: dict[str, Any] = {
            "turn_id": turn_id,
            "robot_id": robot_id,
            "text": text,
            "face": face,
            "speech_s": round(speech_s, 2),
        }
        if emb is not None:
            turn = self.svc.prints.match(
                emb, threshold=cfg.match_score, margin=cfg.match_margin
            )
            self._session_add(emb, speech_s, turn)
            sess_emb = self._session_emb()
            session = (
                self.svc.prints.match(
                    sess_emb, threshold=cfg.match_score, margin=cfg.match_margin
                )
                if sess_emb is not None
                else turn
            )
            self._session_member = session.member_id
            own = None
            if face and face.get("member_id"):
                own = self.svc.prints.scores(emb).get(str(face["member_id"]))
            learn_mid, why = self.svc.learn_decision(face, speech_s, text, turn, own)
            learned = bool(
                learn_mid
                and self.svc.prints.add(
                    learn_mid, emb, speech_s=speech_s, source="face"
                )
            )
            sidecar["voice"] = turn.as_dict()
            sidecar["learn"] = {"member_id": learn_mid, "why": why, "added": learned}
            sidecar["model"] = getattr(self.svc.embedder, "name", "")
            msg = {
                "type": "speaker",
                "turn_id": turn_id,
                "speech_s": round(speech_s, 2),
                "turn": turn.as_dict(),
                "session": session.as_dict(),
                "learned": learned,
                "learn_why": why,
            }
            log.info(
                "voice id turn=%s speech=%.1fs best=%s %.2f runner=%s %.2f -> %s "
                "(session %s %.2f) learn=%s (%s)",
                turn_id,
                speech_s,
                turn.best_id,
                turn.score,
                turn.runner_id,
                turn.runner_score,
                turn.member_id,
                session.member_id,
                session.score,
                learned,
                why,
            )
        if cfg.capture:
            try:
                await asyncio.to_thread(self.svc.store.save, pcm, sidecar)
            except Exception:
                log.exception("voice capture: save failed")
        return msg


_service: VoiceService | None = None


def get_voice_service() -> VoiceService | None:
    """The app's voice service, or None when VOICE_CAPTURE and VOICE_ID are both off."""
    global _service
    if _service is None:
        cfg = VoiceConfig.from_env()
        if not cfg.enabled:
            return None
        _service = VoiceService(cfg)
    return _service
