from __future__ import annotations

import logging
from typing import Iterator

import numpy as np
import sounddevice as sd

from supervisor.devices.face_client import FaceClient

log = logging.getLogger(__name__)


class AudioService:
    def __init__(self, face_client: FaceClient) -> None:
        self._face_client = face_client

    def play_stream(self, audio_iterator: Iterator[bytes]) -> None:
        """Plays a stream of audio chunks and manages lip-sync."""
        try:
            with sd.RawOutputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
            ) as stream:
                log.info("Starting audio playback")
                self._face_client.send_talking(True, 0)
                for chunk in audio_iterator:
                    stream.write(chunk)

                    # Lip-sync
                    audio_data = np.frombuffer(chunk, dtype=np.int16)
                    # Normalize to -1.0 to 1.0
                    audio_data_float = audio_data.astype(np.float32) / 32768.0
                    rms = np.sqrt(np.mean(audio_data_float**2))
                    energy = int(min(1.0, rms * 10) * 255) # Scale up
                    self._face_client.send_talking(True, energy)

                log.info("Audio stream finished")
        except Exception:
            log.exception("Error during audio playback")
        finally:
            self._face_client.send_talking(False, 0)
