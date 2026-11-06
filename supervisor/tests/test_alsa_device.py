"""Tests for ALSA card-name resolution."""

from __future__ import annotations

from supervisor.devices.alsa_device import parse_cards, resolve_alsa_device

CARDS = """\
 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 2 [Array          ]: USB-Audio - reSpeaker XVF3800 4-Mic Array
                      Seeed Studio reSpeaker XVF3800 4-Mic Array at usb-xhci-hcd.1-1, high speed
 3 [Device         ]: USB-Audio - USB Audio Device
                      C-Media USB Audio Device at usb-xhci-hcd.0-2, full speed
"""


def test_parse_cards():
    cards = parse_cards(CARDS)
    assert [c.index for c in cards] == [0, 2, 3]
    assert cards[1].id == "Array"
    assert "Seeed Studio" in cards[1].description


def test_match_by_description():
    assert resolve_alsa_device("match:respeaker", CARDS) == "plughw:CARD=Array,DEV=0"


def test_match_by_id():
    assert resolve_alsa_device("match:device", CARDS) == "plughw:CARD=Device,DEV=0"


def test_no_match():
    assert resolve_alsa_device("match:nothing", CARDS) is None


def test_plain_spec_passes_through():
    assert resolve_alsa_device("plughw:2,0", CARDS) == "plughw:2,0"
    assert resolve_alsa_device("default") == "default"
