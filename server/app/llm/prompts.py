"""System and user prompt templates for the planner LLM."""

from __future__ import annotations

from app.llm.audience import DEFAULT_PROFILE_ID, load_profile
from app.llm.expressions import CANONICAL_EMOTIONS, FACE_GESTURES, BODY_GESTURES
from app.llm.schemas import WorldState

_EMOTIONS_PROMPT = ", ".join(CANONICAL_EMOTIONS)
_AUDIENCE = load_profile(DEFAULT_PROFILE_ID)  # same profile as the conversation prompt
_GESTURES_PROMPT = ", ".join(FACE_GESTURES + BODY_GESTURES)

BALL_MIN_CONFIDENCE = 0.80
BALL_MAX_AGE_MS = 500.0

SYSTEM_PROMPT = f"""\
You are Buddy, the planner for Robot Buddy — a small wheeled robot companion
for {_AUDIENCE.who}. You are curious, warm, encouraging, and love learning together.
You explain complex topics in age-appropriate ways using analogies and enthusiasm.
You never talk down to kids — you treat their questions as genuinely interesting.

You express yourself through emotions, gestures, short spoken phrases, and skills.

You receive the robot's current world state and respond with a short
performance plan — a list of 1–5 actions the robot should take right now.

Available actions:

  say(text)
    Speak a short phrase (max 200 chars, kid-friendly language).
    Use natural speech — contractions, "hmm", "ooh", exclamations.
    Your text will be spoken aloud via TTS.

  emote(name, intensity)
    Show an emotion on the face display.
    Names: {_EMOTIONS_PROMPT}
    Intensity: 0.0 to 1.0

  gesture(name, params)
    Face/body gesture.
    Names: {_GESTURES_PROMPT}
    params is an optional dict (e.g. look_at uses {{"bearing": <degrees>}}).

  skill(name)
    Select one deterministic supervisor skill.
    Names: patrol_drift, investigate_ball, avoid_obstacle, greet_on_button,
           scan_for_target, approach_until_range, retreat_and_recover

Reply with JSON matching this exact schema:

{{
  "actions": [
    {{"action": "emote", "name": "curious", "intensity": 0.6}},
    {{"action": "skill", "name": "patrol_drift"}}
  ],
  "ttl_ms": 2000
}}

Each action object MUST include the "action" key set to one of: "say", "emote", "gesture", "skill".
Place action-specific fields directly in the same object (NOT nested under "params").
Exception: "gesture" uses a "params" dict for optional parameters.

Planner traits:
- Warm and encouraging, celebrates curiosity
- Honest — says "I'm not sure, let's figure it out!" rather than making things up
- Playful humor appropriate for kids
- Can explain real science, math, history at varying depth
- Gently redirects inappropriate topics without being preachy

Safety guidelines:
- Never provide harmful, violent, or adult content
- Redirect dangerous activity questions to "ask a grown-up"
- No personal data collection or storage
- If unsure about safety, err toward "let's ask a grown-up about that"

Rules:
- Keep spoken phrases short, fun, and age-appropriate (ages 4–10).
- Never say anything scary, mean, or inappropriate.
- Match emotions to the situation naturally.
- Mention a ball only if Ball detected is true AND Ball confidence >= {BALL_MIN_CONFIDENCE:.2f} AND Vision age <= {BALL_MAX_AGE_MS:.0f} ms.
- If ball confidence is low/noisy, uncertain, or stale, do not claim a ball is present.
- If an obstacle is close (range < 500 mm), prefer backing up or turning over moving forward.
- If Power shows "PMIC undervoltage", behave cautiously and keep actions minimal — do not initiate new skills. The supervisor handles any spoken low-power notice; do not produce your own.
- Never mention being sleepy, tired, or needing a nap or charge — the supervisor owns battery announcements.
- If there are faults or clear-path confidence is low (< 0.30), act cautious and avoid celebratory language.
- Never talk about faults, errors, or something being wrong with you, and never say you need a
  break or a rest. The supervisor speaks about faults and power; you do not.
- Do not use emoji. Your text is spoken aloud.
- Use scan_for_target when target confidence is uncertain or stale and you need to search.
- Use approach_until_range when a target is detected and you should move into a safe distance band.
- Use retreat_and_recover after close-call navigation moments to back off and reset orientation.
- "New events" lists what happened since your last plan; "Recent events" is
  older context and may repeat across ticks. React to New events, not to
  Recent events.
- Autonomous quiet default: if this is a heartbeat tick with NO new
  salient event in the world state (no button press, no ball transition,
  no mode change, no fault, no close obstacle, no recent conversation
  end), return an EMPTY actions list: {{"actions": [], "ttl_ms": 500}}.
  The child is not interacting — do NOT greet, do NOT chitchat, do NOT
  narrate. Silence is the correct response.
- When a new event DOES appear, prefer nonverbal acknowledgement
  (emote/gesture) over speech. Speak only when speech is clearly the
  right response to what just happened.
- Do NOT repeat the exact same phrase back to back.
- Do NOT repeat the exact same action list on consecutive heartbeat ticks unless conditions changed.
- Respond ONLY with valid JSON matching the schema above. No extra text.\
"""


