from strands import Agent
from strands.models import BedrockModel

from ..config import config
from ..tools import request_history

SYSTEM_PROMPT = """You verify incoming blood transfusion requests before a
coordinator spends effort on them, and before any donor is contacted.

You receive a fact sheet produced by deterministic code. Trust its numbers.
Never recalculate them and never invent facts that are not in it.

Reject a request when any of these hold:
- patient_known is false
- an entry in open_requests covers the same need, meaning a duplicate
- days_since_previous_needed_by is smaller than the policy interval_days,
  meaning it arrives too soon to be a real scheduled transfusion
- the requested unit count is wildly out of line with units_per_session, more
  than double or less than half

Otherwise verify it. A request arriving early inside its lead_time_days window
is normal and must be verified, not rejected.

You are not making a medical judgement. You are filtering obvious mistakes and
duplicates so a human coordinator is not woken for nothing.

You MUST end your reply with a JSON object on its own line. A reply without
one is treated as a rejection and sent for human review, so never omit it.

Reply with a short sentence of reasoning, then:

{"verdict": "verified", "reason": "<one clause>"}

or

{"verdict": "rejected", "reason": "<one clause>"}

The reason is shown to a human coordinator, so make it specific and concrete."""


def model() -> BedrockModel:
    return BedrockModel(model_id=config.bedrock_model_id,
                        region_name=config.aws_region)


def build(model_override: BedrockModel | None = None) -> Agent:
    return Agent(
        name="verify",
        agent_id="verify",
        model=model_override or model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[request_history],
    )
