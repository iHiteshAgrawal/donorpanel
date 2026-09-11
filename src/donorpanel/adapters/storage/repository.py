from concurrent.futures import ThreadPoolExecutor

from donorpanel.adapters.storage import objects as o
from donorpanel.adapters.storage.local import FileStore
from donorpanel.domain import (
    Contact,
    ContactStatus,
    Donor,
    Patient,
    Request,
    RequestStatus,
    now,
    to_item,
)


class PanelRepository:
    def __init__(self, store: "o.ObjectStore | FileStore | None" = None):
        if store is None:
            from donorpanel.adapters.storage import store as default_store

            store = default_store()
        self.store = store
        self._donors: dict[str, Donor | None] = {}
        self._patients: dict[str, Patient | None] = {}

    def put_donor(self, donor: Donor) -> None:
        self._donors.pop(donor.donor_id, None)
        previous = self.get_donor(donor.donor_id)
        if previous and (previous.region, previous.blood_group) != (donor.region, donor.blood_group):
            self.store.delete(o.POOL.format(region=previous.region,
                                            blood_group=previous.blood_group,
                                            donor_id=previous.donor_id))
        self.store.put(o.DONOR.format(donor_id=donor.donor_id), to_item(donor))
        self.store.touch(o.POOL.format(region=donor.region,
                                       blood_group=donor.blood_group,
                                       donor_id=donor.donor_id))
        self._donors[donor.donor_id] = donor

    def get_donor(self, donor_id: str) -> Donor | None:
        if donor_id not in self._donors:
            item = self.store.get(o.DONOR.format(donor_id=donor_id))
            self._donors[donor_id] = Donor(**item) if item else None
        return self._donors[donor_id]

    def get_donors(self, donor_ids: list[str]) -> list[Donor]:
        # Sydney round trips are ~200ms each, so fetching a pool one at a time
        # costs seconds. The repository is per request, so the cache is safe.
        missing = [d for d in donor_ids if d not in self._donors]
        if missing:
            with ThreadPoolExecutor(max_workers=12) as pool:
                for donor_id, donor in zip(missing, pool.map(self.get_donor, missing)):
                    self._donors[donor_id] = donor
        return [d for d in (self._donors.get(i) for i in donor_ids) if d is not None]

    def list_donors(self) -> list[Donor]:
        ids = [k.rsplit("/", 1)[-1].removesuffix(".json")
               for k in self.store.keys("donors/")]
        return sorted(self.get_donors(ids), key=lambda d: d.donor_id)

    def list_pool(self, region: str, blood_group: str) -> list[Donor]:
        prefix = o.POOL.format(region=region, blood_group=blood_group, donor_id="")
        ids = [key.rsplit("/", 1)[-1] for key in self.store.keys(prefix)]
        return self.get_donors(ids)

    def put_patient(self, patient: Patient) -> None:
        self.store.put(o.PATIENT.format(patient_id=patient.patient_id), to_item(patient))
        self._patients[patient.patient_id] = patient

    def get_patient(self, patient_id: str) -> Patient | None:
        if patient_id not in self._patients:
            item = self.store.get(o.PATIENT.format(patient_id=patient_id))
            self._patients[patient_id] = Patient(**item) if item else None
        return self._patients[patient_id]

    def put_request(self, request: Request) -> None:
        request.updated_at = now()
        self.store.put(o.REQUEST.format(request_id=request.request_id), to_item(request))
        self.store.touch(o.PATIENT_REQUEST.format(patient_id=request.patient_id,
                                                  request_id=request.request_id))

    def list_requests(self, patient_id: str) -> list[Request]:
        prefix = o.PATIENT_REQUEST.format(patient_id=patient_id, request_id="")
        ids = [key.rsplit("/", 1)[-1] for key in self.store.keys(prefix)]
        found = [self.get_request(request_id) for request_id in ids]
        requests = [r for r in found if r is not None]
        return sorted(requests, key=lambda r: r.created_at, reverse=True)

    # DRAFT is deliberately not "open". Intake persists a draft before the verifier
    # runs, so counting drafts would make every abandoned request look like a
    # duplicate of the next real one.
    OPEN_STATUSES = (RequestStatus.VERIFIED, RequestStatus.MATCHING,
                     RequestStatus.AWAITING_APPROVAL, RequestStatus.DISPATCHED)

    def open_requests(self, patient_id: str, exclude: str | None = None) -> list[Request]:
        return [r for r in self.list_requests(patient_id)
                if r.status in self.OPEN_STATUSES and r.request_id != exclude]

    def get_request(self, request_id: str) -> Request | None:
        item = self.store.get(o.REQUEST.format(request_id=request_id))
        return Request(**item) if item else None

    def set_status(self, request_id: str, status: RequestStatus) -> Request:
        request = self.get_request(request_id)
        if request is None:
            raise KeyError(f"no request {request_id}")
        request.status = status
        self.put_request(request)
        return request

    def put_contact(self, contact: Contact) -> None:
        self.store.put(o.CONTACT.format(request_id=contact.request_id,
                                        donor_id=contact.donor_id), to_item(contact))

    def put_contacts(self, contacts: list[Contact]) -> None:
        if not contacts:
            return
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(self.put_contact, contacts))

    def list_contacts(self, request_id: str) -> list[Contact]:
        prefix = o.CONTACT.format(request_id=request_id, donor_id="").rsplit("/", 1)[0] + "/"
        keys = self.store.keys(prefix)
        with ThreadPoolExecutor(max_workers=12) as pool:
            found = list(pool.map(self.store.get, keys)) if keys else []
        contacts = [Contact(**item) for item in found if item]
        return sorted(contacts, key=lambda c: c.rank)

    def pledged_units(self, request_id: str) -> int:
        return sum(1 for c in self.list_contacts(request_id)
                   if c.status in (ContactStatus.PLEDGED, ContactStatus.DONATED))

    def put_drafts(self, request_id: str, drafts: list[dict]) -> None:
        self.store.put(o.DRAFTS.format(request_id=request_id), {"drafts": drafts})

    def get_drafts(self, request_id: str) -> list[dict]:
        found = self.store.get(o.DRAFTS.format(request_id=request_id))
        return (found or {}).get("drafts", [])

    def approve(self, request_id: str, by: str, note: str | None = None) -> None:
        self.store.put(o.APPROVAL.format(request_id=request_id),
                       {"request_id": request_id, "approved": True, "by": by,
                        "note": note, "at": now()})

    def get_approval(self, request_id: str) -> dict | None:
        return self.store.get(o.APPROVAL.format(request_id=request_id))

    def awaiting_approval(self) -> list[Request]:
        ids = [k.rsplit("/", 1)[-1].removesuffix(".json")
               for k in self.store.keys("requests/")]
        found = [self.get_request(i) for i in ids]
        return [r for r in found
                if r is not None and r.status == RequestStatus.AWAITING_APPROVAL]

    def in_flight(self) -> list[Request]:
        """Requests a donor could still be answering: waiting on a coordinator, or
        already sent out and not yet closed."""
        ids = [k.rsplit("/", 1)[-1].removesuffix(".json")
               for k in self.store.keys("requests/")]
        found = [self.get_request(i) for i in ids]
        return [r for r in found if r is not None and r.status in
                (RequestStatus.AWAITING_APPROVAL, RequestStatus.DISPATCHED)]

