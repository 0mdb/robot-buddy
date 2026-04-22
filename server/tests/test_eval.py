"""Unit tests for the BFCL-style eval harness.

Tests the pure logic (prompt shape, parser, scorer, runner) with fake
generate callables — no vLLM / server in the loop. The live gate is
exercised separately via `just eval-tools` against a running planner.
"""

from __future__ import annotations

import pytest

from app.eval.harness import (
    NO_TOOL,
    SCENARIOS,
    TOOL_SCHEMAS,
    EvalReport,
    ToolCallScenario,
    build_tool_selection_prompt,
    format_report,
    parse_tool_selection,
    run_scenarios,
    score_scenario,
)


# ── Prompt builder ──────────────────────────────────────────────────


class TestPrompt:
    def test_lists_every_tool(self):
        prompt = build_tool_selection_prompt()
        for t in TOOL_SCHEMAS:
            assert t.name in prompt
            assert t.description.split(".")[0] in prompt

    def test_includes_no_tool_sentinel(self):
        assert NO_TOOL in build_tool_selection_prompt()


# ── Parser ──────────────────────────────────────────────────────────


class TestParser:
    def test_extracts_plain_json(self):
        assert parse_tool_selection('{"tool": "look", "args": {}}') == {
            "tool": "look",
            "args": {},
        }

    def test_tolerates_leading_prose(self):
        raw = 'Sure, here you go: {"tool": "look", "args": {"hint": "drawing"}}'
        assert parse_tool_selection(raw) == {
            "tool": "look",
            "args": {"hint": "drawing"},
        }

    def test_lowercases_tool_name(self):
        assert parse_tool_selection('{"tool":"LOOK","args":{}}')["tool"] == "look"

    def test_returns_none_on_garbage(self):
        assert parse_tool_selection("no json here") is None

    def test_defaults_args_when_missing(self):
        parsed = parse_tool_selection('{"tool": "look"}')
        assert parsed == {"tool": "look", "args": {}}

    def test_rejects_non_string_tool(self):
        assert parse_tool_selection('{"tool": 42, "args": {}}') is None

    def test_rejects_non_object_root(self):
        assert parse_tool_selection('["look"]') is None


# ── Scorer ──────────────────────────────────────────────────────────


class TestScorer:
    def test_matches_expected_tool(self):
        s = ToolCallScenario(
            name="t", user_text="x", expected_tool="look", rationale=""
        )
        res = score_scenario(s, '{"tool":"look","args":{}}')
        assert res.passed is True

    def test_wrong_tool_fails(self):
        s = ToolCallScenario(
            name="t", user_text="x", expected_tool="look", rationale=""
        )
        res = score_scenario(s, '{"tool":"get_memory","args":{}}')
        assert res.passed is False
        assert "wrong tool" in res.failure_reason

    def test_no_tool_expectation_passes_when_none(self):
        s = ToolCallScenario(
            name="t", user_text="hi", expected_tool=NO_TOOL, rationale=""
        )
        res = score_scenario(s, '{"tool":"none","args":{}}')
        assert res.passed is True

    def test_no_tool_expectation_fails_on_eager_call(self):
        s = ToolCallScenario(
            name="t", user_text="hi", expected_tool=NO_TOOL, rationale=""
        )
        res = score_scenario(s, '{"tool":"look","args":{}}')
        assert res.passed is False

    def test_unparseable_response_fails(self):
        s = ToolCallScenario(
            name="t", user_text="x", expected_tool="look", rationale=""
        )
        res = score_scenario(s, "i have no idea")
        assert res.passed is False
        assert "unparseable" in res.failure_reason

    def test_arg_subset_match_passes(self):
        s = ToolCallScenario(
            name="t",
            user_text="x",
            expected_tool="get_memory",
            expected_arg_contains={"category": "topic"},
        )
        res = score_scenario(
            s, '{"tool":"get_memory","args":{"category":"topic","extra":"ok"}}'
        )
        assert res.passed is True

    def test_arg_substring_match(self):
        s = ToolCallScenario(
            name="t",
            user_text="x",
            expected_tool="recent_events",
            expected_arg_contains={"pattern": "ball"},
        )
        # model returned a more specific filter than we asked for — should pass
        # because "ball" is a substring of "ball.detected"
        res = score_scenario(
            s,
            '{"tool":"recent_events","args":{"pattern":"ball.detected","n":10}}',
        )
        assert res.passed is True

    def test_arg_missing_fails(self):
        s = ToolCallScenario(
            name="t",
            user_text="x",
            expected_tool="get_memory",
            expected_arg_contains={"category": "topic"},
        )
        res = score_scenario(s, '{"tool":"get_memory","args":{}}')
        assert res.passed is False
        assert "missing expected arg" in res.failure_reason


