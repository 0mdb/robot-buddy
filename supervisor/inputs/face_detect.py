"""Face detection with OpenCV's YuNet (cv2.FaceDetectorYN).

YuNet ships with OpenCV (4.5.4+), so there is no extra runtime: the model is a 230 KB
ONNX file (opencv_zoo, MIT) in ``supervisor/models``. On the Pi 5 it takes ~8 ms on a
320x240 frame. It also returns five landmarks (eyes, nose, mouth corners), which a later
recognition stage (e.g. cv2.FaceRecognizerSF) needs for alignment.

Faces come back in normalised frame coordinates plus bearing/elevation in degrees, the
same convention as the ball detector: bearing negative = left of the image centre,
positive = right; elevation positive = above centre.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_MODEL = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "face_detection_yunet_2023mar.onnx"
)


def vfov_from_hfov(hfov_deg: float, width: int, height: int) -> float:
    """Vertical FOV for a rectilinear lens, from the horizontal FOV and the aspect ratio."""
    half = math.radians(hfov_deg) / 2.0
    return math.degrees(2.0 * math.atan(math.tan(half) * height / max(1, width)))


def face_from_row(
    row: Any, width: int, height: int, hfov_deg: float
) -> dict[str, float]:
    """One YuNet output row (x, y, w, h, 10 landmark coords, score) → a face dict."""
    x, y, w, h = (float(v) for v in row[:4])
    score = float(row[14])
    cx = (x + w / 2.0) / width
    cy = (y + h / 2.0) / height
    # Pinhole mapping, not linear: a face at the frame edge is at exactly hfov/2.
    tan_h = math.tan(math.radians(hfov_deg) / 2.0)
    tan_v = math.tan(math.radians(vfov_from_hfov(hfov_deg, width, height)) / 2.0)
    bearing = math.degrees(math.atan((cx * 2.0 - 1.0) * tan_h))
    elevation = -math.degrees(math.atan((cy * 2.0 - 1.0) * tan_v))
    return {
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "w": round(w / width, 4),
        "h": round(h / height, 4),
        "score": round(score, 3),
        "bearing_deg": round(bearing, 1),
        "elevation_deg": round(elevation, 1),
    }


class FaceDetector:
    """Lazy YuNet wrapper. ``detect`` returns [] when the model or OpenCV support is
    missing, so vision keeps running without faces."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        top_k: int = 5,
    ) -> None:
        self._model_path = str(model_path)
        self.score_threshold = float(score_threshold)
        self._nms = float(nms_threshold)
        self._top_k = int(top_k)
        self._det: Any | None = None
        self._size: tuple[int, int] = (0, 0)
        self._failed = False
        self.error = ""

    @property
    def available(self) -> bool:
        return not self._failed and Path(self._model_path).is_file()

    def _ensure(self, width: int, height: int) -> bool:
        if self._failed:
            return False
        if self._det is not None and self._size == (width, height):
            return True
        try:
            import cv2

            if self._det is None:
                self._det = cv2.FaceDetectorYN.create(
                    self._model_path,
                    "",
                    (width, height),
                    self.score_threshold,
                    self._nms,
                    self._top_k,
                )
                log.info("face detector loaded (%s)", Path(self._model_path).name)
            else:
                self._det.setInputSize((width, height))
            self._size = (width, height)
            return True
        except Exception as e:  # noqa: BLE001 -- vision must keep running without faces
            self._failed = True
            self.error = f"face detector: {e}"
            log.warning("face detection disabled: %s", e)
            return False

    def set_score_threshold(self, value: float) -> None:
        self.score_threshold = float(value)
        if self._det is not None:
            self._det.setScoreThreshold(self.score_threshold)

    def detect(self, frame_bgr: Any, hfov_deg: float) -> list[dict[str, float]]:
        """Faces in ``frame_bgr``, largest first."""
        height, width = frame_bgr.shape[:2]
        if not self._ensure(width, height):
            return []
        try:
            _, rows = self._det.detect(frame_bgr)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            self.error = f"face detect: {e}"
            return []
        if rows is None:
            return []
        faces = [face_from_row(r, width, height, hfov_deg) for r in rows]
        faces.sort(key=lambda f: f["w"] * f["h"], reverse=True)
        return faces
