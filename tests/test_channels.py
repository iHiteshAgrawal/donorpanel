import pytest

from donorpanel import policies
from donorpanel.channels import ConsoleChannel, Outbound


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
