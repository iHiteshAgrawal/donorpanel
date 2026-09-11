from typing import Any

from donorpanel.graph.nodes.base import JsonNode, find_block, task_text

DECISIONS = ("verified", "rejected")


class Adjudicate(JsonNode):
    name = "adjudicate"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        block = find_block(task_text(task), "verdict")
        verdict = str(block.get("verdict", "")).strip().lower()
        if verdict not in DECISIONS:
            return {"verdict": "rejected", "decided_by": "fallback",
                    "reason": "verifier returned no usable decision, held for human review"}
        # Persisted rather than passed along the graph: a node only receives its
        # immediate predecessor's output, and the gate's predecessor is compose, so
        # anything left in this node's text is invisible by the time the gate runs.
        needs_review = bool(block.get("needs_review"))
        review_reason = (block.get("review_reason") or "the verifier asked for a human"
                         ) if needs_review else None
        if review_reason:
            repo = invocation_state["repo"]
            request = repo.get_request(invocation_state["request_id"])
            if request is not None:
                request.review_reason = review_reason
                repo.put_request(request)
        return {"verdict": verdict, "decided_by": "verifier",
                "reason": block.get("reason") or "no reason given",
                "needs_review": needs_review, "review_reason": review_reason}
