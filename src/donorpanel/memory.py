import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from .config import config

log = logging.getLogger(__name__)

NAME = "DonorPanelMemory"
PREFERENCES = "/donorpanel/{actorId}/shared/preferences/"
FINDINGS = "/donorpanel/{actorId}/agents/{agentid}/findings/"
ROOT = "/donorpanel/{actorId}/"
AGENTS = ("verify", "compose", "forecast", "hygiene")

# Retried by botocore itself. Anything outside this set is deterministic: the same
# call fails the same way forever, so it is logged and degraded rather than retried.
TRANSIENT = ("ThrottledException", "RetryableConflictException", "ServiceException")

_retries = BotoConfig(retries={"max_attempts": 5, "mode": "adaptive"})


def control():
    return boto3.client("bedrock-agentcore-control", region_name=config.aws_region,
                        config=_retries)


def data():
    return boto3.client("bedrock-agentcore", region_name=config.aws_region, config=_retries)


def preferences_ns(actor_id: str) -> str:
    return PREFERENCES.format(actorId=actor_id)


def findings_ns(actor_id: str, agent_id: str) -> str:
    return FINDINGS.format(actorId=actor_id, agentid=agent_id)


def _degrade(what: str, exc: ClientError) -> None:
    code = exc.response["Error"]["Code"]
    level = logging.INFO if code in TRANSIENT else logging.WARNING
    log.log(level, "memory %s failed: %s %s", what, code,
            exc.response["Error"].get("Message", ""))


def ensure(name: str = NAME, client=None) -> str:
    client = client or control()
    # ListMemories summaries carry no name, only an id shaped "<Name>-<suffix>",
    # so the id prefix is the only way to recognise our own memory here.
    for memory in client.list_memories().get("memories", []):
        if memory.get("id", "").startswith(f"{name}-"):
            return memory["id"]

    created = client.create_memory(
        name=name,
        description="DonorPanel coordinator preferences and per agent findings",
        eventExpiryDuration=90,
        memoryStrategies=[
            {"userPreferenceMemoryStrategy": {
                "name": "CoordinatorPreferences",
                "namespaceTemplates": [PREFERENCES]}},
            {"semanticMemoryStrategy": {
                "name": "AgentFindings",
                "namespaceTemplates": [FINDINGS]}},
        ],
        namespaceKeys=[{"key": "agentid",
                        "validation": {"regexPattern": f"^({'|'.join(AGENTS)})$"}}],
    )["memory"]["id"]

    deadline = time.time() + 300
    while time.time() < deadline:
        status = client.get_memory(memoryId=created)["memory"]["status"]
        if status == "ACTIVE":
            return created
        if status in ("FAILED", "DELETING"):
            raise RuntimeError(f"memory {created} went to {status}")
        time.sleep(5)
    raise TimeoutError(f"memory {created} was still not ACTIVE after 300s")


def remember(actor_id: str, session_id: str, turns: list[tuple[str, str]],
             client=None) -> str | None:
    """Writes turns that long-term extraction will mine for coordinator patterns.

    The payload must be `conversational`. AgentCore stores `blob` and `json` events
    happily and then never extracts a single record from them.
    """
    if not config.agentcore_memory_id or not turns:
        return None
    try:
        response = (client or data()).create_event(
            memoryId=config.agentcore_memory_id,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            payload=[{"conversational": {"role": role, "content": {"text": text}}}
                     for role, text in turns],
        )
        return response["event"]["eventId"]
    except ClientError as exc:
        _degrade("remember", exc)
        return None


def record(actor_id: str, agent_id: str, texts: list[str], client=None) -> int:
    """Writes facts we already know verbatim, skipping the ~93s extraction wait."""
    if not config.agentcore_memory_id or not texts:
        return 0
    namespace = findings_ns(actor_id, agent_id)
    now = datetime.now(timezone.utc)
    try:
        # Partial failure comes back in the response body, not as an exception.
        response = (client or data()).batch_create_memory_records(
            memoryId=config.agentcore_memory_id,
            records=[{"requestIdentifier": str(uuid.uuid4()),
                      "namespaces": [namespace],
                      "content": {"text": text},
                      "timestamp": now} for text in texts],
        )
    except ClientError as exc:
        _degrade("record", exc)
        return 0

    for failed in response.get("failedRecords", []):
        log.warning("memory record rejected for %s: %s %s", namespace,
                    failed.get("errorCode"), failed.get("errorMessage"))
    return len(response.get("successfulRecords", []))


def _readable(text: str) -> str:
    # Extracted preference records arrive as JSON ({context, preference, categories});
    # records we wrote ourselves are already prose. Callers want one display string.
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return text
    if isinstance(parsed, dict):
        return parsed.get("preference") or parsed.get("context") or text
    return text


def _hits(response: dict[str, Any]) -> list[str]:
    return [_readable(hit["content"]["text"])
            for hit in response.get("memoryRecordSummaries", [])
            if hit.get("content", {}).get("text")]


def recall(actor_id: str, agent_id: str, query: str, top_k: int = 3,
           client=None) -> list[str]:
    if not config.agentcore_memory_id:
        return []
    try:
        return _hits((client or data()).retrieve_memory_records(
            memoryId=config.agentcore_memory_id,
            namespace=findings_ns(actor_id, agent_id),
            searchCriteria={"searchQuery": query, "topK": top_k},
        ))
    except ClientError as exc:
        _degrade("recall", exc)
        return []


def everything(actor_id: str, query: str = "what is known about this coordinator",
               top_k: int = 20, client=None) -> list[str]:
    if not config.agentcore_memory_id:
        return []
    try:
        return _hits((client or data()).retrieve_memory_records(
            memoryId=config.agentcore_memory_id,
            namespacePath=ROOT.format(actorId=actor_id),
            searchCriteria={"searchQuery": query, "topK": top_k},
        ))
    except ClientError as exc:
        _degrade("everything", exc)
        return []
