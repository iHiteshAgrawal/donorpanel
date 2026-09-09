import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..config import config
from ..domain import RequestStatus
from ..graphs import request as flow
from ..nodes.base import find_block
from ..storage import PanelRepository
from .graphshape import EDGES, NODES
from .schema import Approval, NewRequest

app = FastAPI(title="DonorPanel", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

WEB = Path(__file__).resolve().parents[3] / "web" / "dist"


def repo() -> PanelRepository:
    return PanelRepository()


def sse(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "region": config.aws_region, "model": config.bedrock_model_id,
            "storage": f"s3://{config.bucket}" if config.bucket else config.local_root}


@app.get("/api/graph")
def graph_shape() -> dict:
    return {"nodes": NODES, "edges": EDGES}


@app.get("/api/patients")
def patients() -> list[dict]:
    store = repo()
    ids = [k.rsplit("/", 1)[-1].removesuffix(".json") for k in store.store.keys("patients/")]
    found = [store.get_patient(i) for i in ids]
    return [{"patient_id": p.patient_id, "name": p.name, "blood_group": p.blood_group,
             "condition": p.condition.value, "city": p.city, "hospital": p.hospital,
             "policy_id": p.policy_id, "lat": p.lat, "lon": p.lon}
            for p in found if p]


@app.get("/api/donors")
def donors() -> list[dict]:
    store = repo()
    ids = [k.rsplit("/", 1)[-1].removesuffix(".json") for k in store.store.keys("donors/")]
    found = [store.get_donor(i) for i in ids]
    return [{"donor_id": d.donor_id, "name": d.name, "blood_group": d.blood_group,
             "city": d.city, "lat": d.lat, "lon": d.lon, "channel": d.channel,
             "language": d.language, "consent": d.consent,
             "last_donation": d.last_donation,
             "contacts_this_month": d.contacts_this_month}
            for d in found if d]


@app.get("/api/requests")
def requests() -> list[dict]:
    # Summary only. Building full detail per row means several S3 round trips each,
    # which made this endpoint slow enough to stall the whole UI on first paint.
    store = repo()
    ids = [k.rsplit("/", 1)[-1].removesuffix(".json") for k in store.store.keys("requests/")]
    with ThreadPoolExecutor(max_workers=12) as pool:
        found = list(pool.map(store.get_request, ids))
    rows = [{"request_id": r.request_id, "patient_id": r.patient_id,
             "status": r.status.value, "units_needed": r.units_needed,
             "needed_by": r.needed_by, "created_at": r.created_at,
             "contacts": [], "drafts": [], "approval": None,
             "source": r.source.value, "component": r.component.value,
             "rejection_reason": r.rejection_reason}
            for r in found if r]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


@app.get("/api/requests/{request_id}")
def detail(request_id: str) -> dict:
    store = repo()
    request = store.get_request(request_id)
    if request is None:
        raise HTTPException(404, f"no request {request_id}")
    contacts = store.list_contacts(request_id)
    approval = store.get_approval(request_id)
    return {
        "request_id": request.request_id, "patient_id": request.patient_id,
        "status": request.status.value, "units_needed": request.units_needed,
        "needed_by": request.needed_by, "source": request.source.value,
        "component": request.component.value,
        "rejection_reason": request.rejection_reason,
        "created_at": request.created_at,
        "contacts": [{"rank": c.rank, "donor_id": c.donor_id, "channel": c.channel,
                      "status": c.status.value} for c in contacts],
        "drafts": store.get_drafts(request_id),
        "approval": approval,
    }


@app.post("/api/requests/{request_id}/approve")
def approve(request_id: str, body: Approval) -> dict:
    store = repo()
    if store.get_request(request_id) is None:
        raise HTTPException(404, f"no request {request_id}")
    store.approve(request_id, by=body.by, note=body.note)
    return detail(request_id)


@app.get("/api/pending")
def pending() -> list[dict]:
    return [detail(r.request_id) for r in repo().awaiting_approval()]


@app.post("/api/requests/stream")
async def run_stream(body: NewRequest) -> StreamingResponse:
    raw = {k: v for k, v in body.model_dump().items() if v is not None}
    request_id = f"r-{uuid.uuid4().hex[:10]}"

    async def events():
        store = repo()
        graph = flow.build()
        yield sse("started", {"request_id": request_id, "raw": raw})
        collected: list[str] = []
        try:
            async for event in graph.stream_async(
                json.dumps(raw),
                invocation_state={"repo": store, "request_id": request_id, "raw": raw},
            ):
                kind = event.get("type")
                if kind == "multiagent_node_start":
                    yield sse("node_start", {"node_id": event.get("node_id")})
                elif kind == "multiagent_node_stop":
                    node_result = event.get("node_result")
                    text = str(node_result.result) if node_result else ""
                    collected.append(text)
                    yield sse("node_stop", {
                        "node_id": event.get("node_id"),
                        "ms": getattr(node_result, "execution_time", 0),
                        "output": text[:4000],
                    })
                elif kind == "multiagent_handoff":
                    yield sse("handoff", {"from": event.get("from_node_ids", []),
                                          "to": event.get("to_node_ids", [])})
                await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001
            yield sse("failed", {"error": str(exc)})
            return

        blob = "\n".join(collected)
        yield sse("done", {
            "request_id": request_id,
            "verdict": find_block(blob, "verdict"),
            "eligibility": find_block(blob, "eligible_count"),
            "cohort": find_block(blob, "cohort_size"),
            "gate": find_block(blob, "gate"),
            "detail": detail(request_id),
        })

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/stats")
def stats() -> dict:
    rows = requests()
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {"requests": len(rows), "by_status": by_status,
            "awaiting_approval": by_status.get(RequestStatus.AWAITING_APPROVAL.value, 0),
            "donors": len(donors())}


if WEB.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = WEB / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB / "index.html")
