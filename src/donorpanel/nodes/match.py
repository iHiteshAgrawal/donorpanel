from typing import Any

from .. import policies
from ..domain import (
    Contact,
    ContactStatus,
    RequestStatus,
    compatible_groups,
    distance_km,
    ineligible_reason,
    score,
)
from .base import JsonNode, find_block, task_text


class EligibilityResolver(JsonNode):
    name = "eligibility"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request = repo.get_request(invocation_state["request_id"])
        patient = repo.get_patient(request.patient_id)
        policy = policies.load(request.policy_id)

        rules = policy.get("donor_eligibility", {})
        matching = policy.get("matching", {})
        required = [a for a in matching.get("antigen_requirements", [])
                    if not a.endswith("-negative")]

        groups = compatible_groups(patient.blood_group) if matching.get("require_abo_rh", True) \
            else (patient.blood_group,)

        seen: dict[str, Any] = {}
        for group in groups:
            for donor in repo.list_pool(patient.region, group):
                seen[donor.donor_id] = donor

        eligible, excluded = [], []
        for donor in seen.values():
            reason = ineligible_reason(donor, rules, required)
            if reason:
                excluded.append({"donor_id": donor.donor_id, "reason": reason})
            else:
                eligible.append(donor.donor_id)

        invocation_state["eligible"] = eligible
        return {
            "request_id": request.request_id,
            "recipient_group": patient.blood_group,
            "compatible_groups": list(groups),
            "required_antigens": required,
            "pool_size": len(seen),
            "eligible_count": len(eligible),
            "eligible": eligible,
            "excluded": excluded,
        }


class CohortRanker(JsonNode):
    name = "rank"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request = repo.get_request(invocation_state["request_id"])
        patient = repo.get_patient(request.patient_id)
        policy = policies.load(request.policy_id)

        rules = policy.get("donor_eligibility", {})
        prefer_repeat = policy.get("matching", {}).get("prefer_repeat_donors", True)
        size = policy.get("outreach", {}).get("cohort_size", 8)

        # Read the upstream node's output rather than invocation_state, so this does
        # not depend on whether Strands shares that dict by reference across nodes.
        eligible = find_block(task_text(task), "eligible").get("eligible", [])
        donors = [repo.get_donor(d) for d in eligible]
        scored = []
        for donor in [d for d in donors if d is not None]:
            total, parts = score(donor, rules, patient.lat, patient.lon, prefer_repeat)
            scored.append((total, parts, donor))
        scored.sort(key=lambda row: row[0], reverse=True)

        cohort = []
        for rank, (total, parts, donor) in enumerate(scored[:size], start=1):
            repo.put_contact(Contact(request_id=request.request_id, donor_id=donor.donor_id,
                                     status=ContactStatus.PENDING, channel=donor.channel,
                                     rank=rank))
            cohort.append({
                "rank": rank, "donor_id": donor.donor_id, "name": donor.name,
                "blood_group": donor.blood_group, "channel": donor.channel,
                "language": donor.language, "score": total, "why": parts,
                "km": distance_km(patient.lat, patient.lon, donor.lat, donor.lon),
            })

        repo.set_status(request.request_id, RequestStatus.MATCHING)
        shortfall = max(0, request.units_needed - len(cohort))
        return {
            "request_id": request.request_id,
            "units_needed": request.units_needed,
            "cohort_target": size,
            "cohort_size": len(cohort),
            "shortfall": shortfall,
            "enough_to_proceed": shortfall == 0,
            "cohort": cohort,
        }
