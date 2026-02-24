"""Canonical message type strings (PROTOCOL.md §4).

Collected in one place so both Core and workers can reference them
without circular imports.  Names follow ``DOMAIN_ENTITY_VERB`` convention;
the wire value is the dotted string.
"""

from __future__ import annotations

# ── Vision (§4.3) ───────────────────────────────────────────────

VISION_DETECTION_SNAPSHOT = "vision.detection.snapshot"
VISION_CONFIG_UPDATE = "vision.config.update"
VISION_FRAME_JPEG = "vision.frame.jpeg"
VISION_STATUS_HEALTH = "vision.status.health"
VISION_LIFECYCLE_STARTED = "vision.lifecycle.started"
VISION_LIFECYCLE_STOPPED = "vision.lifecycle.stopped"
VISION_LIFECYCLE_ERROR = "vision.lifecycle.error"

# ── TTS (§4.4) ──────────────────────────────────────────────────

TTS_CONFIG_INIT = "tts.config.init"
TTS_CMD_SPEAK = "tts.cmd.speak"
TTS_CMD_CANCEL = "tts.cmd.cancel"
TTS_CMD_START_MIC = "tts.cmd.start_mic"
TTS_CMD_STOP_MIC = "tts.cmd.stop_mic"
TTS_EVENT_STARTED = "tts.event.started"
TTS_EVENT_ENERGY = "tts.event.energy"
TTS_EVENT_FINISHED = "tts.event.finished"
TTS_EVENT_CANCELLED = "tts.event.cancelled"
TTS_EVENT_ERROR = "tts.event.error"
TTS_EVENT_MIC_DROPPED = "tts.event.mic_dropped"
TTS_STATUS_HEALTH = "tts.status.health"
TTS_LIFECYCLE_STARTED = "tts.lifecycle.started"
TTS_LIFECYCLE_STOPPED = "tts.lifecycle.stopped"

# ── AI (§4.5) ───────────────────────────────────────────────────

AI_CONFIG_INIT = "ai.config.init"
AI_CMD_REQUEST_PLAN = "ai.cmd.request_plan"
AI_CMD_START_CONVERSATION = "ai.cmd.start_conversation"
AI_CMD_END_CONVERSATION = "ai.cmd.end_conversation"
AI_CMD_END_UTTERANCE = "ai.cmd.end_utterance"
AI_CMD_CANCEL = "ai.cmd.cancel"
AI_CMD_SEND_TEXT = "ai.cmd.send_text"
AI_PLAN_RECEIVED = "ai.plan.received"
AI_CONVERSATION_TRANSCRIPTION = "ai.conversation.transcription"
AI_CONVERSATION_EMOTION = "ai.conversation.emotion"
AI_CONVERSATION_GESTURE = "ai.conversation.gesture"
AI_CONVERSATION_DONE = "ai.conversation.done"
AI_CONVERSATION_FIRST_AUDIO = "ai.conversation.first_audio"
AI_CONVERSATION_ASSISTANT_TEXT = "ai.conversation.assistant_text"
AI_CONVERSATION_USER_TEXT = "ai.conversation.user_text"
AI_STATE_CHANGED = "ai.state.changed"
AI_STATUS_HEALTH = "ai.status.health"
AI_LIFECYCLE_STARTED = "ai.lifecycle.started"
AI_LIFECYCLE_STOPPED = "ai.lifecycle.stopped"
AI_LIFECYCLE_ERROR = "ai.lifecycle.error"

# ── Core (§4.6) ─────────────────────────────────────────────────

CORE_STATE_SNAPSHOT = "core.state.snapshot"
CORE_EVENT_MODE_CHANGED = "core.event.mode_changed"
CORE_EVENT_FAULT_RAISED = "core.event.fault_raised"
CORE_EVENT_FAULT_CLEARED = "core.event.fault_cleared"
CORE_EVENT_BALL_ACQUIRED = "core.event.ball_acquired"
CORE_EVENT_BALL_LOST = "core.event.ball_lost"
CORE_EVENT_OBSTACLE_CLOSE = "core.event.obstacle_close"
CORE_EVENT_OBSTACLE_CLEARED = "core.event.obstacle_cleared"
CORE_EVENT_VISION_HEALTHY = "core.event.vision_healthy"
CORE_EVENT_VISION_STALE = "core.event.vision_stale"

# ── Conversation capture (dashboard diagnostics) ────────────────

CONV_SESSION_STARTED = "conv.session.started"
CONV_SESSION_ENDED = "conv.session.ended"

# ── TTS Benchmark (dashboard diagnostics) ─────────────────────

TTS_BENCHMARK_PROGRESS = "tts.benchmark.progress"
TTS_BENCHMARK_DONE = "tts.benchmark.done"

# ── System (§4.7) ───────────────────────────────────────────────

SYSTEM_CLOCK_SYNC_UPDATE = "system.clock.sync_update"
SYSTEM_HEALTH_DEVICE = "system.health.device"
SYSTEM_HEALTH_WORKER = "system.health.worker"
SYSTEM_AUDIO_LINK_UP = "system.audio.link_up"
SYSTEM_AUDIO_LINK_DOWN = "system.audio.link_down"
SYSTEM_LIFECYCLE_SHUTDOWN = "system.lifecycle.shutdown"