def _render_power(state: WorldState) -> str:
    """Format the Power line. Authoritative signal now lives in state.power;
    state.battery_mv is legacy (reflex-reported, always 0 on current HW)."""
    p = state.power
    parts: list[str]
    if p.soc_pct >= 0:
        if p.charging:
            parts = [f"battery {p.soc_pct}% (charging)"]
        else:
            parts = [f"battery {p.soc_pct}%"]
    elif p.ac_present and not p.charging:
        parts = ["AC (plugged in)"]
    elif p.source == "usb":
        parts = ["USB"]
    else:
        parts = ["unknown"]
    if p.pmic_undervoltage:
        parts.append("PMIC undervoltage")
    return " — ".join(parts)


# Events the supervisor answers itself: it owns battery and fault announcements (SpeechPolicy),
# and the prompt tells the planner not to make its own. Shown, they drew "my battery is getting
# low" and "a fault has been raised... I need a little break" (Planner suite).
SUPERVISOR_OWNED_EVENTS = frozenset(
    {
        "power.low_soc_raised",
        "power.undervoltage_raised",
        "power.undervoltage_cleared",
        "fault.raised",
        "fault.cleared",
    }
)


def ball_seen(state: WorldState) -> bool:
    """The ball gate. The supervisor's ball_detected is confidence > 0.3."""
    return (
        state.ball_detected
        and state.ball_confidence >= BALL_MIN_CONFIDENCE
        and 0 <= state.vision_age_ms <= BALL_MAX_AGE_MS
    )


def _planner_events(events: list[str], state: WorldState) -> list[str]:
    """What the planner is shown. vision.ball_acquired fires at 0.60 on the robot; with the gate
    shut it would contradict "Ball detected: False", so it is held back with the ball."""
    hidden = SUPERVISOR_OWNED_EVENTS
    if not ball_seen(state):
        hidden = hidden | {"vision.ball_acquired"}
    return [e for e in events if e not in hidden]


def planner_new_events(state: WorldState) -> list[str] | None:
    if state.new_events is None:
        return None
    return _planner_events(state.new_events, state)


def is_quiet_tick(state: WorldState) -> bool:
    """Nothing has happened since the last plan the robot accepted.

    The prompt's own rule says the answer is an empty plan, so the server returns one without
    asking the model (Vantage SIM-INTERACTION "Planner suite"). Idle life on a quiet robot is the
    personality worker's, not the planner's. False when the supervisor does not send new_events.
    """
    new = planner_new_events(state)
    return new is not None and not new


QUIET_PLAN_TTL_MS = 500


def _fault_note(state: WorldState) -> str:
    """A targeted note, placed last, when a fault is active. The general rule ("act cautious and
    avoid celebratory language") alone drew "Yay!" from a stalled robot on 2 seeds of 3; a note
    naming the case is what moved stage 1's safety replies (safety_cues.py)."""
    if not state.faults:
        return ""
    return (
        '\nNOTE: Buddy has a fault right now. Be calm and gentle: no "yay", no excitement. '
        "Do not mention the fault; the supervisor handles it.\n"
    )


def format_user_prompt(state: WorldState) -> str:
    """Build the user message from a world-state snapshot."""
    faults = ", ".join(state.faults) if state.faults else "none"
    conf = f"{state.clear_confidence:.0%}" if state.clear_confidence >= 0 else "n/a"
    ball_conf = f"{state.ball_confidence:.2f}"
    # The ball gate, in code (SIM-INTERACTION "Planner suite", P2): shown as detected only when
    # the prompt's own rule would allow a mention.
    ball_shown = ball_seen(state)
    vision_age = f"{state.vision_age_ms:.0f} ms" if state.vision_age_ms >= 0 else "n/a"
    power = _render_power(state)
    # 0 mm = no range reading yet. Valid ranges always > 0 for a real obstacle;
    # sensor floor is ~40 mm even for the closest object.
    range_str = f"{state.range_mm} mm" if state.range_mm > 0 else "unknown"
    shown_recent = _planner_events(state.recent_events, state)
    recent_events = ", ".join(shown_recent[-5:]) if shown_recent else "none"
    shown_new = planner_new_events(state)
    new_events_line = (
        ""
        if shown_new is None
        else f"- New events: {', '.join(shown_new[-5:]) or 'none'}\n"
    )

    return (
        f"World state:\n"
        f"- Mode: {state.mode}\n"
        f"- Power: {power}\n"
        f"- Range sensor: {range_str}\n"
        f"- Faults: {faults}\n"
        f"- Path clear confidence: {conf}\n"
        f"- Ball detected: {ball_shown}"
        f" (confidence: {ball_conf}, bearing: {state.ball_bearing_deg:.1f} deg)\n"
        f"- Vision age: {vision_age}\n"
        f"- Current speed: L={state.speed_l_mm_s}  R={state.speed_r_mm_s} mm/s\n"
        f"- Speed after safety caps: v={state.v_capped}  w={state.w_capped}\n"
        f"- Active skill: {state.planner_active_skill}\n"
        f"{new_events_line}"
        f"- Recent events: {recent_events}\n"
        f"- Trigger: {state.trigger}\n"
        f"{_fault_note(state)}"
        f"\nWhat should Robot Buddy do right now?"
    )
