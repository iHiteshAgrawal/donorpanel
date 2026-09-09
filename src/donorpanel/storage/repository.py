from ..domain import (
    Contact,
    ContactStatus,
    Credit,
    Donor,
    Patient,
    Request,
    RequestStatus,
    now,
    to_item,
)
from . import objects as o
from .local import FileStore


class PanelRepository:
    def __init__(self, store: "o.ObjectStore | FileStore | None" = None):
        if store is None:
            from . import store as default_store

            store = default_store()
        self.store = store

    def put_donor(self, donor: Donor) -> None:
        previous = self.get_donor(donor.donor_id)
        if previous and (previous.region, previous.blood_group) != (donor.region, donor.blood_group):
            self.store.delete(o.POOL.format(region=previous.region,
                                            blood_group=previous.blood_group,
                                            donor_id=previous.donor_id))
        self.store.put(o.DONOR.format(donor_id=donor.donor_id), to_item(donor))
        self.store.touch(o.POOL.format(region=donor.region,
                                       blood_group=donor.blood_group,
                                       donor_id=donor.donor_id))

    def get_donor(self, donor_id: str) -> Donor | None:
        item = self.store.get(o.DONOR.format(donor_id=donor_id))
        return Donor(**item) if item else None

    def list_pool(self, region: str, blood_group: str) -> list[Donor]:
        prefix = o.POOL.format(region=region, blood_group=blood_group, donor_id="")
        ids = [key.rsplit("/", 1)[-1] for key in self.store.keys(prefix)]
        found = [self.get_donor(donor_id) for donor_id in ids]
        return [d for d in found if d is not None]

    def put_patient(self, patient: Patient) -> None:
        self.store.put(o.PATIENT.format(patient_id=patient.patient_id), to_item(patient))

    def get_patient(self, patient_id: str) -> Patient | None:
        item = self.store.get(o.PATIENT.format(patient_id=patient_id))
        return Patient(**item) if item else None

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

    def list_contacts(self, request_id: str) -> list[Contact]:
        prefix = o.CONTACT.format(request_id=request_id, donor_id="").rsplit("/", 1)[0] + "/"
        found = [self.store.get(key) for key in self.store.keys(prefix)]
        contacts = [Contact(**item) for item in found if item]
        return sorted(contacts, key=lambda c: c.rank)

    def pledged_units(self, request_id: str) -> int:
        return sum(1 for c in self.list_contacts(request_id)
                   if c.status in (ContactStatus.PLEDGED, ContactStatus.DONATED))

    def get_credit(self, patient_id: str) -> Credit:
        item = self.store.get(o.CREDIT.format(patient_id=patient_id))
        return Credit(**item) if item else Credit(patient_id=patient_id)

    def put_credit(self, credit: Credit) -> None:
        self.store.put(o.CREDIT.format(patient_id=credit.patient_id), to_item(credit))
