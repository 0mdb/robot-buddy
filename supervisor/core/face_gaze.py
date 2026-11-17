"""Camera-driven gaze: the eyes follow the nearest detected face.

The vision worker reports faces (normalised centre, size, bearing) at up to ~10 Hz. This
turns the chosen face into a face-MCU gaze in [-1, 1] (SET_STATE scales it to ±MAX_GAZE):

- **Target:** the face closest to the one already being followed (so the eyes don't flick
  between two people every frame); otherwise the largest, i.e. usually the nearest.
- **Mapping:** offset from the image centre (edge of frame = 1) times a gain. The x gain
  is negative by default because the screen faces the person: someone on the camera's
  right is on the screen's left. The camera sits below the screen, so the y gain is
  smaller than x and is a tuning knob, not geometry.
- **Motion:** the first sight of a face snaps the eyes to it (a saccade); after that the
  gaze is smoothed so detector jitter doesn't shimmer.
- **Loss:** keep looking where the face was for ``hold_ms``, then let go (None), so a
  missed detection or a blink of the detector doesn't send the eyes wandering.

Priority against the conversation gaze lives in the tick loop.
"""

from __future__ import annotations

from dataclasses import dataclass

# A face that moved further than this (normalised units) between updates is treated as a
# different face when choosing whom to keep following.
_SAME_FACE_DIST = 0.25
# Vision older than this counts as no faces (worker stalled or camera gone).
_VISION_STALE_MS = 1000.0


@dataclass
class FaceGazeConfig:
    enabled: bool = True
    gain_x: float = -1.0
    gain_y: float = 0.6
    smooth: float = 0.35
    hold_ms: float = 1500.0


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


class FaceGazeTracker:
    def __init__(self) -> None:
        self._gaze: tuple[float, float] | None = None
        self._target: dict | None = None
        self._last_seen_ms = 0.0
        self._last_seq = -1

    @property
    def tracking(self) -> bool:
        return self._gaze is not None

    @property
    def target(self) -> dict | None:
        return self._target

    def reset(self) -> None:
        self._gaze = None
        self._target = None
        self._last_seq = -1

    def _pick(self, faces: list[dict]) -> dict:
        if self._target is not None:
            tx, ty = self._target.get("cx", 0.5), self._target.get("cy", 0.5)
            best = min(
                faces,
                key=lambda f: (
                    (f.get("cx", 0.5) - tx) ** 2 + (f.get("cy", 0.5) - ty) ** 2
                ),
            )
            d2 = (best.get("cx", 0.5) - tx) ** 2 + (best.get("cy", 0.5) - ty) ** 2
            if d2 <= _SAME_FACE_DIST**2:
                return best
        # Largest first is the vision worker's order, but don't rely on it.
        return max(faces, key=lambda f: f.get("w", 0.0) * f.get("h", 0.0))

    def update(
        self,
        faces: list[dict],
        faces_seq: int,
        vision_age_ms: float,
        now_ms: float,
        cfg: FaceGazeConfig,
    ) -> tuple[float, float] | None:
        """Gaze toward the followed face, or None when not following anyone."""
        if not cfg.enabled:
            self.reset()
            return None

        fresh = 0.0 <= vision_age_ms <= _VISION_STALE_MS
        if fresh and faces and faces_seq != self._last_seq:
            self._last_seq = faces_seq
            face = self._pick(faces)
            raw = (
                _clamp(cfg.gain_x * (float(face.get("cx", 0.5)) * 2.0 - 1.0)),
                _clamp(cfg.gain_y * (float(face.get("cy", 0.5)) * 2.0 - 1.0)),
            )
            if self._gaze is None:
                self._gaze = raw  # first sight: snap
            else:
                a = max(0.0, min(1.0, cfg.smooth))
                gx, gy = self._gaze
                self._gaze = (gx + a * (raw[0] - gx), gy + a * (raw[1] - gy))
            self._target = face
            self._last_seen_ms = now_ms
        elif self._gaze is not None and now_ms - self._last_seen_ms > cfg.hold_ms:
            self.reset()

        return self._gaze
