import pytest

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.pet.events import PetStatus
from nanobot.pet.hub import PetEventHub


@pytest.mark.asyncio
async def test_message_bus_mirrors_inbound_without_consuming_queue() -> None:
    events = []
    hub = PetEventHub()
    hub.subscribe(lambda event: events.append(event))
    bus = MessageBus(pet_hub=hub)

    await bus.publish_inbound(
        InboundMessage(
            channel="telegram",
            sender_id="u1",
            chat_id="c1",
            content="hello",
        )
    )

    queued = await bus.consume_inbound()
    assert queued.content == "hello"
    assert len(events) == 1
    assert events[0].type.value == "pet.status"
    assert events[0].status == PetStatus.WORKING
    assert events[0].session_key == "telegram:c1"
    assert events[0].direction.value == "inbound"


@pytest.mark.asyncio
async def test_message_bus_mirrors_high_signal_outbound_without_consuming_queue() -> None:
    events = []
    hub = PetEventHub()
    hub.subscribe(lambda event: events.append(event))
    bus = MessageBus(pet_hub=hub, pet_show_mode="high_signal", pet_bubble_max_chars=160)

    await bus.publish_outbound(
        OutboundMessage(channel="telegram", chat_id="c1", content="短回复")
    )

    queued = await bus.consume_outbound()
    assert queued.content == "短回复"
    assert len(events) == 1
    assert events[0].type.value == "pet.bubble"
    assert events[0].status == PetStatus.IDLE
    assert events[0].text == "短回复"


@pytest.mark.asyncio
async def test_message_bus_skips_outbound_bubble_already_emitted_by_agent() -> None:
    events = []
    hub = PetEventHub()
    hub.subscribe(lambda event: events.append(event))
    bus = MessageBus(pet_hub=hub)

    await bus.publish_outbound(
        OutboundMessage(
            channel="telegram",
            chat_id="c1",
            content="短回复",
            metadata={"_pet_bubble_emitted": True},
        )
    )

    assert await bus.consume_outbound()
    assert events == []
