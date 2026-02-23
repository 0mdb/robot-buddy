"""Tests for mood transition sequencer."""

from __future__ import annotations

from supervisor.core.mood_sequencer import (
    SEQ_ANTICIPATION_S,
    SEQ_MIN_HOLD_S,
    SEQ_RAMP_DOWN_S,
    SEQ_RAMP_UP_S,
    MoodSequencer,
    SeqPhase,
)
from supervisor.devices.protocol import FaceMood

NEUTRAL = int(FaceMood.NEUTRAL)
HAPPY = int(FaceMood.HAPPY)
SAD = int(FaceMood.SAD)
EXCITED = int(FaceMood.EXCITED)

DT = 0.020  # 50 Hz tick


def _advance(seq: MoodSequencer, seconds: float, dt: float = DT) -> None:
    """Advance sequencer by *seconds* in *dt*-sized steps."""
    elapsed = 0.0
    while elapsed < seconds - 1e-9:
        step = min(dt, seconds - elapsed)
        seq.update(step)
        elapsed += step


def _run_full_transition(seq: MoodSequencer) -> None:
    """Advance through a complete transition until IDLE."""
    # Run enough time for ANTICIPATION + RAMP_DOWN + SWITCH + RAMP_UP + margin
    total = SEQ_ANTICIPATION_S + SEQ_RAMP_DOWN_S + SEQ_RAMP_UP_S + 0.100
    _advance(seq, total)
    assert seq.phase == SeqPhase.IDLE


# ── Initial state ────────────────────────────────────────────────


class TestInitialState:
    def test_starts_idle(self):
        seq = MoodSequencer()
        assert seq.phase == SeqPhase.IDLE
        assert seq.mood_id == NEUTRAL
        assert seq.intensity == 1.0

    def test_not_transitioning(self):
        seq = MoodSequencer()
        assert not seq.transitioning


# ── Request behaviour ────────────────────────────────────────────


