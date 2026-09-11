from datetime import datetime, timedelta, timezone

from .domain import Condition, Donor, Patient

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


def populate(repo, coordinates: dict[str, tuple[float, float]] | None = None) -> int:
    """Write the demo patient and donor pool into whichever namespace repo holds."""
    coordinates = coordinates or {}
    repo.put_patient(Patient(**PATIENT, **dict(zip(
        ("lat", "lon"), coordinates.get(PATIENT["city"], (None, None))))))
    for donor_id, name, group, channel, consent, last, city, contacts in POOL:
        lat, lon = coordinates.get(city, (None, None))
        repo.put_donor(Donor(
            donor_id=donor_id, name=name, blood_group=group, region="IN-TN",
            channel=channel, address=f"{donor_id}@example.test", city=city,
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
