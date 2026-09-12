"""Asking again, and knowing when to stop.

A coordinator who contacted eight people once and then went quiet would not be doing the
job. `policies/*.yaml` has always carried the cadence in `outreach.escalation_hours`,
declared as [0, 24, 48] and, until now, read by nothing: contact at hour zero, ask a
wider group after a day, once more after two, then leave it to a human.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from donorpanel import policies
from donorpanel.domain import Contact, ContactStatus, RequestStatus
from donorpanel.domain.matching import compatible_groups, ineligible_reason, score
from donorpanel.services.outreach import deliver

log = logging.getLogger(__name__)

# A donor who said no, or who could not be reached, is not asked again for this request.
ANSWERED = (ContactStatus.PLEDGED, ContactStatus.DECLINED, ContactStatus.UNREACHABLE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _waves_sent(contacts) -> int:
    """One wave is one round of messages, so distinct send times count the rounds."""
    return len({c.contacted_at for c in contacts if c.contacted_at})


def hours_since_last(contacts, now: datetime | None = None) -> float | None:
    sent = [c.contacted_at for c in contacts if c.contacted_at]
    if not sent:
        return None
    last = datetime.fromisoformat(max(sent))
    return ((now or _now()) - last).total_seconds() / 3600


def next_wave_due(repo, request, now: datetime | None = None) -> bool:
    """Whether this request has waited long enough for the next round."""
    if request.status is not RequestStatus.DISPATCHED:
        # Anything awaiting a human is theirs to move, not ours to escalate around.
        return False
    if repo.pledged_units(request.request_id) >= request.units_needed:
        return False

    contacts = repo.list_contacts(request.request_id)
    waves = _waves_sent(contacts)
    schedule = policies.load(request.policy_id).get("outreach", {}).get(
        "escalation_hours", [0])
    if waves == 0 or waves >= len(schedule):
        # Never sent, or the schedule is exhausted. Exhausted means stop asking: that is
        # the signal a human is needed, not a reason to widen the net further.
        return False
    waited = hours_since_last(contacts, now)
    return waited is not None and waited >= float(schedule[waves])


def next_donors(repo, request, limit: int) -> list:
    """Eligible, compatible donors nobody has contacted for this request yet."""
    patient = repo.get_patient(request.patient_id)
    if patient is None:
        return []
    policy = policies.load(request.policy_id)
    rules = policy.get("donor_eligibility", {})
    matching = policy.get("matching", {})
    required = [a for a in matching.get("antigen_requirements", [])
                if not a.endswith("-negative")]
    groups = (compatible_groups(patient.blood_group)
              if matching.get("require_abo_rh", True) else (patient.blood_group,))

    already = {c.donor_id for c in repo.list_contacts(request.request_id)}
    pool = {}
    for group in groups:
        for donor in repo.list_pool(patient.region, group):
            if donor.donor_id not in already and not ineligible_reason(donor, rules, required):
                pool[donor.donor_id] = donor

    ranked = sorted(pool.values(),
                    key=lambda d: score(d, rules, patient.lat, patient.lon)[0],
                    reverse=True)
    return ranked[:limit]


def chase(repo, now: datetime | None = None, channels=None) -> dict:
    """One pass over everything in flight, sending the next wave where one is due."""
    waves = []
    for request in repo.in_flight():
        if not next_wave_due(repo, request, now):
            continue
        policy = policies.load(request.policy_id)
        size = policy.get("outreach", {}).get("cohort_size", 8)
        found = next_donors(repo, request, size)
        if not found:
            log.info("%s is short but nobody new is eligible", request.request_id)
            continue

        start = len(repo.list_contacts(request.request_id))
        repo.put_contacts([
            Contact(request_id=request.request_id, donor_id=d.donor_id,
                    channel=d.channel, rank=start + i + 1)
            for i, d in enumerate(found)])
        # deliver only messages PENDING contacts, so the earlier waves are untouched.
        sent = deliver(repo, request.request_id, channels=channels)
        waves.append({"request_id": request.request_id,
                      "wave": _waves_sent(repo.list_contacts(request.request_id)),
                      "added": len(found), "delivered": sent["delivered_count"]})
    return {"chased": len(waves), "waves": waves}


def close(repo, today: date | None = None) -> dict:
    """Settles requests whose date has passed.

    Without this `in_flight()` grows forever, and since a patient with an open request is
    deliberately never re-forecast, every one of them would become permanently invisible
    to the forecast.
    """
    today = today or _now().date()
    closed = []
    for request in repo.in_flight():
        if not request.needed_by or date.fromisoformat(request.needed_by) >= today:
            continue
        pledged = repo.pledged_units(request.request_id)
        settled = (RequestStatus.FULFILLED if pledged >= request.units_needed
                   else RequestStatus.SHORT)
        repo.set_status(request.request_id, settled)
        for contact in repo.list_contacts(request.request_id):
            if contact.status is ContactStatus.SENT:
                contact.status = ContactStatus.NO_RESPONSE
                repo.put_contact(contact)
        closed.append({"request_id": request.request_id, "status": settled.value,
                       "pledged": pledged, "needed": request.units_needed})
    return {"closed": len(closed), "requests": closed}


def backdate(repo, request_id: str, hours: int) -> None:
    """Test helper: ages every send on a request so the next wave comes due."""
    when = (_now() - timedelta(hours=hours)).isoformat()
    for contact in repo.list_contacts(request_id):
        if contact.contacted_at:
            contact.contacted_at = when
            repo.put_contact(contact)
