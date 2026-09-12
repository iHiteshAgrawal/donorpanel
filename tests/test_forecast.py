from datetime import date

import pytest

from donorpanel.adapters.storage import FileStore, PanelRepository
from donorpanel.domain import Condition, Patient, Request, RequestStatus
from donorpanel.services import forecast

TODAY = date(2026, 11, 1)


@pytest.fixture
def repo(tmp_path):
    store = PanelRepository(store=FileStore(tmp_path))
    store.put_patient(Patient(patient_id="p-ravi", name="Ravi",
                              condition=Condition.THALASSEMIA, blood_group="B+",
                              policy_id="thalassemia-india", region="IN-TN"))
    return store


def transfused(repo, needed_by: str, status=RequestStatus.DISPATCHED, rid="r-1"):
    row = Request(request_id=rid, patient_id="p-ravi", policy_id="thalassemia-india",
                  units_needed=2, needed_by=needed_by)
    repo.put_request(row)
    repo.set_status(rid, status)
    return row


def test_a_patient_inside_the_lead_time_is_due(repo):
    # thalassemia-india: 21 day interval, 10 day lead. Last on Oct 20 means next is
    # Nov 10, and the lead time opens it from Oct 31.
    transfused(repo, "2026-10-20")
    rows = forecast.due(repo, TODAY)
    assert [r["patient_id"] for r in rows] == ["p-ravi"]
    assert rows[0]["needed_by"] == "2026-11-10"
    assert rows[0]["units_needed"] == 2


def test_a_patient_outside_the_lead_time_is_not(repo):
    transfused(repo, "2026-10-29")          # next is Nov 19, lead opens Nov 9
    assert forecast.due(repo, TODAY) == []


def test_a_patient_with_an_open_request_is_skipped(repo):
    # Yesterday's tick already opened Nov 10. Today's must not open it again, which is
    # what would otherwise happen every day until the first one closed.
    transfused(repo, "2026-10-20", rid="r-history")
    transfused(repo, "2026-11-10", status=RequestStatus.AWAITING_APPROVAL, rid="r-open")
    assert forecast.due(repo, TODAY) == []


def test_a_dispatched_request_in_the_past_is_history_not_a_blocker(repo):
    # in_flight() includes DISPATCHED. If that alone blocked a patient they would come
    # due exactly once and never again.
    transfused(repo, "2026-10-20", status=RequestStatus.DISPATCHED)
    assert [r["patient_id"] for r in forecast.due(repo, TODAY)] == ["p-ravi"]


def test_a_rejected_request_does_not_move_the_cycle(repo):
    # A rejection is not evidence a transfusion happened.
    transfused(repo, "2026-10-20", rid="r-real")
    transfused(repo, "2026-10-30", status=RequestStatus.REJECTED, rid="r-bad")
    assert forecast.due(repo, TODAY)[0]["needed_by"] == "2026-11-10"


def test_a_patient_with_no_history_is_not_guessed_at(repo):
    assert forecast.due(repo, TODAY) == []


def test_tick_runs_one_request_per_due_patient(repo):
    transfused(repo, "2026-10-20")
    seen = []

    def runner(ask, panel, graph, request_id, actor_id):
        seen.append(ask)
        return {"request_id": "r-new", "gate": {"gate": "auto"},
                "dispatch": {"delivered_count": 3}}

    out = forecast.tick(repo, TODAY, runner=runner)
    assert seen == [{"patient_id": "p-ravi", "needed_by": "2026-11-10", "units_needed": 2}]
    assert out["opened"][0]["delivered"] == 3
    assert out["failed"] == []


def test_one_failure_does_not_stop_the_others(repo):
    transfused(repo, "2026-10-20")
    repo.put_patient(Patient(patient_id="p-asha", name="Asha",
                             condition=Condition.THALASSEMIA, blood_group="O+",
                             policy_id="thalassemia-india", region="IN-TN"))
    second = Request(request_id="r-2", patient_id="p-asha", policy_id="thalassemia-india",
                     units_needed=2, needed_by="2026-10-20")
    repo.put_request(second)
    repo.set_status("r-2", RequestStatus.FULFILLED)

    def runner(ask, *rest):
        if ask["patient_id"] == "p-ravi":
            raise RuntimeError("bedrock is having a day")
        return {"request_id": "r-ok", "gate": {"gate": "auto"}, "dispatch": {}}

    out = forecast.tick(repo, TODAY, runner=runner)
    assert len(out["opened"]) == 1 and len(out["failed"]) == 1
    assert out["failed"][0]["patient"] == "Ravi"


def test_a_compatible_donor_is_never_told_they_cannot_help():
    """Nova claimed O+ cannot donate to B+ during a live conversation. The table is
    authoritative and O+ is a valid donor for B+; the tool must say so unambiguously."""
    from donorpanel.domain.matching import compatible_groups

    assert "O+" in compatible_groups("B+")
    assert set(compatible_groups("B+")) == {"O-", "O+", "B-", "B+"}
    # Universal donor reaches everyone; universal recipient receives from everyone.
    for recipient in ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"):
        assert "O-" in compatible_groups(recipient)
    assert len(compatible_groups("AB+")) == 8
