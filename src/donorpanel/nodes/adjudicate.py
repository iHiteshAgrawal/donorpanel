from typing import Any

from .base import JsonNode, find_block, task_text

DECISIONS = ("verified", "rejected")


class Adjudicate(JsonNode):
    name = "adjudicate"

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        block = find_block(task_text(task), "verdict")
        verdict = str(block.get("verdict", "")).strip().lower()
        if verdict not in DECISIONS:
            return {"verdict": "rejected", "decided_by": "fallback",
                    "reason": "verifier returned no usable decision, held for human review"}
        return {"verdict": verdict, "decided_by": "verifier",
                "reason": block.get("reason") or "no reason given"}
