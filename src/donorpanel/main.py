import argparse
import asyncio

from . import __version__, policies
from .channels import Outbound, registry
from .config import config


def status() -> None:
    active = registry()
    print(f"donorpanel {__version__}  env={config.env}  region={config.aws_region}")
    print(f"model: {config.bedrock_model_id or 'sdk default'}")
    print(f"channels: {', '.join(active) or 'none'}")
    print(f"policies: {', '.join(policies.available())}")


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

    send = sub.add_parser("ping")
    send.add_argument("--channel", default="console")
    send.add_argument("--to", required=True)
    send.add_argument("--body", default="DonorPanel channel check.")

    args = parser.parse_args()
    if args.command == "ping":
        asyncio.run(ping(args.channel, args.to, args.body))
    else:
        status()


if __name__ == "__main__":
    main()
