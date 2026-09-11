import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import auth, memory, outreach
from .. import seed as seeds
from ..auth import Actor
from ..config import config
from ..domain import RequestStatus
from ..graphs import request as flow
from ..hooks import MemoryWriter
from ..nodes.base import find_block
from ..storage import PanelRepository, store
from .graphshape import EDGES, NODES
from .schema import Approval, NewRequest

app = FastAPI(title="DonorPanel", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

WEB = Path(__file__).resolve().parents[3] / "web" / "dist"


def current_actor(request: Request,
                  authorization: str | None = Header(default=None)) -> Actor:
    # The SPA sends a stable per browser id so an unauthenticated visitor still
    # gets their own sandbox. Client IP would collide for judges behind one NAT.
    seed = request.headers.get("x-donorpanel-session") or "guest"
    try:
        return auth.actor_from(authorization, fallback_seed=seed)
    except Exception as exc:
        raise HTTPException(401, f"invalid token: {exc}") from exc


def repo(actor: Actor | None = None) -> PanelRepository:
    """One namespace per actor. A fresh sandbox is seeded on first sight, reusing
    coordinates already resolved in the shared root so we do not re-geocode."""
    if actor is None:
        return PanelRepository()
    scoped = PanelRepository(store=store(actor.prefix))
    if seeds.is_empty(scoped):
        seeds.populate(scoped, seeds.coordinates_from(PanelRepository()))
    return scoped


def sse(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "region": config.aws_region, "model": config.bedrock_model_id,
            "storage": f"s3://{config.bucket}" if config.bucket else config.local_root,
            "auth": "cognito" if auth.configured() else "anonymous sandbox"}


@app.get("/api/me")
def me(actor: Actor = Depends(current_actor)) -> dict:
    return {"actor_id": actor.actor_id, "name": actor.name, "email": actor.email,
            "authenticated": actor.authenticated, "namespace": actor.prefix}


@app.get("/api/graph")
def graph_shape() -> dict:
    return {"nodes": NODES, "edges": EDGES}


@app.get("/api/patients")
def patients(actor: Actor = Depends(current_actor)) -> list[dict]:
    store = repo(actor)
    ids = [k.rsplit("/", 1)[-1].removesuffix(".json") for k in store.store.keys("patients/")]
    found = [store.get_patient(i) for i in ids]
    return [{"patient_id": p.patient_id, "name": p.name, "blood_group": p.blood_group,
             "condition": p.condition.value, "city": p.city, "hospital": p.hospital,
             "policy_id": p.policy_id, "lat": p.lat, "lon": p.lon}
            for p in found if p]


@app.get("/api/donors")
def donors(actor: Actor = Depends(current_actor)) -> list[dict]:
    store = repo(actor)
    ids = [k.rsplit("/", 1)[-1].removesuffix(".json") for k in store.store.keys("donors/")]
    found = [store.get_donor(i) for i in ids]
    return [{"donor_id": d.donor_id, "name": d.name, "blood_group": d.blood_group,
             "city": d.city, "lat": d.lat, "lon": d.lon, "channel": d.channel,
             "language": d.language, "consent": d.consent,
             "last_donation": d.last_donation,
             "contacts_this_month": d.contacts_this_month}
            for d in found if d]


@app.get("/api/requests")
def requests(actor: Actor = Depends(current_actor)) -> list[dict]:
    # Summary only. Building full detail per row means several S3 round trips each,
    # which made this endpoint slow enough to stall the whole UI on first paint.
    store = repo(actor)
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
def detail(request_id: str, actor: Actor = Depends(current_actor)) -> dict:
    store = repo(actor)
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
                      "status": c.status.value, "contacted_at": c.contacted_at,
                      "note": c.note, "body": c.body} for c in contacts],
        "drafts": store.get_drafts(request_id),
        "approval": approval,
    }


@app.post("/api/requests/{request_id}/approve")
def approve(request_id: str, body: Approval, actor: Actor = Depends(current_actor)) -> dict:
    store = repo(actor)
    if store.get_request(request_id) is None:
        raise HTTPException(404, f"no request {request_id}")
    store.approve(request_id, by=body.by if not actor.authenticated else actor.name,
                  note=body.note)
    # Approving is the coordinator saying send it. Without this the request sat at
    # awaiting_approval forever and nothing ever left the process.
    outreach.deliver(store, request_id)
    return detail(request_id, actor)


@app.post("/api/sandbox/reset")
def reset_sandbox(actor: Actor = Depends(current_actor)) -> dict:
    scoped = PanelRepository(store=store(actor.prefix))
    removed = seeds.wipe(scoped)
    forgotten = memory.forget(actor.actor_id)
    seeds.populate(scoped, seeds.coordinates_from(PanelRepository()))
    return {"actor_id": actor.actor_id, "cleared": removed,
            "forgotten": forgotten, "reseeded": True}


@app.get("/api/memory")
def remembered(actor: Actor = Depends(current_actor)) -> list[dict]:
    return memory.catalogue(actor.actor_id)


@app.get("/api/pending")
def pending(actor: Actor = Depends(current_actor)) -> list[dict]:
    return [detail(r.request_id, actor) for r in repo(actor).awaiting_approval()]


@app.post("/api/requests/stream")
async def run_stream(body: NewRequest, actor: Actor = Depends(current_actor)) -> StreamingResponse:
    raw = {k: v for k, v in body.model_dump().items() if v is not None}
    request_id = f"r-{uuid.uuid4().hex[:10]}"

    async def events():
        store = repo(actor)
        graph = flow.build(hooks=[MemoryWriter()])
        yield sse("started", {"request_id": request_id, "raw": raw})
        collected: list[str] = []
        try:
            async for event in graph.stream_async(
                json.dumps(raw),
                invocation_state={"repo": store, "request_id": request_id, "raw": raw,
                                  "actor_id": actor.actor_id},
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
            "dispatch": find_block(blob, "delivered_count"),
            "detail": detail(request_id, actor),
        })

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/stats")
def stats(actor: Actor = Depends(current_actor)) -> dict:
    rows = requests(actor)
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    return {"requests": len(rows), "by_status": by_status,
            "awaiting_approval": by_status.get(RequestStatus.AWAITING_APPROVAL.value, 0),
            "donors": len(donors(actor))}


if WEB.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = WEB / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB / "index.html")
