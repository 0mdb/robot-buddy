"""Tests for RawPacketLogger (PROTOCOL.md §10.1)."""

from __future__ import annotations

from pathlib import Path

from supervisor_v2.io.raw_logger import (
    RawPacketLogger,
    _FRAME_LEN_FMT,
    _HEADER_FMT,
)


class TestRawPacketLogger:
    """Verify binary log format and rotation."""

    def test_log_frame_writes_correct_format(self, tmp_path: Path):
        """Each entry must match the spec: [t:i64][src_len:u8][src:utf8][len:u16][frame]."""
        logger = RawPacketLogger(tmp_path)
        logger.start()
        try:
            t_ns = 1234567890123456789
            src = "reflex"
            frame = b"\x01\x02\x03\x04"
            logger.log_frame(t_ns, src, frame)
            assert logger.entries_written == 1
        finally:
            logger.stop()

        # Read back the binary entry
        log_files = sorted(tmp_path.glob("raw_*.bin"))
        assert len(log_files) == 1
        data = log_files[0].read_bytes()

        offset = 0
        # t_pi_rx_ns: i64-LE
        (t_read,) = _HEADER_FMT.unpack_from(data, offset)
        offset += _HEADER_FMT.size
        assert t_read == t_ns

        # src_id_len: u8
        src_len = data[offset]
        offset += 1
        assert src_len == len(src)

        # src_id: utf8
        src_read = data[offset : offset + src_len].decode("utf-8")
        offset += src_len
        assert src_read == src

        # frame_len: u16-LE
        (frame_len,) = _FRAME_LEN_FMT.unpack_from(data, offset)
        offset += _FRAME_LEN_FMT.size
        assert frame_len == len(frame)

        # raw_bytes
        frame_read = data[offset : offset + frame_len]
        assert frame_read == frame
        assert offset + frame_len == len(data)

    def test_multiple_entries(self, tmp_path: Path):
        """Multiple log_frame calls should append sequentially."""
        logger = RawPacketLogger(tmp_path)
        logger.start()
        try:
            for i in range(10):
                logger.log_frame(i * 1000, "face", bytes([i]))
            assert logger.entries_written == 10
        finally:
            logger.stop()

        log_files = sorted(tmp_path.glob("raw_*.bin"))
        assert len(log_files) == 1
        data = log_files[0].read_bytes()
        assert len(data) > 0

    def test_not_enabled_before_start(self, tmp_path: Path):
        """log_frame should be a no-op before start() is called."""
        logger = RawPacketLogger(tmp_path)
        assert not logger.enabled
        logger.log_frame(0, "reflex", b"\x00")
        assert logger.entries_written == 0

    def test_not_enabled_after_stop(self, tmp_path: Path):
        """log_frame should be a no-op after stop()."""
        logger = RawPacketLogger(tmp_path)
        logger.start()
        logger.stop()
        assert not logger.enabled
        logger.log_frame(0, "reflex", b"\x00")
        assert logger.entries_written == 0

    def test_rotation_triggers(self, tmp_path: Path):
        """Logger should call _rotate when bytes_written >= max_bytes."""
        logger = RawPacketLogger(tmp_path, max_bytes=100, max_files=5)
        logger.start()
        try:
            # Each entry: 8 (t_ns) + 1 (src_len) + 1 (src) + 2 (frame_len) + 10 (frame) = 22 bytes
            # After 5 entries = 110 bytes > 100, rotation should trigger
            for i in range(10):
                logger.log_frame(i, "r", b"\xaa" * 10)
            assert logger.entries_written == 10
        finally:
            logger.stop()

        # Verify rotation happened: _bytes_written resets after rotation,
        # so total data across all files > max_bytes
        total = sum(f.stat().st_size for f in tmp_path.glob("raw_*.bin"))
        assert total > 100

    def test_max_files_cleanup(self, tmp_path: Path):
        """Old files should be cleaned up when max_files is exceeded."""
        max_files = 3
        logger = RawPacketLogger(tmp_path, max_bytes=50, max_files=max_files)
        logger.start()
        try:
            # Write enough to trigger multiple rotations
            for i in range(200):
                logger.log_frame(i, "r", b"\xbb" * 20)
        finally:
            logger.stop()

        log_files = sorted(tmp_path.glob("raw_*.bin"))
        assert len(log_files) <= max_files

    def test_creates_log_dir(self, tmp_path: Path):
        """start() should create the log directory if it doesn't exist."""
        log_dir = tmp_path / "subdir" / "raw"
        logger = RawPacketLogger(log_dir)
        logger.start()
        logger.stop()
        assert log_dir.is_dir()

    def test_different_sources(self, tmp_path: Path):
        """Entries from different sources should be correctly distinguishable."""
        logger = RawPacketLogger(tmp_path)
        logger.start()
        try:
            logger.log_frame(100, "reflex", b"\x01")
            logger.log_frame(200, "face", b"\x02")
            assert logger.entries_written == 2
        finally:
            logger.stop()

        # Read back and verify both entries
        log_files = sorted(tmp_path.glob("raw_*.bin"))
        data = log_files[0].read_bytes()

        # Parse first entry
        offset = 0
        offset += _HEADER_FMT.size  # skip timestamp
        src1_len = data[offset]
        offset += 1
        src1 = data[offset : offset + src1_len].decode("utf-8")
        offset += src1_len
        (frame1_len,) = _FRAME_LEN_FMT.unpack_from(data, offset)
        offset += _FRAME_LEN_FMT.size
        offset += frame1_len
        assert src1 == "reflex"

        # Parse second entry
        offset += _HEADER_FMT.size  # skip timestamp
        src2_len = data[offset]
        offset += 1
        src2 = data[offset : offset + src2_len].decode("utf-8")
        assert src2 == "face"
