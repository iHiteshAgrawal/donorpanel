from typing import Any

from donorpanel.graph.nodes.base import JsonNode
from donorpanel.services import outreach


class Dispatch(JsonNode):
    name = "dispatch"

    def __init__(self, channels=None):
        super().__init__()
        self.channels = channels

    def run(self, task: Any, invocation_state: dict[str, Any]) -> dict[str, Any]:
        return outreach.deliver(invocation_state["repo"],
                                invocation_state["request_id"],
                                channels=self.channels)
