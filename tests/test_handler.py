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
                        lambda s, p, c: asked.append((s, p)) or {"text": "hello back"})
    monkeypatch.setattr(handler, "_send", lambda ch, to, body: sent.append((ch, to, body)))
    out = handler.handler(http(UPDATE))
    assert out["statusCode"] == 200
    assert asked == [("8911353204", "Hi, what is this?")]
    assert sent == [("telegram", "8911353204", "hello back")]


def test_a_launch_triggers_a_second_invocation(monkeypatch):
    later = []
    monkeypatch.setattr(handler, "ask_asha",
                        lambda *a: {"text": "searching", "launch": {"patient_id": "p-1"}})
    monkeypatch.setattr(handler, "_send", lambda *a: None)
    monkeypatch.setattr(handler, "_self_invoke", later.append)
    handler.handler(http(UPDATE))
    assert later[0]["mode"] == "search"
    assert later[0]["ask"] == {"patient_id": "p-1"}


def test_the_wrong_secret_is_refused(monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr(handler, "config", replace(handler.config,
                                                   telegram_webhook_secret="letmein"))
    monkeypatch.setattr(handler, "_send", lambda *a: None)
    assert handler.handler(http(UPDATE, {"X-Telegram-Bot-Api-Secret-Token": "nope"}))["statusCode"] == 403
    assert handler.handler(http(UPDATE, {"X-Telegram-Bot-Api-Secret-Token": "letmein"}))["statusCode"] != 403


def test_a_bot_message_is_ignored_without_calling_the_agent(monkeypatch):
    called = []
    monkeypatch.setattr(handler, "ask_asha", lambda *a: called.append(1) or {})
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
