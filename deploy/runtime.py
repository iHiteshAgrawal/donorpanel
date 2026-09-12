"""Creates or updates the AgentCore Runtime that hosts Asha.

Idempotent: reruns update the container image and environment on the existing runtime
rather than creating a second one.
"""
import json
import time

import boto3
from botocore.exceptions import ClientError

from deploy.settings import REGION, RUNTIME_NAME, RUNTIME_REPO, RUNTIME_ROLE, pinned, role_arn
from donorpanel.config import config

ctl = boto3.client("bedrock-agentcore-control", region_name=REGION)


def environment() -> dict[str, str]:
    """Config the container cannot read from .env, because .dockerignore keeps it out."""
    values = {
        "AWS_REGION": REGION,
        "BEDROCK_MODEL_ID": config.bedrock_model_id or "",
        "DONORPANEL_BUCKET": config.bucket or "",
        "AGENTCORE_MEMORY_ID": config.agentcore_memory_id or "",
        "TELEGRAM_BOT_TOKEN": config.telegram_bot_token or "",
        "TELEGRAM_BOT_USERNAME": config.telegram_bot_username,
        "TELEGRAM_DEMO_CHAT_ID": config.telegram_demo_chat_id or "",
        "SES_SENDER_EMAIL": config.ses_sender_email or "",
        "SES_DEMO_EMAIL": config.ses_demo_email or "",
        "DONORPANEL_ENV": "runtime",
    }
    return {k: v for k, v in values.items() if v}


def find() -> dict | None:
    for page in ctl.get_paginator("list_agent_runtimes").paginate():
        for row in page.get("agentRuntimes", []):
            if row.get("agentRuntimeName") == RUNTIME_NAME:
                return row
    return None


def wait_ready(runtime_id: str, timeout: int = 600) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = ctl.get_agent_runtime(agentRuntimeId=runtime_id)["status"]
        if status == "READY":
            return status
        if status in ("CREATE_FAILED", "UPDATE_FAILED", "DELETING"):
            raise SystemExit(f"runtime went to {status}")
        time.sleep(10)
    raise SystemExit(f"runtime still {status} after {timeout}s")


def main() -> None:
    artifact = {"containerConfiguration": {"containerUri": pinned(RUNTIME_REPO)}}
    existing = find()
    if existing:
        runtime_id = existing["agentRuntimeId"]
        ctl.update_agent_runtime(
            agentRuntimeId=runtime_id,
            agentRuntimeArtifact=artifact,
            roleArn=role_arn(RUNTIME_ROLE),
            networkConfiguration={"networkMode": "PUBLIC"},
            environmentVariables=environment(),
        )
        print(f"  updated {RUNTIME_NAME}")
    else:
        created = ctl.create_agent_runtime(
            agentRuntimeName=RUNTIME_NAME,
            description="Asha, the DonorPanel assistant",
            agentRuntimeArtifact=artifact,
            roleArn=role_arn(RUNTIME_ROLE),
            networkConfiguration={"networkMode": "PUBLIC"},
            environmentVariables=environment(),
        )
        runtime_id = created["agentRuntimeId"]
        print(f"  created {RUNTIME_NAME}")

    wait_ready(runtime_id)
    arn = ctl.get_agent_runtime(agentRuntimeId=runtime_id)["agentRuntimeArn"]
    print(f"  READY   {arn}")
    print(f"\nadd this to .env:\n  AGENTCORE_RUNTIME_ARN={arn}")


if __name__ == "__main__":
    try:
        main()
    except ClientError as exc:
        raise SystemExit(json.dumps(exc.response["Error"], indent=2)) from exc
