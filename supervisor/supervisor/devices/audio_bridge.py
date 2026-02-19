"""Audio bridge — routes TTS audio to the face MCU's USB audio device.

Architecture:
  - Planner server renders TTS as WAV/Opus blobs
  - Supervisor receives audio blobs over HTTP/WebSocket
  - Supervisor plays them to the face MCU's ALSA sound card
    (the face MCU appears as a standard USB Audio Class device)
  - Mic capture flows in reverse via the same ALSA device

The face MCU exposes a TinyUSB composite device: CDC (serial commands)
+ UAC (audio). No custom audio protocol is needed — it's just a USB
sound card from the host's perspective.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class AudioBridge:
    """Stub for future audio routing to the face MCU's USB sound card."""

    def __init__(self, alsa_device: str | None = None) -> None:
        self._device = alsa_device
        self._playing = False

    @property
    def playing(self) -> bool:
        return self._playing

    def play(self, audio_data: bytes, fmt: str = "wav") -> None:
        """Play audio blob to the face MCU's speaker.

        Args:
            audio_data: Raw audio bytes (WAV or Opus).
            fmt: Audio format — "wav" or "opus".
        """
        log.warning("audio_bridge: play() not implemented (fmt=%s, %d bytes)", fmt, len(audio_data))

    def stop_playback(self) -> None:
        """Stop any active playback."""
        log.warning("audio_bridge: stop_playback() not implemented")

    def start_mic_capture(self) -> None:
        """Begin capturing audio from the face MCU's microphone."""
        log.warning("audio_bridge: start_mic_capture() not implemented")

    def stop_mic_capture(self) -> bytes:
        """Stop mic capture and return recorded audio as WAV bytes."""
        log.warning("audio_bridge: stop_mic_capture() not implemented")
        return b""
