import asyncio
import logging
from typing import Any

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import AfterNodeCallEvent

from donorpanel.adapters import memory
from donorpanel.domain import RequestSource

log = logging.getLogger(__name__)

# A rejected request routes adjudicate -> close and never reaches the gate, so
# keying only on "gate" would silently drop every rejection.
TERMINAL = ("gate", "close")


def sentence(repo, request_id: str) -> str | None:
    request = repo.get_request(request_id)
    if request is None:
        return None
    patient = repo.get_patient(request.patient_id)
    contacts = repo.list_contacts(request_id)

    reach: set[str] = set()
    for contact in contacts:
        donor = repo.get_donor(contact.donor_id)
        if donor:
            reach.add(f"{donor.language}/{donor.channel}")

    who = patient.name.split()[0] if patient else request.patient_id
    where = f" in {patient.city}" if patient and patient.city else ""
    group = f" ({patient.blood_group})" if patient else ""
    approval = repo.get_approval(request_id) or {}
    decided = approval.get("by") or "no one"

    if not contacts:
        return (f"Request for {who}{group}{where} needing {request.units_needed} units by "
                f"{request.needed_by} ended as {request.status.value} with no cohort.")
    return (f"Outreach for {who}{group}{where} needing {request.units_needed} units by "
            f"{request.needed_by} reached {len(contacts)} donors over "
            f"{', '.join(sorted(reach))}. Status {request.status.value}, approved by {decided}.")


def turns(repo, request_id: str, raw: dict[str, Any]) -> list[tuple[str, str]]:
    """Restates the run as conversation. USER_PREFERENCE extraction mines preferences,
    and a dump of request fields contains none, so a parameter list yields zero records.
    Every clause below is a faithful restatement of something actually recorded."""
    request = repo.get_request(request_id)
    if request is None:
        return []
    patient = repo.get_patient(request.patient_id)
    who = patient.name.split()[0] if patient else request.patient_id

    asked = f"I need {request.units_needed} units for {who} by {request.needed_by}."
    if request.source is not RequestSource.SCHEDULED:
        asked += f" This one is {request.source.value}."

    contacts = repo.list_contacts(request_id)
    channels = sorted({f"{d.language} {d.channel}" for d in
                       (repo.get_donor(c.donor_id) for c in contacts) if d})
    reply = f"Recorded as {request.status.value}."
    if request.rejection_reason:
        reply += f" Rejected because {request.rejection_reason}."
    if contacts:
        reply += f" Reached {len(contacts)} donors over {', '.join(channels)}."
    approval = repo.get_approval(request_id) or {}
    if approval.get("by"):
        reply += f" Approved by {approval['by']}."

    habit = pattern(repo, request, who, channels)
    if habit:
        reply += f" {habit}"
    return [("USER", asked), ("ASSISTANT", reply)]


def pattern(repo, request, who: str, channels: list[str]) -> str | None:
    """USER_PREFERENCE extracts standing preferences, not one-off requests, so a lone
    "I need 2 units by Friday" yields no records. This states the standing pattern the
    history actually shows. It stays silent rather than guess when the history is thin
    or inconsistent, so nothing here is ever put in the coordinator's mouth."""
    history = [r for r in repo.list_requests(request.patient_id)
               if r.request_id != request.request_id]
    if len(history) < 2:
        return None
    units = {r.units_needed for r in history} | {request.units_needed}
    if len(units) != 1:
        return None
    said = f"Your standing pattern for {who} is {request.units_needed} units every time"
    if channels:
        said += f", reached over {', '.join(channels)}"
    return said + "."


class MemoryWriter(HookProvider):
    """Writes one run to AgentCore Memory once the graph reaches a terminal node."""

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterNodeCallEvent, self.on_node_done)

    async def on_node_done(self, event: AfterNodeCallEvent) -> None:
        state = event.invocation_state or {}
        actor_id = state.get("actor_id")
        if event.node_id not in TERMINAL or not actor_id:
            return
        # The registry propagates callback exceptions to the caller, and this event
        # fires from inside a finally block, so anything raised here both kills the
        # run and masks whatever really failed. Memory is never worth that.
        try:
            await asyncio.to_thread(self.write, state, actor_id)
        except Exception:
            log.warning("memory hook failed for %s", state.get("request_id"), exc_info=True)

    def write(self, state: dict[str, Any], actor_id: str) -> None:
        repo = state["repo"]
        request_id = state["request_id"]
        fact = sentence(repo, request_id)
        if fact:
            memory.record(actor_id, "compose", [fact])
        # No namespaceVariables on purpose: without agentid the semantic strategy
        # cannot resolve its template and skips extraction, so this event bills one
        # extraction instead of two.
        memory.remember(actor_id, request_id, turns(repo, request_id, state.get("raw") or {}))
