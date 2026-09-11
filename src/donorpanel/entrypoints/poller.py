import asyncio
import logging

from donorpanel.adapters.channels import Outbound, registry
from donorpanel.services import chat, pool

log = logging.getLogger(__name__)

POLL_SECONDS = 3


async def handle(message, channels) -> str | None:
    """Everyone gets the same Asha. What she can do for them depends on their own
    records, not on which door they came through."""
    launch: dict = {}
    answer = await asyncio.to_thread(
        chat.reply, pool.ensure(), message.body,
        sender=str(message.sender), channel=message.channel, carry=launch)

    channel = channels.get(message.channel)
    if channel:
        await channel.send(Outbound(recipient=message.reply_to, body=answer))
    if launch.get("launch"):
        # After the reply, never before: the graph takes most of a minute.
        asyncio.create_task(search(launch["launch"], message, channel))
    return answer


async def search(ask: dict, message, channel) -> None:
    """Runs the request graph for someone who asked over chat, then reports back."""
    from donorpanel.graph import flow

    try:
        panel = pool.ensure()
        out = await asyncio.to_thread(flow.run, ask, panel, None, None, "public")
        told = _summarise(panel, out)
    except Exception:
        log.warning("chat-started request failed", exc_info=True)
        told = ("I could not finish searching just now. A coordinator will pick this up "
                "and come back to you.")
    if channel:
        await channel.send(Outbound(recipient=message.reply_to, body=told))


def _summarise(panel, out: dict) -> str:
    gate = out.get("gate") or {}
    dispatch = out.get("dispatch") or {}
    sent = dispatch.get("delivered_count") or 0
    if sent:
        return (f"I have reached {sent} donor(s) who match and are due to give. "
                f"I will tell you the moment someone agrees.")
    if gate.get("gate") == "escalated":
        # Gate reasons are written for a coordinator. Say the same thing in the words
        # of someone whose friend is in hospital.
        why = " ".join(gate.get("reasons") or [])
        if "cohort" in why:
            plain = "I could not find enough matched donors near you yet"
        elif "emergency" in why:
            plain = "this is urgent enough that a person should see it"
        elif "contacted" in why:
            plain = "the donors who match have all been asked recently"
        else:
            plain = "it needs a second pair of eyes"
        return (f"{plain}, so a coordinator is on it now and will come back to you. "
                f"I am still looking in the meantime.")
    verdict = out.get("verdict") or {}
    if verdict.get("verdict") == "rejected":
        return (f"I could not open that request: {verdict.get('reason', 'it did not pass checks')}. "
                f"A coordinator will be in touch.")
    return "I have the request logged. A coordinator is looking at it now."


async def poll_forever() -> None:
    """Reads donor replies and answers them. Exactly one loop per deployment: two
    would share Telegram's update offset and each would see half the messages."""
    channels = registry()
    listening = {n: c for n, c in channels.items() if n == "telegram"}
    if not listening:
        log.info("no inbound channel configured, donor replies are not being read")
        return
    log.info("listening for donor replies on %s", ", ".join(listening))
    while True:
        try:
            for name, channel in listening.items():
                for message in await channel.poll():
                    log.info("inbound %s from %s", name, message.sender)
                    await handle(message, channels)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("inbound poll failed", exc_info=True)
        await asyncio.sleep(POLL_SECONDS)
