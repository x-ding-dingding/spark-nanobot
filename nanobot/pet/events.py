"""Desktop pet event models and display filtering."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any


class PetStatus(str, Enum):
    """Small visual state set for the desktop pet."""

    IDLE = "idle"
    WORKING = "working"
    WARNING = "warning"
    DRAGGING = "dragging"


class PetEventType(str, Enum):
    """Wire event types sent to pet clients."""

    STATUS = "pet.status"
    BUBBLE = "pet.bubble"
    ERROR = "pet.error"


class PetDirection(str, Enum):
    """Message direction for pet events."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"


ATTENTION_KEYWORDS = (
    "attention",
    "approval",
    "approve",
    "permission",
    "needs",
    "need you",
    "error",
    "failed",
    "failure",
    "sorry",
    "warning",
    "confirm",
    "requires",
    "需要",
    "确认",
    "权限",
    "错误",
    "失败",
    "抱歉",
    "提醒",
    "注意",
)


class PetEvent:
    """A normalized event for desktop pet UI clients."""

    def __init__(
        self,
        *,
        type: PetEventType,
        status: PetStatus,
        session_key: str,
        channel: str,
        chat_id: str,
        direction: PetDirection,
        text: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        self.type = type
        self.status = status
        self.session_key = session_key
        self.channel = channel
        self.chat_id = chat_id
        self.direction = direction
        self.text = text
        self.timestamp = timestamp or datetime.now()

    @classmethod
    def status(
        cls,
        *,
        status: PetStatus,
        channel: str,
        chat_id: str,
        direction: str | PetDirection,
        text: str | None = None,
        timestamp: datetime | None = None,
    ) -> "PetEvent":
        return cls(
            type=PetEventType.STATUS,
            status=status,
            session_key=_session_key(channel, chat_id),
            channel=channel,
            chat_id=chat_id,
            direction=_direction(direction),
            text=text,
            timestamp=timestamp or datetime.now(),
        )

    @classmethod
    def bubble(
        cls,
        *,
        status: PetStatus = PetStatus.IDLE,
        channel: str,
        chat_id: str,
        direction: str | PetDirection = PetDirection.OUTBOUND,
        text: str,
        timestamp: datetime | None = None,
    ) -> "PetEvent":
        return cls(
            type=PetEventType.BUBBLE,
            status=status,
            session_key=_session_key(channel, chat_id),
            channel=channel,
            chat_id=chat_id,
            direction=_direction(direction),
            text=text,
            timestamp=timestamp or datetime.now(),
        )

    @classmethod
    def error(
        cls,
        *,
        channel: str,
        chat_id: str,
        direction: str | PetDirection = PetDirection.SYSTEM,
        text: str,
        timestamp: datetime | None = None,
    ) -> "PetEvent":
        return cls(
            type=PetEventType.ERROR,
            status=PetStatus.WARNING,
            session_key=_session_key(channel, chat_id),
            channel=channel,
            chat_id=chat_id,
            direction=_direction(direction),
            text=text,
            timestamp=timestamp or datetime.now(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the public WebSocket payload shape."""
        return {
            "type": self.type.value,
            "status": self.status.value,
            "sessionKey": self.session_key,
            "channel": self.channel,
            "chatId": self.chat_id,
            "direction": self.direction.value,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
        }


def should_show_bubble(
    content: str | None,
    *,
    show_mode: str = "high_signal",
    max_chars: int = 160,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Return whether a message should be surfaced in the pet bubble."""
    text = (content or "").strip()
    if not text:
        return False

    meta = metadata or {}
    explicit = meta.get("petVisible", meta.get("pet_visible"))
    if explicit is False:
        return False
    if explicit is True:
        return True

    normalized_mode = (show_mode or "high_signal").strip().lower()
    if normalized_mode in {"off", "none", "hidden"}:
        return False
    if normalized_mode in {"all", "always"}:
        return True
    if normalized_mode == "explicit":
        return False

    if len(text) <= max_chars:
        return True

    lowered = text.lower()
    return any(keyword in lowered for keyword in ATTENTION_KEYWORDS)


def bubble_text(content: str | None, *, max_chars: int = 160) -> str:
    """Trim message text for compact pet bubbles."""
    text = " ".join((content or "").split())
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "..."


def _session_key(channel: str, chat_id: str) -> str:
    return f"{channel}:{chat_id}"


def _direction(value: str | PetDirection) -> PetDirection:
    if isinstance(value, PetDirection):
        return value
    return PetDirection(value)
