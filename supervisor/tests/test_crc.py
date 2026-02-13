"""Tests for CRC16-CCITT."""

from supervisor.io.crc import crc16


def test_empty():
    assert crc16(b"") == 0xFFFF


def test_single_byte():
    result = crc16(b"\x00")
    assert isinstance(result, int)
    assert 0 <= result <= 0xFFFF


def test_known_string():
    # CRC-CCITT of "123456789" with init=0xFFFF, poly=0x1021
    result = crc16(b"123456789")
    assert result == 0x29B1


def test_consistency():
    data = b"\x10\x00\x64\x00\xf4\x01"  # SET_TWIST example
    c1 = crc16(data)
    c2 = crc16(data)
    assert c1 == c2


def test_different_data_different_crc():
    assert crc16(b"\x01") != crc16(b"\x02")
