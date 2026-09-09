import argparse
import asyncio

from . import __version__, policies
from .channels import Outbound, registry
from .config import config


def status() -> None:
    active = registry()
    print(f"donorpanel {__version__}  env={config.env}  region={config.aws_region}")
    print(f"model: {config.bedrock_model_id or 'sdk default'}")
    print(f"table: {config.table_name}  endpoint={config.dynamodb_endpoint or 'aws'}")
    print(f"channels: {', '.join(active) or 'none'}")
    print(f"policies: {', '.join(policies.available())}")


def init() -> None:
    from .storage import ensure_table

    ensure_table()
    print(f"table {config.table_name} ready")


def seed() -> None:
    from .domain import Condition, Donor, Patient
    from .storage import PanelRepository, ensure_table

    ensure_table()
    repo = PanelRepository()
    repo.put_patient(Patient(
        patient_id="p-ravi", name="Ravi", condition=Condition.THALASSEMIA,
        blood_group="B+", policy_id="thalassemia-india", region="IN-TN",
        city="Coimbatore", hospital="Government Hospital",
    ))
    pool = [
        ("d-asha", "Asha", "B+", "telegram", True, "2026-04-02"),
        ("d-vikram", "Vikram", "B+", "email", True, "2026-08-30"),
        ("d-meera", "Meera", "B+", "telegram", True, None),
        ("d-suresh", "Suresh", "B+", "telegram", False, "2026-01-15"),
        ("d-priya", "Priya", "O-", "email", True, "2026-03-11"),
    ]
    for donor_id, name, group, channel, consent, last in pool:
        repo.put_donor(Donor(
            donor_id=donor_id, name=name, blood_group=group, region="IN-TN",
            channel=channel, address=f"{donor_id}@example.test", city="Coimbatore",
            consent=consent, last_donation=last, language="ta",
        ))
    print(f"seeded 1 patient and {len(pool)} donors into {config.table_name}")


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
    else:
        status()
