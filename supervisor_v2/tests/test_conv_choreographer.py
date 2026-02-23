"""Tests for conversation phase transition choreographer."""

from __future__ import annotations


from supervisor_v2.core.conv_choreographer import (
    TRANS_LT_GAZE_RAMP_MS,
    TRANS_SD_SUPPRESS_MS,
    TRANS_SL_NOD_DELAY_MS,
    TRANS_TS_GAZE_RAMP_DELAY_MS,
    TRANS_TS_GAZE_RAMP_MS,
    ConvTransitionChoreographer,
    TransitionAction,
)
from supervisor_v2.devices.protocol import FaceConvState, FaceGesture, FaceMood

DT_MS = 20.0  # 50 Hz tick


def _advance(
    choreo: ConvTransitionChoreographer, ms: float, dt_ms: float = DT_MS
) -> list[TransitionAction]:
    """Advance choreographer by *ms*, collecting all fired actions."""
    all_actions: list[TransitionAction] = []
    elapsed = 0.0
    while elapsed < ms - 1e-6:
        step = min(dt_ms, ms - elapsed)
        all_actions.extend(choreo.update(step))
        elapsed += step
    return all_actions


# ── Initial state ────────────────────────────────────────────────


class TestInitialState:
    def test_starts_inactive(self):
        choreo = ConvTransitionChoreographer()
        assert not choreo.active

    def test_no_gaze_override_when_inactive(self):
        choreo = ConvTransitionChoreographer()
        assert choreo.get_gaze_override() is None

    def test_not_suppressing_mood(self):
        choreo = ConvTransitionChoreographer()
        assert not choreo.suppress_mood_pipeline

    def test_no_blink(self):
        choreo = ConvTransitionChoreographer()
        assert not choreo.has_blink

    def test_update_returns_empty_when_inactive(self):
        choreo = ConvTransitionChoreographer()
        assert choreo.update(DT_MS) == []


# ── Transitions with no choreography ─────────────────────────────


class TestNoChoreography:
    def test_idle_to_attention_no_actions(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.IDLE, FaceConvState.ATTENTION)
        actions = _advance(choreo, 500.0)
        assert actions == []
        assert not choreo.active

    def test_attention_to_listening_no_actions(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.ATTENTION, FaceConvState.LISTENING)
        actions = _advance(choreo, 500.0)
        assert actions == []

    def test_error_to_listening_no_actions(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.ERROR, FaceConvState.LISTENING)
        assert not choreo.active

    def test_done_to_idle_no_actions(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.DONE, FaceConvState.IDLE)
        assert not choreo.active


# ── LISTENING → THINKING ─────────────────────────────────────────


