"""JSONL telemetry recorder with log rotation and disk caps."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TextIO

log = logging.getLogger(__name__)


class Recorder:
    """Records telemetry snapshots to JSONL files with rotation."""

    def __init__(
        self,
        directory: str | Path = "/tmp/robot-buddy-logs",
        record_rate_hz: int = 10,
        max_file_mb: int = 50,
        max_files: int = 3,
        enabled: bool = True,
    ) -> None:
        self._dir = Path(directory)
        self._period_s = 1.0 / record_rate_hz
        self._max_bytes = max_file_mb * 1024 * 1024
        self._max_files = max_files
        self._enabled = enabled

        self._file: TextIO | None = None
        self._file_path: Path | None = None
        self._file_bytes = 0
        self._last_write = 0.0

        if self._enabled:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._open_new_file()

    def record(self, state_dict: dict) -> None:
        """Record a telemetry snapshot if enough time has elapsed."""
        if not self._enabled or not self._file:
            return

        now = time.monotonic()
        if now - self._last_write < self._period_s:
            return

        line = (
            json.dumps(
                {
                    "wall": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    **state_dict,
                }
            )
            + "\n"
        )

        line_bytes = len(line.encode())

        # Rotate if file too large
        if self._file_bytes + line_bytes > self._max_bytes:
            self._rotate()

        try:
            self._file.write(line)
            self._file.flush()
            self._file_bytes += line_bytes
            self._last_write = now
        except OSError as e:
            log.warning("recorder: write error: %s", e)

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    # -- internals -----------------------------------------------------------

    def _open_new_file(self) -> None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._file_path = self._dir / f"telemetry_{ts}.jsonl"
        self._file = open(self._file_path, "w")
        self._file_bytes = 0
        log.info("recorder: opened %s", self._file_path)

    def _rotate(self) -> None:
        self.close()

        # Remove oldest files if we have too many
        files = sorted(self._dir.glob("telemetry_*.jsonl"))
        while len(files) >= self._max_files:
            oldest = files.pop(0)
            try:
                oldest.unlink()
                log.info("recorder: deleted %s", oldest)
            except OSError:
                pass

        self._open_new_file()
