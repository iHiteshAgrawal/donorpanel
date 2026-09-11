import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from donorpanel.config import config
from donorpanel.entrypoints import poller as inbound
from donorpanel.services import pool

# uvicorn only configures its own loggers, so without this the inbound poller and
# every memory warning run silently.
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")
# httpx logs the full request URL, and a Telegram URL carries the bot token in its
# path. At INFO that writes the credential into CloudWatch on every send.
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="DonorPanel", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

WEB = Path(__file__).resolve().parents[3] / "web" / "dist"


@app.on_event("startup")
async def listen_for_replies() -> None:
    app.state.inbound = asyncio.create_task(inbound.poll_forever())


@app.on_event("shutdown")
async def stop_listening() -> None:
    task = getattr(app.state, "inbound", None)
    if task:
        task.cancel()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "region": config.aws_region, "model": config.bedrock_model_id,
            "storage": f"s3://{config.bucket}" if config.bucket else config.local_root,
            "bot": config.telegram_bot_username}


@app.get("/api/public")
def public_pool() -> dict:
    """The only endpoint the site needs. Everything else happens in the chat."""
    panel = pool.ensure()
    patient = panel.get_patient(pool.PATIENT["patient_id"])
    counts = pool.headcount(panel)
    return {
        "bot": config.telegram_bot_username,
        "donors": counts["donors"],
        "cities": counts["cities"],
        "requests": counts["requests"],
        "reached": counts["reached"],
        "patient": {"name": patient.name, "blood_group": patient.blood_group,
                    "condition": patient.condition.value, "city": patient.city,
                    "hospital": patient.hospital} if patient else None,
    }


if WEB.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def site(path: str) -> FileResponse:
        candidate = WEB / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB / "index.html")