class TestRequestMood:
    def test_same_mood_same_intensity_is_noop(self):
        seq = MoodSequencer()
        seq.request_mood(NEUTRAL, 1.0)
        assert seq.phase == SeqPhase.IDLE

    def test_different_mood_starts_anticipation(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        assert seq.phase == SeqPhase.ANTICIPATION
        assert seq.transitioning

    def test_same_mood_different_intensity_skips_choreography(self):
        seq = MoodSequencer()
        seq.request_mood(NEUTRAL, 0.5)
        # Should NOT start a transition — just update target
        assert seq.phase == SeqPhase.IDLE
        assert seq.target_intensity == 0.5


# ── Full transition lifecycle ────────────────────────────────────


class TestFullTransition:
    def test_phases_in_order(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)

        phases_seen = [seq.phase]

        # ANTICIPATION
        _advance(seq, SEQ_ANTICIPATION_S + DT)
        phases_seen.append(seq.phase)

        # RAMP_DOWN
        _advance(seq, SEQ_RAMP_DOWN_S + DT)
        phases_seen.append(seq.phase)

        # SWITCH is instant — processes in one tick and becomes RAMP_UP
        seq.update(DT)
        phases_seen.append(seq.phase)

        # RAMP_UP
        _advance(seq, SEQ_RAMP_UP_S + DT)
        phases_seen.append(seq.phase)

        assert phases_seen == [
            SeqPhase.ANTICIPATION,
            SeqPhase.RAMP_DOWN,
            SeqPhase.RAMP_UP,  # SWITCH is instant, advances to RAMP_UP
            SeqPhase.RAMP_UP,
            SeqPhase.IDLE,
        ]

    def test_mood_changes_at_switch(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        # Run through ANTICIPATION + RAMP_DOWN
        _advance(seq, SEQ_ANTICIPATION_S + SEQ_RAMP_DOWN_S + DT)
        # SWITCH tick
        seq.update(DT)
        assert seq.mood_id == HAPPY

    def test_intensity_zero_at_switch(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _advance(seq, SEQ_ANTICIPATION_S + SEQ_RAMP_DOWN_S + DT)
        # At SWITCH entry, intensity should be near zero
        assert seq.intensity < 0.05

    def test_intensity_reaches_target_after_ramp_up(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        assert seq.mood_id == HAPPY
        assert abs(seq.intensity - 0.8) < 0.01

    def test_hold_timer_resets_after_transition(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        # hold_timer resets at end of RAMP_UP, then accumulates during margin ticks
        assert seq.hold_timer < 0.15

    def test_total_transition_time(self):
        """Full transition takes ~450ms (ANTICIPATION+RAMP_DOWN+1tick+RAMP_UP)."""
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        total_ticks = 0
        while seq.phase != SeqPhase.IDLE:
            seq.update(DT)
            total_ticks += 1
            if total_ticks > 100:  # Safety: 2s max
                break
        total_s = total_ticks * DT
        assert 0.400 < total_s < 0.600


# ── Blink ────────────────────────────────────────────────────────


class TestBlink:
    def test_blink_fires_on_first_anticipation_frame(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        seq.update(DT)
        assert seq.consume_blink()

    def test_blink_consumes_once(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        seq.update(DT)
        seq.consume_blink()
        assert not seq.consume_blink()

    def test_no_blink_during_idle(self):
        seq = MoodSequencer()
        seq.update(DT)
        assert not seq.consume_blink()


# ── Ramp down ────────────────────────────────────────────────────


class TestRampDown:
    def test_intensity_decreases_during_ramp_down(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _advance(seq, SEQ_ANTICIPATION_S + DT)  # Enter RAMP_DOWN
        assert seq.phase == SeqPhase.RAMP_DOWN

        initial = seq.intensity
        seq.update(DT)
        assert seq.intensity < initial

    def test_intensity_near_zero_at_end_of_ramp_down(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _advance(seq, SEQ_ANTICIPATION_S + SEQ_RAMP_DOWN_S)
        assert seq.intensity < 0.05


# ── Ramp up ──────────────────────────────────────────────────────


class TestRampUp:
    def test_intensity_increases_during_ramp_up(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        # Run to RAMP_UP
        _advance(seq, SEQ_ANTICIPATION_S + SEQ_RAMP_DOWN_S + DT)
        seq.update(DT)  # SWITCH
        assert seq.phase == SeqPhase.RAMP_UP

        prev = seq.intensity
        seq.update(DT)
        assert seq.intensity > prev

    def test_ramp_up_completes_at_target(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.6)
        _run_full_transition(seq)
        assert abs(seq.intensity - 0.6) < 0.01


# ── Queuing ──────────────────────────────────────────────────────


class TestQueuing:
    def test_mid_transition_queues_mood(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        seq.update(DT)  # In ANTICIPATION
        seq.request_mood(SAD, 0.5)
        # Should be queued, not replacing current transition
        assert seq.target_mood_id == HAPPY

    def test_queued_mood_processed_after_transition(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        seq.update(DT)
        seq.request_mood(SAD, 0.5)
        # Run through both transitions (HAPPY then queued SAD)
        transition_time = SEQ_ANTICIPATION_S + SEQ_RAMP_DOWN_S + SEQ_RAMP_UP_S
        _advance(seq, transition_time * 2 + 0.200)
        assert seq.phase == SeqPhase.IDLE
        assert seq.mood_id == SAD
        assert abs(seq.intensity - 0.5) < 0.01

    def test_hold_timer_blocks_fast_transitions(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        # Immediately request another mood (hold_timer ≈ 0)
        seq.request_mood(SAD, 0.5)
        # Should be queued due to hold timer
        assert seq.phase == SeqPhase.IDLE
        assert seq._queued_mood_id == SAD

    def test_queued_mood_processed_after_hold_timer(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        seq.request_mood(SAD, 0.5)  # Queued (hold timer too low)
        # Advance past hold timer
        _advance(seq, SEQ_MIN_HOLD_S + DT)
        # Queued mood should have started processing
        assert seq._queued_mood_id is None
        # Should be either transitioning or have the target set
        assert seq.target_mood_id == SAD


# ── Idle intensity ramp ──────────────────────────────────────────


class TestIdleIntensityRamp:
    def test_same_mood_intensity_ramps_smoothly(self):
        seq = MoodSequencer()
        assert seq.intensity == 1.0
        seq.request_mood(NEUTRAL, 0.3)
        # Should be IDLE — no choreography
        assert seq.phase == SeqPhase.IDLE

        # Step a few ticks
        for _ in range(5):
            seq.update(DT)

        # Should be moving toward 0.3
        assert seq.intensity < 1.0
        assert seq.intensity > 0.3  # Not there yet after 5 ticks

    def test_changed_fires_during_ramp(self):
        seq = MoodSequencer()
        seq.request_mood(NEUTRAL, 0.3)
        seq.update(DT)
        assert seq.consume_changed()

    def test_changed_not_fired_in_steady_state(self):
        seq = MoodSequencer()
        seq.update(DT)
        assert not seq.consume_changed()


# ── Transitioning property ───────────────────────────────────────


class TestTransitioning:
    def test_true_during_anticipation(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        assert seq.transitioning

    def test_true_during_ramp_down(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _advance(seq, SEQ_ANTICIPATION_S + DT)
        assert seq.phase == SeqPhase.RAMP_DOWN
        assert seq.transitioning

    def test_false_after_transition(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        assert not seq.transitioning


# ── Consume changed ──────────────────────────────────────────────


class TestConsumeChanged:
    def test_fires_at_ramp_up_end(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        assert seq.consume_changed()

    def test_consumes_once(self):
        seq = MoodSequencer()
        seq.request_mood(HAPPY, 0.8)
        _run_full_transition(seq)
        seq.consume_changed()
        assert not seq.consume_changed()
