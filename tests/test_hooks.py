from types import SimpleNamespace

import pytest
from strands.hooks.events import AfterNodeCallEvent

from donorpanel import hooks
from donorpanel import seed as seeds
from donorpanel.domain import Contact, Request, RequestStatus
from donorpanel.storage import FileStore, PanelRepository


class Spy:
    def __init__(self, explode=False):
        self.records: list[tuple] = []
        self.events: list[tuple] = []
        self.explode = explode

    def record(self, actor_id, agent_id, texts):
        if self.explode:
            raise RuntimeError("memory is down")
        self.records.append((actor_id, agent_id, texts))
        return len(texts)

    def remember(self, actor_id, session_id, turns):
        self.events.append((actor_id, session_id, turns))
        return "ev-1"


@pytest.fixture
def repo(tmp_path):
    store = PanelRepository(store=FileStore(tmp_path))
    seeds.populate(store)
    return store


def request_in(repo, status=RequestStatus.DISPATCHED, with_cohort=True):
    row = Request(request_id="r-abc", patient_id=seeds.PATIENT["patient_id"],
                  policy_id=seeds.PATIENT["policy_id"], units_needed=2,
                  needed_by="2026-10-01")
    repo.put_request(row)
    repo.set_status(row.request_id, status)
    if with_cohort:
        repo.put_contacts([
            Contact(request_id=row.request_id, donor_id=donor[0], channel=donor[3],
                    rank=i + 1)
            for i, donor in enumerate(seeds.POOL[:3])])
    return row


def fire(node_id, state):
    event = AfterNodeCallEvent(source=SimpleNamespace(), node_id=node_id,
                               invocation_state=state)
    import asyncio
    asyncio.run(hooks.MemoryWriter().on_node_done(event))


def state_for(repo, actor_id="a-1"):
    return {"repo": repo, "request_id": "r-abc", "raw": {"patient_id": "p-ravi"},
            "actor_id": actor_id}


def test_writes_both_paths_at_the_gate(repo, monkeypatch):
    spy = Spy()
    monkeypatch.setattr(hooks, "memory", spy)
    request_in(repo)
    fire("gate", state_for(repo))

    assert len(spy.records) == 1
    actor, agent, texts = spy.records[0]
    assert (actor, agent) == ("a-1", "compose")
    assert "units" in texts[0]

    assert len(spy.events) == 1
    _, session, turns = spy.events[0]
    assert session == "r-abc"
    assert [role for role, _ in turns] == ["USER", "ASSISTANT"]


def test_a_rejected_run_still_writes(repo, monkeypatch):
    # adjudicate -> close never reaches the gate, so close must be terminal too.
    spy = Spy()
    monkeypatch.setattr(hooks, "memory", spy)
    request_in(repo, status=RequestStatus.REJECTED)
    fire("close", state_for(repo))
    assert len(spy.records) == 1 and len(spy.events) == 1


@pytest.mark.parametrize("node_id", ["intake", "verify", "rank", "compose"])
def test_non_terminal_nodes_write_nothing(repo, monkeypatch, node_id):
    spy = Spy()
    monkeypatch.setattr(hooks, "memory", spy)
    request_in(repo)
    fire(node_id, state_for(repo))
    assert spy.records == [] and spy.events == []


def test_without_an_actor_nothing_is_written(repo, monkeypatch):
    spy = Spy()
    monkeypatch.setattr(hooks, "memory", spy)
    request_in(repo)
    fire("gate", state_for(repo, actor_id=None))
    assert spy.records == [] and spy.events == []


def test_a_failing_memory_never_escapes_the_hook(repo, monkeypatch):
    # The registry propagates callback exceptions and this fires inside a finally,
    # so a raise here would kill the run and mask the real error.
    monkeypatch.setattr(hooks, "memory", Spy(explode=True))
    request_in(repo)
    fire("gate", state_for(repo))


def test_a_missing_request_is_survivable(repo, monkeypatch):
    spy = Spy()
    monkeypatch.setattr(hooks, "memory", spy)
    fire("gate", state_for(repo))
    assert spy.records == []
    assert spy.events == [("a-1", "r-abc", [])]
