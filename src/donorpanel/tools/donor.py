from datetime import datetime, timezone

from strands import ToolContext, tool

from ..domain import ContactStatus, RequestStatus
from ..domain.matching import ineligible_reason


def _ctx(tool_context: ToolContext):
    """Resolve the donor from whoever is talking. Doing it here rather than up front
    means someone who registers mid-conversation is immediately recognised."""
    state = tool_context.invocation_state
    repo = state["repo"]
    sender = str(state.get("sender") or "")
    donor = next((d for d in repo.list_donors() if d.address == sender), None)
    return repo, (donor.donor_id if donor else None)


ASKED = (ContactStatus.SENT, ContactStatus.PLEDGED, ContactStatus.DECLINED)


def _contacts(repo, donor_id: str, statuses=ASKED):
    """Requests this donor has been asked about. Defaults to answered ones too, so a
    donor who just said yes is still told where and when to go."""
    found = []
    for request in repo.in_flight():
        for contact in repo.list_contacts(request.request_id):
            if contact.donor_id == donor_id and contact.status in statuses:
                found.append((request, contact))
    return found


def _unanswered(repo, donor_id: str):
    return _contacts(repo, donor_id, (ContactStatus.SENT,))


def _where(repo, request) -> str:
    patient = repo.get_patient(request.patient_id)
    where = f" at {patient.hospital}" if patient and patient.hospital else ""
    city = f" in {patient.city}" if patient and patient.city else ""
    return f"{where}{city}".strip()


@tool(context=True)
def my_request(tool_context: ToolContext) -> str:
    """What this donor is currently being asked to help with: the patient's blood
    group, how many units, by when, and where. Use it before answering any question
    about "the request" or "who needs blood"."""
    repo, donor_id = _ctx(tool_context)
    if not donor_id:
        return "I do not know which donor you are yet."
    rows = _contacts(repo, donor_id)
    if not rows:
        return "There is no open request for you right now."
    lines = []
    for request, contact in rows:
        patient = repo.get_patient(request.patient_id)
        answered = {"pledged": " You have already said yes to this one.",
                    "declined": " You already said you could not make this one."
                    }.get(contact.status.value, "")
        lines.append(f"{request.units_needed} units of "
                     f"{patient.blood_group if patient else 'blood'} needed by "
                     f"{request.needed_by} {_where(repo, request)}.{answered}")
    return "\n".join(lines)


@tool(context=True)
def record_answer(willing: bool, note: str | None = None,
                  tool_context: ToolContext = None) -> str:
    """Record whether this donor can help with the request they were asked about.
    Call this as soon as they say yes or no, before replying to them.

    Args:
        willing: True if they agreed to donate, False if they cannot this time.
        note: Anything they said worth keeping, like when they are free.
    """
    repo, donor_id = _ctx(tool_context)
    if not donor_id:
        return "I do not know which donor you are, so I cannot record that."
    rows = _unanswered(repo, donor_id)
    if not rows:
        return "There is no open request to answer."
    if len(rows) > 1:
        listed = ", ".join(r.request_id for r, _ in rows)
        return f"They have more than one open request ({listed}). Ask which one first."

    request, contact = rows[0]
    contact.status = ContactStatus.PLEDGED if willing else ContactStatus.DECLINED
    contact.responded_at = datetime.now(timezone.utc).isoformat()
    if note:
        contact.note = note[:300]
    repo.put_contact(contact)

    pledged = repo.pledged_units(request.request_id)
    if not willing:
        return "Recorded as declined. They will not be asked again for this request."

    # Tell the caller the logistics here: after this write the contact is no longer
    # unanswered, so a follow-up lookup would say there is nothing open.
    place = _where(repo, request) or "the hospital"
    if pledged >= request.units_needed:
        repo.set_status(request.request_id, RequestStatus.FULFILLED)
        return (f"Recorded as pledged, and that covers all {request.units_needed} units. "
                f"Tell them to donate {place} by {request.needed_by}.")
    short = request.units_needed - pledged
    return (f"Recorded as pledged. {short} more unit(s) still needed. "
            f"Tell them to donate {place} by {request.needed_by}.")


@tool(context=True)
def my_eligibility(tool_context: ToolContext) -> str:
    """Whether this donor can donate right now, and if not, when they can. Checks
    consent, the rest period since their last donation, and blood group match."""
    repo, donor_id = _ctx(tool_context)
    donor = repo.get_donor(donor_id) if donor_id else None
    if donor is None:
        return "I do not have a donor record for you."
    rows = _contacts(repo, donor_id)
    if not rows:
        return (f"You are registered as {donor.blood_group} in {donor.city}. "
                f"Last donation {donor.last_donation or 'not recorded'}.")
    from .. import policies

    request, _ = rows[0]
    policy = policies.load(request.policy_id)
    required = [a for a in policy.get("matching", {}).get("antigen_requirements", [])
                if not a.endswith("-negative")]
    why = ineligible_reason(donor, policy.get("donor_eligibility", {}), required)
    if why:
        return f"Not eligible for this request: {why}."
    return (f"Eligible. You are {donor.blood_group}, last donated "
            f"{donor.last_donation or 'not recorded'}.")
