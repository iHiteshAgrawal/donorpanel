from strands import ToolContext, tool

from ..domain import RequestStatus


def _repo(ctx: ToolContext):
    return ctx.invocation_state["repo"]


@tool(context=True)
def panel_summary(tool_context: ToolContext) -> str:
    """Overall state of this coordinator's panel: patients, donors, and where every
    request currently stands. Use it to answer "what is going on" style questions
    before reaching for a more specific tool."""
    repo = _repo(tool_context)
    patient = repo.get_patient("p-ravi")
    donors = repo.list_donors()
    requests = repo.list_requests(patient.patient_id) if patient else []
    counts: dict[str, int] = {}
    for r in requests:
        key = r.status.value if hasattr(r.status, "value") else str(r.status)
        counts[key] = counts.get(key, 0) + 1
    lines = [f"Patient: {patient.name} ({patient.blood_group}, {patient.condition.value}) "
             f"in {patient.city}" if patient else "No patient on file."]
    lines.append(f"Donors in pool: {len(donors)}")
    lines.append(f"Requests: {len(requests)}")
    for status, count in sorted(counts.items()):
        lines.append(f"  {status}: {count}")
    return "\n".join(lines)


@tool(context=True)
def request_detail(request_id: str, tool_context: ToolContext) -> str:
    """Everything known about one request: status, units, date, who was contacted,
    how outreach went, and whether a human approved it.

    Args:
        request_id: The request to look up, like r-1a2b3c4d5e.
    """
    repo = _repo(tool_context)
    request = repo.get_request(request_id)
    if request is None:
        return f"No request {request_id}."
    contacts = repo.list_contacts(request_id)
    approval = repo.get_approval(request_id) or {}
    head = (f"{request.request_id}: {request.status.value}, {request.units_needed} units "
            f"needed by {request.needed_by}, source {request.source.value}")
    lines = [head]
    if request.rejection_reason:
        lines.append(f"Rejected because {request.rejection_reason}")
    if request.review_reason:
        lines.append(f"Flagged for review: {request.review_reason}")
    if approval.get("by"):
        lines.append(f"Approved by {approval['by']} at {approval.get('at')}")
    lines.append(f"Cohort of {len(contacts)}:")
    for c in contacts:
        donor = repo.get_donor(c.donor_id)
        name = donor.name if donor else c.donor_id
        detail = f" ({c.note})" if c.note else ""
        lines.append(f"  {c.rank}. {name} via {c.channel}: {c.status.value}{detail}")
    return "\n".join(lines)


@tool(context=True)
def open_requests(tool_context: ToolContext) -> str:
    """Requests that still need something: awaiting a coordinator's approval, or
    dispatched but not yet fulfilled. Use for "what needs me" questions."""
    repo = _repo(tool_context)
    rows = repo.in_flight()
    if not rows:
        return "Nothing is open. No request is waiting for approval or out with donors."
    lines = []
    for r in rows:
        if r.status is RequestStatus.AWAITING_APPROVAL:
            why = r.review_reason or "policy escalation"
            lines.append(f"{r.request_id}: {r.units_needed} units by {r.needed_by}, "
                         f"waiting on you because {why}")
        else:
            pledged = repo.pledged_units(r.request_id)
            lines.append(f"{r.request_id}: {r.units_needed} units by {r.needed_by}, "
                         f"sent to donors, {pledged} pledged so far")
    return "\n".join(lines)


@tool(context=True)
def donor_detail(donor_id: str, tool_context: ToolContext) -> str:
    """One donor's record: blood group, city, channel, consent, when they last
    donated and how often they have been contacted this month.

    Args:
        donor_id: The donor to look up, like d-asha.
    """
    repo = _repo(tool_context)
    donor = repo.get_donor(donor_id)
    if donor is None:
        return f"No donor {donor_id}."
    return (f"{donor.name} ({donor.donor_id}): {donor.blood_group}, {donor.city}, "
            f"reachable via {donor.channel} in {donor.language}. "
            f"Consent {'on file' if donor.consent else 'NOT given'}. "
            f"Last donation {donor.last_donation or 'never recorded'}. "
            f"Contacted {donor.contacts_this_month} times this month, "
            f"last at {donor.last_contacted or 'never'}.")
