"""The shared pool anyone can join from Telegram.

Per-actor sandboxes keep one visitor's console from colliding with another's. A donor
who registers over Telegram belongs to no browser session, so they land here instead,
alongside a real patient with a real open need.
"""
import logging

from .domain import Condition, Patient, Request, RequestSource, RequestStatus
from .storage import PanelRepository, store

log = logging.getLogger(__name__)

PREFIX = "actors/public/"

PATIENT = {
    "patient_id": "p-ravi", "name": "Ravi", "condition": Condition.THALASSEMIA,
    "blood_group": "B+", "policy_id": "thalassemia-india", "region": "IN-TN",
    "city": "Coimbatore", "hospital": "Government Hospital",
}
OPEN_REQUEST = "r-public-open"


def repo() -> PanelRepository:
    return PanelRepository(store=store(PREFIX))


def ensure(target=None) -> PanelRepository:
    """Idempotent. A registrant needs somewhere to be useful the moment they join,
    so the public pool always carries one patient with one open request."""
    panel = target or repo()
    if panel.get_patient(PATIENT["patient_id"]) is None:
        panel.put_patient(Patient(**PATIENT, lat=11.0168, lon=76.9558))
    if panel.get_request(OPEN_REQUEST) is None:
        panel.put_request(Request(
            request_id=OPEN_REQUEST, patient_id=PATIENT["patient_id"],
            policy_id=PATIENT["policy_id"], units_needed=2,
            needed_by="2026-12-20", source=RequestSource.SCHEDULED,
            status=RequestStatus.MATCHING))
    return panel


def headcount(panel=None) -> dict[str, int]:
    panel = panel or repo()
    donors = panel.list_donors()
    requests = [r for r in (panel.get_request(i) for i in _request_ids(panel)) if r]
    reached = 0
    for request in requests:
        reached += sum(1 for c in panel.list_contacts(request.request_id)
                       if c.contacted_at)
    return {"donors": len(donors),
            "consented": sum(1 for d in donors if d.consent),
            "cities": len({d.city for d in donors if d.city}),
            "requests": len(requests),
            "reached": reached}


def _request_ids(panel) -> list[str]:
    return [k.rsplit("/", 1)[-1].removesuffix(".json")
            for k in panel.store.keys("requests/")]
