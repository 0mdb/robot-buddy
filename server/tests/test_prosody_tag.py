"""Tests for apply_prosody_tag and the intensity-gated cue map.

Orpheus 3B only renders eight paralinguistic tags (<laugh>, <chuckle>,
<sigh>, <cough>, <sniffle>, <groan>, <yawn>, <gasp>). Anything else
tokenises as sub-word BPE and gets pronounced as literal speech — which
was the root cause of the "happy happy …" leak. These tests lock in:

  * no fake emotion tags are ever emitted,
  * always-applied tags fire at any intensity,
  * high-intensity cues fire only when the threshold is met.
"""

from __future__ import annotations

import pytest

from app.tts.orpheus import (
    EMOTION_HIGH_INTENSITY_CUES,
    EMOTION_TO_PROSODY_TAG,
    apply_prosody_tag,
)

# The full list Orpheus 3B 0.1 actually renders as non-verbal sounds.
_ORPHEUS_SUPPORTED_TAGS = {
    "<laugh>",
    "<chuckle>",
    "<sigh>",
    "<cough>",
    "<sniffle>",
    "<groan>",
    "<yawn>",
    "<gasp>",
}


def test_always_applied_tags_are_all_orpheus_supported() -> None:
    for emotion, tag in EMOTION_TO_PROSODY_TAG.items():
        if tag:
            assert tag in _ORPHEUS_SUPPORTED_TAGS, (
                f"{emotion!r} maps to {tag!r} which Orpheus will pronounce"
            )


def test_high_intensity_cues_are_all_orpheus_supported() -> None:
    for emotion, (tag, _threshold) in EMOTION_HIGH_INTENSITY_CUES.items():
        assert tag in _ORPHEUS_SUPPORTED_TAGS, (
            f"{emotion!r} high-intensity cue {tag!r} is not a real Orpheus tag"
        )


def test_happy_low_intensity_no_tag() -> None:
    # Below the chuckle threshold, no cue — plain text.
    assert apply_prosody_tag("happy", "Hi there!", intensity=0.5) == "Hi there!"


def test_happy_high_intensity_gets_chuckle() -> None:
    out = apply_prosody_tag("happy", "Hi there!", intensity=0.85)
    assert out == "<chuckle> Hi there!"


def test_excited_peak_gets_gasp() -> None:
    out = apply_prosody_tag("excited", "Wow!", intensity=0.9)
    assert out == "<gasp> Wow!"


def test_sad_moderate_intensity_gets_sigh() -> None:
    # sad caps at 0.5 per the system prompt; threshold is 0.4.
    out = apply_prosody_tag("sad", "That's tough.", intensity=0.45)
    assert out == "<sigh> That's tough."


def test_sleepy_always_yawns() -> None:
    # Always-applied tags fire regardless of intensity.
    assert apply_prosody_tag("sleepy", "Mmm", intensity=0.1) == "<yawn> Mmm"
    assert apply_prosody_tag("sleepy", "Mmm", intensity=0.9) == "<yawn> Mmm"


def test_silly_always_laughs() -> None:
    assert apply_prosody_tag("silly", "Haha!", intensity=0.2) == "<laugh> Haha!"


def test_neutral_never_gets_a_tag() -> None:
    assert apply_prosody_tag("neutral", "Hello", intensity=0.9) == "Hello"


def test_curious_never_gets_a_tag() -> None:
    assert apply_prosody_tag("curious", "Ooh?", intensity=0.95) == "Ooh?"


def test_unknown_emotion_passes_through() -> None:
    # Defensive — unknown emotions just return the text unchanged.
    assert apply_prosody_tag("lovestruck", "Hi", intensity=1.0) == "Hi"


@pytest.mark.parametrize(
    "emotion,below,above",
    [
        ("happy", 0.79, 0.80),
        ("excited", 0.79, 0.80),
        ("surprised", 0.49, 0.50),
        ("sad", 0.39, 0.40),
        ("scared", 0.39, 0.40),
        ("angry", 0.29, 0.30),
    ],
)
def test_intensity_threshold_boundary(emotion: str, below: float, above: float) -> None:
    below_out = apply_prosody_tag(emotion, "x", intensity=below)
    above_out = apply_prosody_tag(emotion, "x", intensity=above)
    assert below_out == "x"  # no tag below threshold
    # Exact cue content varies per emotion — just assert something got prepended.
    assert above_out != "x"
    assert above_out.endswith(" x")
