from typing import TYPE_CHECKING, Any

from boto3.dynamodb.conditions import Key
from strands.session.session_repository import SessionRepository
from strands.types.exceptions import SessionException
from strands.types.session import Session, SessionAgent, SessionMessage

from . import table as t

if TYPE_CHECKING:
    from strands.multiagent import MultiAgentBase


class DynamoDBSessionRepository(SessionRepository):
    def __init__(self, table=None):
        self._table = table or t.get_table()

    def _put(self, key: dict, payload: dict) -> None:
        self._table.put_item(Item={**key, **t.encode(payload)})

    def _get(self, key: dict) -> dict | None:
        item = self._table.get_item(Key=key).get("Item")
        if not item:
            return None
        return t.decode({k: v for k, v in item.items() if k not in (t.PK, t.SK)})

    def create_session(self, session: Session, **kwargs: Any) -> Session:
        if self.read_session(session.session_id) is not None:
            raise SessionException(f"Session {session.session_id} already exists")
        self._put(t.session_key(session.session_id), session.to_dict())
        return session

    def read_session(self, session_id: str, **kwargs: Any) -> Session | None:
        item = self._get(t.session_key(session_id))
        return Session.from_dict(item) if item else None

    def create_agent(self, session_id: str, session_agent: SessionAgent, **kwargs: Any) -> None:
        self._put(t.agent_key(session_id, session_agent.agent_id), session_agent.to_dict())

    def read_agent(self, session_id: str, agent_id: str, **kwargs: Any) -> SessionAgent | None:
        item = self._get(t.agent_key(session_id, agent_id))
        return SessionAgent.from_dict(item) if item else None

    def update_agent(self, session_id: str, session_agent: SessionAgent, **kwargs: Any) -> None:
        previous = self.read_agent(session_id, session_agent.agent_id)
        if previous is None:
            raise SessionException(
                f"Agent {session_agent.agent_id} in session {session_id} does not exist")
        session_agent.created_at = previous.created_at
        self._put(t.agent_key(session_id, session_agent.agent_id), session_agent.to_dict())

    def create_message(self, session_id: str, agent_id: str,
                       session_message: SessionMessage, **kwargs: Any) -> None:
        self._put(t.message_key(session_id, agent_id, session_message.message_id),
                  session_message.to_dict())

    def read_message(self, session_id: str, agent_id: str, message_id: int,
                     **kwargs: Any) -> SessionMessage | None:
        item = self._get(t.message_key(session_id, agent_id, message_id))
        return SessionMessage.from_dict(item) if item else None

    def update_message(self, session_id: str, agent_id: str,
                       session_message: SessionMessage, **kwargs: Any) -> None:
        previous = self.read_message(session_id, agent_id, session_message.message_id)
        if previous is None:
            raise SessionException(
                f"Message {session_message.message_id} does not exist")
        session_message.created_at = previous.created_at
        self._put(t.message_key(session_id, agent_id, session_message.message_id),
                  session_message.to_dict())

    def list_messages(self, session_id: str, agent_id: str, limit: int | None = None,
                      offset: int = 0, **kwargs: Any) -> list[SessionMessage]:
        # Sort key is MSG#<agent>#<id zero padded to 12>, so lexical order on the
        # range key is numeric order. Without the padding message 10 sorts before 9.
        res = self._table.query(
            KeyConditionExpression=Key(t.PK).eq(f"SESSION#{session_id}")
            & Key(t.SK).begins_with(f"MSG#{agent_id}#"),
        )
        rows = [t.decode({k: v for k, v in i.items() if k not in (t.PK, t.SK)})
                for i in res.get("Items", [])]
        window = rows[offset: offset + limit] if limit is not None else rows[offset:]
        return [SessionMessage.from_dict(r) for r in window]

    def create_multi_agent(self, session_id: str, multi_agent: "MultiAgentBase",
                           **kwargs: Any) -> None:
        self._put(t.multi_agent_key(session_id, multi_agent.id),
                  multi_agent.serialize_state())

    def read_multi_agent(self, session_id: str, multi_agent_id: str,
                         **kwargs: Any) -> dict[str, Any] | None:
        return self._get(t.multi_agent_key(session_id, multi_agent_id))

    def update_multi_agent(self, session_id: str, multi_agent: "MultiAgentBase",
                           **kwargs: Any) -> None:
        if self.read_multi_agent(session_id, multi_agent.id) is None:
            raise SessionException(
                f"MultiAgent state {multi_agent.id} in session {session_id} does not exist")
        self._put(t.multi_agent_key(session_id, multi_agent.id),
                  multi_agent.serialize_state())
