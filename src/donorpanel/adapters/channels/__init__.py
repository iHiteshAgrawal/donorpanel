from donorpanel.adapters.channels.base import Channel, DeliveryResult, Inbound, Outbound
from donorpanel.adapters.channels.console import ConsoleChannel
from donorpanel.adapters.channels.email import EmailChannel
from donorpanel.adapters.channels.telegram import TelegramChannel

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
