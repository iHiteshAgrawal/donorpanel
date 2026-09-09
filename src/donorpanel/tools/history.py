from strands import ToolContext, tool


@tool(context=True)
def request_history(patient_id: str, tool_context: ToolContext) -> str:
    """Look up this patient's past transfusion requests.

    Returns each request with its date, unit count and status, newest first.
    Use it to judge whether a new request duplicates an open one or arrives
    sooner than the patient's transfusion interval allows.

    Args:
        patient_id: The patient to look up.
    """
    repo = tool_context.invocation_state["repo"]
    history = repo.list_requests(patient_id)
    if not history:
        return f"No previous requests for {patient_id}."
    lines = [
        f"{r.request_id}  needed_by={r.needed_by}  units={r.units_needed}  "
        f"status={r.status.value if hasattr(r.status, 'value') else r.status}"
        for r in history[:10]
    ]
    return "\n".join(lines)
