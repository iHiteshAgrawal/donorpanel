import argparse
import asyncio

from donorpanel import __version__, policies
from donorpanel.adapters.channels import Outbound, registry
from donorpanel.config import config


def status() -> None:
    active = registry()
    print(f"donorpanel {__version__}  env={config.env}  region={config.aws_region}")
    print(f"model: {config.bedrock_model_id or 'sdk default'}")
    print(f"storage: {'s3://' + config.bucket if config.bucket else config.local_root}")
    print(f"memory: {config.agentcore_memory_id or 'not provisioned'}")
    print(f"channels: {', '.join(active) or 'none'}")
    print(f"policies: {', '.join(policies.available())}")


def init() -> None:
    from donorpanel.adapters.storage import ensure_bucket

    if config.bucket:
        ensure_bucket()
        print(f"bucket {config.bucket} ready")
    else:
        print(f"local storage at {config.local_root}, set DONORPANEL_BUCKET to use S3")


def reset() -> None:
    from donorpanel import seed as seeds
    from donorpanel.adapters.storage import PanelRepository

    print(f"cleared {seeds.wipe(PanelRepository())} objects")


def seed() -> None:
    from donorpanel import seed as seeds
    from donorpanel.adapters.storage import PanelRepository

    init()
    repo = PanelRepository()
    count = seeds.populate(repo)
    print(f"seeded 1 patient and {count} donors, no coordinates")
    print("run 'donorpanel geocode' to resolve their cities")


def geocode() -> None:
    from donorpanel.adapters.geo import GeocodeDenied, backfill
    from donorpanel.adapters.storage import PanelRepository

    try:
        report = backfill(PanelRepository())
    except GeocodeDenied as exc:
        raise SystemExit(
            f"{exc}. Add geo-places:Geocode to the IAM policy."
        ) from exc
    print(f"filled {report['filled']}, missed {report['missed']}, "
          f"already set {report['skipped']}, api calls {report['api_calls']}")


def request(patient_id: str, needed_by: str, units: int) -> None:
    import json

    from donorpanel.graph import flow

    out = flow.run({"patient_id": patient_id, "needed_by": needed_by,
                      "units_needed": units})
    print(json.dumps(out, indent=2))


def approve(request_id: str, by: str, note: str | None) -> None:
    from donorpanel.adapters.storage import PanelRepository

    repo = PanelRepository()
    if repo.get_request(request_id) is None:
        raise SystemExit(f"no request {request_id}")
    repo.approve(request_id, by=by, note=note)
    # Approving is the coordinator saying send it. Without this the request would sit
    # at awaiting_approval and nothing would ever leave the process.
    from donorpanel.services.outreach import deliver

    out = deliver(repo, request_id)
    print(f"{request_id} approved by {by}: {out['delivered_count']} sent, "
          f"{out['failed_count']} failed")


def pending() -> None:
    from donorpanel.adapters.storage import PanelRepository

    repo = PanelRepository()
    waiting = repo.awaiting_approval()
    if not waiting:
        print("nothing awaiting approval")
        return
    for request in waiting:
        drafts = repo.get_drafts(request.request_id)
        contacts = repo.list_contacts(request.request_id)
        print(f"\n{request.request_id}  patient={request.patient_id}  "
              f"units={request.units_needed}  by={request.needed_by}")
        print(f"  cohort: {', '.join(c.donor_id for c in contacts)}")
        for draft in drafts:
            head = f"  [{draft['language']}/{draft['channel']}]"
            if draft.get("subject"):
                print(f"{head} subject: {draft['subject']}")
            else:
                print(head)
            for line in draft["body"].splitlines():
                print(f"      {line}")


def memory_init() -> None:
    from donorpanel import memory

    memory_id = memory.ensure()
    print(f"memory {memory_id} ready")
    if config.agentcore_memory_id != memory_id:
        print(f"add this to .env:\n  AGENTCORE_MEMORY_ID={memory_id}")


async def ping(channel: str, recipient: str, body: str) -> None:
    active = registry()
    if channel not in active:
        raise SystemExit(f"channel {channel} not configured; available: {', '.join(active)}")
    result = await active[channel].send(Outbound(recipient=recipient, body=body, subject="DonorPanel"))
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(prog="donorpanel")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    sub.add_parser("init")
    sub.add_parser("seed")
    sub.add_parser("reset")
    sub.add_parser("geocode")
    sub.add_parser("memory-init")
    sub.add_parser("pending")

    ok = sub.add_parser("approve")
    ok.add_argument("--request", required=True)
    ok.add_argument("--by", required=True)
    ok.add_argument("--note")

    req = sub.add_parser("request")
    req.add_argument("--patient", required=True)
    req.add_argument("--needed-by", required=True)
    req.add_argument("--units", type=int, default=2)

    send = sub.add_parser("ping")
    send.add_argument("--channel", default="console")
    send.add_argument("--to", required=True)
    send.add_argument("--body", default="DonorPanel channel check.")

    args = parser.parse_args()
    if args.command == "ping":
        asyncio.run(ping(args.channel, args.to, args.body))
    elif args.command == "init":
        init()
    elif args.command == "seed":
        seed()
    elif args.command == "reset":
        reset()
    elif args.command == "geocode":
        geocode()
    elif args.command == "memory-init":
        memory_init()
    elif args.command == "pending":
        pending()
    elif args.command == "approve":
        approve(args.request, args.by, args.note)
    elif args.command == "request":
        request(args.patient, args.needed_by, args.units)
    else:
        status()