class TestListeningToThinking:
    def test_produces_gaze_ramp(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        assert choreo.get_gaze_override() is not None

    def test_gaze_ramp_starts_at_center(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        gx, gy = choreo.get_gaze_override()  # type: ignore[misc]
        assert abs(gx) < 0.01
        assert abs(gy) < 0.01

    def test_gaze_ramp_ends_at_thinking_target(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS + 10.0)
        # Ramp is done — should return None (fall through to static override)
        assert choreo.get_gaze_override() is None

    def test_gaze_at_midpoint_is_interpolated(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS / 2.0)
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, gy = gaze
        # Should be between start (0,0) and end (0.5,-0.3)
        assert 0.0 < gx < 0.5
        assert -0.3 < gy < 0.0

    def test_gaze_ramp_uses_ease_out(self):
        """Ease-out means progress is faster at start, slower at end."""
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS / 2.0)
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, _ = gaze
        # At t=0.5, ease-out gives t'=0.75, so gx should be ~0.375
        # With some tolerance for discrete stepping
        assert gx > 0.25  # More than linear midpoint (0.25)

    def test_active_during_ramp(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS / 2.0)
        assert choreo.active

    def test_inactive_after_ramp_completes(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS + 20.0)
        assert not choreo.active

    def test_no_gesture_actions(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        actions = _advance(choreo, TRANS_LT_GAZE_RAMP_MS + 20.0)
        assert actions == []

    def test_no_mood_suppression(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        assert not choreo.suppress_mood_pipeline


# ── THINKING → SPEAKING ──────────────────────────────────────────


class TestThinkingToSpeaking:
    def test_produces_blink_gesture(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        actions = _advance(choreo, 20.0)
        assert len(actions) == 1
        assert actions[0].kind == "gesture"
        assert actions[0].params["gesture_id"] == int(FaceGesture.BLINK)

    def test_blink_fires_immediately(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # First tick fires the blink (delay_ms=0)
        actions = choreo.update(DT_MS)
        blinks = [a for a in actions if a.kind == "gesture"]
        assert len(blinks) == 1

    def test_has_blink_flag(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        assert choreo.has_blink

    def test_produces_gaze_ramp_back_to_center(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # Gaze should start from thinking position
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, gy = gaze
        assert abs(gx - 0.5) < 0.01
        assert abs(gy - (-0.3)) < 0.01

    def test_gaze_ramp_starts_after_delay(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # Before delay: gaze still at thinking position
        _advance(choreo, TRANS_TS_GAZE_RAMP_DELAY_MS / 2.0)
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, _ = gaze
        assert abs(gx - 0.5) < 0.05  # Still near thinking target

    def test_gaze_reaches_center_after_full_duration(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        total = TRANS_TS_GAZE_RAMP_DELAY_MS + TRANS_TS_GAZE_RAMP_MS + 20.0
        _advance(choreo, total)
        # Ramp done — returns None
        assert choreo.get_gaze_override() is None

    def test_blink_duration_in_params(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        actions = _advance(choreo, 20.0)
        assert actions[0].params["duration_ms"] == 180.0

    def test_active_during_sequence(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        _advance(choreo, 100.0)
        assert choreo.active

    def test_inactive_after_all_complete(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        total = TRANS_TS_GAZE_RAMP_DELAY_MS + TRANS_TS_GAZE_RAMP_MS + 20.0
        _advance(choreo, total)
        assert not choreo.active

    def test_no_mood_suppression(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        assert not choreo.suppress_mood_pipeline


# ── SPEAKING → LISTENING (multi-turn) ────────────────────────────


class TestSpeakingToListening:
    def test_produces_nod_gesture(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        actions = _advance(choreo, 200.0)
        nods = [a for a in actions if a.params.get("name") == "nod"]
        assert len(nods) == 1

    def test_nod_delay(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        # Before delay: no actions
        actions = _advance(choreo, TRANS_SL_NOD_DELAY_MS - 10.0)
        assert len(actions) == 0

    def test_nod_fires_after_delay(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        actions = _advance(choreo, TRANS_SL_NOD_DELAY_MS + 10.0)
        assert len(actions) == 1
        assert actions[0].params["gesture_id"] == int(FaceGesture.NOD)

    def test_no_gaze_ramp(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        assert choreo.get_gaze_override() is None

    def test_no_mood_suppression(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        assert not choreo.suppress_mood_pipeline

    def test_inactive_after_nod(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        _advance(choreo, 600.0)
        assert not choreo.active


# ── SPEAKING → DONE ──────────────────────────────────────────────


class TestSpeakingToDone:
    def test_produces_mood_nudge(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        actions = _advance(choreo, 20.0)
        nudges = [a for a in actions if a.kind == "mood_nudge"]
        assert len(nudges) == 1

    def test_mood_nudge_targets_neutral(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        actions = _advance(choreo, 20.0)
        nudge = actions[0]
        assert nudge.params["mood_id"] == int(FaceMood.NEUTRAL)
        assert nudge.params["intensity"] == 0.0

    def test_suppress_mood_pipeline(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        assert choreo.suppress_mood_pipeline

    def test_suppress_ends_after_duration(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        _advance(choreo, TRANS_SD_SUPPRESS_MS + 20.0)
        assert not choreo.suppress_mood_pipeline

    def test_no_gaze_ramp(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        assert choreo.get_gaze_override() is None

    def test_active_during_suppress(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        _advance(choreo, TRANS_SD_SUPPRESS_MS / 2.0)
        assert choreo.active

    def test_inactive_after_suppress(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        _advance(choreo, TRANS_SD_SUPPRESS_MS + 20.0)
        assert not choreo.active


# ── Interrupted transitions ──────────────────────────────────────


class TestInterruptedTransitions:
    def test_new_transition_cancels_active(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, 100.0)  # Mid-ramp
        assert choreo.active
        # New transition replaces
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # Now has blink, not gaze-only
        assert choreo.has_blink

    def test_gaze_ramp_resets_on_new_transition(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, 150.0)  # Halfway through gaze ramp
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # Should start from thinking position, not mid-ramp
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, _ = gaze
        assert abs(gx - 0.5) < 0.05

    def test_suppress_resets_on_new_transition(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.DONE)
        assert choreo.suppress_mood_pipeline
        # New transition with no suppression
        choreo.on_transition(FaceConvState.DONE, FaceConvState.IDLE)
        assert not choreo.suppress_mood_pipeline


# ── Update timing ────────────────────────────────────────────────


class TestUpdateTiming:
    def test_actions_fire_in_order_by_delay(self):
        """THINKING→SPEAKING has blink at t=0. All should fire in order."""
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        actions = _advance(choreo, 500.0)
        # Only one action (blink)
        assert len(actions) == 1
        assert actions[0].kind == "gesture"

    def test_zero_delay_actions_fire_on_first_update(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        actions = choreo.update(DT_MS)
        assert len(actions) == 1

    def test_actions_fire_exactly_once(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # Multiple updates should not re-fire
        a1 = choreo.update(DT_MS)
        a2 = choreo.update(DT_MS)
        a3 = choreo.update(DT_MS)
        assert len(a1) == 1
        assert len(a2) == 0
        assert len(a3) == 0


# ── Gaze ramp math ──────────────────────────────────────────────


class TestGazeRamp:
    def test_ease_out_curve_shape(self):
        """At t=0.5 linear, ease-out should give ~0.75."""
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS * 0.5)
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, gy = gaze
        # ease_out(0.5) = 1 - (0.5)^2 = 0.75
        expected_x = 0.5 * 0.75  # ~0.375
        assert abs(gx - expected_x) < 0.05

    def test_returns_none_when_not_ramping(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.SPEAKING, FaceConvState.LISTENING)
        assert choreo.get_gaze_override() is None

    def test_returns_none_after_completion(self):
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.LISTENING, FaceConvState.THINKING)
        _advance(choreo, TRANS_LT_GAZE_RAMP_MS + 50.0)
        assert choreo.get_gaze_override() is None

    def test_ramp_with_delay_holds_start_before_delay(self):
        """THINKING→SPEAKING gaze ramp has a 50ms delay."""
        choreo = ConvTransitionChoreographer()
        choreo.on_transition(FaceConvState.THINKING, FaceConvState.SPEAKING)
        # Advance less than the delay
        _advance(choreo, TRANS_TS_GAZE_RAMP_DELAY_MS * 0.5)
        gaze = choreo.get_gaze_override()
        assert gaze is not None
        gx, _ = gaze
        assert abs(gx - 0.5) < 0.05  # Still at thinking position
