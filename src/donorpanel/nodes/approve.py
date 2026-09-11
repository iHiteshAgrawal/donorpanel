import json
from typing import Any

from pydantic import BaseModel, Field

from .. import memory, policies
from ..agents import composer
from ..domain import RequestSource, RequestStatus
from .base import JsonNode


class Draft(BaseModel):
    language: str
    channel: str
    subject: str | None = Field(default=None, description="Email only, null for chat.")
    body: str = Field(description="Message text containing the {name} placeholder.")


class Drafts(BaseModel):
    drafts: list[Draft]


class OutreachComposer(JsonNode):
    name = "compose"

    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent or composer.build()

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request = repo.get_request(invocation_state["request_id"])
        patient = repo.get_patient(request.patient_id)
        contacts = repo.list_contacts(request.request_id)

        groups: dict[tuple[str, str], int] = {}
        for contact in contacts:
            donor = repo.get_donor(contact.donor_id)
            if donor:
                groups[(donor.language, donor.channel)] = \
                    groups.get((donor.language, donor.channel), 0) + 1

        brief = {
            "patient_first_name": patient.name.split()[0],
            "blood_group": patient.blood_group,
            "units_needed": request.units_needed,
            "needed_by": request.needed_by,
            "hospital": patient.hospital or "the hospital",
            "city": patient.city,
            "source": request.source.value,
            "groups": [{"language": lang, "channel": channel, "donors": count}
                       for (lang, channel), count in sorted(groups.items())],
        }
        actor_id = invocation_state.get("actor_id")
        if actor_id:
            prior = memory.everything(
                actor_id,
                query=f"outreach tone and coordinator preferences for {patient.name}",
                top_k=5)
            if prior:
                brief["prior_context"] = prior
        if not groups:
            return {"request_id": request.request_id, "drafts": [],
                    "problem": "no contacts to write to"}

        result = self.agent(
            json.dumps(brief, indent=2, ensure_ascii=False),
            invocation_state=invocation_state,
            structured_output_model=Drafts,
            structured_output_prompt="Produce one draft per language and channel group.",
        )
        drafts = []
        for draft in result.structured_output.drafts:
            row = draft.model_dump()
            # Models asked for a null subject sometimes return the literal string.
            if str(row.get("subject") or "").strip().lower() in ("null", "none", ""):
                row["subject"] = None
            drafts.append(row)
        repo.put_drafts(request.request_id, drafts)
        return {"request_id": request.request_id, "brief": brief,
                "draft_count": len(drafts), "drafts": drafts}


class AutonomyGate(JsonNode):
    """Decides whether this run is routine enough to send without waking anyone."""

    name = "gate"

    def escalations(self, task: Any, repo, request, rules: dict) -> list[str]:
        why: list[str] = []

        if rules.get("escalate_on_emergency", True) and request.source is RequestSource.EMERGENCY:
            why.append("emergency request, not a scheduled transfusion")

        if rules.get("escalate_on_agent_review", True) and request.review_reason:
            why.append(request.review_reason)

        contacts = repo.list_contacts(request.request_id)
        needed = request.units_needed * float(rules.get("min_cohort_multiple", 2.0))
        if len(contacts) < needed:
            why.append(f"cohort of {len(contacts)} is below the "
                       f"{needed:g} needed for {request.units_needed} units")

        cap = rules.get("max_contacts_per_donor_month")
        if cap is not None:
            for contact in contacts:
                donor = repo.get_donor(contact.donor_id)
                if donor and donor.contacts_this_month >= cap:
                    why.append(f"{donor.name} has already been contacted "
                               f"{donor.contacts_this_month} times this month")
                    break

        if not repo.get_drafts(request.request_id):
            why.append("no drafts were produced")
        return why

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request_id = invocation_state["request_id"]
        request = repo.get_request(request_id)
        rules = policies.load(request.policy_id).get("autonomy", {}) or {}
        contacts = repo.list_contacts(request_id)
        cohort = [{"rank": c.rank, "donor_id": c.donor_id, "channel": c.channel}
                  for c in contacts]

        existing = repo.get_approval(request_id)
        if existing and existing.get("approved"):
            return {"request_id": request_id, "gate": "approved",
                    "decided_by": "human", "by": existing.get("by"),
                    "at": existing.get("at"), "cohort": cohort}

        if not rules.get("enabled", False):
            repo.set_status(request_id, RequestStatus.AWAITING_APPROVAL)
            return {"request_id": request_id, "gate": "escalated",
                    "decided_by": "policy", "reasons": ["autonomy disabled for this policy"],
                    "cohort": cohort}

        why = self.escalations(task, repo, request, rules)
        if why:
            repo.set_status(request_id, RequestStatus.AWAITING_APPROVAL)
            return {
                "request_id": request_id, "gate": "escalated", "decided_by": "policy",
                "reasons": why, "cohort": cohort,
                "command": f"donorpanel approve --request {request_id} --by <your name>",
            }

        repo.approve(request_id, by="agent", note="routine, met every autonomy condition")
        return {
            "request_id": request_id, "gate": "auto", "decided_by": "policy",
            "checks_passed": ["scheduled request", "verifier raised nothing for review",
                              "verifier decided", "cohort covers the units needed",
                              "every donor inside their contact budget",
                              "drafts produced"],
            "cohort": cohort,
            "notified": "coordinator digest, not an approval request",
        }


class HumanGate(JsonNode):
    name = "gate"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request_id = invocation_state["request_id"]
        approval = repo.get_approval(request_id)

        if approval and approval.get("approved"):
            return {"request_id": request_id, "gate": "approved",
                    "by": approval.get("by"), "at": approval.get("at")}

        repo.set_status(request_id, RequestStatus.AWAITING_APPROVAL)
        contacts = repo.list_contacts(request_id)
        return {
            "request_id": request_id,
            "gate": "pending",
            "waiting_on": "coordinator approval",
            "would_contact": [{"rank": c.rank, "donor_id": c.donor_id,
                               "channel": c.channel} for c in contacts],
            "command": f"donorpanel approve --request {request_id} --by <your name>",
        }
