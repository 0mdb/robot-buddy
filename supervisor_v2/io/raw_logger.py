"""Raw binary packet logger (PROTOCOL.md §10.1).

Record format per entry:
    [t_pi_rx_ns:i64-LE] [src_id_len:u8] [src_id:utf8] [frame_len:u16-LE] [raw_bytes:N]

This is the deterministic replay stream — feed raw_bytes through the COBS
decoder and packet parser with recorded t_pi_rx_ns timestamps.
"""

from __future__ import annotations

import logging
import struct
import time
from pathlib import Path
from typing import BinaryIO

log = logging.getLogger(__name__)

_HEADER_FMT = struct.Struct("<q")  # t_pi_rx_ns: i64-LE
_FRAME_LEN_FMT = struct.Struct("<H")  # frame_len: u16-LE

# Default: rotate at 50 MB, keep 5 files
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_FILES = 5


class RawPacketLogger:
    """Append-only binary logger for deterministic packet replay.

    Thread-safety: NOT thread-safe.  Call from the serial transport's
    event-loop thread only (same thread that calls _dispatch_frame).
    """

    def __init__(
        self,
        log_dir: Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_files: int = DEFAULT_MAX_FILES,
    ) -> None:
        self._log_dir = log_dir
        self._max_bytes = max_bytes
        self._max_files = max_files
        self._file: BinaryIO | None = None
        self._bytes_written: int = 0
        self._entries_written: int = 0
        self._enabled: bool = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def entries_written(self) -> int:
        return self._entries_written

    def start(self) -> None:
        """Open a new log file and begin recording."""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._rotate_if_needed()
        path = self._log_dir / f"raw_{int(time.time())}.bin"
        self._file = open(path, "ab")  # noqa: SIM115
        self._bytes_written = 0
        self._enabled = True
        log.info("raw logger: started → %s", path)

    def stop(self) -> None:
        """Flush and close the current log file."""
        self._enabled = False
        if self._file:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
            self._file = None
        log.info("raw logger: stopped (%d entries)", self._entries_written)

    def log_frame(self, t_pi_rx_ns: int, src_id: str, raw_frame: bytes) -> None:
        """Record a single raw COBS frame with Pi receive timestamp."""
        if not self._enabled or self._file is None:
            return

        src_bytes = src_id.encode("utf-8")
        entry = (
            _HEADER_FMT.pack(t_pi_rx_ns)
            + bytes([len(src_bytes)])
            + src_bytes
            + _FRAME_LEN_FMT.pack(len(raw_frame))
            + raw_frame
        )

        try:
            self._file.write(entry)
            self._bytes_written += len(entry)
            self._entries_written += 1
        except Exception as e:
            log.warning("raw logger: write error: %s", e)
            return

        if self._bytes_written >= self._max_bytes:
            self._rotate()

    def _rotate(self) -> None:
        """Close current file and open a new one."""
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None

        self._rotate_if_needed()
        path = self._log_dir / f"raw_{int(time.time())}.bin"
        self._file = open(path, "ab")  # noqa: SIM115
        self._bytes_written = 0
        log.info("raw logger: rotated → %s", path)

    def _rotate_if_needed(self) -> None:
        """Remove oldest log files if we exceed max_files."""
        files = sorted(self._log_dir.glob("raw_*.bin"), key=lambda p: p.stat().st_mtime)
        while len(files) >= self._max_files:
            oldest = files.pop(0)
            try:
                oldest.unlink()
                log.info("raw logger: removed old log %s", oldest.name)
            except Exception as e:
                log.warning("raw logger: can't remove %s: %s", oldest.name, e)
