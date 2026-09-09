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
    metadata: dict[str, Any] = field(default_factory=dict)


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
