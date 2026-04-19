"""STT configuration plumbing tests.

These cover the Settings validation paths and WhisperSTT constructor wiring
without loading any model — no GPU or network required.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.stt.whisper import WhisperSTT


def test_settings_accept_gpu_stt_config() -> None:
    settings = Settings(
        stt_model_size="large-v3-turbo",
        stt_device="cuda",
        stt_compute_type="int8_float16",
    )
    assert settings.stt_model_size == "large-v3-turbo"
    assert settings.stt_device == "cuda"
    assert settings.stt_compute_type == "int8_float16"


def test_settings_reject_invalid_stt_device() -> None:
    with pytest.raises(ValueError, match="STT_DEVICE"):
        Settings(stt_device="mps")


def test_settings_reject_invalid_stt_compute_type() -> None:
    with pytest.raises(ValueError, match="STT_COMPUTE_TYPE"):
        Settings(stt_compute_type="bfloat16")


def test_settings_normalize_stt_case() -> None:
    settings = Settings(stt_device="CUDA", stt_compute_type="INT8_FLOAT16")
    assert settings.stt_device == "cuda"
    assert settings.stt_compute_type == "int8_float16"


def test_whisper_stt_debug_snapshot_reports_config() -> None:
    stt = WhisperSTT(
        model_size="large-v3-turbo",
        device="cuda",
        compute_type="int8_float16",
    )
    snap = stt.debug_snapshot()
    assert snap["model_size"] == "large-v3-turbo"
    assert snap["device"] == "cuda"
    assert snap["compute_type"] == "int8_float16"
    assert snap["loaded"] is False
