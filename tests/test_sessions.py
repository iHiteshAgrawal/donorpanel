import pytest
from strands.types.exceptions import SessionException
from strands.types.session import Session, SessionAgent, SessionMessage, SessionType

from donorpanel.storage import DynamoDBSessionRepository


@pytest.fixture
def repo(ddb):
    return DynamoDBSessionRepository(table=ddb)


def message(index: int, text: str = "hi") -> SessionMessage:
    return SessionMessage.from_message({"role": "user", "content": [{"text": text}]}, index)


def test_session_roundtrip(repo):
    repo.create_session(Session(session_id="s1", session_type=SessionType.AGENT))
    assert repo.read_session("s1").session_id == "s1"
    assert repo.read_session("missing") is None


def test_duplicate_session_rejected(repo):
    repo.create_session(Session(session_id="s1", session_type=SessionType.AGENT))
    with pytest.raises(SessionException):
        repo.create_session(Session(session_id="s1", session_type=SessionType.AGENT))


def test_agent_update_preserves_created_at(repo):
    repo.create_session(Session(session_id="s1", session_type=SessionType.AGENT))
    agent = SessionAgent(agent_id="a1", state={"n": 1}, conversation_manager_state={})
    repo.create_agent("s1", agent)
    created = repo.read_agent("s1", "a1").created_at

    updated = SessionAgent(agent_id="a1", state={"n": 2}, conversation_manager_state={})
    repo.update_agent("s1", updated)
    stored = repo.read_agent("s1", "a1")
    assert stored.state == {"n": 2}
    assert stored.created_at == created


def test_update_unknown_agent_raises(repo):
    with pytest.raises(SessionException):
        repo.update_agent("s1", SessionAgent(agent_id="ghost", state={},
                                             conversation_manager_state={}))


def test_messages_stay_in_numeric_order_past_ten(repo):
    for i in range(12):
        repo.create_message("s1", "a1", message(i, f"m{i}"))
    listed = repo.list_messages("s1", "a1")
    assert [m.message_id for m in listed] == list(range(12))


def test_message_pagination(repo):
    for i in range(10):
        repo.create_message("s1", "a1", message(i))
    assert [m.message_id for m in repo.list_messages("s1", "a1", limit=3)] == [0, 1, 2]
    assert [m.message_id for m in repo.list_messages("s1", "a1", limit=3, offset=6)] == [6, 7, 8]
    assert [m.message_id for m in repo.list_messages("s1", "a1", offset=8)] == [8, 9]


def test_messages_scoped_per_agent(repo):
    repo.create_message("s1", "a1", message(0, "for a1"))
    repo.create_message("s1", "a2", message(0, "for a2"))
    only = repo.list_messages("s1", "a1")
    assert len(only) == 1
    assert only[0].to_message()["content"][0]["text"] == "for a1"


def test_message_redaction_update(repo):
    repo.create_message("s1", "a1", message(0, "secret"))
    stored = repo.read_message("s1", "a1", 0)
    stored.redact_message = {"role": "user", "content": [{"text": "[redacted]"}]}
    repo.update_message("s1", "a1", stored)
    assert repo.read_message("s1", "a1", 0).to_message()["content"][0]["text"] == "[redacted]"


def test_agent_uses_repository_through_strands_manager(ddb):
    from strands import Agent
    from strands.session import RepositorySessionManager

    repo = DynamoDBSessionRepository(table=ddb)
    manager = RepositorySessionManager(session_id="s-live", session_repository=repo)
    agent = Agent(agent_id="verifier", session_manager=manager)
    agent.state.set("request_id", "r1")
    manager.sync_agent(agent)

    assert repo.read_session("s-live") is not None
    assert repo.read_agent("s-live", "verifier").state["request_id"] == "r1"
