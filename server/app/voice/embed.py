"""Speaker embeddings: SpeechBrain ECAPA-TDNN (VoxCeleb, 192-d), on the CPU.

About 40 ms per second of audio on the dev box, run in a worker thread beside STT, so
it adds nothing to reply latency. The model downloads once to ``server/models/`` (from
the Hugging Face cache). Only the speech frames are embedded: the robot's pre-roll and the
silence before end-of-utterance carry no voice and dilute short clips.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
_FRAME = 480  # 30 ms
MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "spkrec-ecapa-voxceleb"
MIN_SPEECH_S = 0.4


def speech_frames(pcm: bytes) -> tuple[np.ndarray, float]:
    """The clip's speech as float32 in [-1, 1], and its length in seconds.

    Energy gate per 30 ms frame, relative to the clip's loud frames (the XVF3800 output is
    echo-cancelled and gain-controlled, so levels vary little between turns), with one
    frame of padding either side so word edges stay."""
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    n = len(x) // _FRAME
    if n == 0:
        return np.zeros(0, np.float32), 0.0
    frames = x[: n * _FRAME].reshape(n, _FRAME)
    rms = np.sqrt((frames**2).mean(axis=1))
    loud = float(np.percentile(rms, 95))
    thresh = max(0.006, 0.12 * loud)  # 0.006 ~ -44 dBFS
    keep = rms >= thresh
    padded = keep.copy()
    padded[1:] |= keep[:-1]
    padded[:-1] |= keep[1:]
    speech = frames[padded].reshape(-1)
    return speech, float(keep.sum()) * _FRAME / SAMPLE_RATE


class Embedder:
    """Lazy, thread-safe ECAPA wrapper. ``embed`` returns a unit vector or None."""

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self._model: Any = None
        self._lock = threading.Lock()
        self.name = "ecapa-voxceleb"

    def _load(self) -> Any:
        if self._model is None:
            import torch
            from speechbrain.inference.speaker import EncoderClassifier

            torch.set_num_threads(4)
            self._model = EncoderClassifier.from_hparams(
                source=MODEL_SOURCE,
                savedir=str(MODEL_DIR),
                run_opts={"device": self.device},
            )
            log.info("voice id: %s loaded on %s", MODEL_SOURCE, self.device)
        return self._model

    def warm(self) -> None:
        with self._lock:
            self._load()

    def embed_samples(self, speech: np.ndarray) -> np.ndarray:
        import torch

        with self._lock:
            model = self._load()
            with torch.inference_mode():
                e = model.encode_batch(torch.from_numpy(speech).unsqueeze(0))
        v = e.squeeze().cpu().numpy().astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def embed(self, pcm: bytes) -> tuple[np.ndarray | None, float]:
        """(unit embedding or None if too little speech, speech seconds)."""
        speech, speech_s = speech_frames(pcm)
        if speech_s < MIN_SPEECH_S:
            return None, speech_s
        return self.embed_samples(speech), speech_s