# ── Runner / report ─────────────────────────────────────────────────


class TestRunner:
    @pytest.mark.asyncio
    async def test_happy_path_all_pass(self):
        scenarios = [
            ToolCallScenario(name="a", user_text="look", expected_tool="look"),
            ToolCallScenario(name="b", user_text="hi", expected_tool=NO_TOOL),
        ]

        async def generate(_sys: str, user: str) -> str:
            if "look" in user:
                return '{"tool":"look","args":{}}'
            return '{"tool":"none","args":{}}'

        report = await run_scenarios(generate, scenarios)
        assert report.total == 2
        assert report.passed == 2
        assert report.pass_rate == 1.0

    @pytest.mark.asyncio
    async def test_generate_raises_counts_as_failure(self):
        scenarios = [
            ToolCallScenario(name="a", user_text="x", expected_tool="look"),
        ]

        async def generate(_sys: str, _user: str) -> str:
            raise RuntimeError("model died")

        report = await run_scenarios(generate, scenarios)
        assert report.passed == 0
        assert "model died" in report.results[0].failure_reason

    @pytest.mark.asyncio
    async def test_per_tool_breakdown(self):
        scenarios = [
            ToolCallScenario(name="a", user_text="x", expected_tool="look"),
            ToolCallScenario(name="b", user_text="y", expected_tool="look"),
            ToolCallScenario(name="c", user_text="z", expected_tool=NO_TOOL),
        ]

        async def generate(_sys: str, user: str) -> str:
            if user == "x":
                return '{"tool":"look","args":{}}'  # pass
            if user == "y":
                return '{"tool":"get_memory","args":{}}'  # fail
            return '{"tool":"none","args":{}}'  # pass

        report = await run_scenarios(generate, scenarios)
        per_tool = report.per_tool()
        assert per_tool["look"] == {"pass": 1, "fail": 1}
        assert per_tool[NO_TOOL] == {"pass": 1, "fail": 0}


# ── Report rendering ────────────────────────────────────────────────


class TestReport:
    def test_renders_pass_gate(self):
        report = EvalReport()
        for s in SCENARIOS[:5]:
            report.results.append(score_scenario(s, '{"tool":"none","args":{}}'))
        rendered = format_report(report, gate_threshold=0.0)
        assert "Gate (≥ 0%)" in rendered or "Gate" in rendered
        assert "PASS" in rendered

    def test_renders_fail_gate(self):
        report = EvalReport()
        for s in SCENARIOS[:5]:
            report.results.append(score_scenario(s, "no json"))
        rendered = format_report(report, gate_threshold=0.85)
        assert "FAIL" in rendered

    def test_scenarios_cover_each_tool_bucket(self):
        buckets: dict[str, int] = {}
        for s in SCENARIOS:
            buckets[s.expected_tool] = buckets.get(s.expected_tool, 0) + 1
        # Minimum coverage: each tool + NO_TOOL should have multiple scenarios
        assert buckets.get("look", 0) >= 3
        assert buckets.get("get_memory", 0) >= 3
        assert buckets.get("recent_events", 0) >= 3
        assert buckets.get(NO_TOOL, 0) >= 3
