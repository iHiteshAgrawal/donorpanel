from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Outbound:
    recipient: str
    body: str
    subject: str | None = None
    locale: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Inbound:
    sender: str
    body: str
    channel: str
    received_at: str
    # Who spoke and where to answer are the same thing in a one to one chat and
    # different in a group. Identity follows the speaker, delivery follows the room.
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.reply_to = self.reply_to or self.sender


@dataclass
class DeliveryResult:
    delivered: bool
    channel: str
    reference: str | None = None
    error: str | None = None


class Channel(ABC):
    name: str

    @abstractmethod
    async def send(self, message: Outbound) -> DeliveryResult: ...

    @abstractmethod
    async def poll(self) -> list[Inbound]: ...

    @abstractmethod
    def available(self) -> bool: ...
