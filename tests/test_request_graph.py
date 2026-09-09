import os
from typing import Any

import pytest

from donorpanel.domain import Condition, Patient, RequestStatus
from donorpanel.graphs import request as flow
from donorpanel.nodes.base import DeterministicNode
from donorpanel.storage import FileStore, PanelRepository


class StubVerifier(DeterministicNode):
    name = "verify"

    def __init__(self, verdict: str, reason: str = "stub"):
        super().__init__()
        self.verdict = verdict
        self.reason = reason
        self.seen: list[str] = []

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        self.seen.append(str(task))
        return {"verdict": self.verdict, "reason": self.reason}


@pytest.fixture
def repo(tmp_path):
    repo = PanelRepository(store=FileStore(tmp_path))
    repo.put_patient(Patient(patient_id="p-ravi", name="Ravi",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN"))
    return repo


def ask(repo, verdict, reason="stub", **overrides):
    stub = StubVerifier(verdict, reason)
    graph = flow.build(agent=stub)
    raw = {"patient_id": "p-ravi", "units_needed": 2, "needed_by": "2026-10-01"}
    raw.update(overrides)
    return flow.run(raw, repo=repo, graph=graph), stub


def test_verified_request_takes_the_accept_branch(repo):
    out, _ = ask(repo, "verified", "matches the 21 day interval")
    assert out["path"] == ["intake", "verify", "adjudicate", "accept",
                           "eligibility", "rank"]
    assert out["verdict"]["verdict"] == "verified"
    assert repo.get_request(out["request_id"]).status == RequestStatus.MATCHING


def test_rejected_request_takes_the_close_branch(repo):
    out, _ = ask(repo, "rejected", "duplicate of r-existing")
    assert out["path"] == ["intake", "verify", "adjudicate", "close"]
    stored = repo.get_request(out["request_id"])
    assert stored.status == RequestStatus.REJECTED
    assert stored.rejection_reason == "duplicate of r-existing"


def test_only_one_branch_ever_runs(repo):
    out, _ = ask(repo, "verified")
    assert "close" not in out["path"]


def test_rejected_requests_never_reach_matching(repo):
    out, _ = ask(repo, "rejected")
    assert "eligibility" not in out["path"]
    assert "rank" not in out["path"]


def test_fact_sheet_reaches_the_verifier(repo):
    _, stub = ask(repo, "verified")
    seen = stub.seen[0]
    assert "thalassemia-india" in seen
    assert "interval_days" in seen
    assert "days_until_needed" in seen


def test_unknown_patient_is_flagged_before_the_model_sees_it(repo):
    _, stub = ask(repo, "rejected", patient_id="p-nobody")
    assert '"patient_known": false' in stub.seen[0]


def test_intake_persists_the_request_as_draft_before_verification(repo):
    stub = StubVerifier("verified")
    graph = flow.build(agent=stub)
    out = flow.run({"patient_id": "p-ravi", "units_needed": 2,
                      "needed_by": "2026-10-01"}, repo=repo, graph=graph,
                     request_id="r-fixed")
    assert out["request_id"] == "r-fixed"
    assert repo.get_request("r-fixed") is not None


def test_open_requests_are_surfaced_to_the_verifier(repo):
    ask(repo, "verified")
    _, stub = ask(repo, "verified")
    assert '"open_requests"' in stub.seen[0]
    assert "r-" in stub.seen[0]


@pytest.mark.skipif(not os.getenv("DONORPANEL_LIVE"),
                    reason="set DONORPANEL_LIVE=1 to call Bedrock")
def test_live_verifier_rejects_an_unknown_patient(repo):
    out = flow.run({"patient_id": "p-nobody", "units_needed": 2,
                      "needed_by": "2026-10-01"}, repo=repo)
    assert out["verdict"]["verdict"] == "rejected"
    assert out["path"][-1] == "close"


class SilentVerifier(DeterministicNode):
    name = "verify"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        return {"thinking": "looks fine to me but I forgot the verdict"}


def test_a_verifier_that_returns_no_verdict_fails_closed(repo):
    graph = flow.build(agent=SilentVerifier())
    out = flow.run({"patient_id": "p-ravi", "units_needed": 2,
                      "needed_by": "2026-10-01"}, repo=repo, graph=graph)
    assert out["path"] == ["intake", "verify", "adjudicate", "close"]
    assert out["verdict"]["decided_by"] == "fallback"
    stored = repo.get_request(out["request_id"])
    assert stored.status == RequestStatus.REJECTED
    assert "human review" in stored.rejection_reason


def test_cadence_gap_is_measured_between_needed_by_dates(repo):
    ask(repo, "verified", needed_by="2026-10-01")
    _, stub = ask(repo, "verified", needed_by="2026-10-22")
    assert '"days_since_previous_needed_by": 21' in stub.seen[0]


def pool_of(repo, rows):
    from donorpanel.domain import Donor

    for donor_id, group, consent, last, lat, lon in rows:
        repo.put_donor(Donor(donor_id=donor_id, name=donor_id, blood_group=group,
                             region="IN-TN", channel="telegram", address="x",
                             consent=consent, last_donation=last, lat=lat, lon=lon))


def test_incompatible_groups_never_enter_the_pool(repo):
    pool_of(repo, [("d-b", "B+", True, None, None, None),
                   ("d-a", "A+", True, None, None, None),
                   ("d-o", "O-", True, None, None, None)])
    out, _ = ask(repo, "verified")
    assert out["eligibility"]["pool_size"] == 2
    assert set(out["eligibility"]["eligible"]) == {"d-b", "d-o"}


def test_ineligible_donors_are_excluded_with_a_reason(repo):
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc).date() - timedelta(days=10)).isoformat()
    pool_of(repo, [("d-ok", "B+", True, None, None, None),
                   ("d-noconsent", "B+", False, None, None, None),
                   ("d-recent", "B+", True, recent, None, None)])
    out, _ = ask(repo, "verified")
    reasons = {x["donor_id"]: x["reason"] for x in out["eligibility"]["excluded"]}
    assert reasons["d-noconsent"] == "no consent on file"
    assert "needs 90" in reasons["d-recent"]
    assert out["eligibility"]["eligible"] == ["d-ok"]


def test_ranking_persists_contacts_in_rank_order(repo):
    pool_of(repo, [("d-far", "B+", True, None, 13.08, 80.27),
                   ("d-near", "B+", True, None, 11.02, 76.96)])
    repo.put_patient(Patient(patient_id="p-ravi", name="Ravi",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN",
                             lat=11.0168, lon=76.9558))
    out, _ = ask(repo, "verified")
    contacts = repo.list_contacts(out["request_id"])
    assert [c.donor_id for c in contacts] == ["d-near", "d-far"]
    assert [c.rank for c in contacts] == [1, 2]
    assert all(c.status.value == "pending" for c in contacts)


def test_an_empty_pool_reports_a_shortfall(repo):
    out, _ = ask(repo, "verified")
    assert out["cohort"]["cohort_size"] == 0
    assert out["cohort"]["shortfall"] == 2
    assert out["cohort"]["enough_to_proceed"] is False
