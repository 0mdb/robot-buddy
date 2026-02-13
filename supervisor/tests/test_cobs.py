"""Tests for COBS encode/decode."""

import pytest

from supervisor.io.cobs import decode, encode


def test_empty():
    enc = encode(b"")
    assert enc == b"\x01"
    assert decode(enc) == b""


def test_single_zero():
    enc = encode(b"\x00")
    assert decode(enc) == b"\x00"


def test_single_nonzero():
    enc = encode(b"\x42")
    assert decode(enc) == b"\x42"


def test_no_zeros():
    data = bytes([1, 2, 3, 4, 5])
    assert decode(encode(data)) == data


def test_all_zeros():
    data = b"\x00\x00\x00"
    assert decode(encode(data)) == data


def test_mixed():
    data = b"\x00\x11\x22\x00\x33"
    assert decode(encode(data)) == data


def test_round_trip_various_lengths():
    for length in [0, 1, 2, 10, 50, 254, 255, 300]:
        data = bytes(range(256)) * 2
        data = data[:length]
        result = decode(encode(data))
        assert result == data, f"failed at length {length}"


def test_known_vectors():
    # Standard COBS test vectors
    assert encode(b"\x00") == b"\x01\x01"
    assert encode(b"\x00\x00") == b"\x01\x01\x01"
    assert encode(b"\x11\x22\x00\x33") == b"\x03\x11\x22\x02\x33"
    assert encode(b"\x11\x22\x33\x44") == b"\x05\x11\x22\x33\x44"


def test_decode_bad_zero():
    with pytest.raises(ValueError, match="unexpected zero"):
        decode(b"\x00\x01")  # zero as code byte at start of block


def test_decode_truncated():
    with pytest.raises(ValueError, match="truncated"):
        decode(b"\x05\x01\x02")  # says 4 bytes follow but only 2
