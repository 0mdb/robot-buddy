"""conversation.quiet_mode: no unprompted remarks; battery/safety lines still play."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from supervisor.api.param_registry import create_default_registry
from supervisor.core.event_bus import PlannerEvent
from supervisor.core.tick_loop import TickLoop, _essential_speech
from supervisor.messages.types import TTS_CMD_SPEAK


def _loop(quiet: bool) -> TickLoop:
    workers = MagicMock()
    workers.send_to = AsyncMock(return_value=True)
    reg = create_default_registry()
    ok, msg = reg.set("conversation.quiet_mode", quiet)
    assert ok, msg
    return TickLoop(reflex=None, face=None, workers=workers, param_registry=reg)


def _spoken(loop: TickLoop) -> list[str]:
    return [
        c.args[2]["text"]
        for c in loop._workers.send_to.call_args_list
        if len(c.args) >= 3 and c.args[0] == "tts" and c.args[1] == TTS_CMD_SPEAK
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("quiet", [False, True])
async def test_wander_remark_only_when_not_quiet(quiet):
    loop = _loop(quiet)
    await loop._emit_worker_actions(
        1000.0, [PlannerEvent("mode.changed", {"to": "WANDER"}, 1000.0)]
    )
    assert bool(_spoken(loop)) is (not quiet)
    if quiet:
        assert loop.world.say_dropped_reason["quiet_mode"] == 1


@pytest.mark.asyncio
async def test_battery_critical_speaks_in_quiet_mode():
    loop = _loop(True)
    evt = PlannerEvent("power.low_soc_raised", {"severity": "critical"}, 1000.0)
    await loop._emit_worker_actions(1000.0, [evt])
    assert _spoken(loop)


@pytest.mark.asyncio
async def test_direct_say_still_works_in_quiet_mode():
    # Dashboard "say" and conversation speech do not go through the quiet filter.
    loop = _loop(True)
    await loop._enqueue_say("hello", source="api", priority=1)
    assert _spoken(loop) == ["hello"]


def test_essential_speech_keys():
    assert _essential_speech("fault.raised")
    assert _essential_speech("power.undervoltage_raised")
    assert _essential_speech("held:power.low_soc_raised:critical")
    assert not _essential_speech("vision.ball_acquired")
    assert not _essential_speech("held:face.touch.boop")
    assert not _essential_speech("mode.changed")


@pytest.mark.asyncio
@pytest.mark.parametrize("quiet", [False, True])
async def test_planner_say_only_when_not_quiet(quiet):
    loop = _loop(quiet)
    loop._scheduler.pop_due_actions = MagicMock(
        return_value=[{"action": "say", "text": "I wonder what's over there."}]
    )
    await loop._emit_worker_actions(1000.0, [])
    assert bool(_spoken(loop)) is (not quiet)
