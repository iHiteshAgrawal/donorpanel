"""Opens the requests nobody asked for yet.

A patient on a fixed transfusion cycle is predictable: the last transfusion plus the
policy interval is the next one. This is what makes the agent anticipatory rather than
reactive, and it is deliberately ordinary code. Nothing here needs a model.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from donorpanel import policies
from donorpanel.domain import RequestStatus

log = logging.getLogger(__name__)


def _today() -> date:
    return datetime.now(timezone.utc).date()


# A draft was never real and a rejection was never accepted, so neither moves the cycle
# forward. Everything else does, including SHORT: the date still passed, and the patient
# is due again an interval later whether or not we found enough donors that time.
NOT_A_TRANSFUSION = (RequestStatus.DRAFT, RequestStatus.REJECTED)


def _last_needed_by(repo, patient_id: str):
    dates = [r.needed_by for r in repo.list_requests(patient_id)
             if r.status not in NOT_A_TRANSFUSION and r.needed_by]
    return max(dates) if dates else None


def due(repo, today: date | None = None) -> list[dict]:
    """Patients whose next transfusion falls inside the policy's lead time."""
    today = today or _today()
    # Only a request still pointing at a future date is "already open". in_flight()
    # includes DISPATCHED, and a dispatched request whose date has passed is history:
    # treating it as open would mean a patient came due exactly once, ever.
    waiting = {r.patient_id for r in repo.in_flight()
               if r.needed_by and r.needed_by >= today.isoformat()}
    found = []
    for patient_id in patient_ids(repo):
        if patient_id in waiting:
            # Something is already open for them. Without this a daily tick opens a
            # fresh duplicate every single day until the first one closes.
            continue
        patient = repo.get_patient(patient_id)
        if patient is None:
            continue
        last = _last_needed_by(repo, patient_id)
        if last is None:
            continue
        cadence = policies.load(patient.policy_id).get("cadence", {})
        interval = cadence.get("interval_days")
        lead = cadence.get("lead_time_days", 0)
        if not interval:
            continue
        next_due = date.fromisoformat(last) + timedelta(days=int(interval))
        if next_due - timedelta(days=int(lead)) <= today:
            found.append({"patient_id": patient_id, "needed_by": next_due.isoformat(),
                          "units_needed": int(cadence.get("units_per_session", 2)),
                          "name": patient.name, "last": last})
    return sorted(found, key=lambda r: r["needed_by"])


def patient_ids(repo) -> list[str]:
    return [k.rsplit("/", 1)[-1].removesuffix(".json")
            for k in repo.store.keys("patients/")]


def tick(repo, today: date | None = None, runner=None, channels=None) -> dict:
    """One scheduled pass over the pool, in three parts.

    Close first: a request whose date has passed is history, and leaving it open would
    hide its patient from the forecast that follows.
    """
    from donorpanel.services import chase as chasing

    settled = chasing.close(repo, today)
    opened = open_due(repo, today, runner)
    waves = chasing.chase(repo, channels=channels)
    return {**opened, "closed": settled["closed"], "settled": settled["requests"],
            "chased": waves["chased"], "waves": waves["waves"]}


def open_due(repo, today: date | None = None, runner=None) -> dict:
    """Opens and runs a request for every patient who is due. One run per patient, and
    a failure on one must not stop the rest: they are unrelated people."""
    from donorpanel.graph import flow

    runner = runner or flow.run
    opened, failed = [], []
    for row in due(repo, today):
        ask = {"patient_id": row["patient_id"], "needed_by": row["needed_by"],
               "units_needed": row["units_needed"]}
        try:
            out = runner(ask, repo, None, None, "public")
            opened.append({"patient": row["name"], "request_id": out.get("request_id"),
                           "gate": (out.get("gate") or {}).get("gate"),
                           "delivered": (out.get("dispatch") or {}).get("delivered_count", 0)})
        except Exception as exc:
            log.warning("forecast run failed for %s", row["patient_id"], exc_info=True)
            failed.append({"patient": row["name"], "error": str(exc)[:200]})
    return {"checked": len(patient_ids(repo)), "due": len(opened) + len(failed),
            "opened": opened, "failed": failed}


def main() -> None:
    """Dry run against the live pool. Reports what a tick would open, without opening it."""
    import json

    from donorpanel.services import pool

    panel = pool.ensure()
    rows = due(panel)
    print(json.dumps({"today": _today().isoformat(), "patients": len(patient_ids(panel)),
                      "due": rows}, indent=2))


if __name__ == "__main__":
    main()
