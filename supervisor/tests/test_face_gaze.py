"""Face detection mapping, the face-gaze tracker, and its priority in the tick loop."""

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from supervisor.api.param_registry import create_default_registry
from supervisor.core.face_gaze import FaceGazeConfig, FaceGazeTracker
from supervisor.inputs.face_detect import (
    DEFAULT_MODEL,
    FaceDetector,
    face_from_row,
    vfov_from_hfov,
)


def _face(cx: float, cy: float = 0.5, size: float = 0.2) -> dict:
    return {"cx": cx, "cy": cy, "w": size, "h": size, "score": 0.9}


# ── face_from_row ────────────────────────────────────────────────


def _row(x, y, w, h, score=0.9):
    return [x, y, w, h] + [0.0] * 10 + [score]


def test_centred_face_has_zero_bearing():
    f = face_from_row(_row(140, 100, 40, 40), 320, 240, 66.0)
    assert f["cx"] == pytest.approx(0.5)
    assert f["bearing_deg"] == pytest.approx(0.0)
    assert f["elevation_deg"] == pytest.approx(0.0)


def test_face_at_right_edge_is_half_hfov():
    # Centre on the right edge → bearing = +hfov/2 (pinhole, so exact at the edge).
    f = face_from_row(_row(300, 100, 40, 40), 320, 240, 66.0)
    assert f["bearing_deg"] == pytest.approx(33.0, abs=0.1)


def test_face_high_in_frame_has_positive_elevation():
    f = face_from_row(_row(140, 0, 40, 40), 320, 240, 66.0)
    assert f["elevation_deg"] > 0


def test_vfov_from_hfov_4_3():
    assert vfov_from_hfov(66.0, 640, 480) == pytest.approx(51.8, abs=0.2)


def test_detector_without_model_returns_nothing(tmp_path):
    det = FaceDetector(model_path=tmp_path / "missing.onnx")
    assert not det.available
    assert det.detect(np.zeros((240, 320, 3), np.uint8), 66.0) == []


def test_detector_runs_on_blank_frame():
    det = FaceDetector()
    if not det.available:
        pytest.skip("YuNet model not present")
    assert det.detect(np.zeros((240, 320, 3), np.uint8), 66.0) == []
    assert DEFAULT_MODEL.is_file()


# ── FaceGazeTracker ──────────────────────────────────────────────

CFG = FaceGazeConfig(gain_x=-1.0, gain_y=0.6, smooth=0.5, hold_ms=1000.0)


def test_no_faces_no_gaze():
    t = FaceGazeTracker()
    assert t.update([], 1, 50.0, 0.0, CFG) is None
    assert not t.tracking


def test_first_sight_snaps_with_mirrored_x():
    t = FaceGazeTracker()
    # Face on the camera's right (cx 0.75) → eyes to the screen's left (negative x).
    g = t.update([_face(0.75, 0.75)], 1, 50.0, 0.0, CFG)
    assert g == pytest.approx((-0.5, 0.3))


def test_smoothing_after_first_sight():
    t = FaceGazeTracker()
    t.update([_face(0.5)], 1, 50.0, 0.0, CFG)
    g = t.update([_face(1.0)], 2, 50.0, 100.0, CFG)
    assert g[0] == pytest.approx(-0.5)  # halfway to -1.0 with smooth 0.5


def test_same_seq_does_not_update():
    t = FaceGazeTracker()
    t.update([_face(0.5)], 1, 50.0, 0.0, CFG)
    g = t.update([_face(1.0)], 1, 50.0, 100.0, CFG)
    assert g == pytest.approx((0.0, 0.0))


def test_holds_then_lets_go():
    t = FaceGazeTracker()
    t.update([_face(0.75)], 1, 50.0, 0.0, CFG)
    assert t.update([], 2, 50.0, 900.0, CFG) is not None  # within hold
    assert t.update([], 3, 50.0, 1100.0, CFG) is None  # past hold


def test_stale_vision_counts_as_no_faces():
    t = FaceGazeTracker()
    assert t.update([_face(0.75)], 1, 5000.0, 0.0, CFG) is None
    assert t.update([_face(0.75)], 1, -1.0, 0.0, CFG) is None  # no vision yet


