import uuid
from datetime import date, datetime, timezone

from strands import ToolContext, tool

from donorpanel.domain import Condition, Patient, RequestStatus
from donorpanel.domain.matching import COMPATIBLE_DONORS

GROUPS = tuple(COMPATIBLE_DONORS.keys())
CONDITIONS = {c.value: c for c in Condition}


@tool(context=True)
def start_request(patient_name: str, city: str, blood_group: str, units_needed: int,
                  needed_by: str, condition: str = "other", dob: str | None = None,
                  hospital: str | None = None, tool_context: ToolContext = None) -> str:
    """Open a blood request and start searching the donor network for it. Only call
    this once you have the patient's name, their city, their blood group, how many
    units, and the date it is needed by. Everything else is optional.

    Args:
        patient_name: Who the blood is for.
        city: Where they need it, used to find donors near them.
        blood_group: One of A+, A-, B+, B-, AB+, AB-, O+, O-.
        units_needed: How many units, usually one or two.
        needed_by: The date it is needed by, as YYYY-MM-DD.
        condition: thalassemia, sickle_cell, surgery, trauma or other.
        dob: The patient's date of birth as YYYY-MM-DD, if they gave it.
        hospital: The hospital, if they named one.
    """
    state = tool_context.invocation_state
    repo = state["repo"]

    group = blood_group.strip().upper().replace(" ", "")
    if group not in GROUPS:
        return (f"INTERNAL: {blood_group} is not one of the eight blood groups. Ask them "
                f"for it again in your own words. Nothing has been saved.")
    try:
        when = date.fromisoformat(needed_by.strip())
    except ValueError:
        return (f"INTERNAL: {needed_by} is not a readable date. Ask them for the actual "
                f"calendar date in your own words. Nothing has been saved.")
    if when < datetime.now(timezone.utc).date():
        return (f"INTERNAL: {needed_by} is in the past. Ask them which date they mean. "
                f"Nothing has been saved.")
    if not 1 <= int(units_needed) <= 12:
        return (f"INTERNAL: {units_needed} units is outside one request. Ask them to "
                f"confirm how many. Nothing has been saved.")

    from donorpanel.adapters.geo import Geocoder

    where = Geocoder().locate(city)
    patient_id = f"p-{uuid.uuid4().hex[:8]}"
    repo.put_patient(Patient(
        patient_id=patient_id, name=patient_name.strip()[:60],
        condition=CONDITIONS.get(condition.strip().lower(), Condition.OTHER),
        blood_group=group, policy_id="thalassemia-india", region="IN-TN",
        city=city.strip()[:60], hospital=(hospital or "").strip()[:80] or None,
        dob=dob, lat=where[0] if where else None, lon=where[1] if where else None,
        coordinator_channel=state.get("channel"), coordinator_address=state.get("sender")))

    # Picked up by the inbound handler once this reply is sent: the graph takes the
    # better part of a minute and nobody should watch a typing indicator for that.
    state["launch"] = {"patient_id": patient_id, "needed_by": when.isoformat(),
                       "units_needed": int(units_needed)}
    return (f"Request opened for {patient_name}, {group}, {units_needed} unit(s) in "
            f"{city} by {when.isoformat()}. Tell them you are searching the network now "
            f"and will report back shortly. Do not promise a specific donor yet.")


@tool(context=True)
def request_progress(tool_context: ToolContext) -> str:
    """How the search for this person's request is going: who was contacted and who
    has agreed so far. Use it when they ask for an update."""
    state = tool_context.invocation_state
    repo = state["repo"]
    sender = state.get("sender")
    mine = [p for p in [repo.get_patient(pid) for pid in _patient_ids(repo)]
            if p and p.coordinator_address == str(sender)]
    if not mine:
        return "They have no open request with me."
    lines = []
    for patient in mine:
        for request in repo.list_requests(patient.patient_id):
            if request.status is RequestStatus.CLOSED:
                continue
            contacts = repo.list_contacts(request.request_id)
            sent = sum(1 for c in contacts if c.status.value in ("sent", "pledged"))
            pledged = repo.pledged_units(request.request_id)
            lines.append(f"{patient.name} ({request.units_needed} units by "
                         f"{request.needed_by}): {request.status.value}, "
                         f"{sent} donors contacted, {pledged} agreed so far.")
    return "\n".join(lines) if lines else "They have no open request with me."


def _patient_ids(repo) -> list[str]:
    return [k.rsplit("/", 1)[-1].removesuffix(".json")
            for k in repo.store.keys("patients/")]
