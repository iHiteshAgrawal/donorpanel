import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ..config import config
from .base import Channel, DeliveryResult, Inbound, Outbound


class EmailChannel(Channel):
    name = "email"

    def __init__(self, sender: str | None = None, region: str | None = None) -> None:
        self.sender = sender or config.ses_sender_email
        self.region = region or config.aws_region
        self._client = None

    def available(self) -> bool:
        return bool(self.sender)

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("sesv2", region_name=self.region)
        return self._client

    async def send(self, message: Outbound) -> DeliveryResult:
        if not self.available():
            return DeliveryResult(delivered=False, channel=self.name, error="missing SES_SENDER_EMAIL")
        try:
            response = self.client.send_email(
                FromEmailAddress=self.sender,
                Destination={"ToAddresses": [message.recipient]},
                Content={
                    "Simple": {
                        "Subject": {"Data": message.subject or "DonorLink"},
                        "Body": {"Text": {"Data": message.body}},
                    }
                },
            )
        except (BotoCoreError, ClientError) as exc:
            return DeliveryResult(delivered=False, channel=self.name, error=str(exc)[:200])
        return DeliveryResult(delivered=True, channel=self.name, reference=response.get("MessageId"))

    async def poll(self) -> list[Inbound]:
        return []
