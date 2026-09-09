import json
from datetime import date, datetime, timezone
from typing import Any

from .. import policies
from ..domain import Component, Request, RequestSource, RequestStatus
from .base import JsonNode


class IntakeNormalizer(JsonNode):
    name = "intake"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request_id = invocation_state["request_id"]
        raw = invocation_state.get("raw") or json.loads(str(task))

        patient_id = str(raw["patient_id"]).strip()
        patient = repo.get_patient(patient_id)
        if patient is None:
            return {"request_id": request_id, "patient_known": False,
                    "patient_id": patient_id,
                    "problem": f"no patient record for {patient_id}"}

        policy = policies.load(patient.policy_id)
        needed_by = str(raw["needed_by"]).strip()
        units = int(raw.get("units_needed") or policy["cadence"]["units_per_session"])
        history = repo.list_requests(patient_id)
        open_now = repo.open_requests(patient_id, exclude=request_id)

        request = Request(
            request_id=request_id,
            patient_id=patient_id,
            policy_id=patient.policy_id,
            units_needed=units,
            needed_by=needed_by,
            component=Component(raw.get("component") or Component.PACKED_CELLS.value),
            source=RequestSource(raw.get("source") or RequestSource.SCHEDULED.value),
            status=RequestStatus.DRAFT,
        )
        repo.put_request(request)

        last = next((r for r in history if r.request_id != request_id), None)
        return {
            "request_id": request_id,
            "patient_known": True,
            "patient": {"id": patient.patient_id, "name": patient.name,
                        "condition": patient.condition.value if hasattr(patient.condition, "value") else patient.condition,
                        "blood_group": patient.blood_group, "region": patient.region},
            "policy": {"id": patient.policy_id,
                       "interval_days": policy["cadence"]["interval_days"],
                       "units_per_session": policy["cadence"]["units_per_session"],
                       "lead_time_days": policy["cadence"]["lead_time_days"]},
            "requested": {"units": units, "needed_by": needed_by,
                          "component": request.component.value,
                          "source": request.source.value},
            "days_until_needed": (date.fromisoformat(needed_by) - datetime.now(timezone.utc).date()).days,
            "open_requests": [{"request_id": r.request_id, "needed_by": r.needed_by,
                               "status": r.status.value if hasattr(r.status, "value") else r.status}
                              for r in open_now],
            "days_since_previous_needed_by": (
                (date.fromisoformat(needed_by) - date.fromisoformat(last.needed_by)).days
                if last else None),
        }
