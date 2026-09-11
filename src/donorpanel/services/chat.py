import logging

from donorpanel.adapters import memory
from donorpanel.adapters.storage import session_manager
from donorpanel.agents import assistant

log = logging.getLogger(__name__)


def reply(repo, text: str, sender: str, channel: str = "telegram",
          carry: dict | None = None, agent=None) -> str:
    """One conversational turn. The session manager keeps the thread; AgentCore Memory
    keeps what is worth remembering after the thread is gone. One thread per person,
    whether they are asking for blood, offering it, or answering an earlier ask."""
    session = f"chat-{sender}"
    if agent is None:
        agent = assistant.build(session_manager=session_manager(session))

    state = {"repo": repo, "sender": sender, "channel": channel, "chat": True}
    result = agent(text, invocation_state=state)
    if carry is not None and state.get("launch"):
        # Tools cannot start long work themselves, so they leave it here.
        carry["launch"] = state["launch"]
    answer = str(result).strip()

    # Conversation is exactly the shape USER_PREFERENCE mines, so chat is the richest
    # source of standing preferences the system has.
    memory.remember(str(sender), session, [("USER", text), ("ASSISTANT", answer)])
    return answer
