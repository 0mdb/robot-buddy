"""Tests for conversation state tracker."""

from __future__ import annotations

from supervisor.core.conv_state import (
    ATTENTION_DURATION_MS,
    DONE_FADE_DURATION_MS,
    ERROR_TOTAL_DURATION_MS,
    ConvStateTracker,
)
from supervisor.devices.protocol import FaceConvState, FaceMood


class TestConvStateTransitions:
    """Test basic state transitions."""

    def test_starts_idle(self):
        t = ConvStateTracker()
        assert t.state == FaceConvState.IDLE
        assert not t.session_active

    def test_set_state_tracks_previous(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        assert t.state == FaceConvState.ATTENTION
        assert t.prev_state == FaceConvState.IDLE

    def test_set_state_resets_timer(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        t.update(200.0)
        assert t.timer_ms == 200.0
        t.set_state(FaceConvState.LISTENING)
        assert t.timer_ms == 0.0

    def test_set_same_state_is_noop(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        t.update(100.0)
        t.set_state(FaceConvState.ATTENTION)
        # Timer should NOT reset since state didn't change
        assert t.timer_ms == 100.0

    def test_full_conversation_flow(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        assert t.session_active
        t.set_state(FaceConvState.LISTENING)
        assert t.session_active
        t.set_state(FaceConvState.THINKING)
        assert t.session_active
        t.set_state(FaceConvState.SPEAKING)
        assert t.session_active
        t.set_state(FaceConvState.DONE)
        assert t.session_active  # Still active during DONE fade
        # DONE auto-transitions to IDLE after 500ms
        t.update(DONE_FADE_DURATION_MS + 1)
        assert t.state == FaceConvState.IDLE
        assert not t.session_active

    def test_ptt_flow(self):
        t = ConvStateTracker()
        t.ptt_held = True
        t.set_state(FaceConvState.ATTENTION)
        # ATTENTION auto-transitions to PTT when ptt_held
        t.update(ATTENTION_DURATION_MS + 1)
        assert t.state == FaceConvState.PTT


class TestAutoTransitions:
    """Test timed auto-transitions."""

    def test_attention_to_listening(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        t.update(ATTENTION_DURATION_MS - 1)
        assert t.state == FaceConvState.ATTENTION
        t.update(2.0)
        assert t.state == FaceConvState.LISTENING

    def test_attention_to_ptt_when_held(self):
        t = ConvStateTracker()
        t.ptt_held = True
        t.set_state(FaceConvState.ATTENTION)
        t.update(ATTENTION_DURATION_MS + 1)
        assert t.state == FaceConvState.PTT

    def test_error_to_listening_when_session(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)  # session_active = True
        t.set_state(FaceConvState.ERROR)
        t.update(ERROR_TOTAL_DURATION_MS + 1)
        assert t.state == FaceConvState.LISTENING

    def test_error_to_idle_when_no_session(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ERROR)
        t.update(ERROR_TOTAL_DURATION_MS + 1)
        assert t.state == FaceConvState.IDLE

    def test_done_to_idle(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.DONE)
        t.update(DONE_FADE_DURATION_MS - 1)
        assert t.state == FaceConvState.DONE
        t.update(2.0)
        assert t.state == FaceConvState.IDLE

    def test_listening_does_not_auto_transition(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        t.update(30000.0)  # 30 seconds
        assert t.state == FaceConvState.LISTENING

    def test_speaking_does_not_auto_transition(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.SPEAKING)
        t.update(60000.0)  # 60 seconds
        assert t.state == FaceConvState.SPEAKING


class TestConsumeChanged:
    """Test state change detection."""

    def test_consume_on_transition(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        assert t.consume_changed()
        assert not t.consume_changed()  # Only fires once

    def test_no_change_without_transition(self):
        t = ConvStateTracker()
        assert not t.consume_changed()

    def test_auto_transition_triggers_changed(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.DONE)
        t.consume_changed()
        t.update(DONE_FADE_DURATION_MS + 1)
        assert t.consume_changed()  # DONE→IDLE auto-transition


class TestGazeOverrides:
    """Test per-state gaze overrides."""

    def test_idle_no_gaze(self):
        t = ConvStateTracker()
        assert t.get_gaze_override() is None
        assert t.get_gaze_for_send() is None

    def test_listening_center_gaze(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        gaze = t.get_gaze_override()
        assert gaze == (0.0, 0.0)

    def test_thinking_aversion_gaze(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.THINKING)
        gaze = t.get_gaze_override()
        assert gaze is not None
        assert gaze[0] == 0.5  # Right
        assert gaze[1] == -0.3  # Up

    def test_error_micro_aversion(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ERROR)
        # During first 200ms: leftward aversion
        gaze = t.get_gaze_override()
        assert gaze is not None
        assert gaze[0] < 0  # Leftward
        # After 200ms: no override
        t.update(201.0)
        gaze = t.get_gaze_override()
        assert gaze is None

    def test_gaze_for_send_passes_through(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.THINKING)
        gaze_send = t.get_gaze_for_send()
        assert gaze_send is not None
        # Now passes through normalized values directly (send_state uses * 127)
        assert abs(gaze_send[0] - 0.5) < 0.01
        assert abs(gaze_send[1] - (-0.3)) < 0.01


class TestFlagOverrides:
    """Test per-state flag overrides."""

    def test_idle_has_all_flags(self):
        t = ConvStateTracker()
        flags = t.get_flags()
        assert flags != -1
        assert flags & 0x01  # IDLE_WANDER on

    def test_listening_no_wander(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        flags = t.get_flags()
        assert not (flags & 0x01)  # IDLE_WANDER off
        assert flags & 0x02  # AUTOBLINK on
        assert flags & 0x20  # SPARKLE on

    def test_thinking_no_wander_no_sparkle(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.THINKING)
        flags = t.get_flags()
        assert not (flags & 0x01)  # IDLE_WANDER off
        assert not (flags & 0x20)  # SPARKLE off
        assert flags & 0x02  # AUTOBLINK on

    def test_error_no_change(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ERROR)
        assert t.get_flags() == -1

    def test_done_restores_idle_flags(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.DONE)
        flags = t.get_flags()
        t2 = ConvStateTracker()
        assert flags == t2.get_flags()  # Same as IDLE


class TestMoodHints:
    """Test per-state mood hints."""

    def test_idle_no_hint(self):
        t = ConvStateTracker()
        assert t.get_mood_hint() is None

    def test_listening_neutral_hint(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        hint = t.get_mood_hint()
        assert hint is not None
        mood_id, intensity = hint
        assert mood_id == int(FaceMood.NEUTRAL)
        assert intensity == 0.3

    def test_thinking_hint(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.THINKING)
        hint = t.get_mood_hint()
        assert hint is not None
        mood_id, intensity = hint
        assert mood_id == int(FaceMood.THINKING)
        assert intensity == 0.5

    def test_speaking_no_hint(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.SPEAKING)
        assert t.get_mood_hint() is None


class TestBackchannel:
    """Test backchannel NODs during LISTENING."""

    def test_nod_fires_during_listening(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        # Advance past the first nod interval (3-5 seconds)
        t.update(5001.0)
        assert t.consume_nod()

    def test_nod_consumes_once(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        t.update(5001.0)
        t.consume_nod()
        assert not t.consume_nod()

    def test_nod_does_not_fire_outside_listening(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.THINKING)
        t.update(10000.0)
        assert not t.consume_nod()

    def test_interest_scale_ramps(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        # Before onset: scale = 1.0
        t.update(5000.0)
        assert t.interest_scale == 1.0
        # After onset (10s): scale should be > 1.0
        t.update(6000.0)  # total = 11s
        assert t.interest_scale > 1.0
        assert t.interest_scale <= 1.05

    def test_interest_resets_on_state_change(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.LISTENING)
        t.update(15000.0)
        assert t.interest_scale > 1.0
        t.set_state(FaceConvState.THINKING)
        assert t.interest_scale == 1.0


class TestSessionLifecycle:
    """Test session_active tracking."""

    def test_session_starts_on_attention(self):
        t = ConvStateTracker()
        assert not t.session_active
        t.set_state(FaceConvState.ATTENTION)
        assert t.session_active

    def test_session_persists_through_states(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        for s in [
            FaceConvState.LISTENING,
            FaceConvState.THINKING,
            FaceConvState.SPEAKING,
        ]:
            t.set_state(s)
            assert t.session_active

    def test_session_ends_on_idle(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        t.set_state(FaceConvState.IDLE)
        assert not t.session_active

    def test_done_then_idle_ends_session(self):
        t = ConvStateTracker()
        t.set_state(FaceConvState.ATTENTION)
        t.set_state(FaceConvState.DONE)
        assert t.session_active  # Still active during fade
        t.update(DONE_FADE_DURATION_MS + 1)
        assert t.state == FaceConvState.IDLE
        assert not t.session_active
