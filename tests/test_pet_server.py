import json

import pytest
import websockets

from nanobot.pet.events import PetEvent, PetEventType, PetStatus
from nanobot.pet.hub import PetEventHub
from nanobot.pet.server import PetWebSocketServer


@pytest.mark.asyncio
async def test_pet_websocket_server_broadcasts_events() -> None:
    hub = PetEventHub()
    server = PetWebSocketServer(hub=hub, host="127.0.0.1", port=0)
    await server.start()
    try:
        async with websockets.connect(f"ws://127.0.0.1:{server.bound_port}") as ws:
            await hub.publish(
                PetEvent.status(
                    status=PetStatus.WORKING,
                    channel="telegram",
                    chat_id="c1",
                    direction="inbound",
                    text="hello",
                )
            )
            payload = json.loads(await ws.recv())

        assert payload["type"] == PetEventType.STATUS.value
        assert payload["status"] == PetStatus.WORKING.value
        assert payload["sessionKey"] == "telegram:c1"
    finally:
        await server.stop()
