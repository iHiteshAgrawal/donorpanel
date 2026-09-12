"""Creates or updates the Lambda that receives webhooks, runs the graph, and ticks."""
import time

import boto3
from botocore.exceptions import ClientError

from deploy.runtime import environment
from deploy.settings import FUNCTION_NAME, LAMBDA_REPO, LAMBDA_ROLE, REGION, pinned, role_arn
from donorpanel.config import config

lam = boto3.client("lambda", region_name=REGION)

# The graph takes 30 to 70 seconds and search mode runs it to completion, so the
# ceiling has to clear that with room for a cold start.
TIMEOUT = 300
MEMORY = 2048


# Lambda sets these itself and rejects any attempt to supply them.
RESERVED = ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")


def settings() -> dict:
    env = {k: v for k, v in environment().items() if k not in RESERVED}
    env["AGENTCORE_RUNTIME_ARN"] = config.agentcore_runtime_arn or ""
    env["TELEGRAM_WEBHOOK_SECRET"] = config.telegram_webhook_secret or ""
    env["DONORPANEL_ENV"] = "lambda"
    return {k: v for k, v in env.items() if v}


def wait_active() -> None:
    for _ in range(60):
        state = lam.get_function(FunctionName=FUNCTION_NAME)["Configuration"]
        if state.get("LastUpdateStatus") != "InProgress" and state.get("State") == "Active":
            return
        time.sleep(5)
    raise SystemExit("function did not become active")


def main() -> None:
    image = pinned(LAMBDA_REPO)
    try:
        lam.create_function(
            FunctionName=FUNCTION_NAME,
            PackageType="Image",
            Code={"ImageUri": image},
            Role=role_arn(LAMBDA_ROLE),
            Timeout=TIMEOUT,
            MemorySize=MEMORY,
            Architectures=["arm64"],
            Environment={"Variables": settings()},
            Description="DonorPanel webhook, forecast and request graph",
            Tags={"project": "donorpanel"},
        )
        print(f"  created {FUNCTION_NAME}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise
        lam.update_function_code(FunctionName=FUNCTION_NAME, ImageUri=image)
        wait_active()
        lam.update_function_configuration(
            FunctionName=FUNCTION_NAME, Role=role_arn(LAMBDA_ROLE),
            Timeout=TIMEOUT, MemorySize=MEMORY,
            Environment={"Variables": settings()})
        print(f"  updated {FUNCTION_NAME}")
    wait_active()
    arn = lam.get_function(FunctionName=FUNCTION_NAME)["Configuration"]["FunctionArn"]
    print(f"  ACTIVE  {arn}")


if __name__ == "__main__":
    main()
