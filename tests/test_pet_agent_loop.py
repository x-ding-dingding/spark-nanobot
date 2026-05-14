from pathlib import Path
from typing import Any

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.pet.events import PetEventType, PetStatus
from nanobot.pet.hub import PetEventHub
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.session.manager import SessionManager


class FakeProvider(LLMProvider):
    def __init__(self, response: LLMResponse | None = None, error: Exception | None = None):
        super().__init__(api_key="fake")
        self.response = response
        self.error = error

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response

    def get_default_model(self) -> str:
        return "fake-model"


def _make_agent(tmp_path: Path, provider: LLMProvider, hub: PetEventHub) -> AgentLoop:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=workspace,
        session_manager=SessionManager(workspace),
        pet_hub=hub,
        pet_show_mode="high_signal",
        pet_bubble_max_chars=160,
    )


@pytest.mark.asyncio
async def test_agent_loop_emits_working_bubble_idle_for_short_reply(tmp_path) -> None:
    events = []
    hub = PetEventHub()
    hub.subscribe(lambda event: events.append(event))
    agent = _make_agent(tmp_path, FakeProvider(LLMResponse(content="短回复")), hub)

    response = await agent.process_direct("hello", channel="telegram", chat_id="c1")

    assert response == "短回复"
    assert [(event.type, event.status) for event in events] == [
        (PetEventType.STATUS, PetStatus.WORKING),
        (PetEventType.BUBBLE, PetStatus.IDLE),
        (PetEventType.STATUS, PetStatus.IDLE),
    ]
    assert events[1].text == "短回复"


@pytest.mark.asyncio
async def test_agent_loop_suppresses_long_normal_reply_bubble(tmp_path) -> None:
    events = []
    hub = PetEventHub()
    hub.subscribe(lambda event: events.append(event))
    long_reply = "普通说明" * 100
    agent = _make_agent(tmp_path, FakeProvider(LLMResponse(content=long_reply)), hub)

    response = await agent.process_direct("hello", channel="telegram", chat_id="c2")

    assert response == long_reply
    assert [(event.type, event.status) for event in events] == [
        (PetEventType.STATUS, PetStatus.WORKING),
        (PetEventType.STATUS, PetStatus.IDLE),
    ]


@pytest.mark.asyncio
async def test_agent_loop_emits_error_event_when_processing_fails(tmp_path) -> None:
    events = []
    hub = PetEventHub()
    hub.subscribe(lambda event: events.append(event))
    agent = _make_agent(tmp_path, FakeProvider(error=RuntimeError("boom")), hub)

    with pytest.raises(RuntimeError, match="boom"):
        await agent.process_direct("hello", channel="telegram", chat_id="c3")

    assert [(event.type, event.status) for event in events] == [
        (PetEventType.STATUS, PetStatus.WORKING),
        (PetEventType.ERROR, PetStatus.WARNING),
    ]
    assert "boom" in (events[1].text or "")
