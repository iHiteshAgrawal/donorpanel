import logging

from . import memory
from .agents import assistant
from .storage import session_manager

log = logging.getLogger(__name__)

DONOR = "donor"
VISITOR = "visitor"

BUILDERS = {DONOR: "donor", VISITOR: "visitor"}


def session_for(kind: str, who: str) -> str:
    return f"{kind}-{who}"


def reply(repo, text: str, kind: str = VISITOR,
          donor_id: str | None = None, sender: str | None = None,
          channel: str = "telegram", carry: dict | None = None, agent=None) -> str:
    """One conversational turn. The session manager keeps the thread; AgentCore Memory
    keeps what is worth remembering after the thread is gone."""
    who = donor_id if kind == DONOR else sender
    session = session_for(kind, str(who or "guest"))
    if agent is None:
        build = getattr(assistant, BUILDERS.get(kind, VISITOR))
        agent = build(session_manager=session_manager(session))

    state = {"repo": repo, "donor_id": donor_id, "sender": sender,
             "channel": channel, "chat": True}
    result = agent(text, invocation_state=state)
    if carry is not None and state.get("launch"):
        # Tools cannot start long work themselves, so they leave it here.
        carry["launch"] = state["launch"]
    answer = str(result).strip()

    # Conversation is exactly the shape USER_PREFERENCE mines, so chat is the richest
    # source of standing preferences the system has. The actor is whoever is talking.
    if who:
        memory.remember(str(who), session, [("USER", text), ("ASSISTANT", answer)])
    return answer
