"""Voice ID on the robot: the face label and roster ids sent to the server, the server's
guess kept and (only with conversation.voice_id_use) used to tell who is talking, and the
guess written to conversation history."""

from __future__ import annotations

import json
import time

from supervisor.core.conversation_history import ConversationHistory
from supervisor.messages.envelope import Envelope
from supervisor.messages.types import AI_CONVERSATION_SPEAKER
from supervisor.tests.test_memory_per_person import _loop, _Params, _see


def _guess(member_id, session=None):
    return {
        "turn": {"member_id": member_id, "score": 0.7, "best_id": member_id},
        "session": {"member_id": session or member_id, "score": 0.72},
        "speech_s": 2.1,
        "learned": False,
        "learn_why": "no face label",
    }


def _voice_on(loop):
    loop._param_registry = _Params(**{"conversation.voice_id_use": True})


class TestFaceLabel:
    def test_one_recognised_face_labels_the_turn(self):
        loop = _loop()
        loop._roster_ok = True
        loop.world.faces_held = [
            {"member_id": "kid_a", "id_score": 0.61, "bearing_deg": -4}
        ]
        loop.world.faces_seen_mono_ms = time.monotonic() * 1000.0
        p: dict = {}
        loop._add_voice_labels(p)
        assert p["face_speaker"] == {
            "member_id": "kid_a", "score": 0.61, "faces": 1, "bearing_deg": -4,
        }  # fmt: skip
        assert p["roster_ids"] == ["dad", "kid_a"]

    def test_two_faces_or_unknown_face_no_label(self):
        loop = _loop()
        _see(loop, "kid_a", "dad")
        p: dict = {}
        loop._add_voice_labels(p)
        _see(loop, None)
        loop._add_voice_labels(p)
        assert "face_speaker" not in p

    def test_no_roster_ids_unless_the_roster_was_read(self):
        """An unread or disabled roster must not tell the server to drop every print."""
        loop = _loop()
        p: dict = {}
        loop._add_voice_labels(p)
        assert "roster_ids" not in p


class TestVoiceUse:
    def test_ignored_while_off(self):
        loop = _loop()
        loop._take_voice_guess(_guess("kid_a"))
        assert loop._speaker_member_id() is None

    def test_names_a_child_out_of_frame(self):
        loop = _loop()
        _voice_on(loop)
        loop._take_voice_guess(_guess("kid_a"))
        assert loop._speaker_member_id() == "kid_a"

    def test_session_match_preferred_over_turn(self):
        loop = _loop()
        _voice_on(loop)
        loop._take_voice_guess(_guess(None, session="kid_a"))
        assert loop._speaker_member_id() == "kid_a"

    def test_face_wins_over_voice(self):
        loop = _loop()
        _voice_on(loop)
        _see(loop, "dad")
        loop._take_voice_guess(_guess("kid_a"))
        assert loop._speaker_member_id() == "dad"

    def test_picks_the_talker_among_faces(self):
        loop = _loop()
        _voice_on(loop)
        _see(loop, "kid_a", "dad")
        loop._take_voice_guess(_guess("kid_a"))
        assert loop._speaker_member_id() == "kid_a"

    def test_voice_of_nobody_in_view_among_several(self):
        loop = _loop()
        _voice_on(loop)
        loop.world.household_kinds["kid_b"] = "kid"
        _see(loop, "kid_a", "dad")
        loop._take_voice_guess(_guess("kid_b"))
        assert loop._speaker_member_id() is None

    def test_stale_guess_and_removed_member_ignored(self):
        loop = _loop()
        _voice_on(loop)
        loop._take_voice_guess(_guess("kid_a"))
        loop._voice_guess["mono"] -= 120
        assert loop._speaker_member_id() is None
        loop._take_voice_guess(_guess("gone"))
        assert loop._speaker_member_id() is None


def test_history_records_the_guess_by_name(tmp_path):
    path = tmp_path / "h.jsonl"
    h = ConversationHistory(
        path, lambda: True, lambda: 3, names=lambda: {"kid_a": "Owen"}
    )
    env = Envelope(type=AI_CONVERSATION_SPEAKER, src="ai", seq=1, t_ns=0, payload={
        "session_id": "s1", **_guess("kid_a"), "learned": True})  # fmt: skip
    h.feed(env)
    [entry] = [json.loads(line) for line in path.read_text().splitlines()]
    assert entry["role"] == "voice" and entry["voice"] == "Owen"
    assert entry["conversation"] == "Owen" and entry["learned"] is True
