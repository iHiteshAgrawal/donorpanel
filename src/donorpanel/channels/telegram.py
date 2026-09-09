from datetime import datetime, timezone

import httpx

from ..config import config
from .base import Channel, DeliveryResult, Inbound, Outbound

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or config.telegram_bot_token
        self._offset: int | None = None

    def available(self) -> bool:
        return bool(self.token)

    async def send(self, message: Outbound) -> DeliveryResult:
        if not self.available():
            return DeliveryResult(delivered=False, channel=self.name, error="missing TELEGRAM_BOT_TOKEN")
        url = API.format(token=self.token, method="sendMessage")
        payload = {"chat_id": message.recipient, "text": message.body}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=payload)
        if response.status_code != 200:
            return DeliveryResult(delivered=False, channel=self.name, error=response.text[:200])
        result = response.json().get("result", {})
        return DeliveryResult(delivered=True, channel=self.name, reference=str(result.get("message_id")))

    async def poll(self) -> list[Inbound]:
        if not self.available():
            return []
        url = API.format(token=self.token, method="getUpdates")
        params = {"timeout": 0}
        if self._offset is not None:
            params["offset"] = self._offset
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
        if response.status_code != 200:
            return []
        updates = response.json().get("result", [])
        inbound: list[Inbound] = []
        for update in updates:
            self._offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg or "text" not in msg:
                continue
            chat_id = str(msg["chat"]["id"])
            if config.telegram_allowed_chat_ids and chat_id not in config.telegram_allowed_chat_ids:
                continue
            inbound.append(
                Inbound(
                    sender=chat_id,
                    body=msg["text"],
                    channel=self.name,
                    received_at=datetime.fromtimestamp(msg["date"], tz=timezone.utc).isoformat(),
                    metadata={"update_id": update["update_id"]},
                )
            )
        return inbound
