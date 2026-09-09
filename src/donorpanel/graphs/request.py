import json
import uuid
from typing import Any

from strands.multiagent import GraphBuilder

from ..agents import verifier
from ..nodes import (
    Adjudicate,
    CloseRejected,
    CohortRanker,
    EligibilityResolver,
    IntakeNormalizer,
    MarkVerified,
)
from ..nodes.base import find_block, node_text
from ..storage import PanelRepository


def _verdict(state) -> str:
    return find_block(node_text(state, "adjudicate"), "verdict").get("verdict", "")


def is_verified(state) -> bool:
    return _verdict(state) == "verified"


def is_rejected(state) -> bool:
    return _verdict(state) == "rejected"


def build(agent=None, session_manager=None):
    builder = GraphBuilder()
    builder.add_node(IntakeNormalizer(), "intake")
    builder.add_node(agent or verifier.build(), "verify")
    builder.add_node(Adjudicate(), "adjudicate")
    builder.add_node(MarkVerified(), "accept")
    builder.add_node(CloseRejected(), "close")
    builder.add_node(EligibilityResolver(), "eligibility")
    builder.add_node(CohortRanker(), "rank")

    builder.add_edge("intake", "verify")
    builder.add_edge("verify", "adjudicate")
    builder.add_edge("adjudicate", "accept", condition=is_verified)
    builder.add_edge("adjudicate", "close", condition=is_rejected)
    builder.add_edge("accept", "eligibility")
    builder.add_edge("eligibility", "rank")

    builder.set_entry_point("intake")
    builder.set_max_node_executions(12)
    builder.set_execution_timeout(180)
    builder.set_node_timeout(90)
    if session_manager is not None:
        builder.set_session_manager(session_manager)
    return builder.build()


def run(raw: dict[str, Any], repo: PanelRepository | None = None, graph=None,
        request_id: str | None = None) -> dict[str, Any]:
    repo = repo or PanelRepository()
    request_id = request_id or f"r-{uuid.uuid4().hex[:10]}"
    graph = graph or build()

    result = graph(
        json.dumps(raw),
        invocation_state={"repo": repo, "request_id": request_id, "raw": raw},
    )
    text = str(result)
    return {
        "request_id": request_id,
        "graph_status": result.status.value,
        "path": [node.node_id for node in result.execution_order],
        "verdict": find_block(text, "verdict"),
        "outcome": find_block(text, "status"),
        "eligibility": find_block(text, "eligible_count"),
        "cohort": find_block(text, "cohort_size"),
    }
