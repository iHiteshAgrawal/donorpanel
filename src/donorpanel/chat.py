import logging

from . import memory
from .agents import assistant
from .storage import session_manager

log = logging.getLogger(__name__)

COORDINATOR = "coordinator"
DONOR = "donor"
VISITOR = "visitor"

BUILDERS = {COORDINATOR: "coordinator", DONOR: "donor", VISITOR: "visitor"}


def session_for(kind: str, who: str) -> str:
    return f"{kind}-{who}"


def reply(repo, text: str, actor_id: str | None = None, kind: str = COORDINATOR,
          donor_id: str | None = None, sender: str | None = None,
          channel: str = "telegram", agent=None) -> str:
    """One conversational turn. The session manager keeps the thread; AgentCore Memory
    keeps what is worth remembering after the thread is gone."""
    who = {DONOR: donor_id, VISITOR: sender}.get(kind, actor_id)
    session = session_for(kind, str(who or "guest"))
    if agent is None:
        build = getattr(assistant, BUILDERS.get(kind, COORDINATOR))
        agent = build(session_manager=session_manager(session))

    result = agent(text, invocation_state={"repo": repo, "actor_id": actor_id,
                                           "donor_id": donor_id, "sender": sender,
                                           "channel": channel, "chat": True})
    answer = str(result).strip()

    if actor_id:
        # Conversation is exactly the shape USER_PREFERENCE mines, so chat is the
        # richest source of standing preferences the system has.
        memory.remember(actor_id, session, [("USER", text), ("ASSISTANT", answer)])
    return answer
