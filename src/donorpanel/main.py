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
    for prefix in ("requests/", "contacts/", "patient-requests/",
                   "donors/", "pool/", "patients/", "credits/"):
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
        lat=11.0168, lon=76.9558,
    ))
    pool = [
        ("d-asha", "Asha", "B+", "telegram", "ta", True, ago(160), 11.02, 76.96, 0),
        ("d-vikram", "Vikram", "B+", "email", "ta", True, ago(20), 11.05, 76.99, 0),
        ("d-meera", "Meera", "O-", "telegram", "ta", True, None, 11.01, 76.94, 0),
        ("d-suresh", "Suresh", "B+", "telegram", "ta", False, ago(400), 11.03, 76.97, 0),
        ("d-kavya", "Kavya", "O+", "telegram", "ta", True, ago(210), 11.30, 77.40, 3),
        ("d-arun", "Arun", "B-", "email", "ta", True, ago(120), 13.08, 80.27, 0),
        ("d-divya", "Divya", "A+", "telegram", "ta", True, ago(300), 11.00, 76.95, 0),
    ]
    for donor_id, name, group, channel, lang, consent, last, lat, lon, contacts in pool:
        repo.put_donor(Donor(
            donor_id=donor_id, name=name, blood_group=group, region="IN-TN",
            channel=channel, address=f"{donor_id}@example.test", city="Coimbatore",
            consent=consent, last_donation=last, language=lang, lat=lat, lon=lon,
            contacts_this_month=contacts,
        ))
    print(f"seeded 1 patient and {len(pool)} donors")


def request(patient_id: str, needed_by: str, units: int) -> None:
    import json

    from .graphs import request as flow

    out = flow.run({"patient_id": patient_id, "needed_by": needed_by,
                      "units_needed": units})
    print(json.dumps(out, indent=2))


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
    elif args.command == "request":
        request(args.patient, args.needed_by, args.units)
    else:
        status()
