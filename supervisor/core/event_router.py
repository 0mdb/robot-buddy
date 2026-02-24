"""Routes worker events to WorldState updates and plan acceptance.

Core stamps t_plan_rx_ns on plan receipt and is authoritative for
dedup, seq ordering, TTL enforcement, validation, and scheduling.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from supervisor.core.action_scheduler import (
    ActionScheduler,
    PlanValidator,
)
from supervisor.core.state import WorldState
from supervisor.messages.envelope import Envelope
from supervisor.messages.types import (
    AI_CONVERSATION_DONE,
    AI_CONVERSATION_EMOTION,
    AI_CONVERSATION_GESTURE,
    AI_CONVERSATION_TRANSCRIPTION,
    AI_LIFECYCLE_ERROR,
    AI_LIFECYCLE_STARTED,
    AI_PLAN_RECEIVED,
    AI_STATE_CHANGED,
    AI_STATUS_HEALTH,
    EAR_EVENT_END_OF_UTTERANCE,
    EAR_EVENT_WAKE_WORD,
    EAR_STATUS_HEALTH,
    SYSTEM_AUDIO_LINK_DOWN,
    SYSTEM_AUDIO_LINK_UP,
    TTS_EVENT_CANCELLED,
    TTS_EVENT_ENERGY,
    TTS_EVENT_ERROR,
    TTS_EVENT_FINISHED,
    TTS_EVENT_MIC_DROPPED,
    TTS_EVENT_STARTED,
    TTS_STATUS_HEALTH,
    PERSONALITY_EVENT_GUARDRAIL_TRIGGERED,
    PERSONALITY_STATE_SNAPSHOT,
    PERSONALITY_STATUS_HEALTH,
    VISION_DETECTION_SNAPSHOT,
    VISION_FRAME_JPEG,
    VISION_STATUS_HEALTH,
)

log = logging.getLogger(__name__)

# Plan dedup window (PROTOCOL.md Appendix C)
_PLAN_DEDUP_WINDOW = 256
_PLAN_DEDUP_TTL_S = 60.0


class EventRouter:
    """Update WorldState from inbound worker events."""

    def __init__(
        self,
        world: WorldState,
        scheduler: ActionScheduler,
        validator: PlanValidator,
    ) -> None:
        self._world = world
        self._scheduler = scheduler
        self._validator = validator

        # Plan dedup: plan_id → mono_ns
        self._seen_plans: OrderedDict[str, int] = OrderedDict()

    async def route(self, worker_name: str, env: Envelope) -> None:
        """Dispatch an inbound worker event to the appropriate handler."""
        t = env.type
        p = env.payload
        now_ms = time.monotonic() * 1000.0

        # ── Vision ───────────────────────────────────────────────
        if t == VISION_DETECTION_SNAPSHOT:
            self._world.clear_confidence = float(p.get("clear_confidence", -1.0))
            self._world.ball_confidence = float(p.get("ball_confidence", 0.0))
            self._world.ball_bearing_deg = float(p.get("ball_bearing_deg", 0.0))
            self._world.vision_fps = float(p.get("fps", 0.0))
            self._world.vision_rx_mono_ms = now_ms
            self._world.vision_frame_seq = int(p.get("frame_seq", 0))

        elif t == VISION_FRAME_JPEG:
            self._world.latest_jpeg_b64 = str(p.get("data_b64", ""))

        elif t == VISION_STATUS_HEALTH:
            self._world.worker_last_heartbeat_ms["vision"] = now_ms
            self._world.worker_alive["vision"] = True

        # ── TTS ──────────────────────────────────────────────────
        elif t == TTS_EVENT_STARTED:
            self._world.speaking = True
            self._world.current_energy = 0

        elif t == TTS_EVENT_ENERGY:
            self._world.current_energy = int(p.get("energy", 0))

        elif t == TTS_EVENT_FINISHED:
            self._world.speaking = False
            self._world.current_energy = 0

        elif t == TTS_EVENT_CANCELLED:
            self._world.speaking = False
            self._world.current_energy = 0

        elif t == TTS_EVENT_ERROR:
            self._world.speaking = False
            self._world.current_energy = 0

        elif t == TTS_EVENT_MIC_DROPPED:
            pass  # logged but no state update needed

        elif t == TTS_STATUS_HEALTH:
            self._world.worker_last_heartbeat_ms["tts"] = now_ms
            self._world.worker_alive["tts"] = True

        # ── AI ───────────────────────────────────────────────────
        elif t == AI_PLAN_RECEIVED:
            self._handle_plan(env, now_ms)

        elif t == AI_CONVERSATION_EMOTION:
            pass  # handled by tick_loop for face composition

        elif t == AI_CONVERSATION_GESTURE:
            pass  # handled by tick_loop for face composition

        elif t == AI_CONVERSATION_TRANSCRIPTION:
            pass  # logged for telemetry

        elif t == AI_CONVERSATION_DONE:
            pass  # handled by tick_loop

        elif t == AI_STATE_CHANGED:
            self._world.ai_state = str(p.get("state", "idle"))

        elif t == AI_STATUS_HEALTH:
            self._world.worker_last_heartbeat_ms["ai"] = now_ms
            self._world.worker_alive["ai"] = True
            self._world.planner_connected = bool(p.get("connected", False))

        elif t == AI_LIFECYCLE_STARTED:
            self._world.worker_last_heartbeat_ms["ai"] = now_ms
            self._world.worker_alive["ai"] = True

        elif t == AI_LIFECYCLE_ERROR:
            self._world.planner_connected = False

        # ── Ear (wake word + VAD) ─────────────────────────────────
        elif t == EAR_EVENT_WAKE_WORD:
            pass  # handled by tick_loop

        elif t == EAR_EVENT_END_OF_UTTERANCE:
            pass  # handled by tick_loop

        elif t == EAR_STATUS_HEALTH:
            self._world.worker_last_heartbeat_ms["ear"] = now_ms
            self._world.worker_alive["ear"] = True

        # ── System audio link ────────────────────────────────────
        elif t == SYSTEM_AUDIO_LINK_UP:
            socket = str(p.get("socket", ""))
            if socket == "mic":
                self._world.mic_link_up = True
            elif socket == "spk":
                self._world.spk_link_up = True
            log.info("audio link up: %s (from %s)", socket, worker_name)

        elif t == SYSTEM_AUDIO_LINK_DOWN:
            socket = str(p.get("socket", ""))
            if socket == "mic":
                self._world.mic_link_up = False
            elif socket == "spk":
                self._world.spk_link_up = False
            log.warning(
                "audio link down: %s (from %s, reason=%s)",
                socket,
                worker_name,
                p.get("reason", "unknown"),
            )

        # ── Personality ─────────────────────────────────────────────
        elif t == PERSONALITY_STATE_SNAPSHOT:
            self._world.personality_mood = str(p.get("mood", "neutral"))
            self._world.personality_intensity = float(p.get("intensity", 0.0))
            self._world.personality_valence = float(p.get("valence", 0.0))
            self._world.personality_arousal = float(p.get("arousal", 0.0))
            self._world.personality_layer = int(p.get("layer", 0))
            self._world.personality_idle_state = str(p.get("idle_state", "awake"))
            self._world.personality_snapshot_ts_ms = now_ms
            self._world.personality_conversation_active = bool(
                p.get("conversation_active", False)
            )
            self._world.personality_session_time_s = float(p.get("session_time_s", 0.0))
            self._world.personality_daily_time_s = float(p.get("daily_time_s", 0.0))
            self._world.personality_session_limit_reached = bool(
                p.get("session_limit_reached", False)
            )
            self._world.personality_daily_limit_reached = bool(
                p.get("daily_limit_reached", False)
            )

        elif t == PERSONALITY_EVENT_GUARDRAIL_TRIGGERED:
            pass  # handled by tick_loop via world state flags

        elif t == PERSONALITY_STATUS_HEALTH:
            self._world.worker_last_heartbeat_ms["personality"] = now_ms
            self._world.worker_alive["personality"] = True

    def _handle_plan(self, env: Envelope, now_ms: float) -> None:
        """Core-authoritative plan acceptance (§7.3.4)."""
        p = env.payload
        plan_id = str(p.get("plan_id", ""))
        plan_seq = int(p.get("plan_seq", 0))
        actions = p.get("actions", [])
        ttl_ms = int(p.get("ttl_ms", 2000))

        # Dedup by plan_id
        now_ns = time.monotonic_ns()
        self._prune_dedup(now_ns)
        if plan_id in self._seen_plans:
            self._world.plan_dropped_duplicate += 1
            return
        self._seen_plans[plan_id] = now_ns

        # Seq ordering
        if plan_seq <= self._world.plan_seq_last_accepted:
            self._world.plan_dropped_out_of_order += 1
            return

        # Validate
        validated = self._validator.validate(actions, ttl_ms)

        # Schedule
        self._scheduler.schedule_plan(
            validated,
            now_mono_ms=now_ms,
            issued_mono_ms=now_ms,  # t_plan_rx_ns is "now" since plan just arrived
        )

        # Update world state
        self._world.plan_seq_last_accepted = plan_seq
        self._world.last_plan_mono_ms = now_ms
        self._world.last_plan_actions = len(validated.actions)
        self._world.last_plan_id = plan_id
        self._world.last_plan = actions

    def _prune_dedup(self, now_ns: int) -> None:
        """Remove expired entries from the plan dedup window."""
        cutoff = now_ns - int(_PLAN_DEDUP_TTL_S * 1_000_000_000)
        while self._seen_plans:
            pid, t = next(iter(self._seen_plans.items()))
            if t > cutoff:
                break
            self._seen_plans.pop(pid)
        # Also cap window size
        while len(self._seen_plans) > _PLAN_DEDUP_WINDOW:
            self._seen_plans.popitem(last=False)
