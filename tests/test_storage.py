import pytest

from donorpanel.domain import (
    Component,
    Condition,
    Contact,
    ContactStatus,
    Donor,
    Patient,
    Request,
    RequestStatus,
)
from donorpanel.storage import PanelRepository


@pytest.fixture
def repo(ddb):
    return PanelRepository(table=ddb)


def donor(donor_id="d1", group="B+", region="IN-TN", **kw):
    return Donor(donor_id=donor_id, name="Asha", blood_group=group, region=region,
                 channel="telegram", address="123", **kw)


def test_donor_roundtrip(repo):
    repo.put_donor(donor(lat=11.0168, lon=76.9558, antigens=["Ro"]))
    got = repo.get_donor("d1")
    assert got.name == "Asha"
    assert got.lat == 11.0168
    assert got.antigens == ["Ro"]
    assert got.consent is False


def test_missing_donor_is_none(repo):
    assert repo.get_donor("nope") is None


def test_pool_query_is_scoped_by_region_and_group(repo):
    repo.put_donor(donor("d1", "B+", "IN-TN"))
    repo.put_donor(donor("d2", "B+", "IN-TN"))
    repo.put_donor(donor("d3", "O-", "IN-TN"))
    repo.put_donor(donor("d4", "B+", "IN-KA"))
    assert {d.donor_id for d in repo.list_pool("IN-TN", "B+")} == {"d1", "d2"}


def test_patient_and_request(repo):
    repo.put_patient(Patient(patient_id="p1", name="Ravi",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN"))
    repo.put_request(Request(request_id="r1", patient_id="p1",
                             policy_id="thalassemia-india", units_needed=2,
                             needed_by="2026-09-21", component=Component.PACKED_CELLS))
    assert repo.get_patient("p1").condition == Condition.THALASSEMIA
    assert repo.get_request("r1").units_needed == 2
    assert repo.set_status("r1", RequestStatus.VERIFIED).status == RequestStatus.VERIFIED


def test_contacts_sort_by_rank_and_count_pledges(repo):
    repo.put_contact(Contact(request_id="r1", donor_id="d2", rank=2))
    repo.put_contact(Contact(request_id="r1", donor_id="d1", rank=1,
                             status=ContactStatus.PLEDGED))
    repo.put_contact(Contact(request_id="r1", donor_id="d3", rank=3,
                             status=ContactStatus.DECLINED))
    assert [c.donor_id for c in repo.list_contacts("r1")] == ["d1", "d2", "d3"]
    assert repo.pledged_units("r1") == 1


def test_credit_defaults_and_outstanding(repo):
    credit = repo.get_credit("p1")
    assert credit.outstanding == 0
    credit.units_owed = 4
    credit.units_repaid = 1
    repo.put_credit(credit)
    assert repo.get_credit("p1").outstanding == 3
