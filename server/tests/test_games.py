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
            assert "wasn't a clear answer" in s  # asked again, not marked
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


# ── Progress records and the learner's step (learning-games.md §2, §2.1) ─────

from app.llm.games import drill  # noqa: E402


def _kid_profile(learner: dict | None) -> dict:
    p = {"mood": "happy", "intensity": 0.5, "turn_id": 2, "valence": 0.2,
         "audience": {"present": [{"kind": "kid", "confidence": 0.9, "age": 7,
                                   "sources": ["face"]}], "speaking": 0}}  # fmt: skip
    if learner is not None:
        p["learner"] = learner
    return p


def test_practice_record_for_the_answered_item() -> None:
    h = ConversationHistory()
    h.update_profile(_kid_profile(None))
    q = rocket.question(h.game_picks.seed, 0, "G2")
    h.add_user("rocket math please")
    assert h.practice_record() is None  # nothing asked yet
    h.add_assistant(f"Go! {q.ask}", notes="Game: rocket_math. Q#0")
    h.add_user(f"it's {q.answer}")
    rec = h.practice_record()
    assert rec is not None
    assert rec["verdict"] == "right" and rec["decided"] == "code"
    assert rec["skill"] == "add_sub_facts" and rec["step"] == "G2" and rec["q"] == 0
    assert rec["key"] == f"{h.game_picks.seed}:rocket_math:0"
    h.add_assistant("Yes!", notes="Game: rocket_math. Q#1")
    h.add_user("um I don't know")
    assert h.practice_record()["verdict"] == "none"  # a miss, counted


def test_goodbye_is_not_a_miss_and_gets_no_question() -> None:
    h = ConversationHistory()
    h.add_user("rocket math")
    h.add_assistant("Go!", notes="Game: rocket_math. Q#2")
    h.add_user("goodbye alexa")
    assert h.practice_record() is None
    # The reply's notes still promise Q#3 (playtest 2026-11-18): no question after goodbye.
    assert h.game_tail_line("Bye bye!", "Game: rocket_math. Q#3") is None


def test_learner_step_pitches_the_game_and_round_keeps_its_grade() -> None:
    h = ConversationHistory()
    h.update_profile(
        _kid_profile({"base": "G2", "ceiling": "G3", "steps": {"add_sub_facts": "G3"}})
    )
    h.add_user("let's play rocket math")
    t = _text(h)
    assert "LEVEL (Grade 3)" in t
    q0 = rocket.question(h.game_picks.seed, 0, "G3")
    assert q0.ask in t
    # The step drops mid-round (or someone else steps up): this round stays at Grade 3.
    h.add_assistant(f"Go! {q0.ask}", notes="Game: rocket_math. Q#0")
    h.update_profile(
        _kid_profile({"base": "G2", "ceiling": "G3", "steps": {"add_sub_facts": "G2"}})
    )
    h.add_user(q0.answer)
    rec = h.practice_record()
    assert rec["step"] == "G3" and rec["verdict"] == "right"
    assert rocket.question(h.game_picks.seed, 1, "G3").ask in _text(h)


def test_confident_skill_may_be_praised() -> None:
    h = ConversationHistory()
    h.update_profile(
        _kid_profile(
            {"base": "G2", "ceiling": "G3", "steps": {}, "confident": ["add_sub_facts"]}
        )  # fmt: skip
    )
    h.add_user("rocket math")
    assert "PROGRESS: " in _text(h)
    h2 = ConversationHistory()
    h2.update_profile(_kid_profile({"base": "G2", "ceiling": "G3", "steps": {}}))
    h2.add_user("rocket math")
    assert "PROGRESS: " not in _text(h2)


def test_ending_words() -> None:
    for said in (
        "goodbye",
        "bye alexa",
        "I want to stop",
        "can we play something else",
    ):
        assert drill.ending(said), said
    for said in ("15", "fifteen", "is it nine"):
        assert not drill.ending(said), said


def test_practice_record_keeps_parsed_answer_not_words() -> None:
    from app.llm.games import drill, rocket

    it = drill.item(rocket.DRILL, 21, 0, "G2")
    rec = drill.practice(
        rocket.DRILL, "add_sub_facts",
        [("Game: rocket_math. Q#0", f"um my brother says it's {it.answer}")], 21, "G2",
    )  # fmt: skip
    assert rec is not None and rec["verdict"] == "right"
    assert rec["answer"] == it.answer and "said" not in rec
    assert "brother" not in str(rec)


def test_naming_a_game_mid_round_is_not_scored() -> None:
    h = ConversationHistory()
    h.add_user("rocket math please")
    h.add_assistant("Five questions to blast-off! What is 2 plus 2?",
                    notes="Game: rocket_math. Q#0")  # fmt: skip
    h.add_user("can we play sound swap instead")
    h.add_assistant("Sure!", notes="Game: sound_swap. Q#0")
    assert h.practice_record() is None


# ── Rocket Math with Owen, 2026-11-18 (real transcript) ──────────────────

from app.llm.games.checker import numbers_in  # noqa: E402


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Ninety. Ninety. Ninety.", 90),  # was 270: repeats were added up
        ("Ten. It's eleven.", 11),  # self-correction: the last number
        ("What is it? Fifteen?", 15),
        ("Is it free?", 3),  # Whisper's "three"
        ("Is that sweet?", 3),
        ("Is it 8 plus 6?", None),  # the sum said back, not an answer
        ("2 or 3", None),
        ("Mix 13", 13),
        ("go for it", None),
        ("three hundred forty seven", 347),
        ("a hundred and five", 105),
    ],
)
def test_number_in_real_answers(said: str, expected: int | None) -> None:
    assert number_in(said, expect=expected) == expected


def test_sound_alike_only_gives_credit() -> None:
    assert number_in("Is it free?", expect=3) == 3
    assert number_in("Is it free?", expect=7) is None  # unclear, asked again
    assert number_in("Is it free?") is None


def test_numbers_in_keeps_repeats_apart() -> None:
    assert numbers_in("ninety ninety") == [90, 90]
    assert numbers_in("forty two") == [42]
    assert numbers_in("twenty twenty") == [20, 20]


def _pairs(*steps: tuple[int, str]) -> list[tuple[str, str]]:
    return [(f"Game: rocket_math. Q#{n}", said) for n, said in steps]


def test_unclear_is_asked_again_once_then_answered() -> None:
    seed, g = 13, "G2"
    s1 = rocket.status(_pairs((0, "is it free-ish maybe")), seed, g)
    assert "Just the number this time" in s1 and "Q#0" in s1
    s2 = rocket.status(_pairs((0, "is it free-ish maybe"), (0, "umm")), seed, g)
    assert "no answer" in s2 and "Q#1" in s2  # second time: give the answer, move on


def test_dispute_rescored_right_and_current_asked_again() -> None:
    seed, g = 17, "G2"
    q0 = rocket.question(seed, 0, g)
    pairs = _pairs((0, "plus four, plus four"), (1, f"I said {q0.answer}"))
    s = rocket.status(pairs, seed, g)
    assert "say sorry for mishearing" in s and "Score 1/1" in s and "Q#1" in s
    rec = drill_mod.practice(rocket.DRILL, "add_sub_facts", pairs, seed, g)
    assert rec is not None and rec["q"] == 0 and rec["verdict"] == "right"


def test_unclear_and_dispute_not_recorded_as_misses() -> None:
    seed, g = 19, "G2"
    rec = drill_mod.practice(
        rocket.DRILL, "add_sub_facts", _pairs((0, "is it 8 plus 6?")), seed, g
    )
    assert rec is None


from app.llm.games import drill as drill_mod  # noqa: E402
