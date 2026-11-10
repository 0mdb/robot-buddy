"""Audio format shared by the ear, TTS and AI workers (PROTOCOL.md Appendix C).

Everything inside the supervisor is 16 kHz, 16-bit signed little-endian, mono.
"""

from __future__ import annotations

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # bytes, S16_LE
CHANNELS = 1
CHUNK_BYTES = 320  # 10 ms
BYTES_PER_MS = SAMPLE_RATE * SAMPLE_WIDTH // 1000  # 32

# Largest PCM payload in one [u16-LE len][pcm] socket frame (PROTOCOL.md §6.7).
MAX_FRAME_BYTES = 4096

# Unix-socket connect retry (mic and speaker data-plane sockets).
SOCKET_RETRY_INTERVAL_S = 0.1
SOCKET_RETRY_TIMEOUT_S = 30.0