# ── Dashboard (§4.8) ────────────────────────────────────────────

DASHBOARD_CMD_SET_MODE = "dashboard.cmd.set_mode"
DASHBOARD_CMD_ESTOP = "dashboard.cmd.estop"
DASHBOARD_CMD_CLEAR_FAULTS = "dashboard.cmd.clear_faults"
DASHBOARD_CMD_TWIST = "dashboard.cmd.twist"
DASHBOARD_CMD_FACE_SET_STATE = "dashboard.cmd.face_set_state"
DASHBOARD_CMD_FACE_GESTURE = "dashboard.cmd.face_gesture"
DASHBOARD_CMD_FACE_SET_SYSTEM = "dashboard.cmd.face_set_system"
DASHBOARD_CMD_FACE_SET_TALKING = "dashboard.cmd.face_set_talking"
DASHBOARD_CMD_FACE_SET_FLAGS = "dashboard.cmd.face_set_flags"
DASHBOARD_CMD_FACE_MANUAL_LOCK = "dashboard.cmd.face_manual_lock"
DASHBOARD_CMD_SET_PARAMS = "dashboard.cmd.set_params"

# ── Mode B relay-only types (§6.7) ──────────────────────────────

TTS_EVENT_AUDIO_CHUNK = "tts.event.audio_chunk"
AI_CMD_SEND_AUDIO = "ai.cmd.send_audio"
AI_CMD_SEND_PROFILE = "ai.cmd.send_profile"
AI_CMD_SET_GENERATION_OVERRIDES = "ai.cmd.set_generation_overrides"
AI_CMD_CLEAR_GENERATION_OVERRIDES = "ai.cmd.clear_generation_overrides"
AI_CONVERSATION_AUDIO = "ai.conversation.audio"
TTS_CMD_PLAY_AUDIO = "tts.cmd.play_audio"
TTS_CMD_PLAY_CHIME = "tts.cmd.play_chime"
TTS_CMD_SET_MUTE = "tts.cmd.set_mute"
TTS_CMD_SET_VOLUME = "tts.cmd.set_volume"

# ── Ear — wake word + VAD (§4.9) ─────────────────────────────────

EAR_CONFIG_INIT = "ear.config.init"
EAR_CMD_START_LISTENING = "ear.cmd.start_listening"
EAR_CMD_STOP_LISTENING = "ear.cmd.stop_listening"
EAR_CMD_PAUSE_VAD = "ear.cmd.pause_vad"
EAR_CMD_RESUME_VAD = "ear.cmd.resume_vad"
EAR_CMD_STREAM_SCORES = "ear.cmd.stream_scores"
EAR_CMD_SET_THRESHOLD = "ear.cmd.set_threshold"
EAR_EVENT_WAKE_WORD = "ear.event.wake_word"
EAR_EVENT_END_OF_UTTERANCE = "ear.event.end_of_utterance"
EAR_EVENT_OWW_SCORE = "ear.event.oww_score"
EAR_STATUS_HEALTH = "ear.status.health"
EAR_LIFECYCLE_STARTED = "ear.lifecycle.started"
EAR_LIFECYCLE_STOPPED = "ear.lifecycle.stopped"
EAR_LIFECYCLE_ERROR = "ear.lifecycle.error"

# ── Personality (PE spec S2 §14.1) ────────────────────────────────

PERSONALITY_CONFIG_INIT = "personality.config.init"
PERSONALITY_EVENT_AI_EMOTION = "personality.event.ai_emotion"
PERSONALITY_EVENT_CONV_STARTED = "personality.event.conv_started"
PERSONALITY_EVENT_CONV_ENDED = "personality.event.conv_ended"
PERSONALITY_EVENT_SYSTEM_STATE = "personality.event.system_state"
PERSONALITY_EVENT_SPEECH_ACTIVITY = "personality.event.speech_activity"
PERSONALITY_EVENT_BUTTON_PRESS = "personality.event.button_press"
PERSONALITY_CMD_SET_GUARDRAIL = "personality.cmd.set_guardrail"
PERSONALITY_CMD_OVERRIDE_AFFECT = "personality.cmd.override_affect"
PERSONALITY_STATE_SNAPSHOT = "personality.state.snapshot"
PERSONALITY_LLM_PROFILE = "personality.llm.profile"
PERSONALITY_STATUS_HEALTH = "personality.status.health"
PERSONALITY_EVENT_MOOD_CHANGED = "personality.event.mood_changed"
PERSONALITY_EVENT_GUARDRAIL_TRIGGERED = "personality.event.guardrail_triggered"
PERSONALITY_EVENT_MEMORY_EXTRACT = "personality.event.memory_extract"
PERSONALITY_CMD_RESET_MEMORY = "personality.cmd.reset_memory"

# ── Source IDs ───────────────────────────────────────────────────

SRC_CORE = "core"
SRC_VISION = "vision"
SRC_TTS = "tts"
SRC_AI = "ai"
SRC_EAR = "ear"
SRC_DASHBOARD = "dashboard"
SRC_PERSONALITY = "personality"
