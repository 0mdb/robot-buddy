"""Game cards (app/llm/games, docs/learning-games.md §3)."""

from __future__ import annotations

import pytest

from app.llm import games
from app.llm.conversation import ConversationHistory, build_system_prompt


def test_all_cards_load_with_levels() -> None:
    cs = games.cards()
    assert {
        "guess",
        "number_detective",
        "rocket_math",
        "sound_swap",
        "rhyme_time",
    } <= set(cs)
    for c in cs.values():
        if c.skill:  # learning games carry every grade
            assert set(c.levels) == set(games.GRADES), c.id


def test_menu_in_every_system_prompt_not_the_cards() -> None:
    prompt = build_system_prompt("child")
    assert "Rocket Math" in prompt and "GAME CARD: " not in prompt
    assert "<<GAMES>>" not in prompt


@pytest.mark.parametrize(
    ("said", "notes", "expected"),
    [
        ("can we play rocket math", "", ("rocket_math", True)),
        ("ok 15", "Game: rocket_math. Score 1/1", ("rocket_math", False)),
        ("let's play a rhyming game", "Game: rocket_math", ("rhyme_time", True)),
        ("what rhymes with orange", "", None),  # a question, not a game
        ("i like doing sums at school", "", None),
        ("is it a zebra", "Game: guess. Secret: zebra", ("guess", False)),
        ("hello", "Game: not_a_game", None),
    ],
)
def test_active_game(said: str, notes: str, expected: tuple[str, bool] | None) -> None:
    found = games.active_game(said, notes)
    assert (None if found is None else (found[0].id, found[1])) == expected


def test_grade_for_age() -> None:
    assert [games.grade_for_age(a) for a in (4, 5, 6, 7, 8, 9, None)] == [
        "K", "K", "G1", "G2", "G3", "G3", "G2",
    ]  # fmt: skip


def test_asked_card_starts_only_if_asked() -> None:
    card = games.cards()["sound_swap"]
    assert "start it right away" in card.render("K", asked=True)
    assert "start it right away" not in card.render("K")
    assert "LEVEL (Kindergarten)" in card.render("K")


def _history(audience: dict) -> ConversationHistory:
    h = ConversationHistory()
    h.update_profile({"mood": "happy", "intensity": 0.5, "turn_id": 2, "valence": 0.2,
                      "audience": audience})  # fmt: skip
    return h


def _text(h: ConversationHistory) -> str:
    return "\n".join(str(m["content"]) for m in h.to_ollama_messages())


def test_card_injected_while_playing_at_speaker_grade() -> None:
    five = {"present": [{"kind": "kid", "confidence": 0.9, "age": 5, "sources": ["face"]}],
            "speaking": 0, "household": {"primary_kid_age": 7}}  # fmt: skip
    h = _history(five)
    h.add_user("let's play rocket math")
    t = _text(h)
    assert "GAME CARD: Rocket Math" in t and "LEVEL (Kindergarten)" in t
    h.add_assistant(
        "Blast-off in five! What's 2 + 1?", notes="Game: rocket_math. Score 0/0"
    )
    h.add_user("three")
    t = _text(h)
    assert "GAME CARD: Rocket Math" in t and "start it right away" not in t


def test_no_card_in_plain_chat_and_household_grade_fallback() -> None:
    h = _history({"present": [], "speaking": None, "household": {"primary_kid_age": 7}})
    h.add_user("why is the sky blue")
    assert "GAME CARD: " not in _text(h)
    h.add_user("can we play number detective")
    assert "LEVEL (Grade 2)" in _text(h)


# ── Rocket Math run by code (games/rocket.py) ─────────────────────────────

from app.llm.games import rocket  # noqa: E402
from app.llm.games.checker import check_guess, number_in  # noqa: E402


def test_round_questions_distinct_and_stable() -> None:
    qs = [rocket.question(7, n, "G2").ask for n in range(5)]
    assert len(set(qs)) == 5
    assert qs == [rocket.question(7, n, "G2").ask for n in range(5)]


