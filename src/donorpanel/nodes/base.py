import json
import time
from typing import Any

from strands.agent.agent_result import AgentResult
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.telemetry.metrics import EventLoopMetrics


class DeterministicNode(MultiAgentBase):
    name = "deterministic"

    def __init__(self, name: str | None = None):
        super().__init__()
        if name:
            self.name = name
        self.id = self.name

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def invoke_async(self, task, invocation_state=None, **kwargs) -> MultiAgentResult:
        started = time.time()
        state = invocation_state or {}
        try:
            payload = self.run(task, state)
            status = Status.COMPLETED
            text = json.dumps(payload, indent=2, default=str)
        # Broad on purpose: a node failure must surface as a FAILED NodeResult the
        # graph can route on, never as an exception that kills the whole run.
        except Exception as exc:  # noqa: BLE001
            status = Status.FAILED
            text = json.dumps({"node": self.name, "error": str(exc)})

        elapsed = int((time.time() - started) * 1000)
        result = AgentResult(
            stop_reason="end_turn",
            message={"role": "assistant", "content": [{"text": text}]},
            metrics=EventLoopMetrics(),
            state={},
        )
        return MultiAgentResult(
            status=status,
            results={self.name: NodeResult(result=result, status=status,
                                           execution_time=elapsed, execution_count=1)},
            execution_count=1,
            execution_time=elapsed,
        )

    def serialize_state(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}

    def deserialize_state(self, payload: dict[str, Any]) -> None:
        return None


def task_text(task: Any) -> str:
    # Graph hands a node a list of ContentBlock dicts, not a string. repr() of that
    # escapes the newlines inside each block and breaks any JSON parse downstream.
    if isinstance(task, list):
        return "\n".join(block.get("text", "") for block in task
                          if isinstance(block, dict))
    return str(task)


def json_blocks(text: str) -> list[dict[str, Any]]:
    # A node's input carries every upstream node's output concatenated, so naive
    # "first brace to last brace" would span two objects and fail to parse.
    blocks: list[dict[str, Any]] = []
    depth = 0
    start = -1
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    blocks.append(json.loads(text[start: index + 1]))
                except json.JSONDecodeError:
                    pass
                start = -1
    return blocks


def find_block(text: str, key: str) -> dict[str, Any]:
    for block in reversed(json_blocks(text)):
        if key in block:
            return block
    return {}


def node_text(state, node_id: str) -> str:
    result = state.results.get(node_id)
    return str(result.result) if result else ""
