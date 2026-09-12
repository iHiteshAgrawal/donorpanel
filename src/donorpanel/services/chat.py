import logging
import re

from donorpanel.adapters import memory
from donorpanel.adapters.storage import session_manager
from donorpanel.agents import assistant

log = logging.getLogger(__name__)

# Nova emits its reasoning inline rather than in a separate channel, so it arrives in
# the same string as the reply and would otherwise be sent to the person.
THINKING = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)


def spoken(text: str) -> str:
    cleaned = THINKING.sub("", text)
    # A stray unclosed tag would otherwise leave everything after it visible.
    cleaned = re.sub(r"</?thinking>", "", cleaned, flags=re.IGNORECASE)
    return plain(cleaned).strip()


def plain(text: str) -> str:
    """Telegram shows the characters, so a model that reaches for markdown produces
    literal asterisks and dashes in a chat bubble. The prompt asks for none; this is
    what happens when a model does it anyway."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        # A bullet becomes a sentence, so several become one flowing reply.
        bullet = re.match(r"^[-*\u2022]\s+(.*)$", stripped)
        if bullet:
            item = bullet.group(1).rstrip(".")
            out.append(f"{item}.")
        else:
            out.append(stripped)
    joined = " ".join(p for p in out if p)
    joined = re.sub(r"\*\*(.+?)\*\*", r"\1", joined)      # bold
    joined = re.sub(r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1", joined)   # italics
    return re.sub(r"\s{2,}", " ", joined)


def reply(repo, text: str, sender: str, channel: str = "telegram",
          carry: dict | None = None, agent=None, on_answer=None) -> str:
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
    answer = spoken(str(result))

    # Send before remembering. The memory write costs about 1.5s and nothing in the reply
    # depends on it, so doing it first simply made the person wait longer for the same words.
    if on_answer is not None:
        on_answer(answer)

    # Conversation is exactly the shape USER_PREFERENCE mines, so chat is the richest
    # source of standing preferences the system has.
    memory.remember(str(sender), session, [("USER", text), ("ASSISTANT", answer)])
    return answer
