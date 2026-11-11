"""Text as it reaches the TTS backends."""

from __future__ import annotations


def test_speakable_strips_emoji_and_keeps_words():
    """TODO "Emoji reach TTS": planner say text carried 🎉 / 🤔 into the speech path."""
    from app.tts.orpheus import speakable

    assert speakable("Yay! You pressed my face! 🎉") == "Yay! You pressed my face!"
    assert (
        speakable("Hmm, things are quiet out here! 🤔")
        == "Hmm, things are quiet out here!"
    )
    assert speakable("👨‍👩‍👧 family ❤️ time ✨") == "family time"
    assert speakable("🎉🎉") == ""
    assert speakable("Café — 3 × 4 = 12, ok?") == "Café — 3 × 4 = 12, ok?"
