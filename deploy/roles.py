"""Creates the three execution roles. Idempotent: rerun after any permission change.

Roles are created once and their inline policy is rewritten every run, so this is the
one place to edit what the deployed code is allowed to do.
"""
import json
import sys

import boto3
from botocore.exceptions import ClientError

from deploy.settings import (
    ACCOUNT,
    FUNCTION_NAME,
    LAMBDA_REPO,
    LAMBDA_ROLE,
    MEMORY_ARN,
    PANEL_BUCKET,
    REGION,
    RUNTIME_REPO,
    RUNTIME_ROLE,
    SCHEDULER_ROLE,
    role_arn,
)

iam = boto3.client("iam")


def trust(service: str, guard: bool = False) -> dict:
    statement = {"Effect": "Allow", "Principal": {"Service": service},
                 "Action": "sts:AssumeRole"}
    if guard:
        # Confused deputy protection: without these any account could induce AgentCore
        # to assume this role on their behalf.
        statement["Condition"] = {
            "StringEquals": {"aws:SourceAccount": ACCOUNT},
            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:*"},
        }
    return {"Version": "2012-10-17", "Statement": [statement]}


def agent_permissions(repo: str) -> list[dict]:
    """What both the Runtime container and the Lambda need to do their work."""
    statements = [
        {"Sid": "Models", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse", "bedrock:ConverseStream"],
         "Resource": ["arn:aws:bedrock:*::foundation-model/*",
                      f"arn:aws:bedrock:*:{ACCOUNT}:inference-profile/*"]},
        # GetAuthorizationToken is account level and cannot be scoped to a
        # repository. Scoping it there fails the ECR URI validation with a message
        # that reads like the whole grant is missing.
        {"Sid": "EcrAuth", "Effect": "Allow",
         "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
        {"Sid": "PullImage", "Effect": "Allow",
         "Action": ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage"],
         "Resource": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{repo}"},
        {"Sid": "Logs", "Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                    "logs:DescribeLogStreams", "logs:DescribeLogGroups"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:*"},
        {"Sid": "Traces", "Effect": "Allow",
         "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords",
                    "cloudwatch:PutMetricData"],
         "Resource": "*"},
        {"Sid": "Panel", "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{PANEL_BUCKET}", f"arn:aws:s3:::{PANEL_BUCKET}/*"]},
        {"Sid": "Geocoding", "Effect": "Allow",
         "Action": ["geo-places:Geocode"], "Resource": "*"},
    ]
    if MEMORY_ARN:
        statements.append(
            {"Sid": "Memory", "Effect": "Allow",
             "Action": ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents",
                        "bedrock-agentcore:DeleteEvent", "bedrock-agentcore:ListSessions",
                        "bedrock-agentcore:RetrieveMemoryRecords",
                        "bedrock-agentcore:ListMemoryRecords",
                        "bedrock-agentcore:BatchCreateMemoryRecords",
                        "bedrock-agentcore:BatchDeleteMemoryRecords"],
             "Resource": MEMORY_ARN})
    return statements


ROLES = {
    RUNTIME_ROLE: (
        trust("bedrock-agentcore.amazonaws.com", guard=True),
        agent_permissions(RUNTIME_REPO),
    ),
    LAMBDA_ROLE: (
        trust("lambda.amazonaws.com"),
        agent_permissions(LAMBDA_REPO) + [
            # Passing runtimeUserId requires both actions. With only the first, the
            # call is refused and the message names the missing one.
            {"Sid": "CallAsha", "Effect": "Allow",
             "Action": ["bedrock-agentcore:InvokeAgentRuntime",
                        "bedrock-agentcore:InvokeAgentRuntimeForUser"],
             "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/*"},
            {"Sid": "SelfInvoke", "Effect": "Allow",
             "Action": "lambda:InvokeFunction",
             "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION_NAME}"},
        ],
    ),
    SCHEDULER_ROLE: (
        trust("scheduler.amazonaws.com"),
        [{"Sid": "RunTheTick", "Effect": "Allow", "Action": "lambda:InvokeFunction",
          "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION_NAME}"}],
    ),
}


def ensure(name: str, trust_policy: dict, statements: list[dict]) -> str:
    try:
        iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust_policy),
                        Description=f"DonorPanel {name}",
                        Tags=[{"Key": "project", "Value": "donorpanel"}])
        action = "created"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        action = "updated"
        try:
            iam.update_assume_role_policy(RoleName=name,
                                          PolicyDocument=json.dumps(trust_policy))
        except ClientError as denied:
            # Not fatal: the role already exists with the trust policy it was created
            # with, and only a deliberate change to trust would need this.
            if denied.response["Error"]["Code"] != "AccessDenied":
                raise
            action = "kept"
    iam.put_role_policy(RoleName=name, PolicyName=f"{name}-inline",
                        PolicyDocument=json.dumps(
                            {"Version": "2012-10-17", "Statement": statements}))
    print(f"  {action:8} {role_arn(name)}")
    return role_arn(name)


# AgentCore creates network interfaces through a service linked role, and wants it even
# when networkMode is PUBLIC. The docs only mention it under VPC configuration, so a
# fresh account fails create_agent_runtime with an opaque "failed creating service
# linked role" until this exists.
# Scheduler is deliberately absent: it assumes donorpanel-scheduler, not a service
# linked role.
# All five AgentCore service linked roles. Creating one it does not need is harmless;
# missing one fails create_agent_runtime with a message that names no service at all.
SERVICE_LINKED = (
    "bedrock-agentcore.amazonaws.com",
    "network.bedrock-agentcore.amazonaws.com",
    "runtime-identity.bedrock-agentcore.amazonaws.com",
    "runtime-instances.bedrock-agentcore.amazonaws.com",
    "gateway-network.bedrock-agentcore.amazonaws.com",
)


def service_linked_roles() -> None:
    for service in SERVICE_LINKED:
        try:
            iam.create_service_linked_role(AWSServiceName=service)
            print(f"  created  service linked role for {service}")
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "InvalidInput":       # already exists
                print(f"  exists   service linked role for {service}")
            elif code == "AccessDenied":
                print(f"  DENIED   service linked role for {service}")
            else:
                raise


def main() -> None:
    service_linked_roles()
    if MEMORY_ARN is None:
        print("AGENTCORE_MEMORY_ID is unset, so the roles will have no memory access.",
              file=sys.stderr)
    for name, (trust_policy, statements) in ROLES.items():
        ensure(name, trust_policy, statements)


if __name__ == "__main__":
    main()
