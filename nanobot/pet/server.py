"""WebSocket server for desktop pet clients."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from nanobot.pet.events import PetEvent
from nanobot.pet.hub import PetEventHub


class PetWebSocketServer:
    """Broadcast pet events to local WebSocket clients."""

    def __init__(self, hub: PetEventHub, host: str = "127.0.0.1", port: int = 18791):
        self.hub = hub
        self.host = host
        self.port = port
        self.bound_port = port
        self._server: Any = None
        self._clients: set[Any] = set()

    async def start(self) -> None:
        """Start accepting WebSocket clients."""
        import websockets

        self._server = await websockets.serve(self._handle_client, self.host, self.port)
        sockets = getattr(self._server, "sockets", None) or []
        if sockets:
            self.bound_port = int(sockets[0].getsockname()[1])
        self.hub.subscribe(self._broadcast)
        logger.info(f"Desktop pet WebSocket listening on ws://{self.host}:{self.bound_port}")

    async def stop(self) -> None:
        """Stop the server and close all clients."""
        self.hub.unsubscribe(self._broadcast)
        for client in list(self._clients):
            await client.close()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, websocket: Any, *args: Any) -> None:
        self._clients.add(websocket)
        logger.info("Desktop pet client connected")
        try:
            async for _ in websocket:
                pass
        finally:
            self._clients.discard(websocket)
            logger.info("Desktop pet client disconnected")

    async def _broadcast(self, event: PetEvent) -> None:
        if not self._clients:
            return
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        dead_clients: list[Any] = []
        for client in list(self._clients):
            try:
                await client.send(payload)
            except Exception as exc:
                logger.warning(f"Failed to send desktop pet event: {exc}")
                dead_clients.append(client)
        for client in dead_clients:
            self._clients.discard(client)
