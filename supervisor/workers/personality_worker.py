"""PersonalityWorker — process-isolated affect engine (PE spec S2 §10).

Maintains a continuous affect vector, applies Layer 0 deterministic
impulse rules, projects to discrete moods, enforces guardrails, and
emits personality snapshots consumed by the tick loop.

Layer 0 operates with zero server dependency.  The robot has emotional
life (boot curiosity, idle sleepiness, conversation warmth) even when
the LLM is offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from supervisor.config import GuardrailConfig
from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    PERSONALITY_CMD_OVERRIDE_AFFECT,
    PERSONALITY_CMD_SET_GUARDRAIL,
    PERSONALITY_CONFIG_INIT,
    PERSONALITY_EVENT_AI_EMOTION,
    PERSONALITY_EVENT_BUTTON_PRESS,
    PERSONALITY_EVENT_CONV_ENDED,
    PERSONALITY_EVENT_CONV_STARTED,
    PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
    PERSONALITY_EVENT_SPEECH_ACTIVITY,
    PERSONALITY_EVENT_SYSTEM_STATE,
    PERSONALITY_STATE_SNAPSHOT,
)
from supervisor.personality.affect import (
    EMOTION_VA_TARGETS,
    AffectVector,
    Impulse,
    PersonalitySnapshot,
    TraitParameters,
    compute_trait_parameters,
    enforce_context_gate,
    project_mood,
    update_affect,
)
from supervisor.workers.base import BaseWorker, worker_main

log = logging.getLogger(__name__)

# ── Duration Caps (spec §9.1) ───────────────────────────────────────
# mood_name → max continuous seconds before auto-recovery impulse.
DURATION_CAPS: dict[str, float] = {
    "sad": 4.0,
    "scared": 2.0,
    "angry": 2.0,
    "surprised": 3.0,
}

# ── Intensity Caps (spec §9.1) ─────────────────────────────────────
# Per-mood maximum intensity enforced before snapshot emission.
INTENSITY_CAPS: dict[str, float] = {
    "sad": 0.70,
    "scared": 0.60,
    "angry": 0.50,
    "surprised": 0.80,
}

# ── Idle State Thresholds ───────────────────────────────────────────
IDLE_DROWSY_S: float = 300.0  # 5 min
IDLE_ASLEEP_S: float = 900.0  # 15 min

# ── Post-Conversation Idle Suppression ──────────────────────────────
IDLE_SUPPRESS_AFTER_CONV_S: float = 120.0  # 2 min

# ── Session Cooldown (RS-7: 2-min post-conv suppression) ───────────
SESSION_COOLDOWN_S: float = 120.0

# ── Daily Timer Persistence ─────────────────────────────────────────
_DAILY_PERSIST_INTERVAL_S: float = 60.0  # flush to disk every 60s


@dataclass(slots=True)
class _DailyState:
    """Persistent daily usage state (survives reboots)."""

    date: str = ""  # ISO date YYYY-MM-DD when this counter applies
    total_s: float = 0.0


class PersonalityWorker(BaseWorker):
    """Affect engine implementing Layer 0 deterministic personality rules."""

    domain = "personality"

    def __init__(self) -> None:
        super().__init__()

        # Trait parameters (set by config.init)
        self._trait: TraitParameters | None = None

        # Guardrail configuration (overridden by config.init)
        self._guardrails = GuardrailConfig()

        # Memory config (stored but not yet consumed by L1)
        self._memory_path: str = "./data/personality_memory.json"
        self._memory_consent: bool = False

        # Affect state
        self._affect = AffectVector()
        self._current_mood: str = "neutral"
        self._current_intensity: float = 0.0
        self._pending_impulses: list[Impulse] = []

        # Conversation tracking
        self._conversation_active: bool = False

        # Timers
        self._idle_timer_s: float = 0.0
        self._conv_ended_ago_s: float = float("inf")
        self._negative_mood_timer_s: float = 0.0
        self._negative_mood_name: str = ""
        self._last_tick_ts: float = 0.0

        # Session time tracking (RS-1)
        self._session_time_s: float = 0.0
        self._session_limit_reached: bool = False

        # Daily time tracking (RS-2)
        self._daily_state = _DailyState()
        self._daily_persist_path: Path | None = None
        self._daily_last_persist_ts: float = 0.0
        self._daily_limit_notified: bool = False

        # Cooldowns: rule_id → monotonic timestamp of last fire
        self._cooldowns: dict[str, float] = {}

        # Lifecycle
        self._configured = asyncio.Event()
        self._boot_fired: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop: wait for config, fire boot impulse, tick at 1 Hz."""
        log.info("waiting for config.init")
        try:
            await asyncio.wait_for(self._configured.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.error("config.init not received within 10s, using defaults")
            self._trait = compute_trait_parameters(0.40, 0.50, 0.30, 0.35, 0.75)

        assert self._trait is not None
        self._affect.valence = self._trait.baseline_valence
        self._affect.arousal = self._trait.baseline_arousal
        self._last_tick_ts = time.monotonic()

        # Load daily timer persistence
        self._load_daily_state()

        # L0-01: Boot impulse (once)
        if not self._boot_fired:
            self._boot_fired = True
            self._pending_impulses.append(Impulse(0.35, 0.40, 0.50, "system_event"))
            log.info("L0-01 boot impulse queued")

        # 1 Hz tick loop
        while self.running:
            self._tick_1hz()
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=1.0)
                # Persist daily state on shutdown
                self._persist_daily_state()
                return  # shutdown signalled
            except asyncio.TimeoutError:
                pass  # 1s elapsed — run next tick

    async def on_message(self, envelope: Envelope) -> None:
        """Dispatch inbound messages from core."""
        t = envelope.type
        p = envelope.payload

        if t == PERSONALITY_CONFIG_INIT:
            self._handle_config(p)
        elif t == PERSONALITY_EVENT_AI_EMOTION:
            self._handle_ai_emotion(p)
        elif t == PERSONALITY_EVENT_CONV_STARTED:
            self._handle_conv_started(p)
        elif t == PERSONALITY_EVENT_CONV_ENDED:
            self._handle_conv_ended(p)
        elif t == PERSONALITY_EVENT_SYSTEM_STATE:
            self._handle_system_event(p)
        elif t == PERSONALITY_EVENT_SPEECH_ACTIVITY:
            self._handle_speech_activity(p)
        elif t == PERSONALITY_EVENT_BUTTON_PRESS:
            self._handle_button_press(p)
        elif t == PERSONALITY_CMD_OVERRIDE_AFFECT:
            self._handle_override(p)
        elif t == PERSONALITY_CMD_SET_GUARDRAIL:
            self._handle_set_guardrail(p)
        else:
            log.debug("unhandled message: %s", t)

    def health_payload(self) -> dict:
        return {
            "mood": self._current_mood,
            "intensity": round(self._current_intensity, 3),
            "valence": round(self._affect.valence, 4),
            "arousal": round(self._affect.arousal, 4),
            "layer": 0,
            "conversation_active": self._conversation_active,
            "idle_state": self._idle_state(),
            "idle_timer_s": round(self._idle_timer_s, 1),
            "session_time_s": round(self._session_time_s, 1),
            "daily_time_s": round(self._daily_state.total_s, 1),
            "session_limit_s": self._guardrails.session_time_limit_s,
            "daily_limit_s": self._guardrails.daily_time_limit_s,
            "session_limit_reached": self._session_limit_reached,
            "daily_limit_reached": self._daily_limit_reached,
            "configured": self._trait is not None,
        }

    # ── Core Tick (1 Hz + event-triggered fast path) ────────────────

    def _tick_1hz(self) -> None:
        """Full tick: idle rules → affect update → project → guardrails → emit."""
        now = time.monotonic()
        dt = now - self._last_tick_ts
        self._last_tick_ts = now

        # Advance timers
        self._idle_timer_s += dt
        if self._conv_ended_ago_s < float("inf"):
            self._conv_ended_ago_s += dt

        # Session / daily time tracking
        if self._conversation_active:
            self._session_time_s += dt
            self._daily_state.total_s += dt

            # RS-1: session time limit
            if (
                self._guardrails.session_time_limit_s > 0
                and self._session_time_s >= self._guardrails.session_time_limit_s
                and not self._session_limit_reached
            ):
                self._session_limit_reached = True
                self._emit_guardrail_triggered(
                    "session_time_limit",
                    {
                        "elapsed_s": round(self._session_time_s, 1),
                        "limit_s": self._guardrails.session_time_limit_s,
                    },
                )
                log.info(
                    "RS-1 session time limit reached: %.0fs",
                    self._session_time_s,
                )

            # RS-2: daily time limit
            if (
                self._guardrails.daily_time_limit_s > 0
                and self._daily_state.total_s >= self._guardrails.daily_time_limit_s
                and not self._daily_limit_notified
            ):
                self._daily_limit_notified = True
                self._emit_guardrail_triggered(
                    "daily_time_limit",
                    {
                        "elapsed_s": round(self._daily_state.total_s, 1),
                        "limit_s": self._guardrails.daily_time_limit_s,
                    },
                )
                log.info(
                    "RS-2 daily time limit reached: %.0fs",
                    self._daily_state.total_s,
                )

        # Periodic daily state persistence
        if now - self._daily_last_persist_ts > _DAILY_PERSIST_INTERVAL_S:
            self._daily_last_persist_ts = now
            self._persist_daily_state()

        # Evaluate idle rules (only at 1 Hz, not on fast path)
        self._evaluate_idle_rules()

        # Process and emit
        self._process_and_emit(dt)

    def _process_and_emit(self, dt: float) -> None:
        """Affect update → project mood → guardrails → emit snapshot.

        Called from both 1 Hz tick and event-triggered fast path.
        """
        if self._trait is None:
            return

        # Update affect vector (decay + impulses + noise + clamp)
        update_affect(self._affect, self._trait, self._pending_impulses, dt)

        # Project to discrete mood
        self._current_mood, self._current_intensity = project_mood(
            self._affect, self._current_mood
        )

        # Context gate: block negative moods outside conversation
        if self._guardrails.context_gate:
            gated = enforce_context_gate(self._current_mood, self._conversation_active)
            if gated != self._current_mood:
                # Mood was gated — recalculate intensity for neutral
                self._current_mood = gated
                _, self._current_intensity = project_mood(
                    self._affect, self._current_mood
                )

        # Duration caps: auto-recovery for sustained negative/surprised moods
        if self._guardrails.negative_duration_caps:
            self._enforce_duration_caps(dt)

        # Intensity caps: PE-side enforcement (spec §9.1)
        if self._guardrails.negative_intensity_caps:
            cap = INTENSITY_CAPS.get(self._current_mood)
            if cap is not None:
                self._current_intensity = min(self._current_intensity, cap)

        # Emit snapshot
        self._emit_snapshot()

    def _emit_snapshot(self) -> None:
        """Send personality.state.snapshot to core."""
        snap = PersonalitySnapshot(
            mood=self._current_mood,
            intensity=self._current_intensity,
            valence=self._affect.valence,
            arousal=self._affect.arousal,
            layer=0,
            conversation_active=self._conversation_active,
            idle_state=self._idle_state(),
            ts=time.monotonic(),
        )
        self.send(
            PERSONALITY_STATE_SNAPSHOT,
            {
                "mood": snap.mood,
                "intensity": round(snap.intensity, 3),
                "valence": round(snap.valence, 4),
                "arousal": round(snap.arousal, 4),
                "layer": snap.layer,
                "conversation_active": snap.conversation_active,
                "idle_state": snap.idle_state,
                "session_time_s": round(self._session_time_s, 1),
                "daily_time_s": round(self._daily_state.total_s, 1),
                "session_limit_reached": self._session_limit_reached,
                "daily_limit_reached": self._daily_limit_reached,
            },
        )

    # ── Guardrail Events ──────────────────────────────────────────

    def _emit_guardrail_triggered(self, rule: str, details: dict) -> None:
        """Emit personality.event.guardrail_triggered for telemetry/dashboard."""
        self.send(
            PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
            {"rule": rule, **details},
        )

    # ── Idle Rules ──────────────────────────────────────────────────

    def _evaluate_idle_rules(self) -> None:
        """Evaluate timer-based idle impulse rules (spec §5.1 L0-11, L0-12)."""
        if self._conversation_active:
            return
        # Suppress idle rules briefly after conversation ends
        if self._conv_ended_ago_s < IDLE_SUPPRESS_AFTER_CONV_S:
            return

        # L0-11: Medium idle (5+ min)
        if self._idle_timer_s > IDLE_DROWSY_S:
            if self._check_cooldown("L0-11", 600.0):
                self._pending_impulses.append(Impulse(0.00, -0.15, 0.30, "idle_rule"))
                log.debug("L0-11 medium idle impulse")

        # L0-12: Long idle (15+ min)
        if self._idle_timer_s > IDLE_ASLEEP_S:
            if self._check_cooldown("L0-12", 1800.0):
                self._pending_impulses.append(Impulse(0.00, -0.30, 0.40, "idle_rule"))
                log.debug("L0-12 long idle impulse")

    def _idle_state(self) -> str:
        """Classify idle state from timer."""
        if self._idle_timer_s >= IDLE_ASLEEP_S:
            return "asleep"
        if self._idle_timer_s >= IDLE_DROWSY_S:
            return "drowsy"
        return "awake"

    # ── Duration Caps (spec §9.1) ───────────────────────────────────

    def _enforce_duration_caps(self, dt: float) -> None:
        """Track consecutive time in capped moods, inject recovery when exceeded."""
        cap = DURATION_CAPS.get(self._current_mood)
        if cap is not None:
            if self._negative_mood_name == self._current_mood:
                self._negative_mood_timer_s += dt
            else:
                self._negative_mood_name = self._current_mood
                self._negative_mood_timer_s = 0.0

            if self._negative_mood_timer_s > cap:
                # Inject recovery impulse toward baseline
                if self._trait is not None:
                    self._pending_impulses.append(
                        Impulse(
                            self._trait.baseline_valence,
                            self._trait.baseline_arousal,
                            0.40,
                            "system_event",
                        )
                    )
                    log.info(
                        "duration cap: %s exceeded %.1fs, recovery impulse",
                        self._current_mood,
                        cap,
                    )
                self._negative_mood_timer_s = 0.0
                self._negative_mood_name = ""
        else:
            # Not a capped mood — reset tracker
            self._negative_mood_timer_s = 0.0
            self._negative_mood_name = ""

    # ── Cooldown Tracking ───────────────────────────────────────────

    def _check_cooldown(self, rule_id: str, cooldown_s: float) -> bool:
        """Return True if the rule can fire (enough time elapsed since last fire)."""
        now = time.monotonic()
        last = self._cooldowns.get(rule_id, 0.0)
        if now - last < cooldown_s:
            return False
        self._cooldowns[rule_id] = now
        return True

    # ── Session / Daily Time Properties ──────────────────────────────

    @property
    def _daily_limit_reached(self) -> bool:
        """True if daily time limit exceeded."""
        if self._guardrails.daily_time_limit_s <= 0:
            return False
        return self._daily_state.total_s >= self._guardrails.daily_time_limit_s

    # ── Daily Timer Persistence ──────────────────────────────────────

    def _load_daily_state(self) -> None:
        """Load persisted daily usage counter, resetting if date has changed."""
        import datetime

        today = datetime.date.today().isoformat()

        if self._daily_persist_path is None:
            # Store alongside memory_path
            parent = Path(self._memory_path).parent
            self._daily_persist_path = parent / "daily_usage.json"

        try:
            if self._daily_persist_path.exists():
                raw = json.loads(self._daily_persist_path.read_text())
                if raw.get("date") == today:
                    self._daily_state.date = today
                    self._daily_state.total_s = float(raw.get("total_s", 0.0))
                    log.info(
                        "daily usage loaded: %.0fs on %s",
                        self._daily_state.total_s,
                        today,
                    )
                else:
                    # Different day — reset counter
                    self._daily_state.date = today
                    self._daily_state.total_s = 0.0
                    log.info("daily usage reset for new day: %s", today)
            else:
                self._daily_state.date = today
                self._daily_state.total_s = 0.0
        except Exception as e:
            log.warning("failed to load daily state: %s", e)
            self._daily_state.date = today
            self._daily_state.total_s = 0.0

    def _persist_daily_state(self) -> None:
        """Write daily usage counter to disk."""
        if self._daily_persist_path is None:
            return
        try:
            self._daily_persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "date": self._daily_state.date,
                "total_s": round(self._daily_state.total_s, 1),
            }
            self._daily_persist_path.write_text(json.dumps(data) + "\n")
        except Exception as e:
            log.warning("failed to persist daily state: %s", e)

    # ── Event Handlers (L0 Impulse Catalog) ─────────────────────────

    def _handle_config(self, payload: dict) -> None:
        """Process personality.config.init — compute trait parameters + guardrails."""
        axes = payload.get("axes", {})
        self._trait = compute_trait_parameters(
            energy=float(axes.get("energy", 0.40)),
            reactivity=float(axes.get("reactivity", 0.50)),
            initiative=float(axes.get("initiative", 0.30)),
            vulnerability=float(axes.get("vulnerability", 0.35)),
            predictability=float(axes.get("predictability", 0.75)),
        )

        # Parse guardrail config
        gr = payload.get("guardrails", {})
        if gr:
            self._guardrails.negative_duration_caps = bool(
                gr.get("negative_duration_caps", True)
            )
            self._guardrails.negative_intensity_caps = bool(
                gr.get("negative_intensity_caps", True)
            )
            self._guardrails.context_gate = bool(gr.get("context_gate", True))
            self._guardrails.session_time_limit_s = float(
                gr.get("session_time_limit_s", 900.0)
            )
            self._guardrails.daily_time_limit_s = float(
                gr.get("daily_time_limit_s", 2700.0)
            )

        # Memory config
        self._memory_path = str(payload.get("memory_path", self._memory_path))
        self._memory_consent = bool(payload.get("memory_consent", False))

        self._configured.set()
        log.info(
            "configured: baseline=(%.2f, %.2f) decay=%.4f/s "
            "session_limit=%.0fs daily_limit=%.0fs",
            self._trait.baseline_valence,
            self._trait.baseline_arousal,
            self._trait.decay_rate_phasic,
            self._guardrails.session_time_limit_s,
            self._guardrails.daily_time_limit_s,
        )

    def _handle_ai_emotion(self, payload: dict) -> None:
        """L1: Map LLM emotion to VA impulse (spec §5.2).

        Accepts optional session_id, turn_id, mood_reason from v2 schema.
        """
        emotion = str(payload.get("emotion", "")).strip().lower()
        intensity = float(payload.get("intensity", 0.7))
        mood_reason = str(payload.get("mood_reason", ""))

        target = EMOTION_VA_TARGETS.get(emotion)
        if target is None:
            log.warning("unknown AI emotion: %r", emotion)
            return

        target_v, target_a, base_mag = target
        # Scale magnitude by the LLM-provided intensity (0.0–1.0)
        magnitude = base_mag * max(0.0, min(1.0, intensity))

        self._pending_impulses.append(
            Impulse(target_v, target_a, magnitude, "ai_emotion")
        )
        self._idle_timer_s = 0.0  # interaction resets idle

        if mood_reason:
            log.debug("ai_emotion mood_reason: %s", mood_reason)

        # Event-triggered fast path: immediate processing
        self._fast_path()

    def _handle_conv_started(self, payload: dict) -> None:
        """L0-06 + L0-13: Conversation started."""
        # Check if daily limit already reached — block new conversation
        if self._daily_limit_reached:
            self._emit_guardrail_triggered(
                "daily_limit_blocked",
                {"daily_time_s": round(self._daily_state.total_s, 1)},
            )
            log.info("conversation blocked: daily time limit reached")
            return

        self._conversation_active = True
        self._idle_timer_s = 0.0
        self._conv_ended_ago_s = float("inf")
        self._session_time_s = 0.0
        self._session_limit_reached = False

        # L0-06: Conversation started impulse
        self._pending_impulses.append(Impulse(0.10, 0.15, 0.30, "system_event"))

        # L0-13: Child approach (wake word trigger)
        trigger = str(payload.get("trigger", ""))
        if trigger == "wake_word" and self._check_cooldown("L0-13", 10.0):
            self._pending_impulses.append(Impulse(0.10, 0.15, 0.25, "system_event"))
            log.debug("L0-13 child approach (wake word)")

        self._fast_path()

    def _handle_conv_ended(self, payload: dict) -> None:
        """L0-07 / L0-08: Conversation ended (positive/negative)."""
        self._conversation_active = False
        self._conv_ended_ago_s = 0.0

        if self._affect.valence > 0:
            # L0-07: Positive conversation end
            self._pending_impulses.append(Impulse(0.20, -0.05, 0.40, "system_event"))
        else:
            # L0-08: Negative conversation end
            self._pending_impulses.append(Impulse(0.05, -0.10, 0.30, "system_event"))

        self._fast_path()

    def _handle_system_event(self, payload: dict) -> None:
        """L0-01 through L0-05: System state events."""
        event = str(payload.get("event", ""))

        if event == "boot":
            if not self._boot_fired:
                self._boot_fired = True
                self._pending_impulses.append(Impulse(0.35, 0.40, 0.50, "system_event"))

        elif event == "low_battery":
            # L0-02: Low battery
            if self._check_cooldown("L0-02", 120.0):
                self._pending_impulses.append(
                    Impulse(-0.15, 0.10, 0.30, "system_event")
                )

        elif event == "critical_battery":
            # L0-03: Critical battery (no cooldown)
            self._pending_impulses.append(Impulse(0.05, -0.60, 0.40, "system_event"))

        elif event == "fault_raised":
            # L0-04: Fault raised
            if self._check_cooldown("L0-04", 30.0):
                self._pending_impulses.append(
                    Impulse(-0.10, 0.25, 0.40, "system_event")
                )

        elif event == "fault_cleared":
            # L0-05: Fault cleared (no cooldown)
            self._pending_impulses.append(Impulse(0.15, -0.10, 0.30, "system_event"))

        else:
            log.debug("unknown system event: %r", event)
            return

        self._fast_path()

    def _handle_speech_activity(self, payload: dict) -> None:
        """L0-09: Speech activity detected."""
        speaking = bool(payload.get("speaking", False))
        if speaking and self._check_cooldown("L0-09", 5.0):
            self._pending_impulses.append(Impulse(0.05, 0.10, 0.20, "speech_signal"))
            self._idle_timer_s = 0.0
            self._fast_path()

    def _handle_button_press(self, payload: dict) -> None:
        """L0-10: Face button press."""
        if self._check_cooldown("L0-10", 5.0):
            self._pending_impulses.append(Impulse(0.15, 0.20, 0.40, "system_event"))
            self._idle_timer_s = 0.0
            self._fast_path()

    def _handle_override(self, payload: dict) -> None:
        """Debug: inject arbitrary affect impulse."""
        self._pending_impulses.append(
            Impulse(
                float(payload.get("valence", 0.0)),
                float(payload.get("arousal", 0.0)),
                float(payload.get("magnitude", 0.5)),
                "override",
            )
        )
        self._fast_path()

    def _handle_set_guardrail(self, payload: dict) -> None:
        """Parent override: adjust guardrail settings at runtime (PE spec S2 §9.5).

        Payload example: {"session_time_limit_s": 1200, "daily_time_limit_s": 3600}
        Only specified fields are updated; omitted fields keep current values.
        """
        changed = []
        for field_name in (
            "negative_duration_caps",
            "negative_intensity_caps",
            "context_gate",
        ):
            if field_name in payload:
                old = getattr(self._guardrails, field_name)
                new = bool(payload[field_name])
                if old != new:
                    setattr(self._guardrails, field_name, new)
                    changed.append(f"{field_name}={new}")

        for field_name in ("session_time_limit_s", "daily_time_limit_s"):
            if field_name in payload:
                old = getattr(self._guardrails, field_name)
                new = float(payload[field_name])
                if old != new:
                    setattr(self._guardrails, field_name, new)
                    changed.append(f"{field_name}={new}")

        # Special command: reset daily counter
        if payload.get("reset_daily", False):
            self._daily_state.total_s = 0.0
            self._daily_limit_notified = False
            self._persist_daily_state()
            changed.append("daily_reset")

        if changed:
            log.info("guardrail updated: %s", ", ".join(changed))

    # ── Fast Path ───────────────────────────────────────────────────

    def _fast_path(self) -> None:
        """Event-triggered immediate processing (no idle rule evaluation)."""
        if self._trait is None:
            return
        now = time.monotonic()
        dt = now - self._last_tick_ts
        self._last_tick_ts = now
        self._process_and_emit(dt)


if __name__ == "__main__":
    worker_main(PersonalityWorker)
