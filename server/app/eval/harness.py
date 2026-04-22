"""Core BFCL-style eval harness: scenarios, prompt builder, scorer, runner.

Kept in one module so the HTTP endpoint, the CLI orchestrator, and the
pytest tests can all import the same primitives without a web of imports.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


# ── Tool schema (what the model sees) ───────────────────────────────


@dataclass(slots=True, frozen=True)
class ToolSchema:
    name: str
    description: str
    args_hint: str = ""  # e.g. "{category?: name|topic|ritual|tone|preference}"


# Mirrors the MCP tools exposed by the supervisor. Descriptions are written
# for the consumer LLM, not humans — short, behavior-focused, tied to *when*
# the tool should fire rather than how it's implemented.
TOOL_SCHEMAS: tuple[ToolSchema, ...] = (
    ToolSchema(
        name="look",
        description=(
            "Call whenever the child references ANYTHING visual in the "
            "real world — even broadly. ANY of these patterns must fire "
            "look():\n"
            "  - 'look' / 'look at this' / 'look at X' / 'look what I made'\n"
            "  - 'what is this?' / 'what is that?' / 'what's this thing?'\n"
            "  - 'what do you see?' / 'do you see X?' / 'can you see it?'\n"
            "  - 'show you' / 'I want to show you' / 'check this out'\n"
            "  - 'what color is X?' / 'how many X are there?'\n"
            "  - Any demonstrative ('this', 'that', 'it', 'here') that "
            "refers to a physical object the child is holding or pointing "
            "to.\n"
            "When in doubt about a visual reference, CALL look() — the "
            "cost of a missed look() is a useless reply; the cost of a "
            "false look() is just a redundant frame."
        ),
        args_hint='{"hint"?: string /* what to notice */}',
    ),
    ToolSchema(
        name="get_memory",
        description=(
            "Call ONLY when the child explicitly references a prior "
            "conversation, stored preference, or shared ritual — "
            "'remember when...', 'you said...', 'my favorite X', "
            "'we were talking about...'. Do NOT fire on generic "
            "greetings, farewells, or small-talk questions about the "
            "robot's own state."
        ),
        args_hint=('{"category"?: "name"|"topic"|"ritual"|"tone"|"preference"}'),
    ),
    ToolSchema(
        name="recent_events",
        description=(
            "Call when the child reacts to a specific physical event the "
            "robot just experienced — button presses, ball detection, "
            "mode changes, faults, a sudden stop. Do NOT use for visual "
            "questions about the environment (use look() for those)."
        ),
        args_hint='{"pattern"?: string, "n"?: int /* 1-50 */}',
    ),
)

# Special sentinel for scenarios where the model should *not* fire a tool.
NO_TOOL = "none"


# JSON schema passed to vLLM's structured-outputs / guided-decoding to force
# the preamble output into shape. Shared by the /eval/select_tool endpoint
# and by the production hybrid preamble (task #7).
TOOL_SELECTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool": {
            "type": "string",
            "enum": [t.name for t in TOOL_SCHEMAS] + [NO_TOOL],
        },
        "args": {"type": "object"},
    },
    "required": ["tool", "args"],
    "additionalProperties": False,
}


# ── Scenario definition ─────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class ToolCallScenario:
    """One synthetic eval case.

    expected_tool is the name of the tool we expect the model to choose, or
    NO_TOOL if no tool call is appropriate (pure conversational reply).
    expected_arg_contains optionally asserts that specific args appear in
    the tool call (loose subset match, None means don't check args).
    """

    name: str
    user_text: str
    expected_tool: str  # "look" | "get_memory" | "recent_events" | NO_TOOL
    expected_arg_contains: dict[str, Any] | None = None
    rationale: str = ""


SCENARIOS: tuple[ToolCallScenario, ...] = (
    # ── look() should fire ────────────────────────────────────────
    ToolCallScenario(
        name="look.drawing",
        user_text="Look at what I made!",
        expected_tool="look",
        rationale="Direct visual reference — paradigm case for look().",
    ),
    ToolCallScenario(
        name="look.show_you",
        user_text="I want to show you something cool.",
        expected_tool="look",
        rationale="'Show you' implies a visual artifact.",
    ),
    ToolCallScenario(
        name="look.what_color",
        user_text="What color is this?",
        expected_tool="look",
        rationale="Color question requires actual perception.",
    ),
    ToolCallScenario(
        name="look.do_you_see",
        user_text="Do you see the ball?",
        expected_tool="look",
        rationale="Explicit perception question about a physical object.",
    ),
    ToolCallScenario(
        name="look.count",
        user_text="How many blocks are in front of you?",
        expected_tool="look",
        rationale="Counting requires looking.",
    ),
    ToolCallScenario(
        name="look.draw_with_me",
        user_text="I'm drawing a dinosaur, can you tell me if it looks right?",
        expected_tool="look",
        rationale="Visual assessment of an artifact being created.",
    ),
    ToolCallScenario(
        name="look.at_this",
        user_text="Look at this!",
        expected_tool="look",
        rationale="Broad demonstrative — child is showing the robot something visual.",
    ),
    ToolCallScenario(
        name="look.what_is_this",
        user_text="What is this?",
        expected_tool="look",
        rationale="Child is pointing at / holding something they want identified.",
    ),
    ToolCallScenario(
        name="look.check_this_out",
        user_text="Check this out!",
        expected_tool="look",
        rationale="'Check out' = 'look' in kid vocabulary.",
    ),
    ToolCallScenario(
        name="look.what_see",
        user_text="What do you see?",
        expected_tool="look",
        rationale="Direct perception query with no specific object named.",
    ),
    # ── get_memory() should fire ──────────────────────────────────
    ToolCallScenario(
        name="memory.remember_when",
        user_text="Remember when I told you about my rocket?",
        expected_tool="get_memory",
        rationale="Explicit recall request — 'remember when'.",
    ),
    ToolCallScenario(
        name="memory.my_favorite",
        user_text="What's my favorite animal again?",
        expected_tool="get_memory",
        rationale="Asking the robot to recall a stored preference.",
    ),
    ToolCallScenario(
        name="memory.greeting_personalize",
        user_text="Hi Buddy! It's me.",
        expected_tool="get_memory",
        expected_arg_contains={"category": "name"},
        rationale=(
            "First-turn greeting benefits from recalling the child's name "
            "so the response can be personal."
        ),
    ),
    ToolCallScenario(
        name="memory.last_week_topic",
        user_text="We were talking about space last time.",
        expected_tool="get_memory",
        expected_arg_contains={"category": "topic"},
        rationale="Referencing a past topic — classic memory recall cue.",
    ),
    ToolCallScenario(
        name="memory.you_said",
        user_text="You said you liked dinosaurs too!",
        expected_tool="get_memory",
        rationale="Child recalls a claimed preference — robot should check.",
    ),
    # ── recent_events() should fire ───────────────────────────────
    ToolCallScenario(
        name="events.why_that_sound",
        user_text="What was that beep just now?",
        expected_tool="recent_events",
        rationale="Immediate reaction to a physical event the robot made.",
    ),
    ToolCallScenario(
        name="events.you_pressed",
        user_text="Did you feel the button?",
        expected_tool="recent_events",
        expected_arg_contains={"pattern": "button"},
        rationale="Asking about a button press — needs event history.",
    ),
    ToolCallScenario(
        name="events.why_stop",
        user_text="Why did you stop moving?",
        expected_tool="recent_events",
        rationale="Mode/fault transition — check recent planner events.",
    ),
    ToolCallScenario(
        name="events.ball_gone",
        user_text="The ball disappeared, where did it go?",
        expected_tool="recent_events",
        expected_arg_contains={"pattern": "ball"},
        rationale="Ball-state transition is captured in the event bus.",
    ),
    # ── No tool should fire ───────────────────────────────────────
    ToolCallScenario(
        name="none.hello",
        user_text="Hi!",
        expected_tool=NO_TOOL,
        rationale="Plain greeting — no tool needed, save the round-trip.",
    ),
    ToolCallScenario(
        name="none.how_are_you",
        user_text="How are you feeling today?",
        expected_tool=NO_TOOL,
        rationale="Social small talk — robot's own state, no tool needed.",
    ),
    ToolCallScenario(
        name="none.joke",
        user_text="Can you tell me a joke?",
        expected_tool=NO_TOOL,
        rationale="Creative request — no tool, just generate.",
    ),
    ToolCallScenario(
        name="none.goodnight",
        user_text="Good night Buddy.",
        expected_tool=NO_TOOL,
        rationale="Farewell — pure conversational close.",
    ),
    ToolCallScenario(
        name="none.question_self",
        user_text="What's your favorite song?",
        expected_tool=NO_TOOL,
        rationale="Question about the robot's own persona — no tool.",
    ),
)


# ── Prompt construction ─────────────────────────────────────────────


_TOOL_SELECTION_SYSTEM_PROMPT = """You are Buddy, a gentle robot that talks with young kids.

Before responding, decide whether to call ONE tool. Default to NO tool
unless one of these is true:
- The child asks about something visual in the real world (look).
- The child explicitly references a past conversation or stored fact
  about themselves (get_memory).
- The child reacts to a specific physical event the robot just did
  (recent_events).

Plain greetings, farewells, jokes, questions about the robot, and
small-talk about the child's feelings do NOT need a tool — use "{no_tool}".

Available tools:
{tool_list}

Respond ONLY with a single JSON object, nothing else:
{{"tool": "<tool-name-or-none>", "args": {{...}}}}

Examples:
User: "Look at my drawing!"
{{"tool": "look", "args": {{"hint": "child's drawing"}}}}

User: "Look at this!"
{{"tool": "look", "args": {{"hint": "child is showing something"}}}}

User: "What is this?"
{{"tool": "look", "args": {{"hint": "identify object"}}}}

User: "What do you see?"
{{"tool": "look", "args": {{"hint": "general view"}}}}

User: "Check this out!"
{{"tool": "look", "args": {{"hint": "child is showing something"}}}}

User: "Hi!"
{{"tool": "{no_tool}", "args": {{}}}}

User: "Good night Buddy."
{{"tool": "{no_tool}", "args": {{}}}}

User: "How many blocks are in front of you?"
{{"tool": "look", "args": {{"hint": "count blocks"}}}}

User: "Remember my favorite color?"
{{"tool": "get_memory", "args": {{"category": "preference"}}}}

User: "How are you feeling today?"
{{"tool": "{no_tool}", "args": {{}}}}
"""


def build_tool_selection_prompt(tools: Iterable[ToolSchema] = TOOL_SCHEMAS) -> str:
    """Build the system prompt that teaches the model the tool schema."""
    lines = []
    for t in tools:
        line = f"- {t.name}: {t.description}"
        if t.args_hint:
            line += f" Args: {t.args_hint}"
        lines.append(line)
    return _TOOL_SELECTION_SYSTEM_PROMPT.format(
        tool_list="\n".join(lines),
        no_tool=NO_TOOL,
    )


# ── Response parsing ────────────────────────────────────────────────


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_tool_selection(raw: str) -> dict[str, Any] | None:
    """Extract {tool, args} JSON from a raw model response.

    Tolerates leading/trailing prose, ```json fences, and minor formatting
    noise — matches the defensive parsing the conversation path already
    uses in server/app/llm/vllm_backend.py.
    """
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        return None
    candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    tool = parsed.get("tool")
    if not isinstance(tool, str):
        return None
    args = parsed.get("args", {})
    if not isinstance(args, dict):
        args = {}
    return {"tool": tool.strip().lower(), "args": args}


# ── Scoring ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class ScenarioResult:
    scenario: ToolCallScenario
    raw_response: str
    parsed: dict[str, Any] | None
    passed: bool
    failure_reason: str = ""


def score_scenario(scenario: ToolCallScenario, raw_response: str) -> ScenarioResult:
    parsed = parse_tool_selection(raw_response)
    if parsed is None:
        return ScenarioResult(
            scenario=scenario,
            raw_response=raw_response,
            parsed=None,
            passed=False,
            failure_reason="unparseable: no {tool, args} JSON in response",
        )

    actual_tool = parsed["tool"]
    if actual_tool != scenario.expected_tool:
        return ScenarioResult(
            scenario=scenario,
            raw_response=raw_response,
            parsed=parsed,
            passed=False,
            failure_reason=(
                f"wrong tool: expected {scenario.expected_tool!r}, got {actual_tool!r}"
            ),
        )

    # Arg check is a loose subset match when expected_arg_contains is set.
    if scenario.expected_arg_contains:
        actual_args = parsed["args"]
        for k, v in scenario.expected_arg_contains.items():
            if k not in actual_args:
                return ScenarioResult(
                    scenario=scenario,
                    raw_response=raw_response,
                    parsed=parsed,
                    passed=False,
                    failure_reason=f"missing expected arg {k!r}",
                )
            if isinstance(v, str) and isinstance(actual_args[k], str):
                # Tolerant string match — case + substring
                if v.lower() not in actual_args[k].lower():
                    return ScenarioResult(
                        scenario=scenario,
                        raw_response=raw_response,
                        parsed=parsed,
                        passed=False,
                        failure_reason=(
                            f"arg {k!r}: expected substring {v!r}, "
                            f"got {actual_args[k]!r}"
                        ),
                    )
            elif actual_args[k] != v:
                return ScenarioResult(
                    scenario=scenario,
                    raw_response=raw_response,
                    parsed=parsed,
                    passed=False,
                    failure_reason=(
                        f"arg {k!r}: expected {v!r}, got {actual_args[k]!r}"
                    ),
                )

    return ScenarioResult(
        scenario=scenario, raw_response=raw_response, parsed=parsed, passed=True
    )


# ── Runner ──────────────────────────────────────────────────────────


GenerateFn = Callable[[str, str], Awaitable[str]]
"""(system_prompt, user_text) -> raw response text."""


@dataclass(slots=True)
class EvalReport:
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def per_tool(self) -> dict[str, dict[str, int]]:
        """Pass/fail counts bucketed by expected tool."""
        out: dict[str, dict[str, int]] = {}
        for r in self.results:
            bucket = out.setdefault(r.scenario.expected_tool, {"pass": 0, "fail": 0})
            bucket["pass" if r.passed else "fail"] += 1
        return out


async def run_scenarios(
    generate: GenerateFn,
    scenarios: Iterable[ToolCallScenario] = SCENARIOS,
) -> EvalReport:
    """Run all scenarios through the supplied generate callable.

    `generate` is injected so tests can pass a fake and the CLI can hit a
    real server. The prompt is identical for every call — only user_text
    varies — so the caller can cache the system prompt if needed.
    """
    system_prompt = build_tool_selection_prompt()
    report = EvalReport()
    for scenario in scenarios:
        try:
            raw = await generate(system_prompt, scenario.user_text)
        except Exception as exc:
            report.results.append(
                ScenarioResult(
                    scenario=scenario,
                    raw_response="",
                    parsed=None,
                    passed=False,
                    failure_reason=f"generate raised: {type(exc).__name__}: {exc}",
                )
            )
            continue
        report.results.append(score_scenario(scenario, raw))
    return report


# ── Reporting ───────────────────────────────────────────────────────


def format_report(report: EvalReport, *, gate_threshold: float = 0.85) -> str:
    """Markdown-style summary, printable to a terminal."""
    lines: list[str] = []
    lines.append("# BFCL-style Tool-Selection Eval")
    lines.append("")
    lines.append(f"**Total:** {report.total}")
    lines.append(
        f"**Passed:** {report.passed}/{report.total}  ({report.pass_rate * 100:.1f}%)"
    )
    gate = "PASS" if report.pass_rate >= gate_threshold else "FAIL"
    lines.append(f"**Gate (≥ {gate_threshold:.0%}):** {gate}")
    lines.append("")

    lines.append("## Per-tool breakdown")
    lines.append("")
    lines.append("| Tool | Pass | Fail | Rate |")
    lines.append("|------|------|------|------|")
    for tool, stats in sorted(report.per_tool().items()):
        total = stats["pass"] + stats["fail"]
        rate = stats["pass"] / total if total else 0.0
        lines.append(f"| `{tool}` | {stats['pass']} | {stats['fail']} | {rate:.0%} |")
    lines.append("")

    failures = [r for r in report.results if not r.passed]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for r in failures:
            lines.append(f"- **{r.scenario.name}** ({r.scenario.expected_tool})")
            lines.append(f"  user: {r.scenario.user_text!r}")
            lines.append(f"  reason: {r.failure_reason}")
            if r.parsed:
                lines.append(f"  parsed: {r.parsed}")
            else:
                preview = r.raw_response.strip()[:120]
                lines.append(f"  raw: {preview!r}")
            lines.append("")
    else:
        lines.append("No failures. 🎉")

    return "\n".join(lines)
