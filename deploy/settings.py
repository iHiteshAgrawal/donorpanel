"""Names and ARNs every deploy step shares. Change them here, nowhere else."""
import json
import pathlib
import time

import boto3

from donorpanel.config import config

REGION = config.aws_region
ACCOUNT = boto3.client("sts").get_caller_identity()["Account"]

# AgentCore pulls Runtime images from a repository named bedrock-agentcore-*, which is
# what the AWS samples scope their execution roles to. Matching it avoids a pull denial
# that would surface as an opaque runtime failure.
RUNTIME_REPO = "bedrock-agentcore-donorpanel"
LAMBDA_REPO = "donorpanel-lambda"

RUNTIME_ROLE = "donorpanel-runtime"
LAMBDA_ROLE = "donorpanel-lambda"
SCHEDULER_ROLE = "donorpanel-scheduler"

# agentRuntimeName rejects hyphens: [a-zA-Z][a-zA-Z0-9_]{0,47}
RUNTIME_NAME = "DonorPanelAsha"
FUNCTION_NAME = "donorpanel"
SCHEDULE_NAME = "donorpanel-daily-forecast"
SITE_BUCKET = f"donorpanel-site-{ACCOUNT}"

PANEL_BUCKET = config.bucket or f"donorpanel-{ACCOUNT}"
MEMORY_ARN = (f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:memory/"
              f"{config.agentcore_memory_id}") if config.agentcore_memory_id else None


def image_tag() -> str:
    """What is being deployed, as a tag you can point at later. A dirty tree gets a
    timestamp so two builds from the same commit never share a tag."""
    import subprocess

    def git(*args: str) -> str:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        return out.stdout.strip()

    sha = git("rev-parse", "--short", "HEAD") or "nogit"
    return f"{sha}-{int(time.time())}" if git("status", "--porcelain") else sha


def deployed() -> dict:
    """What push.py last shipped. Absent on a fresh clone, so callers fall back."""
    record = pathlib.Path(__file__).parent / "deployed.json"
    return json.loads(record.read_text()) if record.exists() else {}


def pinned(repo: str) -> str:
    """The exact image to deploy, by tag, falling back to latest."""
    tag = deployed().get("tag", "latest")
    return f"{repo_uri(repo)}:{tag}"


def repo_uri(name: str) -> str:
    return f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{name}"


def role_arn(name: str) -> str:
    return f"arn:aws:iam::{ACCOUNT}:role/{name}"
