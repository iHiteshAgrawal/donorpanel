import json
from typing import Any

from pydantic import BaseModel, Field

from ..agents import composer
from ..domain import RequestStatus
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
