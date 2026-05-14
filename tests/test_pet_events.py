from datetime import datetime

from nanobot.pet.events import (
    PetDirection,
    PetEvent,
    PetEventType,
    PetStatus,
    should_show_bubble,
)


def test_pet_event_serializes_to_wire_protocol() -> None:
    event = PetEvent(
        type=PetEventType.STATUS,
        status=PetStatus.WORKING,
        session_key="telegram:123",
        channel="telegram",
        chat_id="123",
        direction=PetDirection.INBOUND,
        text="hello",
        timestamp=datetime(2026, 5, 13, 10, 30, 0),
    )

    assert event.to_dict() == {
        "type": "pet.status",
        "status": "working",
        "sessionKey": "telegram:123",
        "channel": "telegram",
        "chatId": "123",
        "direction": "inbound",
        "text": "hello",
        "timestamp": "2026-05-13T10:30:00",
    }


def test_high_signal_filter_shows_short_replies_and_hides_long_normal_text() -> None:
    assert should_show_bubble("好的，已经记下。", show_mode="high_signal", max_chars=160) is True

    long_normal = "这是一个普通说明。" * 80
    assert should_show_bubble(long_normal, show_mode="high_signal", max_chars=160) is False


def test_high_signal_filter_allows_explicit_and_attention_messages() -> None:
    long_attention = "需要你确认权限后我才能继续。" + ("详细说明" * 80)

    assert should_show_bubble(long_attention, show_mode="high_signal", max_chars=160) is True
    assert (
        should_show_bubble(
            "normal long text" * 80,
            show_mode="high_signal",
            max_chars=160,
            metadata={"petVisible": True},
        )
        is True
    )
    assert (
        should_show_bubble(
            "short but hidden",
            show_mode="high_signal",
            max_chars=160,
            metadata={"petVisible": False},
        )
        is False
    )
