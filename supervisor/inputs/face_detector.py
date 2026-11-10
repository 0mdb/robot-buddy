"""Face detection and recognition via SCRFD + MobileFaceNet (ONNX Runtime).

Models are loaded lazily on first use. If onnxruntime is not installed,
all detection returns empty results. Designed for a small family gallery
(4-6 people) on Raspberry Pi 5.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

try:
    import onnxruntime as ort

    _ORT_AVAILABLE = True
except ImportError:
    ort = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False

log = logging.getLogger(__name__)

# ArcFace-standard alignment reference points for 112x112 crop.
_ARCFACE_REF = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

_GALLERY_VERSION = 1


@dataclass
class FaceDetection:
    """A single detected face with optional identity."""

    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in original frame coords
    confidence: float
    name: str = ""
    identity_confidence: float = 0.0
    embedding: np.ndarray | None = field(default=None, repr=False)


class FaceRecognizer:
    """Lazy-loading SCRFD detector + MobileFaceNet recognizer."""

    def __init__(
        self,
        detection_model_path: str = "./models/scrfd_500m.onnx",
        recognition_model_path: str = "./models/mobilefacenet.onnx",
        gallery_path: str = "./data/face_embeddings.json",
        detection_threshold: float = 0.5,
        recognition_threshold: float = 0.45,
        detection_input_size: tuple[int, int] = (640, 640),
    ) -> None:
        self._det_path = detection_model_path
        self._rec_path = recognition_model_path
        self._gallery_path = gallery_path
        self._det_threshold = detection_threshold
        self._rec_threshold = recognition_threshold
        self._det_input_size = detection_input_size

        self._det_session: ort.InferenceSession | None = None  # type: ignore[union-attr]
        self._rec_session: ort.InferenceSession | None = None  # type: ignore[union-attr]
        self._gallery: dict[str, list[np.ndarray]] = {}
        self._gallery_loaded = False

    @property
    def available(self) -> bool:
        """True if onnxruntime is installed and both model files exist."""
        return (
            _ORT_AVAILABLE
            and os.path.isfile(self._det_path)
            and os.path.isfile(self._rec_path)
        )

    def _create_session(self, model_path: str) -> ort.InferenceSession:  # type: ignore[name-defined]
        """Create an ONNX inference session. Override in tests for mocking."""
        providers = ["CPUExecutionProvider"]
        opts = ort.SessionOptions()  # type: ignore[union-attr]
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        return ort.InferenceSession(model_path, opts, providers=providers)  # type: ignore[union-attr]

    def _ensure_models(self) -> bool:
        """Load models lazily. Returns True if both sessions are ready."""
        if self._det_session is not None and self._rec_session is not None:
            return True
        if not self.available:
            return False
        try:
            if self._det_session is None:
                self._det_session = self._create_session(self._det_path)
                log.info("SCRFD detection model loaded from %s", self._det_path)
            if self._rec_session is None:
                self._rec_session = self._create_session(self._rec_path)
                log.info("MobileFaceNet recognition model loaded from %s", self._rec_path)
            return True
        except Exception:
            log.exception("Failed to load face recognition models")
            return False

    def _ensure_gallery(self) -> None:
        if self._gallery_loaded:
            return
        self._gallery_loaded = True
        self.load_gallery()

    # ── Detection ────────────────────────────────────────────────

    def detect_faces(self, frame: np.ndarray) -> list[FaceDetection]:
        """Detect and optionally identify faces in a BGR frame."""
        if not self._ensure_models():
            return []
        self._ensure_gallery()

        h, w = frame.shape[:2]
        det_w, det_h = self._det_input_size

        blob, scale, pad_w, pad_h = self._preprocess_detection(frame, det_w, det_h)
        raw_boxes, raw_scores, raw_landmarks = self._run_detection(blob)

        results: list[FaceDetection] = []
        for i in range(len(raw_scores)):
            if raw_scores[i] < self._det_threshold:
                continue

            x1, y1, x2, y2 = raw_boxes[i]
            x1 = int(np.clip((x1 - pad_w) / scale, 0, w - 1))
            y1 = int(np.clip((y1 - pad_h) / scale, 0, h - 1))
            x2 = int(np.clip((x2 - pad_w) / scale, 0, w - 1))
            y2 = int(np.clip((y2 - pad_h) / scale, 0, h - 1))

            if x2 - x1 < 10 or y2 - y1 < 10:
                continue

            landmarks = None
            if raw_landmarks is not None and i < len(raw_landmarks):
                lm = raw_landmarks[i].copy()
                lm[:, 0] = (lm[:, 0] - pad_w) / scale
                lm[:, 1] = (lm[:, 1] - pad_h) / scale
                landmarks = lm

            embedding = None
            name = ""
            identity_conf = 0.0

            if landmarks is not None and len(landmarks) == 5:
                aligned = self._align_face(frame, landmarks)
                embedding = self.compute_embedding(aligned)
                if embedding is not None and self._gallery:
                    name, identity_conf = self.identify(embedding)

            results.append(
                FaceDetection(
                    bbox=(x1, y1, x2, y2),
                    confidence=float(raw_scores[i]),
                    name=name,
                    identity_confidence=identity_conf,
                    embedding=embedding,
                )
            )

        return results

    def _preprocess_detection(
        self, frame: np.ndarray, det_w: int, det_h: int
    ) -> tuple[np.ndarray, float, int, int]:
        """Letterbox + normalize for SCRFD."""
        h, w = frame.shape[:2]
        scale = min(det_w / w, det_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        pad_w = (det_w - new_w) // 2
        pad_h = (det_h - new_h) // 2

        resized = cv2.resize(frame, (new_w, new_h))
        padded = np.full((det_h, det_w, 3), 127, dtype=np.uint8)
        padded[pad_h : pad_h + new_h, pad_w : pad_w + new_w] = resized

        blob = (padded.astype(np.float32) - 127.5) / 128.0
        blob = blob.transpose(2, 0, 1)[np.newaxis]  # NCHW

        return blob, scale, pad_w, pad_h

    def _run_detection(
        self, blob: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """Run SCRFD and decode outputs into boxes, scores, landmarks."""
        assert self._det_session is not None
        input_name = self._det_session.get_inputs()[0].name
        outputs = self._det_session.run(None, {input_name: blob})

        return self._decode_scrfd_outputs(outputs, self._det_input_size)

    @staticmethod
    def _decode_scrfd_outputs(
        outputs: list[np.ndarray],
        input_size: tuple[int, int],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """Decode SCRFD multi-stride outputs.

        SCRFD outputs 3 groups of (scores, boxes, landmarks) for strides 8, 16, 32.
        Total outputs: 9 (3 strides x 3 tensors each).
        """
        strides = [8, 16, 32]
        det_w, det_h = input_size
        all_boxes: list[np.ndarray] = []
        all_scores: list[np.ndarray] = []
        all_landmarks: list[np.ndarray] = []
        has_landmarks = len(outputs) >= 9

        for idx, stride in enumerate(strides):
            feat_h = det_h // stride
            feat_w = det_w // stride

            scores = outputs[idx].reshape(-1)
            boxes_raw = outputs[idx + len(strides)].reshape(-1, 4)

            anchors_x = np.arange(feat_w, dtype=np.float32) * stride
            anchors_y = np.arange(feat_h, dtype=np.float32) * stride
            ax, ay = np.meshgrid(anchors_x, anchors_y)
            anchors = np.stack([ax.ravel(), ay.ravel()], axis=1)

            num_anchors_per_point = scores.shape[0] // anchors.shape[0]
            anchors = np.repeat(anchors, num_anchors_per_point, axis=0)

            if len(anchors) != len(boxes_raw):
                anchors = anchors[: len(boxes_raw)]

            x1 = anchors[:, 0] - boxes_raw[:, 0] * stride
            y1 = anchors[:, 1] - boxes_raw[:, 1] * stride
            x2 = anchors[:, 0] + boxes_raw[:, 2] * stride
            y2 = anchors[:, 1] + boxes_raw[:, 3] * stride
            boxes = np.stack([x1, y1, x2, y2], axis=1)

            all_scores.append(scores)
            all_boxes.append(boxes)

            if has_landmarks:
                lm_raw = outputs[idx + 2 * len(strides)].reshape(-1, 10)
                lm = np.zeros_like(lm_raw)
                for k in range(5):
                    lm[:, 2 * k] = anchors[:, 0] + lm_raw[:, 2 * k] * stride
                    lm[:, 2 * k + 1] = anchors[:, 1] + lm_raw[:, 2 * k + 1] * stride
                all_landmarks.append(lm)

        scores = np.concatenate(all_scores)
        boxes = np.concatenate(all_boxes)
        landmarks = np.concatenate(all_landmarks) if all_landmarks else None

        keep = _nms(boxes, scores, iou_threshold=0.4)
        boxes = boxes[keep]
        scores = scores[keep]
        if landmarks is not None:
            landmarks = landmarks[keep].reshape(-1, 5, 2)

        return boxes, scores, landmarks

    # ── Alignment ────────────────────────────────────────────────

    @staticmethod
    def _align_face(frame: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """Warp face to 112x112 ArcFace-aligned crop using 5 landmarks."""
        M = cv2.estimateAffinePartial2D(landmarks, _ARCFACE_REF, method=cv2.LMEDS)[0]
        if M is None:
            cx = int(landmarks[:, 0].mean())
            cy = int(landmarks[:, 1].mean())
            h, w = frame.shape[:2]
            size = max(int(np.ptp(landmarks[:, 0]) * 1.5), 56)
            x1 = max(0, cx - size)
            y1 = max(0, cy - size)
            x2 = min(w, cx + size)
            y2 = min(h, cy + size)
            crop = frame[y1:y2, x1:x2]
            return cv2.resize(crop, (112, 112))
        return cv2.warpAffine(frame, M, (112, 112), borderValue=0)

    # ── Recognition ──────────────────────────────────────────────

    def compute_embedding(self, aligned_face: np.ndarray) -> np.ndarray | None:
        """Extract 128-dim L2-normalized embedding from a 112x112 aligned face."""
        if self._rec_session is None:
            return None

        rgb = cv2.cvtColor(aligned_face, cv2.COLOR_BGR2RGB)
        blob = (rgb.astype(np.float32) - 127.5) / 127.5  # [-1, 1]
        blob = blob.transpose(2, 0, 1)[np.newaxis]  # NCHW

        input_name = self._rec_session.get_inputs()[0].name
        out = self._rec_session.run(None, {input_name: blob})[0].flatten()

        norm = np.linalg.norm(out)
        if norm > 0:
            out = out / norm
        return out

    def identify(self, embedding: np.ndarray) -> tuple[str, float]:
        """Match embedding against gallery. Returns (name, confidence)."""
        best_name = ""
        best_score = 0.0

        for name, embeddings in self._gallery.items():
            for stored in embeddings:
                score = float(np.dot(embedding, stored))
                if score > best_score:
                    best_score = score
                    best_name = name

        if best_score >= self._rec_threshold:
            return best_name, best_score
        return "", 0.0

    # ── Enrollment ───────────────────────────────────────────────

    def enroll(self, name: str, embedding: np.ndarray) -> None:
        """Add an embedding to the gallery for a person."""
        self._ensure_gallery()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        self._gallery.setdefault(name, []).append(embedding)
        self.save_gallery()

    def delete_person(self, name: str) -> bool:
        """Remove all embeddings for a person. Returns True if found."""
        self._ensure_gallery()
        if name in self._gallery:
            del self._gallery[name]
            self.save_gallery()
            return True
        return False

    def list_enrolled(self) -> list[str]:
        """List enrolled person names."""
        self._ensure_gallery()
        return list(self._gallery.keys())

    def enrollment_count(self, name: str) -> int:
        """Number of embeddings stored for a person."""
        self._ensure_gallery()
        return len(self._gallery.get(name, []))

    # ── Gallery persistence ──────────────────────────────────────

    def save_gallery(self) -> None:
        """Persist gallery to JSON."""
        path = Path(self._gallery_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": _GALLERY_VERSION,
            "people": {
                name: {"embeddings": [e.tolist() for e in embeds]}
                for name, embeds in self._gallery.items()
            },
        }
        path.write_text(json.dumps(data, indent=2))

    def load_gallery(self) -> None:
        """Load gallery from JSON."""
        path = Path(self._gallery_path)
        if not path.is_file():
            self._gallery = {}
            return
        try:
            data = json.loads(path.read_text())
            if data.get("version") != _GALLERY_VERSION:
                log.warning("Gallery version mismatch, starting fresh")
                self._gallery = {}
                return
            self._gallery = {}
            for name, info in data.get("people", {}).items():
                embeds = [
                    np.array(e, dtype=np.float32) for e in info.get("embeddings", [])
                ]
                if embeds:
                    self._gallery[name] = embeds
            log.info(
                "Loaded face gallery: %d people, %d total embeddings",
                len(self._gallery),
                sum(len(v) for v in self._gallery.values()),
            )
        except Exception:
            log.exception("Failed to load face gallery from %s", path)
            self._gallery = {}


def _nms(
    boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.4
) -> np.ndarray:
    """Non-maximum suppression. Returns indices to keep."""
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    order = scores.argsort()[::-1]
    keep: list[int] = []

    while len(order) > 0:
        i = order[0]
        keep.append(i)
        if len(order) == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

        remaining = np.where(iou <= iou_threshold)[0]
        order = order[remaining + 1]

    return np.array(keep, dtype=np.intp)
