"""The Guessing Game run by code (games/guess.py), from the 2026-11-18 evening session."""

from __future__ import annotations

from app.llm import games
from app.llm.conversation import ConversationHistory
from app.llm.games import guess

PICKS = {"animal": "otter", "food": "pear", "thing": "kite"}
BUDDY_BUS = "Game: guess. Picker: buddy. Secret: bus"


def test_named_spelled_and_plural() -> None:
    assert guess.named("bus", "Is it a bus?")
    assert guess.named("bus", "B-U-S. Is it B-U-S?")  # Owen spelled it
    assert guess.named("teddy bear", "is it a teddy bear")
    assert guess.named("kite", "kites!")
    assert not guess.named("bus", "Is it a boss?")


def test_boss_for_bus_asks_did_you_say() -> None:
    s = guess.status([(BUDDY_BUS, "Is it a boss?")], PICKS)
    assert "Did you say bus?" in s and "boss" in s
    assert guess.sounds_like("bus", "is it a car") is None


def test_a_claim_is_not_a_win() -> None:
    """ "Oh, I got it." was congratulated with no guess said (secret kite)."""
    s = guess.status(
        [("Game: guess. Picker: buddy. Secret: kite", "Oh, I got it.")], PICKS
    )
    assert "Don't say they won" in s and "Secret: kite" in s


def test_right_guess_wins_and_ends_the_round() -> None:
    s = guess.status([(BUDDY_BUS, "is it a bus?")], PICKS)
    assert "they guessed it" in s and "Round over. Picker: buddy" in s


def test_buddy_never_guesses_its_own_secret() -> None:
    """Clark's round: Buddy guessed its own guitar."""
    s = guess.status([("Game: guess. Picker: buddy. Secret: guitar", "I know.")], PICKS)
    assert "Never guess yourself" in s and "guitar" in s


def test_who_picks_a_new_round() -> None:
    assert "CHILD picks" in guess.status([("", "No, I you guess it, okay?")], PICKS)
    s = guess.status([("", "Okay, now I guess. Is it a thing?")], PICKS)
    assert 'secret is "kite"' in s and "a thing" in s
    # after a round, roles swap unless they say otherwise
    over = "Game: guess. Round over. Picker: buddy"
    assert "CHILD picks" in guess.status([(over, "Again!")], PICKS)
    assert 'secret is "otter"' in guess.status(
        [("Game: guess. Round over. Picker: child", "again")], PICKS
    )


def test_child_picked_buddy_has_no_secret() -> None:
    s = guess.status([("Game: guess. Picker: child", "I'm ready.")], PICKS)
    assert "You have no secret of your own" in s


def test_hint_after_eight_questions() -> None:
    pairs = [(BUDDY_BUS, "is it big?")] * 8
    assert "offer a small hint" in guess.status(pairs, PICKS)
    assert "hint" not in guess.status(pairs[:3], PICKS)


def test_secret_none_is_no_secret() -> None:
    assert guess._state("Game: guess; Turn: alexa; Secret: none") == (None, None, False)


def test_history_injects_the_guess_line() -> None:
    h = ConversationHistory()
    h.add_user("let's play the guessing game")
    h.add_assistant(
        "I've got one! It's a thing.", notes="Game: guess. Picker: buddy. Secret: bus"
    )
    h.add_user("Is it a boss?")
    card = h._game_card()
    assert card is not None and "Did you say bus?" in card
    assert games.cards()["guess"].id == "guess"


def test_yes_to_did_you_say_wins() -> None:
    """Live check: "is it a walf?" -> "Did you say wolf?" -> "yes" didn't end the round."""
    wolf = "Game: guess. Picker: buddy. Secret: wolf"
    pairs = [(wolf, "is it a walf?"), (wolf, "yes")]
    assert "they guessed it" in guess.status(pairs, PICKS)
    # a plain "yes" with no misheard guess before it is not a win
    assert "they guessed it" not in guess.status(
        [(wolf, "is it big?"), (wolf, "yes")], PICKS
    )
