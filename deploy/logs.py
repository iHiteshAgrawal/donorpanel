"""Retention and a data protection policy on both log groups.

Agent output never reaches stdout (callback_handler=None), verified on the deployed
groups. This is the second line rather than the first: if a future change starts logging
a message body, the masking catches it before a person's name is durable.
"""
import json

import boto3
from botocore.exceptions import ClientError

from deploy.settings import FUNCTION_NAME, REGION, RUNTIME_NAME
from donorpanel.config import config

logs = boto3.client("logs", region_name=REGION)

RETENTION_DAYS = 30

# Probed against the API rather than taken from the docs: PhoneNumber-IN and every
# Aadhaar spelling are rejected as invalid identifiers, so AWS has no managed identifier
# for Indian IDs. That is a reason not to store them at all rather than to rely on
# masking, which is what the intake flow already does.
IDENTIFIERS = ["Name", "Address", "EmailAddress", "DateOfBirth", "PhoneNumber-US"]


def groups() -> list[str]:
    found = [f"/aws/lambda/{FUNCTION_NAME}"]
    prefix = "/aws/bedrock-agentcore/runtimes/"
    for page in logs.get_paginator("describe_log_groups").paginate(
            logGroupNamePrefix=prefix):
        found += [g["logGroupName"] for g in page["logGroups"]
                  if RUNTIME_NAME in g["logGroupName"]]
    return found


def policy() -> dict:
    """Exactly two statements, one Audit and one Deidentify. The API rejects any other
    shape, including a single masking statement on its own."""
    arns = [f"arn:aws:dataprotection::aws:data-identifier/{i}" for i in IDENTIFIERS]
    return {
        "Name": "donorpanel-mask-personal-data",
        "Version": "2021-06-01",
        "Statement": [
            {"Sid": "Audit", "DataIdentifier": arns,
             "Operation": {"Audit": {"FindingsDestination": {}}}},
            {"Sid": "Mask", "DataIdentifier": arns,
             "Operation": {"Deidentify": {"MaskConfig": {}}}},
        ],
    }


def main() -> None:
    if not config.agentcore_runtime_arn:
        print("  no runtime arn configured, only the lambda group will be covered")
    for group in groups():
        logs.put_retention_policy(logGroupName=group, retentionInDays=RETENTION_DAYS)
        try:
            logs.put_data_protection_policy(logGroupIdentifier=group,
                                            policyDocument=json.dumps(policy()))
            print(f"  {RETENTION_DAYS}d retention + masking on {group}")
        except ClientError as exc:
            print(f"  {RETENTION_DAYS}d retention on {group} "
                  f"(masking failed: {exc.response['Error']['Code']})")


if __name__ == "__main__":
    main()
