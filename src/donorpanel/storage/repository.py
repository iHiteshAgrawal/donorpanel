from boto3.dynamodb.conditions import Key

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
from . import table as t


class PanelRepository:
    def __init__(self, table=None):
        self._table = table or t.get_table()

    def _put(self, key: dict, obj, extra: dict | None = None) -> None:
        item = {**key, **t.encode(to_item(obj)), **(extra or {})}
        self._table.put_item(Item=item)

    def _get(self, key: dict) -> dict | None:
        got = self._table.get_item(Key=key).get("Item")
        return t.decode(got) if got else None

    @staticmethod
    def _strip(item: dict) -> dict:
        return {k: v for k, v in item.items()
                if k not in (t.PK, t.SK, t.GSI1PK, t.GSI1SK)}

    def put_donor(self, donor: Donor) -> None:
        self._put(t.donor_key(donor.donor_id), donor,
                  t.pool_key(donor.region, donor.blood_group, donor.donor_id))

    def get_donor(self, donor_id: str) -> Donor | None:
        item = self._get(t.donor_key(donor_id))
        return Donor(**self._strip(item)) if item else None

    def list_pool(self, region: str, blood_group: str) -> list[Donor]:
        res = self._table.query(
            IndexName=t.GSI1,
            KeyConditionExpression=Key(t.GSI1PK).eq(f"POOL#{region}#{blood_group}"),
        )
        return [Donor(**self._strip(t.decode(i))) for i in res.get("Items", [])]

    def put_patient(self, patient: Patient) -> None:
        self._put(t.patient_key(patient.patient_id), patient)

    def get_patient(self, patient_id: str) -> Patient | None:
        item = self._get(t.patient_key(patient_id))
        return Patient(**self._strip(item)) if item else None

    def put_request(self, request: Request) -> None:
        request.updated_at = now()
        self._put(t.request_key(request.request_id), request)

    def get_request(self, request_id: str) -> Request | None:
        item = self._get(t.request_key(request_id))
        return Request(**self._strip(item)) if item else None

    def set_status(self, request_id: str, status: RequestStatus) -> Request:
        request = self.get_request(request_id)
        if request is None:
            raise KeyError(f"no request {request_id}")
        request.status = status
        self.put_request(request)
        return request

    def put_contact(self, contact: Contact) -> None:
        self._put(t.contact_key(contact.request_id, contact.donor_id), contact)

    def list_contacts(self, request_id: str) -> list[Contact]:
        res = self._table.query(
            KeyConditionExpression=Key(t.PK).eq(f"REQUEST#{request_id}")
            & Key(t.SK).begins_with("CONTACT#"),
        )
        items = [Contact(**self._strip(t.decode(i))) for i in res.get("Items", [])]
        return sorted(items, key=lambda c: c.rank)

    def pledged_units(self, request_id: str) -> int:
        return sum(1 for c in self.list_contacts(request_id)
                   if c.status in (ContactStatus.PLEDGED, ContactStatus.DONATED))

    def get_credit(self, patient_id: str) -> Credit:
        item = self._get(t.credit_key(patient_id))
        return Credit(**self._strip(item)) if item else Credit(patient_id=patient_id)

    def put_credit(self, credit: Credit) -> None:
        self._put(t.credit_key(credit.patient_id), credit)
