from datetime import datetime, timezone

import httpx

from donorpanel.adapters.channels.base import Channel, DeliveryResult, Inbound, Outbound
from donorpanel.config import config

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

    def webhook_update(self, update: dict) -> Inbound | None:
        """Same shaping as poll(), for updates Telegram pushes to us instead.

        Webhooks are how this runs deployed: polling needs one process forever, which
        is the opposite of what a serverless deployment is for. poll() stays for local
        development where there is no public endpoint to point Telegram at."""
        msg = update.get("message") or {}
        if "text" not in msg:
            return None
        author = msg.get("from") or {}
        if author.get("is_bot"):
            return None
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        if config.telegram_allowed_chat_ids and chat_id not in config.telegram_allowed_chat_ids:
            return None
        return Inbound(
            sender=str(author.get("id") or chat_id),
            reply_to=chat_id,
            body=msg["text"],
            channel=self.name,
            received_at=datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc).isoformat(),
            metadata={"update_id": update.get("update_id"), "name": author.get("first_name")},
        )

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
            author = msg.get("from") or {}
            if author.get("is_bot"):
                continue
            # chat.id is the room. In a group that is shared by everyone in it, so
            # keying identity on it would give a whole group one donor record and one
            # memory. from.id is the person who actually typed.
            speaker = str(author.get("id") or chat_id)
            if config.telegram_allowed_chat_ids and chat_id not in config.telegram_allowed_chat_ids:
                continue
            inbound.append(
                Inbound(
                    sender=speaker,
                    reply_to=chat_id,
                    body=msg["text"],
                    channel=self.name,
                    received_at=datetime.fromtimestamp(msg["date"], tz=timezone.utc).isoformat(),
                    metadata={"update_id": update["update_id"],
                              "name": author.get("first_name")},
                )
            )
        return inbound
