"""Names and ARNs every deploy step shares. Change them here, nowhere else."""
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


def repo_uri(name: str) -> str:
    return f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{name}"


def role_arn(name: str) -> str:
    return f"arn:aws:iam::{ACCOUNT}:role/{name}"