@pytest.mark.parametrize("grade", games.GRADES)
def test_questions_have_whole_answers(grade: str) -> None:
    for n in range(40):
        q = rocket.question(3, n, grade)
        assert q.answer.isdigit()


def test_status_scores_honestly() -> None:
    seed, g = 11, "G2"
    q0, q1 = rocket.question(seed, 0, g), rocket.question(seed, 1, g)
    start = rocket.status([("", "let's play rocket math")], seed, g)
    assert "Q#0" in start and q0.ask in start
    wrong = rocket.status(
        [("Game: rocket_math. Q#0", str(int(q0.answer) + 2))], seed, g
    )
    assert "WRONG" in wrong and "Score 0/1" in wrong and q1.ask in wrong
    pairs = [("Game: rocket_math. Q#0", str(q0.answer)),
             ("Game: rocket_math. Q#1", "I don't know")]  # fmt: skip
    s = rocket.status(pairs, seed, g)
    assert "no answer" in s and "Score 1/2" in s


def test_status_round_over_after_five() -> None:
    seed, g = 5, "G1"
    pairs = [(f"Game: rocket_math. Q#{n}", str(rocket.question(seed, n, g).answer))
             for n in range(5)]  # fmt: skip
    s = rocket.status(pairs, seed, g)
    assert "BLAST OFF" in s and "5 out of 5" in s
    again = rocket.status(pairs + [("Game: rocket_math. Round over", "yes!")], seed, g)
    assert "Q#5" in again  # next round starts at question 5


def test_teen_ty_mixup_is_unclear_not_wrong() -> None:
    seed, g = 1, "G2"
    for n in range(30):
        q = rocket.question(seed, n, g)
        if q.answer in [str(x) for x in range(13, 20)]:
            s = rocket.status(
                [
                    (
                        f"Game: rocket_math. Q#{n}",
                        str((int(q.answer) - 10) * 10),  # 14 heard as 40
                    )
                ],
                seed,
                g,
            )
            assert "unclear" in s
            return
    pytest.skip("no teen answer in sample")


def test_game_tail_speaks_unasked_question() -> None:
    h = ConversationHistory()
    q = rocket.question(h.game_picks.seed, 3, "G2")
    assert h.game_tail_line("Great job!", "Game: rocket_math. Q#3") == q.ask
    asked = f"Nice! {q.ask}"
    assert h.game_tail_line(asked, "Game: rocket_math. Q#3") is None
    assert h.game_tail_line("Hi!", "Game: guess. Secret: zebra") is None


def test_number_parsing_and_guess_check() -> None:
    assert number_in("forty-two") == 42
    assert number_in("a hundred and five") == 105
    assert number_in("oh I think seven") == 7
    assert number_in("2 or 3") is None
    assert "LOWER" in check_guess("Secret: 247", "is it 300")
    assert "IS the secret" in check_guess("Game: number_detective. Secret: 247", "247")


def test_sound_swap_drill_checks_words() -> None:
    from app.llm.games import drill, sound_swap

    for g in games.GRADES:
        for n in range(15):
            it = drill.item(sound_swap.DRILL, 4, n, g)
            assert it.kind == "word" and it.answer
            assert drill.verdict(it, f"um, {it.answer}!") == "right"
            assert drill.verdict(it, "banana") == "wrong"
            assert drill.verdict(it, "I don't know") == "none"


def test_sound_swap_tail_and_status() -> None:
    from app.llm.games import drill, sound_swap

    h = ConversationHistory()
    it = drill.item(sound_swap.DRILL, h.game_picks.seed, 0, "G2")
    assert h.game_tail_line("Woo, sounds!", "Game: sound_swap. Q#0") == it.ask
    assert h.game_tail_line(f"Ready? {it.ask}", "Game: sound_swap. Q#0") is None
    s = drill.status(sound_swap.DRILL, [("Game: sound_swap. Q#0", it.answer)], 9, "G2")
    assert "Q#1" in s
