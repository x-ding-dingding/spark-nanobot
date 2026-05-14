"""Async fan-out hub for desktop pet events."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from nanobot.pet.events import PetEvent

PetSubscriber = Callable[[PetEvent], Awaitable[None] | None]


class PetEventHub:
    """In-process pub/sub hub used by gateway, bus, and pet WebSocket clients."""

    def __init__(self) -> None:
        self._subscribers: list[PetSubscriber] = []

    def subscribe(self, callback: PetSubscriber) -> None:
        """Subscribe to future pet events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: PetSubscriber) -> None:
        """Remove a subscriber if it is registered."""
        try:
            self._subscribers.remove(callback)
        except ValueError:
            return

    async def publish(self, event: PetEvent) -> None:
        """Publish an event to all subscribers without affecting core flow."""
        for callback in list(self._subscribers):
            try:
                result = callback(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning(f"Desktop pet subscriber failed: {exc}")

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
