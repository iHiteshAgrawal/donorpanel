from typing import Any, Literal

from pydantic import BaseModel, Field

from ..agents import verifier
from .base import JsonNode, task_text


class Verdict(BaseModel):
    verdict: Literal["verified", "rejected"]
    reason: str = Field(description="One concrete clause a coordinator will read.")


class RequestVerifier(JsonNode):
    name = "verify"

    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent or verifier.build()

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        # invocation_state must be forwarded by hand. The Graph injects it when an
        # Agent is a node directly, but this node owns the agent, so its tools would
        # otherwise find no repo and every verification would fail.
        result = self.agent(
            task_text(task),
            invocation_state=invocation_state,
            structured_output_model=Verdict,
            structured_output_prompt="State your decision on this request.",
        )
        decision = result.structured_output
        return {
            "verdict": decision.verdict,
            "reason": decision.reason,
            "reasoning": str(result).strip()[:600],
        }
