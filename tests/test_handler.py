import json

import pytest

from donorpanel.entrypoints import lambda_fn as handler

with open("tests/fixtures/telegram-update.json") as fixture:
    UPDATE = json.load(fixture)


@pytest.fixture(autouse=True)
def open_to_everyone(monkeypatch):
    """.env pins the allow list to one chat and now carries a webhook secret. Both are
    real production settings and both would reject every fixture here."""
    from dataclasses import replace

    from donorpanel.adapters.channels import telegram as tg
    monkeypatch.setattr(tg, "config", replace(tg.config, telegram_allowed_chat_ids=()))
    monkeypatch.setattr(handler, "config",
                        replace(handler.config, telegram_webhook_secret=None))


def http(body, headers=None, path="/webhook"):
    return {"rawPath": path, "headers": headers or {}, "body": json.dumps(body)}


def test_webhook_answers_and_sends(monkeypatch):
    sent, asked = [], []
    monkeypatch.setattr(handler, "ask_asha",
                        lambda s, p, c, **kw: asked.append((s, p)) or {"text": "hello back"})
    monkeypatch.setattr(handler, "_send", lambda ch, to, body: sent.append((ch, to, body)))
    out = handler.handler(http(UPDATE))
    assert out["statusCode"] == 200
    assert asked == [("8911353204", "Hi, what is this?")]
    assert sent == [("telegram", "8911353204", "hello back")]


def test_a_launch_triggers_a_second_invocation(monkeypatch):
    later = []
    monkeypatch.setattr(handler, "ask_asha",
                        lambda *a, **kw: {"text": "searching", "launch": {"patient_id": "p-1"}})
    monkeypatch.setattr(handler, "_send", lambda *a: None)
    monkeypatch.setattr(handler, "_self_invoke", later.append)
    handler.reply({"sender": "8911353204", "text": "hi", "reply_to": "8911353204",
                   "channel": "telegram"})
    assert later[0]["mode"] == "search"
    assert later[0]["ask"] == {"patient_id": "p-1"}


def test_the_webhook_acknowledges_without_calling_the_model(monkeypatch):
    """API Gateway caps an HTTP API integration at 30s, and a model call runs past it. The
    webhook must hand Telegram a 200 immediately, or Telegram reads the 503 as a cue to
    redeliver and does so every couple of minutes indefinitely."""
    queued, asked = [], []
    monkeypatch.setattr(handler, "_self_invoke", queued.append)
    monkeypatch.setattr(handler, "ask_asha", lambda *a, **kw: asked.append(1) or {})

    out = handler.handler(http(UPDATE))

    assert out["statusCode"] == 200
    assert asked == []
    assert queued[0]["mode"] == "reply"
    assert queued[0]["text"] == "Hi, what is this?"
    assert queued[0]["sender"] == "8911353204"


