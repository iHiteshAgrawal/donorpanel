import argparse
import asyncio

from . import __version__, policies
from .channels import Outbound, registry
from .config import config


def status() -> None:
    active = registry()
    print(f"donorpanel {__version__}  env={config.env}  region={config.aws_region}")
    print(f"model: {config.bedrock_model_id or 'sdk default'}")
    print(f"storage: {'s3://' + config.bucket if config.bucket else config.local_root}")
    print(f"channels: {', '.join(active) or 'none'}")
    print(f"policies: {', '.join(policies.available())}")


def init() -> None:
    from .storage import ensure_bucket

    if config.bucket:
        ensure_bucket()
        print(f"bucket {config.bucket} ready")
    else:
        print(f"local storage at {config.local_root}, set DONORPANEL_BUCKET to use S3")


def reset() -> None:
    from .storage import store

    backing = store()
    removed = 0
    for prefix in ("requests/", "contacts/", "patient-requests/", "drafts/",
                   "approvals/", "donors/", "pool/", "patients/", "credits/"):
        for key in backing.keys(prefix):
            backing.delete(key)
            removed += 1
    print(f"cleared {removed} objects")


def seed() -> None:
    from datetime import datetime, timedelta, timezone

    from .domain import Condition, Donor, Patient
    from .storage import PanelRepository

    def ago(days: int) -> str:
        return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    init()
    repo = PanelRepository()
    repo.put_patient(Patient(
        patient_id="p-ravi", name="Ravi", condition=Condition.THALASSEMIA,
        blood_group="B+", policy_id="thalassemia-india", region="IN-TN",
        city="Coimbatore", hospital="Government Hospital",
    ))
    pool = [
        ("d-asha", "Asha", "B+", "telegram", True, ago(160), "Coimbatore", 0),
        ("d-vikram", "Vikram", "B+", "email", True, ago(20), "Coimbatore", 0),
        ("d-meera", "Meera", "O-", "telegram", True, None, "Tiruppur", 0),
        ("d-suresh", "Suresh", "B+", "telegram", False, ago(400), "Coimbatore", 0),
        ("d-kavya", "Kavya", "O+", "telegram", True, ago(210), "Erode", 3),
        ("d-arun", "Arun", "B-", "email", True, ago(120), "Chennai", 0),
        ("d-divya", "Divya", "A+", "telegram", True, ago(300), "Coimbatore", 0),
        ("d-nithya", "Nithya", "B+", "telegram", True, ago(95), "Pollachi", 1),
    ]
    for donor_id, name, group, channel, consent, last, city, contacts in pool:
        repo.put_donor(Donor(
            donor_id=donor_id, name=name, blood_group=group, region="IN-TN",
            channel=channel, address=f"{donor_id}@example.test", city=city,
            consent=consent, last_donation=last, language="ta",
            contacts_this_month=contacts,
        ))
    print(f"seeded 1 patient and {len(pool)} donors, no coordinates")
    print("run 'donorpanel geocode' to resolve their cities")


def geocode() -> None:
    from .geo import GeocodeDenied, backfill
    from .storage import PanelRepository

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

    from .graphs import request as flow

    out = flow.run({"patient_id": patient_id, "needed_by": needed_by,
                      "units_needed": units})
    print(json.dumps(out, indent=2))


def approve(request_id: str, by: str, note: str | None) -> None:
    from .storage import PanelRepository

    repo = PanelRepository()
    if repo.get_request(request_id) is None:
        raise SystemExit(f"no request {request_id}")
    repo.approve(request_id, by=by, note=note)
    print(f"{request_id} approved by {by}")


def pending() -> None:
    from .storage import PanelRepository

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
    elif args.command == "pending":
        pending()
    elif args.command == "approve":
        approve(args.request, args.by, args.note)
    elif args.command == "request":
        request(args.patient, args.needed_by, args.units)
    else:
        status()
