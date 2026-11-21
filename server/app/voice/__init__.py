"""Voice identification (SIM-INTERACTION stage 5; docs/voice-id.md).

Who is talking, from their voice, on Buddy's LAN server:

- ``capture``: each committed turn's audio saved as a WAV with a sidecar (transcript, the
  face label from the robot), for tuning and the model bake-off. Opt-in, robot-family only.
- ``embed``: a speaker embedding per clip (SpeechBrain ECAPA-TDNN, CPU).
- ``prints``: voiceprints per roster member id (no names), learned from turns where the
  camera was sure who was speaking.
- ``service``: per connection, ties them together and reports a ``speaker`` guess.
"""

from app.voice.config import VoiceConfig

__all__ = ["VoiceConfig"]