def test_the_wrong_secret_is_refused(monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr(handler, "config", replace(handler.config,
                                                   telegram_webhook_secret="letmein"))
    monkeypatch.setattr(handler, "_send", lambda *a: None)
    # Without this the accepted case runs the real agent, calling AgentCore and Bedrock
    # for a test about a header. That was 328 of this file's 344 seconds.
    monkeypatch.setattr(handler, "ask_asha", lambda *a, **kw: {"text": "hello back"})
    assert handler.handler(http(UPDATE, {"X-Telegram-Bot-Api-Secret-Token": "nope"}))["statusCode"] == 403
    assert handler.handler(http(UPDATE, {"X-Telegram-Bot-Api-Secret-Token": "letmein"}))["statusCode"] != 403


def test_a_bot_message_is_ignored_without_calling_the_agent(monkeypatch):
    called = []
    monkeypatch.setattr(handler, "ask_asha", lambda *a, **kw: called.append(1) or {})
    update = json.loads(json.dumps(UPDATE))
    update["message"]["from"]["is_bot"] = True
    assert handler.handler(http(update))["body"] == "ignored"
    assert called == []


def test_public_path_returns_the_pool(monkeypatch):
    monkeypatch.setattr(handler, "public_pool", lambda: {"donors": 7})
    out = handler.handler({"rawPath": "/api/public", "headers": {}})
    assert json.loads(out["body"]) == {"donors": 7}
    assert out["headers"]["access-control-allow-origin"] == "*"


def test_tick_mode_runs_the_forecast(monkeypatch):
    monkeypatch.setattr(handler.forecast, "tick", lambda repo: {"opened": [], "due": 0})
    monkeypatch.setattr(handler.pool, "ensure", lambda: object())
    assert handler.handler({"mode": "tick"})["due"] == 0


def test_a_crash_never_reaches_telegram_as_a_500(monkeypatch):
    # Telegram answers a 500 by sending the same message again, forever.
    def boom(*a, **k):
        raise RuntimeError("bedrock is down")
    monkeypatch.setattr(handler, "ask_asha", boom)
    assert handler.handler(http(UPDATE))["statusCode"] == 200


def test_session_id_satisfies_the_runtime_length_rule():
    from donorpanel.entrypoints.runtime import session_id

    made = session_id("8911353204")
    assert 33 <= len(made) <= 256
    assert made == session_id("8911353204")
    assert made != session_id("8911353205")


def test_reasoning_never_reaches_the_person():
    """Nova emits <thinking> inline, in the same string as the reply."""
    from donorpanel.services.chat import spoken

    assert spoken("<thinking> I should check </thinking>\nYes, O+ works.") == "Yes, O+ works."
    assert spoken("<THINKING>x</THINKING>Hello") == "Hello"
    assert spoken("<thinking>never closed. Hello") == "never closed. Hello"
    assert spoken("Plain reply") == "Plain reply"
    assert spoken("<thinking>a</thinking>One<thinking>b</thinking>Two") == "OneTwo"


def test_markdown_never_reaches_a_chat_bubble():
    """Telegram shows the characters, so asterisks and dashes arrive literally. Nova 2
    reaches for bullets even when the prompt forbids them."""
    from donorpanel.services.chat import plain

    assert plain("I need:\n- Name\n- City") == "I need: Name. City."
    assert plain("Hello **Hitesh**, you are _registered_.") == "Hello Hitesh, you are registered."
    assert plain("* one\n* two") == "one. two."
    assert plain("One plain line.") == "One plain line."
    # A hyphen inside a sentence is not a bullet.
    assert plain("O-negative is rare") == "O-negative is rare"


def no_runtime(monkeypatch):
    # config is a frozen dataclass, so it is replaced rather than mutated. Without this
    # the test would try the real Runtime ARN from .env.
    from dataclasses import replace
    monkeypatch.setattr(handler, "config",
                        replace(handler.config, agentcore_runtime_arn=None,
                                telegram_webhook_secret=None))


def test_a_throttled_model_still_gets_a_reply(monkeypatch):
    """A throttle used to mean total silence: the Lambda sat through four backoff retries
    until it was killed at 300s, so it never replied and never returned, and Telegram read
    the resulting 503 as an instruction to send the same message again."""
    sent = []
    from donorpanel.services import chat as chat_module

    def throttled(*a, **k):
        raise RuntimeError("An error occurred (ThrottlingException) when calling ConverseStream")

    no_runtime(monkeypatch)
    monkeypatch.setattr(chat_module, "reply", throttled)
    monkeypatch.setattr(handler, "_send", lambda ch, to, body: sent.append(body))
    out = handler.handler(http(UPDATE))

    assert out["statusCode"] == 200
    assert len(sent) == 1
    assert "more messages than I can answer" in sent[0]


def test_an_unexpected_failure_also_gets_a_reply(monkeypatch):
    """A fault that is not a throttle must not tell the person to try again shortly,
    because for a genuine bug that is untrue."""
    sent = []
    from donorpanel.services import chat as chat_module

    no_runtime(monkeypatch)
    monkeypatch.setattr(chat_module, "reply",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk on fire")))
    monkeypatch.setattr(handler, "_send", lambda ch, to, body: sent.append(body))
    handler.handler(http(UPDATE))

    assert "Something went wrong at my end" in sent[0]
    assert "shortly" not in sent[0]


def test_the_model_call_is_bounded():
    """The retry count is the throttle multiplier: 196 real invocations produced 3,737
    throttle events, because each one was retried four times with backoff."""
    import boto3

    from donorpanel.agents import model as model_module

    cfg = model_module.client_config()
    boto3.client("bedrock-runtime", region_name="ap-southeast-2", config=cfg)
    # Only after a client is built does botocore normalise this into the total, and that
    # total is what actually bounds the call.
    assert cfg.retries["total_max_attempts"] == 2
    assert cfg.read_timeout <= 60


def test_each_model_gets_its_own_client_config():
    """botocore rewrites the config object it is handed, so a shared instance would be
    mutated by whichever client was built from it first."""
    from donorpanel.agents import model as model_module

    assert model_module.client_config() is not model_module.client_config()


def test_the_retry_backoff_is_bounded():
    """Strands retries a throttle above botocore, and that layer is the expensive one.
    Its defaults sleep 4, 8, 16, 32 then 64 seconds, which made a throttled call take
    152 seconds to fail: past Telegram's patience, so Telegram resent the message and
    spent the exhausted quota again."""
    from donorpanel.agents.model import retries

    strategy = retries()
    assert strategy._max_attempts == 2
    assert strategy._initial_delay <= 2
    assert strategy._max_delay <= 4


def test_the_provider_is_selected_by_config(monkeypatch):
    from dataclasses import replace

    from donorpanel.agents import model as model_module

    def using(**kw):
        monkeypatch.setattr(model_module, "config", replace(model_module.config, **kw))

    using(model_provider="bedrock", bedrock_model_id="apac.amazon.nova-pro-v1:0")
    assert type(model_module.llm()).__name__ == "BedrockModel"

    using(model_provider="openrouter", openrouter_api_key="sk-test",
          openrouter_model_id="anthropic/claude-sonnet-4-5")
    assert type(model_module.llm()).__name__ == "OpenAIModel"


def test_openrouter_without_a_key_fails_loudly(monkeypatch):
    """Falling back to Bedrock here would be worse than failing: the reason to select
    openrouter at all is that Bedrock is capped."""
    from dataclasses import replace

    import pytest as pt

    from donorpanel.agents import model as model_module
    monkeypatch.setattr(model_module, "config",
                        replace(model_module.config, model_provider="openrouter",
                                openrouter_api_key=None))
    with pt.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        model_module.llm()
