from datetime import datetime, timedelta, timezone

from donorpanel.config import config
from donorpanel.domain import (
    Condition,
    Contact,
    ContactStatus,
    Donor,
    Patient,
    Request,
    RequestSource,
    RequestStatus,
)

PATIENT = {
    "patient_id": "p-ravi", "name": "Ravi", "condition": Condition.THALASSEMIA,
    "blood_group": "B+", "policy_id": "thalassemia-india", "region": "IN-TN",
    "city": "Coimbatore", "hospital": "Government Hospital",
}

# donor_id, name, group, channel, consent, days since last donation, city, contacts
POOL = [
    ("d-asha",    "Asha",   "B+", "telegram", True,  160,  "Coimbatore", 0),
    ("d-vikram",  "Vikram", "B+", "email",    True,   20,  "Coimbatore", 0),
    ("d-meera",   "Meera",  "O-", "telegram", True,  None, "Tiruppur",   0),
    ("d-suresh",  "Suresh", "B+", "telegram", False, 400,  "Coimbatore", 0),
    ("d-kavya",   "Kavya",  "O+", "telegram", True,  210,  "Erode",      3),
    ("d-arun",    "Arun",   "B-", "email",    True,  120,  "Chennai",    0),
    ("d-divya",   "Divya",  "A+", "telegram", True,  300,  "Coimbatore", 0),
    ("d-nithya",  "Nithya", "B+", "telegram", True,   95,  "Pollachi",   1),
]

PREFIXES = ("requests/", "contacts/", "patient-requests/", "drafts/",
            "approvals/", "donors/", "pool/", "patients/", "credits/")


def ago(days: int | None) -> str | None:
    if days is None:
        return None
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


def is_empty(repo) -> bool:
    return not repo.store.keys("patients/")


def address_for(channel: str, donor_id: str) -> str:
    """Demo donors are fictional, so their messages route to the operator's own chat
    and inbox. The API calls and their receipts are real; only the recipient is shared.
    SES in the sandbox can only send to a verified address, so this is also required."""
    if channel == "telegram" and config.telegram_demo_chat_id:
        return config.telegram_demo_chat_id
    if channel == "email" and config.ses_demo_email:
        return config.ses_demo_email
    return f"{donor_id}@example.test"


def populate(repo, coordinates: dict[str, tuple[float, float]] | None = None) -> int:
    """Write the demo patient and donor pool into whichever namespace repo holds."""
    coordinates = coordinates or {}
    repo.put_patient(Patient(**PATIENT, **dict(zip(
        ("lat", "lon"), coordinates.get(PATIENT["city"], (None, None))))))
    for donor_id, name, group, channel, consent, last, city, contacts in POOL:
        lat, lon = coordinates.get(city, (None, None))
        repo.put_donor(Donor(
            donor_id=donor_id, name=name, blood_group=group, region="IN-TN",
            channel=channel, address=address_for(channel, donor_id), city=city,
            consent=consent, last_donation=ago(last), language="ta",
            contacts_this_month=contacts, lat=lat, lon=lon))
    return len(POOL)


def wipe(repo) -> int:
    removed = 0
    for prefix in PREFIXES:
        for key in repo.store.keys(prefix):
            repo.store.delete(key)
            removed += 1
    return removed


def coordinates_from(repo) -> dict[str, tuple[float, float]]:
    """Harvest already geocoded cities so a fresh sandbox starts with coordinates
    instead of paying Amazon Location again for the same five towns."""
    found: dict[str, tuple[float, float]] = {}
    patient = repo.get_patient(PATIENT["patient_id"])
    if patient and patient.lat is not None:
        found[patient.city] = (patient.lat, patient.lon)
    for donor_id, *_ , city, _ in POOL:
        donor = repo.get_donor(donor_id)
        if donor and donor.lat is not None:
            found[city] = (donor.lat, donor.lon)
    return found


# One transfusion that already happened, so the pool reads as a network that has done the
# work rather than an empty directory. Every count on the landing page comes from these
# rows, so inventing the numbers there instead would make the page lie about the store.
HISTORY_REQUEST = "r-public-past"
HISTORY = [
    ("d-asha", 1, ContactStatus.DONATED, 9, 9),
    ("d-nithya", 2, ContactStatus.DONATED, 9, 8),
    ("d-vikram", 3, ContactStatus.PLEDGED, 9, 8),
    ("d-divya", 4, ContactStatus.DECLINED, 9, 7),
    ("d-kavya", 5, ContactStatus.NO_RESPONSE, 9, None),
]


def history(repo) -> int:
    """A settled request from a fortnight ago with its real contact rows."""
    repo.put_request(Request(
        request_id=HISTORY_REQUEST, patient_id=PATIENT["patient_id"],
        policy_id=PATIENT["policy_id"], units_needed=2,
        needed_by=ago(12), source=RequestSource.SCHEDULED,
        status=RequestStatus.FULFILLED, units_pledged=2,
        created_at=f"{ago(14)}T09:00:00+00:00", updated_at=f"{ago(12)}T18:30:00+00:00"))

    rows = []
    for donor_id, rank, status, asked, answered in HISTORY:
        donor = repo.get_donor(donor_id)
        rows.append(Contact(
            request_id=HISTORY_REQUEST, donor_id=donor_id, status=status,
            channel=donor.channel if donor else "telegram", rank=rank,
            contacted_at=f"{ago(asked)}T09:05:00+00:00",
            responded_at=f"{ago(answered)}T10:20:00+00:00" if answered else None))
    repo.put_contacts(rows)
    return len(rows)
