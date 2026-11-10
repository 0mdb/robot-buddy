"""Tests for supervisor.inputs.face_detector — gallery, identify, NMS, alignment."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from inputs.face_detector import FaceDetection, FaceRecognizer, _nms


# ── NMS ──────────────────────────────────────────────────────────


class TestNMS:
    def test_empty(self):
        boxes = np.empty((0, 4))
        scores = np.empty(0)
        keep = _nms(boxes, scores)
        assert len(keep) == 0

    def test_single(self):
        boxes = np.array([[10, 10, 50, 50]], dtype=np.float32)
        scores = np.array([0.9])
        keep = _nms(boxes, scores)
        assert list(keep) == [0]

    def test_suppresses_overlap(self):
        boxes = np.array(
            [[10, 10, 50, 50], [12, 12, 52, 52], [100, 100, 150, 150]],
            dtype=np.float32,
        )
        scores = np.array([0.9, 0.8, 0.7])
        keep = _nms(boxes, scores, iou_threshold=0.3)
        assert 0 in keep
        assert 1 not in keep  # suppressed by box 0
        assert 2 in keep  # no overlap

    def test_no_suppression_when_distant(self):
        boxes = np.array(
            [[0, 0, 10, 10], [100, 100, 110, 110]], dtype=np.float32
        )
        scores = np.array([0.9, 0.8])
        keep = _nms(boxes, scores)
        assert len(keep) == 2


# ── Gallery persistence ──────────────────────────────────────────


class TestGallery:
    def _make_recognizer(self, tmp_path: Path) -> FaceRecognizer:
        r = FaceRecognizer(
            detection_model_path="/nonexistent/det.onnx",
            recognition_model_path="/nonexistent/rec.onnx",
            gallery_path=str(tmp_path / "gallery.json"),
        )
        r._gallery_loaded = True
        return r

    def test_enroll_and_list(self, tmp_path: Path):
        r = self._make_recognizer(tmp_path)
        emb = np.random.randn(128).astype(np.float32)
        emb /= np.linalg.norm(emb)
        r.enroll("Alice", emb)
        assert r.list_enrolled() == ["Alice"]
        assert r.enrollment_count("Alice") == 1

    def test_enroll_multiple(self, tmp_path: Path):
        r = self._make_recognizer(tmp_path)
        for _ in range(3):
            emb = np.random.randn(128).astype(np.float32)
            emb /= np.linalg.norm(emb)
            r.enroll("Bob", emb)
        assert r.enrollment_count("Bob") == 3

    def test_delete(self, tmp_path: Path):
        r = self._make_recognizer(tmp_path)
        emb = np.random.randn(128).astype(np.float32)
        r.enroll("Alice", emb)
        assert r.delete_person("Alice")
        assert r.list_enrolled() == []
        assert not r.delete_person("Nobody")

    def test_save_and_load(self, tmp_path: Path):
        r1 = self._make_recognizer(tmp_path)
        emb = np.random.randn(128).astype(np.float32)
        emb /= np.linalg.norm(emb)
        r1.enroll("Alice", emb)
        r1.enroll("Bob", np.random.randn(128).astype(np.float32))

        r2 = self._make_recognizer(tmp_path)
        r2._gallery_loaded = False
        r2._ensure_gallery()
        assert sorted(r2.list_enrolled()) == ["Alice", "Bob"]
        assert r2.enrollment_count("Alice") == 1

    def test_load_missing_file(self, tmp_path: Path):
        r = self._make_recognizer(tmp_path)
        r._gallery_loaded = False
        r._ensure_gallery()
        assert r.list_enrolled() == []

    def test_load_bad_version(self, tmp_path: Path):
        gallery_path = tmp_path / "gallery.json"
        gallery_path.write_text(json.dumps({"version": 999, "people": {}}))
        r = self._make_recognizer(tmp_path)
        r._gallery_loaded = False
        r._ensure_gallery()
        assert r.list_enrolled() == []


# ── Identify ─────────────────────────────────────────────────────


class TestIdentify:
    def test_match_above_threshold(self):
        r = FaceRecognizer(
            detection_model_path="/x", recognition_model_path="/x",
            recognition_threshold=0.4,
        )
        r._gallery_loaded = True
        emb = np.array([1.0] + [0.0] * 127, dtype=np.float32)
        r._gallery = {"Alice": [emb.copy()]}

        name, conf = r.identify(emb)
        assert name == "Alice"
        assert conf >= 0.99

    def test_no_match_below_threshold(self):
        r = FaceRecognizer(
            detection_model_path="/x", recognition_model_path="/x",
            recognition_threshold=0.9,
        )
        r._gallery_loaded = True
        emb_a = np.random.randn(128).astype(np.float32)
        emb_a /= np.linalg.norm(emb_a)
        emb_b = np.random.randn(128).astype(np.float32)
        emb_b /= np.linalg.norm(emb_b)
        r._gallery = {"Alice": [emb_a]}

        name, conf = r.identify(emb_b)
        assert name == ""

    def test_best_match_across_people(self):
        r = FaceRecognizer(
            detection_model_path="/x", recognition_model_path="/x",
            recognition_threshold=0.3,
        )
        r._gallery_loaded = True

        emb_alice = np.zeros(128, dtype=np.float32)
        emb_alice[0] = 1.0
        emb_bob = np.zeros(128, dtype=np.float32)
        emb_bob[1] = 1.0
        r._gallery = {"Alice": [emb_alice], "Bob": [emb_bob]}

        query = np.zeros(128, dtype=np.float32)
        query[1] = 0.9
        query[2] = 0.1
        query /= np.linalg.norm(query)

        name, _ = r.identify(query)
        assert name == "Bob"

    def test_empty_gallery(self):
        r = FaceRecognizer(detection_model_path="/x", recognition_model_path="/x")
        r._gallery_loaded = True
        r._gallery = {}
        name, conf = r.identify(np.random.randn(128).astype(np.float32))
        assert name == ""
        assert conf == 0.0


# ── Available property ───────────────────────────────────────────


class TestAvailable:
    def test_not_available_without_models(self):
        r = FaceRecognizer(
            detection_model_path="/nonexistent/det.onnx",
            recognition_model_path="/nonexistent/rec.onnx",
        )
        assert not r.available

    def test_detect_returns_empty_when_unavailable(self):
        r = FaceRecognizer(
            detection_model_path="/nonexistent/det.onnx",
            recognition_model_path="/nonexistent/rec.onnx",
        )
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        assert r.detect_faces(frame) == []


# ── Embedding normalization ──────────────────────────────────────


class TestEnrollNormalization:
    def test_enroll_normalizes(self, tmp_path: Path):
        r = FaceRecognizer(
            detection_model_path="/x", recognition_model_path="/x",
            gallery_path=str(tmp_path / "g.json"),
        )
        r._gallery_loaded = True
        raw = np.ones(128, dtype=np.float32) * 5.0
        r.enroll("Test", raw)
        stored = r._gallery["Test"][0]
        assert abs(np.linalg.norm(stored) - 1.0) < 1e-5
