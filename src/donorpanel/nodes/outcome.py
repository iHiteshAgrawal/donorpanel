from typing import Any

from ..domain import RequestStatus
from .base import DeterministicNode, find_block, task_text


class MarkVerified(DeterministicNode):
    name = "accept"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request_id = invocation_state["request_id"]
        request = repo.set_status(request_id, RequestStatus.VERIFIED)
        return {"request_id": request_id, "status": request.status.value,
                "next": "match", "units_needed": request.units_needed,
                "needed_by": request.needed_by}


class CloseRejected(DeterministicNode):
    name = "close"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        repo = invocation_state["repo"]
        request_id = invocation_state["request_id"]
        reason = find_block(task_text(task), "verdict").get("reason") or "not verified"
        request = repo.get_request(request_id)
        if request is not None:
            request.status = RequestStatus.REJECTED
            request.rejection_reason = reason
            repo.put_request(request)
        return {"request_id": request_id, "status": RequestStatus.REJECTED.value,
                "reason": reason}


__all__ = ["CloseRejected", "MarkVerified"]
