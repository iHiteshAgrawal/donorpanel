import os
from types import SimpleNamespace
from typing import Any

import pytest

from donorpanel.domain import Condition, Patient, RequestStatus
from donorpanel.graphs import request as flow
from donorpanel.nodes.base import JsonNode
from donorpanel.storage import FileStore, PanelRepository


class StubVerifier(JsonNode):
    name = "verify"

    def __init__(self, verdict: str, reason: str = "stub", needs_review: bool = False,
                 review_reason: str | None = None):
        super().__init__()
        self.verdict = verdict
        self.reason = reason
        self.needs_review = needs_review
        self.review_reason = review_reason
        self.seen: list[str] = []

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        self.seen.append(str(task))
        return {"verdict": self.verdict, "reason": self.reason,
                "needs_review": self.needs_review, "review_reason": self.review_reason}


def wired():
    """The seeded pool is on telegram, which is not configured in tests."""
    from donorpanel.channels import ConsoleChannel

    sender = ConsoleChannel()
    return {"telegram": sender, "email": sender, "console": sender}


@pytest.fixture
def repo(tmp_path):
    repo = PanelRepository(store=FileStore(tmp_path))
    repo.put_patient(Patient(patient_id="p-ravi", name="Ravi",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN"))
    return repo


class StubComposer:
    def __init__(self, drafts=None):
        self.drafts = drafts or [{"language": "ta", "channel": "telegram",
                                  "subject": None, "body": "Hello {name}"}]
        self.briefs = []

    def __call__(self, prompt, invocation_state=None, structured_output_model=None,
                 structured_output_prompt=None, **kwargs):
        self.briefs.append(prompt)
        return SimpleNamespace(
            structured_output=structured_output_model(drafts=self.drafts),
            __str__=lambda _: "drafted",
        )


def ask(repo, verdict, reason="stub", composer=None, needs_review=False,
        review_reason=None, channels=None, **overrides):
    stub = StubVerifier(verdict, reason, needs_review, review_reason)
    graph = flow.build(agent=stub, composer_agent=composer or StubComposer(),
                       channels=channels if channels is not None else wired())
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


class SilentVerifier(JsonNode):
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


class ChattyAgent:
    """Reasons in prose and never prints JSON, the exact Nova failure mode."""

    def __init__(self, verdict="verified", reason="looks fine"):
        self.verdict, self.reason = verdict, reason
        self.prompts = []

    def __call__(self, prompt, invocation_state=None, structured_output_model=None,
                 structured_output_prompt=None, **kwargs):
        self.prompts.append(prompt)
        self.state_seen = invocation_state
        return SimpleNamespace(
            structured_output=structured_output_model(verdict=self.verdict,
                                                      reason=self.reason),
            __str__=lambda _: "I considered the fact sheet and reached a view.",
        )


def test_structured_output_rescues_a_verifier_that_writes_no_json(repo):
    from donorpanel.nodes import RequestVerifier

    chatty = ChattyAgent("verified", "interval respected")
    out = flow.run({"patient_id": "p-ravi", "units_needed": 2, "needed_by": "2026-10-01"},
                   repo=repo, graph=flow.build(agent=RequestVerifier(agent=chatty)))

    assert out["verdict"]["verdict"] == "verified"
    assert out["verdict"]["decided_by"] == "verifier"
    assert out["path"][-1] == "rank"
    assert chatty.state_seen["request_id"] == out["request_id"]


def test_the_reasoning_pass_sees_the_fact_sheet(repo):
    from donorpanel.nodes import RequestVerifier

    chatty = ChattyAgent()
    flow.run({"patient_id": "p-ravi", "units_needed": 2, "needed_by": "2026-10-01"},
             repo=repo, graph=flow.build(agent=RequestVerifier(agent=chatty)))
    assert "interval_days" in chatty.prompts[0]


def test_a_structured_rejection_still_closes_the_request(repo):
    from donorpanel.nodes import RequestVerifier

    chatty = ChattyAgent("rejected", "duplicate of an open request")
    out = flow.run({"patient_id": "p-ravi", "units_needed": 2, "needed_by": "2026-10-01"},
                   repo=repo, graph=flow.build(agent=RequestVerifier(agent=chatty)))
    assert out["path"][-1] == "close"
    assert repo.get_request(out["request_id"]).rejection_reason == "duplicate of an open request"


def with_pool(repo):
    pool_of(repo, [("d-one", "B+", True, None, 11.02, 76.96),
                   ("d-two", "O-", True, None, 11.09, 77.36)])
    repo.put_patient(Patient(patient_id="p-ravi", name="Ravi Kumar",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN",
                             city="Coimbatore", hospital="Government Hospital",
                             lat=11.0168, lon=76.9558))


def test_an_empty_cohort_never_reaches_the_composer(repo):
    out, _ = ask(repo, "verified")
    assert out["path"][-1] == "rank"
    assert "compose" not in out["path"]
    assert "gate" not in out["path"]


def test_a_thin_cohort_is_composed_and_escalated(repo):
    with_pool(repo)
    out, _ = ask(repo, "verified")
    assert out["path"][-2:] == ["compose", "gate"]
    assert out["gate"]["gate"] == "escalated"
    assert repo.get_request(out["request_id"]).status == RequestStatus.AWAITING_APPROVAL
    assert [c["donor_id"] for c in out["gate"]["cohort"]] == ["d-one", "d-two"]


def test_the_verifier_can_demand_a_human_in_its_own_words(repo):
    big_pool(repo)
    ask(repo, "verified", needed_by="2026-10-01")
    out, _ = ask(repo, "verified", needed_by="2026-11-05", needs_review=True,
                 review_reason="no prescription on file for this transfusion")

    assert out["gate"]["gate"] == "escalated"
    assert "no prescription on file for this transfusion" in out["gate"]["reasons"]
    assert repo.get_request(out["request_id"]).status == RequestStatus.AWAITING_APPROVAL


def test_a_review_flag_with_no_reason_still_escalates(repo):
    big_pool(repo)
    ask(repo, "verified", needed_by="2026-10-01")
    out, _ = ask(repo, "verified", needed_by="2026-11-05", needs_review=True)
    assert out["gate"]["gate"] == "escalated"
    assert out["gate"]["reasons"] == ["the verifier asked for a human"]


def test_a_first_ever_request_is_no_longer_escalated_for_being_first(repo):
    big_pool(repo)
    out, _ = ask(repo, "verified")
    assert out["gate"]["gate"] == "auto"


def big_pool(repo):
    """Six eligible donors, enough to clear a 2x cohort multiple for 2 units."""
    pool_of(repo, [(f"d-{i}", "B+", True, None, 11.02, 76.96) for i in range(6)])
    repo.put_patient(Patient(patient_id="p-ravi", name="Ravi Kumar",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN",
                             city="Coimbatore", hospital="Government Hospital",
                             lat=11.0168, lon=76.9558))


def test_a_routine_repeat_request_is_sent_without_waking_anyone(repo):
    big_pool(repo)
    ask(repo, "verified", needed_by="2026-10-01")          # establishes history
    out, _ = ask(repo, "verified", needed_by="2026-11-05")

    assert out["gate"]["gate"] == "auto"
    assert out["gate"]["decided_by"] == "policy"
    assert repo.get_request(out["request_id"]).status == RequestStatus.DISPATCHED
    assert repo.get_approval(out["request_id"])["by"] == "agent"
    assert out["dispatch"]["delivered_count"] == 6


def test_an_emergency_always_escalates(repo):
    big_pool(repo)
    ask(repo, "verified", needed_by="2026-10-01")
    out, _ = ask(repo, "verified", needed_by="2026-11-05", source="emergency")
    assert out["gate"]["gate"] == "escalated"
    assert any("emergency" in r for r in out["gate"]["reasons"])


def test_a_thin_cohort_escalates_rather_than_sending(repo):
    with_pool(repo)
    ask(repo, "verified", needed_by="2026-10-01")
    out, _ = ask(repo, "verified", needed_by="2026-11-05")
    assert out["gate"]["gate"] == "escalated"
    assert any("below the" in r for r in out["gate"]["reasons"])


def test_a_tired_donor_blocks_autonomy(repo):

    big_pool(repo)
    ask(repo, "verified", needed_by="2026-10-01")
    worn = repo.get_donor("d-0")
    worn.contacts_this_month = 9
    repo.put_donor(worn)
    out, _ = ask(repo, "verified", needed_by="2026-11-05")
    assert out["gate"]["gate"] == "escalated"
    assert any("contacted 9 times" in r for r in out["gate"]["reasons"])


def test_an_existing_human_approval_still_wins(repo):
    big_pool(repo)
    first, _ = ask(repo, "verified")
    repo.approve(first["request_id"], by="coordinator-anita")
    graph = flow.build(agent=StubVerifier("verified"), composer_agent=StubComposer())
    again = flow.run({"patient_id": "p-ravi", "units_needed": 2,
                      "needed_by": "2026-10-01"}, repo=repo, graph=graph,
                     request_id=first["request_id"])
    assert again["gate"]["gate"] == "approved"
    assert again["gate"]["decided_by"] == "human"


def test_the_gate_opens_once_approval_is_recorded(repo):
    with_pool(repo)
    first, _ = ask(repo, "verified")
    repo.approve(first["request_id"], by="coordinator-anita")

    graph = flow.build(agent=StubVerifier("verified"), composer_agent=StubComposer())
    second = flow.run({"patient_id": "p-ravi", "units_needed": 2,
                       "needed_by": "2026-10-01"}, repo=repo, graph=graph,
                      request_id=first["request_id"])
    assert second["gate"]["gate"] == "approved"
    assert second["gate"]["by"] == "coordinator-anita"


def test_the_brief_carries_no_patient_detail_beyond_a_first_name(repo):
    with_pool(repo)
    composer = StubComposer()
    ask(repo, "verified", composer=composer)
    brief = composer.briefs[0]
    assert '"patient_first_name": "Ravi"' in brief
    assert "Kumar" not in brief
    assert "thalassemia" not in brief.lower()


def test_donors_are_grouped_by_language_and_channel(repo):
    with_pool(repo)
    composer = StubComposer()
    out, _ = ask(repo, "verified", composer=composer)
    groups = out["drafts"]["brief"]["groups"]
    assert groups == [{"language": "en", "channel": "telegram", "donors": 2}]


def test_drafts_are_persisted_for_the_coordinator(repo):
    with_pool(repo)
    out, _ = ask(repo, "verified")
    stored = repo.get_drafts(out["request_id"])
    assert stored[0]["body"] == "Hello {name}"
    assert [r.request_id for r in repo.awaiting_approval()] == [out["request_id"]]
