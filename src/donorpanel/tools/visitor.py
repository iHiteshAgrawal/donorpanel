from strands import ToolContext, tool

from donorpanel.domain import Donor, distance_km
from donorpanel.domain.matching import COMPATIBLE_DONORS, compatible_groups

GROUPS = tuple(COMPATIBLE_DONORS.keys())


def _state(tool_context: ToolContext):
    state = tool_context.invocation_state
    return state["repo"], state.get("sender"), state.get("channel", "telegram")


def mine(repo, sender):
    """The donor this person registered, matched on the id derived from their sender.

    Not on `address`: seeded demo donors deliberately share the operator's contact address so
    outreach reaches a real phone, which made every one of them look like the same human. The
    same collision would hit two real donors sharing a household number.
    """
    prefix = donor_id_for(sender, "")
    return next((d for d in repo.list_donors() if d.donor_id.startswith(prefix)), None)


def donor_id_for(sender, group: str) -> str:
    suffix = group.lower().replace("+", "p").replace("-", "n")
    return f"d-{str(sender)[-6:]}-{suffix}"


@tool(context=True)
def who_needs_blood(tool_context: ToolContext) -> str:
    """The patient currently looking for donors, and which blood groups can help them.
    Use this when someone asks who they would be donating to, or whether their group
    is useful."""
    repo, sender, _ = _state(tool_context)
    patient = repo.get_patient("p-ravi")
    if patient is None:
        return "Nobody is waiting right now."
    helpful = ", ".join(compatible_groups(patient.blood_group)) or patient.blood_group
    said = (f"{patient.name} has {patient.condition.value} and needs {patient.blood_group} "
            f"blood every few weeks, at {patient.hospital} in {patient.city}. "
            f"Donors with these groups can help: {helpful}.")

    # The ranking already measures this, so without it here the model answers "quite far"
    # from its own idea of Indian geography rather than from the coordinates we hold.
    donor = mine(repo, sender) if sender else None
    if donor:
        km = distance_km(donor.lat, donor.lon, patient.lat, patient.lon)
        if km is not None:
            said += (f" They are about {km:,.0f} km from {donor.city}, which is the real "
                     f"distance between the two, so state it as given.")
    return said


@tool
def blood_compatibility(donor_group: str, recipient_group: str) -> str:
    """Whether one blood group can donate to another. Use this for EVERY question about
    compatibility, including ones you believe you already know the answer to.

    Args:
        donor_group: The group giving blood, like O+.
        recipient_group: The group receiving it, like B+.
    """
    donor = donor_group.strip().upper().replace(" ", "")
    recipient = recipient_group.strip().upper().replace(" ", "")
    if donor not in GROUPS or recipient not in GROUPS:
        return (f"INTERNAL: {donor_group} or {recipient_group} is not one of the eight "
                f"blood groups. Ask them to say it again.")
    if donor in compatible_groups(recipient):
        return (f"YES. {donor} can donate to {recipient}. State this plainly and do not "
                f"qualify it.")
    return (f"NO. {donor} cannot donate to {recipient}. The groups that can are: "
            f"{', '.join(compatible_groups(recipient))}.")


@tool
def who_can_i_help(blood_group: str) -> str:
    """Every blood group a donor of this group can give to. Use this for "who can I
    help" and "who can receive my blood", which blood_compatibility cannot answer
    because it compares one pair at a time.

    Args:
        blood_group: The donor's group, like AB+.
    """
    donor = blood_group.strip().upper().replace(" ", "")
    if donor not in GROUPS:
        return (f"INTERNAL: {blood_group} is not one of the eight blood groups. Ask "
                f"them again in your own words.")
    helps = [r for r in GROUPS if donor in compatible_groups(r)]
    return (f"{donor} can donate to: {', '.join(helps)}. That is the complete list, "
            f"state it as given.")


@tool(context=True)
def am_i_registered(tool_context: ToolContext) -> str:
    """Whether this person is already in the donor pool. Call this before asking them
    to register, so nobody is asked to sign up twice."""
    repo, sender, _ = _state(tool_context)
    if not sender:
        return "I cannot tell who you are on this channel."
    donor = mine(repo, sender)
    if donor:
        return (f"Already registered as {donor.name}, {donor.blood_group}, "
                f"in {donor.city}. Consent is "
                f"{'on file' if donor.consent else 'not given yet'}.")
    return "Not registered yet."


@tool(context=True)
def register_donor(name: str, city: str, blood_group: str, consent: bool,
                   tool_context: ToolContext = None) -> str:
    """Add this person to the donor pool. Only call it once you have all four values
    and they have clearly agreed to be contacted.

    Args:
        name: What they want to be called.
        city: The city they can donate in, used to match them to nearby patients.
        blood_group: One of A+, A-, B+, B-, AB+, AB-, O+, O-.
        consent: True only if they explicitly agreed to be contacted about donating.
    """
    repo, sender, channel = _state(tool_context)
    if not sender:
        return "I cannot register anyone without a contact address."
    group = blood_group.strip().upper().replace(" ", "")
    if group not in GROUPS:
        return (f"INTERNAL: {blood_group} is not one of the eight blood groups. Ask "
                f"them again in your own words. Nothing has been saved.")
    if not consent:
        return ("INTERNAL: consent was not given, so nobody was registered. Ask them "
                "plainly whether they are happy to be contacted.")

    from donorpanel.adapters.geo import Geocoder

    existing = mine(repo, sender)
    donor_id = existing.donor_id if existing else donor_id_for(sender, group)
    where = Geocoder().locate(city)
    repo.put_donor(Donor(
        donor_id=donor_id, name=name.strip()[:60], blood_group=group,
        region="IN-TN", channel=channel, address=str(sender), city=city.strip()[:60],
        language="en", consent=True,
        lat=where[0] if where else None, lon=where[1] if where else None))

    patient = repo.get_patient("p-ravi")
    useful = patient and group in compatible_groups(patient.blood_group)
    if not patient:
        tail = "Nobody is waiting right now, but that changes weekly."
    elif useful:
        tail = (f"CONFIRMED COMPATIBLE: {group} can donate to {patient.name}, who needs "
                f"{patient.blood_group}. Tell them so.")
    else:
        tail = (f"NOT COMPATIBLE: {group} cannot donate to {patient.name}, who needs "
                f"{patient.blood_group}. Say someone else may need them soon.")
    return f"Registered {name} as {group} in {city}. {tail}"
