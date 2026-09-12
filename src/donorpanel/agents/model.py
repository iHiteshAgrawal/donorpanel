from botocore.config import Config as BotoConfig
from strands.event_loop._retry import ModelRetryStrategy
from strands.models import BedrockModel
from strands.models.model import Model

from donorpanel.config import config

OPENROUTER_URL = "https://openrouter.ai/api/v1"

# botocore counts max_attempts as retries on top of the first call, so 1 means two attempts
# in total. Strands defaults to four retries with backoff, and that default is the throttle
# multiplier: 196 real invocations produced 3,737 throttle events. A per-minute throttle
# clears on one retry and a daily token cap never does, so further attempts only spend more
# of the quota that is already gone. The cap once cost 175 seconds per call, long enough for
# Lambda to be killed at 300s, which handed Telegram a 503 and made Telegram redeliver.
RETRIES = 1
READ_TIMEOUT = 45


def client_config() -> BotoConfig:
    # A fresh object each time. botocore rewrites the config it is given in place, turning
    # max_attempts into total_max_attempts, so a shared instance is mutated by whoever
    # builds a client from it first.
    return BotoConfig(retries={"max_attempts": RETRIES, "mode": "standard"},
                      connect_timeout=5, read_timeout=READ_TIMEOUT)


def bedrock() -> BedrockModel:
    return BedrockModel(model_id=config.bedrock_model_id,
                        region_name=config.aws_region,
                        boto_client_config=client_config())


def openrouter() -> Model:
    from strands.models.openai import OpenAIModel

    return OpenAIModel(
        client_args={"api_key": config.openrouter_api_key,
                     "base_url": OPENROUTER_URL,
                     "timeout": READ_TIMEOUT,
                     # The OpenAI client retries too, and stacking its retries under the
                     # Strands ones is what made a Bedrock throttle take 152 seconds.
                     "max_retries": RETRIES},
        model_id=config.openrouter_model_id,
    )


def llm() -> Model:
    if config.model_provider == "openrouter":
        if not config.openrouter_api_key:
            raise RuntimeError("model provider is openrouter but OPENROUTER_API_KEY is unset")
        return openrouter()
    return bedrock()


# Strands retries a throttle again above the client, and this layer is the expensive one:
# six attempts sleeping 4, 8, 16, 32 then 64 seconds, so a throttled call took 152 seconds
# to fail. Nobody waiting on a chat message waits two and a half minutes, and a daily token
# cap is still there at the end of it. Two attempts two seconds apart, then say so.
def retries() -> ModelRetryStrategy:
    return ModelRetryStrategy(max_attempts=2, initial_delay=2, max_delay=4)
