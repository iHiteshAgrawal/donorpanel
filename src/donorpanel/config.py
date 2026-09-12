import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "ap-southeast-2"))
    bedrock_model_id: str | None = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID") or None)
    model_provider: str = field(
        default_factory=lambda: os.getenv("MODEL_PROVIDER", "bedrock").strip().lower())
    openrouter_api_key: str | None = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY") or None)
    openrouter_model_id: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL_ID", "anthropic/claude-sonnet-4-5"))
    telegram_bot_token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN") or None)
    telegram_allowed_chat_ids: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            c.strip() for c in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if c.strip()
        )
    )
    telegram_bot_username: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_USERNAME", "donorpanelbot"))
    telegram_demo_chat_id: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_DEMO_CHAT_ID") or None)
    ses_sender_email: str | None = field(default_factory=lambda: os.getenv("SES_SENDER_EMAIL") or None)
    ses_demo_email: str | None = field(default_factory=lambda: os.getenv("SES_DEMO_EMAIL") or None)
    bucket: str | None = field(default_factory=lambda: os.getenv("DONORPANEL_BUCKET") or None)
    agentcore_runtime_arn: str | None = field(
        default_factory=lambda: os.getenv("AGENTCORE_RUNTIME_ARN") or None)
    telegram_webhook_secret: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_WEBHOOK_SECRET") or None)
    agentcore_memory_id: str | None = field(
        default_factory=lambda: os.getenv("AGENTCORE_MEMORY_ID") or None)
    cognito_pool_id: str | None = field(default_factory=lambda: os.getenv("COGNITO_POOL_ID") or None)
    cognito_client_id: str | None = field(default_factory=lambda: os.getenv("COGNITO_CLIENT_ID") or None)
    local_root: str = field(default_factory=lambda: os.getenv("DONORPANEL_LOCAL_ROOT", "data/local"))
    env: str = field(default_factory=lambda: os.getenv("DONORPANEL_ENV", "local"))


config = Config()
