from dataclasses import replace

import pytest
from botocore.exceptions import ClientError

from donorpanel import memory


def error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "no"}}, "op")


class FakeClient:
    def __init__(self, **responses):
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            value = self.responses.get(name, {})
            if isinstance(value, list):
                value = value.pop(0)
            if isinstance(value, ClientError):
                raise value
            return value
        return call

    def kwargs(self, name: str) -> dict:
        return next(k for n, k in self.calls if n == name)

    @property
    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(memory, "config", replace(memory.config,
                                                  agentcore_memory_id="DonorPanelMemory-abc"))


@pytest.fixture
def unset(monkeypatch):
    monkeypatch.setattr(memory, "config", replace(memory.config, agentcore_memory_id=None))


def test_namespaces_start_and_end_with_a_slash():
    # A retrieval namespace missing its trailing slash is rejected by the service.
    for template in (memory.PREFERENCES, memory.FINDINGS, memory.ROOT):
        assert template.startswith("/") and template.endswith("/")
    assert memory.findings_ns("a-1", "compose") == "/donorpanel/a-1/agents/compose/findings/"
    assert memory.preferences_ns("a-1") == "/donorpanel/a-1/shared/preferences/"


def test_ensure_reuses_an_existing_memory_by_id_prefix():
    client = FakeClient(list_memories={"memories": [{"id": "Other-zzz"},
                                                    {"id": "DonorPanelMemory-abc"}]})
    assert memory.ensure(client=client) == "DonorPanelMemory-abc"
    assert "create_memory" not in client.names


def test_ensure_creates_then_polls_until_active():
    client = FakeClient(
        list_memories={"memories": []},
        create_memory={"memory": {"id": "DonorPanelMemory-new"}},
        get_memory=[{"memory": {"status": "CREATING"}}, {"memory": {"status": "ACTIVE"}}],
    )
    assert memory.ensure(client=client) == "DonorPanelMemory-new"

    created = client.kwargs("create_memory")
    assert created["eventExpiryDuration"] == 90
    strategies = {k: v for s in created["memoryStrategies"] for k, v in s.items()}
    assert strategies["userPreferenceMemoryStrategy"]["namespaceTemplates"] == [memory.PREFERENCES]
    assert strategies["semanticMemoryStrategy"]["namespaceTemplates"] == [memory.FINDINGS]
    assert created["namespaceKeys"][0]["key"] == "agentid"
    assert client.names.count("get_memory") == 2


def test_ensure_raises_when_creation_fails():
    client = FakeClient(
        list_memories={"memories": []},
        create_memory={"memory": {"id": "DonorPanelMemory-bad"}},
        get_memory={"memory": {"status": "FAILED"}},
    )
    with pytest.raises(RuntimeError):
        memory.ensure(client=client)


def test_remember_writes_conversational_payloads(live):
    client = FakeClient(create_event={"event": {"eventId": "ev-1"}})
    assert memory.remember("a-1", "r-1", [("USER", "two units"), ("ASSISTANT", "ok")],
                           client=client) == "ev-1"

    sent = client.kwargs("create_event")
    assert sent["actorId"] == "a-1" and sent["sessionId"] == "r-1"
    # Only conversational payloads are ever mined for long-term records.
    assert [p["conversational"]["role"] for p in sent["payload"]] == ["USER", "ASSISTANT"]
    assert sent["payload"][0]["conversational"]["content"] == {"text": "two units"}


def test_record_targets_the_agent_namespace_and_counts_successes(live):
    client = FakeClient(batch_create_memory_records={
        "successfulRecords": [{"memoryRecordId": "m-1"}],
        "failedRecords": [{"requestIdentifier": "x", "errorCode": "ValidationException"}],
    })
    assert memory.record("a-1", "compose", ["one", "two"], client=client) == 1
    sent = client.kwargs("batch_create_memory_records")
    assert all(r["namespaces"] == ["/donorpanel/a-1/agents/compose/findings/"]
               for r in sent["records"])
    assert len({r["requestIdentifier"] for r in sent["records"]}) == 2


def test_recall_and_everything_unwrap_summaries(live):
    hits = {"memoryRecordSummaries": [{"content": {"text": "prefers tamil"}}, {"content": {}}]}
    client = FakeClient(retrieve_memory_records=[hits, hits])
    assert memory.recall("a-1", "compose", "tone", client=client) == ["prefers tamil"]
    assert memory.everything("a-1", client=client) == ["prefers tamil"]
    assert client.calls[0][1]["namespace"] == "/donorpanel/a-1/agents/compose/findings/"
    assert client.calls[1][1]["namespacePath"] == "/donorpanel/a-1/"


@pytest.mark.parametrize("code", ["ValidationException", "AccessDeniedException",
                                  "ResourceNotFoundException", "ThrottledException"])
def test_every_call_degrades_instead_of_raising(live, code):
    client = FakeClient(create_event=error(code), batch_create_memory_records=error(code),
                        retrieve_memory_records=[error(code), error(code)])
    assert memory.remember("a-1", "r-1", [("USER", "hi")], client=client) is None
    assert memory.record("a-1", "compose", ["x"], client=client) == 0
    assert memory.recall("a-1", "compose", "q", client=client) == []
    assert memory.everything("a-1", client=client) == []


def test_without_a_memory_id_nothing_reaches_aws(unset):
    client = FakeClient()
    assert memory.remember("a-1", "r-1", [("USER", "hi")], client=client) is None
    assert memory.record("a-1", "compose", ["x"], client=client) == 0
    assert memory.recall("a-1", "compose", "q", client=client) == []
    assert memory.everything("a-1", client=client) == []
    assert client.calls == []


def test_extracted_preferences_are_unwrapped_for_display(live):
    client = FakeClient(retrieve_memory_records={"memoryRecordSummaries": [
        {"content": {"text": '{"context": "said so", "preference": "two units for Ravi"}'}},
        {"content": {"text": '{"context": "only context"}'}},
        {"content": {"text": "plain prose we wrote ourselves"}},
        {"content": {"text": "[1, 2]"}},
    ]})
    assert memory.everything("a-1", client=client) == [
        "two units for Ravi", "only context",
        "plain prose we wrote ourselves", "[1, 2]",
    ]
