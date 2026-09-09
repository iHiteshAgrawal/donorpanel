from .base import Channel, DeliveryResult, Inbound, Outbound
from .console import ConsoleChannel
from .email import EmailChannel
from .telegram import TelegramChannel

__all__ = [
    "Channel",
    "ConsoleChannel",
    "DeliveryResult",
    "EmailChannel",
    "Inbound",
    "Outbound",
    "TelegramChannel",
]


def registry() -> dict[str, Channel]:
    channels: list[Channel] = [ConsoleChannel(), TelegramChannel(), EmailChannel()]
    return {c.name: c for c in channels if c.available()}
