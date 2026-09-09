import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    bedrock_model_id: str | None = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID") or None)
    telegram_bot_token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN") or None)
    telegram_allowed_chat_ids: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            c.strip() for c in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()
        )
    )
    ses_sender_email: str | None = field(default_factory=lambda: os.getenv("SES_SENDER_EMAIL") or None)
    bucket: str | None = field(default_factory=lambda: os.getenv("DONORPANEL_BUCKET") or None)
    local_root: str = field(default_factory=lambda: os.getenv("DONORPANEL_LOCAL_ROOT", "data/local"))
    env: str = field(default_factory=lambda: os.getenv("DONORPANEL_ENV", "local"))


config = Config()
