"""Asha, hosted on AgentCore Runtime.

One agent, one request, one response, and a dedicated session per person: exactly what
Runtime is for. The request graph stays in Lambda because it is the opposite shape, a
30 to 70 second batch job nobody waits for.
"""
import hashlib
import logging

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from donorpanel.services import chat, pool

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


# AgentCore keeps its own state per runtimeSessionId, and clearing the Strands session
# store does not reach it. One session here degraded until every call timed out at 20s
# while a fresh id answered in 5.7s, with no way to reset it by id. Bumping this abandons
# the bad sessions and starts clean ones, so it is the lever for exactly that.
SESSION_EPOCH = "5"


def session_id(sender: str) -> str:
    """runtimeSessionId must be 33 to 256 characters and a Telegram id is about ten
    digits, so it cannot be passed through. Deterministic so the same person resumes
    the same session; the raw id travels in runtimeUserId, which is the field for it."""
    seed = f"{sender}:{SESSION_EPOCH}"
    return f"tg-{sender}-{hashlib.sha256(seed.encode()).hexdigest()[:24]}"


@app.entrypoint
def invoke(payload: dict) -> dict:
    sender = str(payload.get("sender") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    if not sender or not prompt:
        return {"error": "sender and prompt are both required"}

    carry: dict = {}
    answer = chat.reply(pool.ensure(), prompt, sender=sender,
                        channel=payload.get("channel") or "telegram", carry=carry)
    return {"text": answer, "launch": carry.get("launch")}


if __name__ == "__main__":
    app.run()
