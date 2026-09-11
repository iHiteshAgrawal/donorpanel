import pytest

from donorpanel import policies
from donorpanel.adapters.channels import ConsoleChannel, Outbound


async def test_console_channel_delivers():
    channel = ConsoleChannel()
    result = await channel.send(Outbound(recipient="tester", body="hello"))
    assert result.delivered
    assert channel.sent[0].body == "hello"


def test_policies_load():
    ids = policies.available()
    assert "thalassemia-india" in ids
    loaded = policies.load("thalassemia-india")
    assert loaded["cadence"]["interval_days"] == 21


def test_unknown_policy_raises():
    with pytest.raises(FileNotFoundError):
        policies.load("does-not-exist")


def update(update_id: int, chat_id: int, user_id: int, text: str, is_bot: bool = False):
    return {"update_id": update_id,
            "message": {"date": 1760000000, "text": text,
                        "chat": {"id": chat_id},
                        "from": {"id": user_id, "is_bot": is_bot, "first_name": "P"}}}


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


async def poll_with(monkeypatch, updates, allowed=()):
    from dataclasses import replace

    import httpx

    from donorpanel.adapters.channels import TelegramChannel
    from donorpanel.adapters.channels import telegram as tg

    # .env pins the allow list to the operator's own chat, which would drop every
    # fixture here.
    monkeypatch.setattr(tg, "config", replace(tg.config, telegram_allowed_chat_ids=allowed))

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None):
            return FakeResponse({"result": updates})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    return await TelegramChannel(token="t").poll()


async def test_two_people_in_one_group_are_two_identities(monkeypatch):
    # chat.id is the room, so keying on it would merge everyone in a group into one
    # donor record and one memory namespace.
    got = await poll_with(monkeypatch, [update(1, -100200, 501, "hi"),
                                        update(2, -100200, 502, "hello")])
    assert [m.sender for m in got] == ["501", "502"]
    assert {m.reply_to for m in got} == {"-100200"}


async def test_a_private_chat_still_answers_itself(monkeypatch):
    got = await poll_with(monkeypatch, [update(3, 8911353204, 8911353204, "hi")])
    assert got[0].sender == "8911353204"
    assert got[0].reply_to == "8911353204"


async def test_bot_messages_are_ignored(monkeypatch):
    # Without this a reply from another bot in the room could loop.
    assert await poll_with(monkeypatch, [update(4, -1, 9, "beep", is_bot=True)]) == []
