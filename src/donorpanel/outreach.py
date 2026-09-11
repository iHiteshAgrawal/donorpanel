import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .channels import Channel, DeliveryResult, Outbound, registry
from .domain import ContactStatus, RequestStatus

log = logging.getLogger(__name__)


def pick_draft(drafts: list[dict], language: str, channel: str) -> dict | None:
    """Drafts are composed one per language and channel group, so an exact match is
    the norm. The fallbacks matter when a donor's pairing produced no group."""
    for draft in drafts:
        if draft.get("language") == language and draft.get("channel") == channel:
            return draft
    for draft in drafts:
        if draft.get("channel") == channel:
            return draft
    return drafts[0] if drafts else None


def personalise(body: str, donor) -> str:
    return body.replace("{name}", donor.name.split()[0])


async def _send_all(jobs: list[tuple[Any, Channel, Outbound]]) -> list[DeliveryResult]:
    async def one(channel: Channel, message: Outbound) -> DeliveryResult:
        try:
            return await channel.send(message)
        except Exception as exc:  # noqa: BLE001
            return DeliveryResult(delivered=False, channel=channel.name, error=str(exc)[:200])

    return await asyncio.gather(*(one(channel, message) for _, channel, message in jobs))


def deliver(repo, request_id: str, channels: dict[str, Channel] | None = None) -> dict:
    """Sends the composed drafts to every donor in the cohort.

    Safe to call from a graph node or a FastAPI endpoint: both run on a worker thread
    with no event loop of their own, so asyncio.run does not raise.
    """
    active = registry() if channels is None else channels
    contacts = repo.list_contacts(request_id)
    drafts = repo.get_drafts(request_id)
    if not contacts:
        return {"request_id": request_id, "delivered_count": 0, "failed_count": 0,
                "problem": "no cohort to contact", "outreach": []}
    if not drafts:
        return {"request_id": request_id, "delivered_count": 0, "failed_count": 0,
                "problem": "no drafts to send", "outreach": []}

    donors = {d.donor_id: d for d in repo.get_donors([c.donor_id for c in contacts])}
    jobs, skipped = [], []
    for contact in contacts:
        donor = donors.get(contact.donor_id)
        if donor is None:
            skipped.append((contact, None, "donor record is missing"))
            continue
        draft = pick_draft(drafts, donor.language, donor.channel)
        if draft is None:
            skipped.append((contact, donor, "no draft matched this donor"))
            continue
        channel = active.get(donor.channel)
        if channel is None:
            skipped.append((contact, donor, f"{donor.channel} channel not configured"))
            continue
        body = personalise(draft["body"], donor)
        jobs.append((contact, channel, Outbound(recipient=donor.address, body=body,
                                                subject=draft.get("subject"),
                                                locale=donor.language,
                                                metadata={"request_id": request_id,
                                                          "donor_id": donor.donor_id})))

    results = asyncio.run(_send_all(jobs)) if jobs else []
    at = datetime.now(timezone.utc).isoformat()
    rows, touched, delivered = [], [], 0

    for (contact, _, message), result in zip(jobs, results):
        donor = donors[contact.donor_id]
        contact.status = ContactStatus.SENT if result.delivered else ContactStatus.UNREACHABLE
        contact.contacted_at = at
        contact.note = result.reference if result.delivered else result.error
        contact.body = message.body
        rows.append({"rank": contact.rank, "donor_id": contact.donor_id, "name": donor.name,
                     "channel": donor.channel, "delivered": result.delivered,
                     "at": at, "detail": contact.note})
        if result.delivered:
            delivered += 1
            donor.contacts_this_month += 1
            donor.last_contacted = at
            touched.append(donor)

    for contact, donor, why in skipped:
        contact.status = ContactStatus.UNREACHABLE
        contact.contacted_at = at
        contact.note = why
        rows.append({"rank": contact.rank, "donor_id": contact.donor_id,
                     "name": donor.name if donor else contact.donor_id,
                     "channel": contact.channel, "delivered": False,
                     "at": at, "detail": why})

    repo.put_contacts([c for c, _, _ in skipped] + [c for c, _, _ in jobs])
    # Only successful sends spend the donor's monthly contact budget, which is what
    # the autonomy gate reads on later runs.
    for donor in touched:
        repo.put_donor(donor)

    failed = len(rows) - delivered
    if delivered:
        repo.set_status(request_id, RequestStatus.DISPATCHED)
    else:
        repo.set_status(request_id, RequestStatus.AWAITING_APPROVAL)
    return {"request_id": request_id, "delivered_count": delivered, "failed_count": failed,
            "outreach": sorted(rows, key=lambda r: r["rank"])}
