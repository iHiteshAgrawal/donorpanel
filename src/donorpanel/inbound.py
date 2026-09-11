import asyncio
import logging

from . import chat, public
from .channels import Outbound, registry
from .domain import ContactStatus
from .storage import PanelRepository, store

log = logging.getLogger(__name__)

POLL_SECONDS = 3


def sandboxes() -> list[str]:
    """Every per-actor namespace. Donor replies arrive with no idea which visitor's
    sandbox they belong to, so the owner has to be found by looking."""
    seen = set()
    for key in store("").keys("actors/"):
        parts = key.split("/")
        if len(parts) > 2:
            seen.add(f"actors/{parts[1]}/")
    return sorted(seen)


def open_contact_for(repo, address: str):
    """A donor in this sandbox who was sent a message and has not answered."""
    for request in repo.in_flight():
        for contact in repo.list_contacts(request.request_id):
            if contact.status is not ContactStatus.SENT:
                continue
            donor = repo.get_donor(contact.donor_id)
            if donor and donor.address == address:
                return donor
    return None


def locate(address: str) -> tuple[PanelRepository, object] | tuple[None, None]:
    for prefix in sandboxes():
        repo = PanelRepository(store=store(prefix))
        donor = open_contact_for(repo, address)
        if donor is not None:
            return repo, donor
    return None, None


async def handle(message, channels) -> str | None:
    repo, donor = locate(message.sender)
    if donor is not None:
        answer = await asyncio.to_thread(
            chat.reply, repo, message.body, kind=chat.DONOR,
            donor_id=donor.donor_id, sender=message.sender, channel=message.channel)
    else:
        # Nobody is waiting on them, so this is someone curious, wanting to join, or
        # asking for blood. The public persona works out which.
        launch: dict = {}
        answer = await asyncio.to_thread(
            chat.reply, public.ensure(), message.body, kind=chat.VISITOR,
            sender=message.sender, channel=message.channel, carry=launch)
    channel = channels.get(message.channel)
    if channel:
        await channel.send(Outbound(recipient=message.sender, body=answer))
    if donor is None and launch.get("launch"):
        # After the reply, never before: the graph takes most of a minute.
        asyncio.create_task(search(launch["launch"], message, channel))
    return answer


async def search(ask: dict, message, channel) -> None:
    """Runs the request graph for someone who asked over chat, then reports back."""
    from .graphs import request as flow

    try:
        panel = public.ensure()
        out = await asyncio.to_thread(flow.run, ask, panel, None, None, "public")
        told = _summarise(panel, out)
    except Exception:
        log.warning("chat-started request failed", exc_info=True)
        told = ("I could not finish searching just now. A coordinator will pick this up "
                "and come back to you.")
    if channel:
        await channel.send(Outbound(recipient=message.sender, body=told))


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