def test_keeps_following_the_same_person():
    t = FaceGazeTracker()
    t.update([_face(0.2, size=0.3)], 1, 50.0, 0.0, CFG)
    # A bigger face appears on the other side; keep the one we were following.
    t.update([_face(0.8, size=0.5), _face(0.22, size=0.3)], 2, 50.0, 100.0, CFG)
    assert t.target["cx"] == pytest.approx(0.22)


def test_switches_when_followed_face_is_gone():
    t = FaceGazeTracker()
    t.update([_face(0.2)], 1, 50.0, 0.0, CFG)
    t.update([_face(0.8)], 2, 50.0, 100.0, CFG)
    assert t.target["cx"] == pytest.approx(0.8)


def test_disabled_resets():
    t = FaceGazeTracker()
    t.update([_face(0.75)], 1, 50.0, 0.0, CFG)
    off = FaceGazeConfig(enabled=False)
    assert t.update([_face(0.75)], 2, 50.0, 100.0, off) is None
    assert not t.tracking


# ── Tick loop priority ───────────────────────────────────────────


def _loop():
    from supervisor.core.tick_loop import TickLoop

    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    face = MagicMock()
    face.connected = True
    loop = TickLoop(
        reflex=None,
        face=face,
        workers=workers,
        param_registry=create_default_registry(),
    )
    return loop, face


def _see_face(loop, cx: float, seq: int) -> None:
    import time

    loop.world.faces = [_face(cx)]
    loop.world.faces_frame_seq = seq
    loop.world.vision_rx_mono_ms = time.monotonic() * 1000.0


def _last_gaze(face) -> tuple[float, float]:
    kw = face.send_state.call_args.kwargs
    return kw["gaze_x"], kw["gaze_y"]


def _tick(loop) -> None:
    from supervisor.core.state import DesiredTwist

    loop._emit_mcu(DesiredTwist(), loop.robot.tick_mono_ms)


def test_idle_face_drives_gaze_and_pauses_wander():
    from supervisor.core.conv_state import DEFAULT_FACE_FLAGS
    from supervisor.devices.protocol import FACE_FLAG_IDLE_WANDER

    loop, face = _loop()
    _see_face(loop, 0.75, 1)
    _tick(loop)
    assert _last_gaze(face)[0] == pytest.approx(-0.5)
    face.send_flags.assert_called_with(DEFAULT_FACE_FLAGS & ~FACE_FLAG_IDLE_WANDER)
    assert loop.robot.face_gaze_target["cx"] == pytest.approx(0.75)


def test_wander_resumes_after_face_lost():
    from supervisor.core.conv_state import DEFAULT_FACE_FLAGS

    loop, face = _loop()
    loop._param_registry.set("gaze.face_hold_ms", 0.0)
    _see_face(loop, 0.75, 1)
    _tick(loop)
    loop.world.faces = []
    loop.world.faces_frame_seq = 2
    loop.robot.tick_mono_ms += 100.0
    _tick(loop)
    face.send_flags.assert_called_with(DEFAULT_FACE_FLAGS)
    assert loop.robot.face_gaze_target is None


def test_thinking_keeps_its_aversion():
    from supervisor.devices.protocol import FaceConvState

    loop, face = _loop()
    loop._conv.set_state(FaceConvState.THINKING)
    _tick(loop)  # transition (choreographer ramp)
    loop._conv_choreo._gaze_ramp = None  # ramp finished
    _see_face(loop, 0.75, 1)
    _tick(loop)
    assert _last_gaze(face) == pytest.approx((0.5, -0.3), abs=0.01)


def test_listening_looks_at_the_face_not_centre():
    from supervisor.devices.protocol import FaceConvState

    loop, face = _loop()
    loop._conv.set_state(FaceConvState.LISTENING)
    _tick(loop)
    loop._conv_choreo._gaze_ramp = None
    _see_face(loop, 0.25, 1)
    _tick(loop)
    assert _last_gaze(face)[0] == pytest.approx(0.5)


def test_face_track_param_off_falls_back():
    loop, face = _loop()
    loop._param_registry.set("gaze.face_track", False)
    _see_face(loop, 0.75, 1)
    _tick(loop)
    assert loop.robot.face_gaze_target is None
