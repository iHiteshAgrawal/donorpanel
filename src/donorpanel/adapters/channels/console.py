from donorpanel.adapters.channels.base import Channel, DeliveryResult, Inbound, Outbound


class ConsoleChannel(Channel):
    name = "console"

    def __init__(self) -> None:
        self.sent: list[Outbound] = []

    async def send(self, message: Outbound) -> DeliveryResult:
        self.sent.append(message)
        header = f"[{self.name} -> {message.recipient}]"
        if message.subject:
            header += f" {message.subject}"
        print(f"{header}\n{message.body}\n")
        return DeliveryResult(delivered=True, channel=self.name, reference=str(len(self.sent)))

    async def poll(self) -> list[Inbound]:
        return []

    def available(self) -> bool:
        return True
