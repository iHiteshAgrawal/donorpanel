from math import asin, cos, radians, sin, sqrt

from .models import Donor, days_since

# Red cell compatibility for a recipient group. Plasma and platelets run the
# opposite direction, so do not reuse this table for those components.
COMPATIBLE_DONORS: dict[str, tuple[str, ...]] = {
    "O-": ("O-",),
    "O+": ("O-", "O+"),
    "A-": ("O-", "A-"),
    "A+": ("O-", "O+", "A-", "A+"),
    "B-": ("O-", "B-"),
    "B+": ("O-", "O+", "B-", "B+"),
    "AB-": ("O-", "A-", "B-", "AB-"),
    "AB+": ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"),
}


def compatible_groups(recipient: str) -> tuple[str, ...]:
    return COMPATIBLE_DONORS.get(recipient.strip().upper(), ())


def distance_km(lat1, lon1, lat2, lon2) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = p2 - p1, radians(lon2 - lon1)
    h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return round(2 * 6371.0 * asin(sqrt(h)), 1)


def ineligible_reason(donor: Donor, rules: dict, required_antigens: list[str]) -> str | None:
    if not donor.consent:
        return "no consent on file"
    if not donor.reachable:
        return "marked unreachable"

    gap = rules.get("min_days_between_donations")
    rested = days_since(donor.last_donation)
    if gap and rested is not None and rested < gap:
        return f"donated {rested} days ago, needs {gap}"

    missing = [a for a in required_antigens if a not in donor.antigens]
    if missing:
        return f"missing antigen {', '.join(missing)}"
    return None


def score(donor: Donor, rules: dict, patient_lat=None, patient_lon=None,
          prefer_repeat: bool = True) -> tuple[float, dict]:
    parts: dict[str, float] = {}

    rested = days_since(donor.last_donation)
    gap = rules.get("min_days_between_donations") or 90
    if rested is None:
        parts["never_donated"] = 20.0
    else:
        parts["rested"] = min(40.0, 20.0 + (rested - gap) / 6)

    fatigue = donor.contacts_this_month
    parts["contact_fatigue"] = -12.0 * fatigue

    if prefer_repeat and donor.last_donation:
        parts["repeat_donor"] = 15.0

    km = distance_km(patient_lat, patient_lon, donor.lat, donor.lon)
    if km is not None:
        parts["proximity"] = max(0.0, 25.0 - km / 4)

    return round(sum(parts.values()), 1), {k: round(v, 1) for k, v in parts.items()}
