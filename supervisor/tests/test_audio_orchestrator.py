from __future__ import annotations

import pytest

from supervisor.devices.audio_orchestrator import AudioOrchestrator, PLANNER_SPEECH_QUEUE_MAX


class _FakeConversation:
    connected = True
    speaking = False
    ptt_enabled = False

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def cancel(self) -> None:
        return None

    async def set_ptt_enabled(self, enabled: bool) -> None:
        self.ptt_enabled = enabled


def test_enqueue_speech_is_bounded():
    ao = AudioOrchestrator("http://127.0.0.1:8100")
    for i in range(PLANNER_SPEECH_QUEUE_MAX):
        assert ao.enqueue_speech(f"line {i}")
    assert not ao.enqueue_speech("overflow")


@pytest.mark.asyncio
async def test_ptt_enable_preempts_planner_speech(monkeypatch):
    ao = AudioOrchestrator("http://127.0.0.1:8100")
    ao._conversation = _FakeConversation()  # type: ignore[assignment]

    calls: list[str] = []

    async def _cancel() -> None:
        calls.append("cancel")

    async def _set_ptt(enabled: bool) -> None:
        calls.append(f"ptt={enabled}")

    monkeypatch.setattr(ao, "cancel_planner_speech", _cancel)
    monkeypatch.setattr(ao._conversation, "set_ptt_enabled", _set_ptt)

    await ao.set_ptt_enabled(True)
    assert calls == ["cancel", "ptt=True"]

