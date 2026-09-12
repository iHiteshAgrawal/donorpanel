"""The recurring tick: close settled requests, forecast what is due, chase what is quiet.

Six hours rather than a day because the policy, not the schedule, holds the real cadence.
outreach.escalation_hours declares waves at 0, 24 and 48 hours, and a 24 hour wave cannot
fire reliably on a 24 hour timer without drifting past it. Every pass is idempotent, so a
tick with nothing to do is a cheap no-op.
"""
import json
import sys

import boto3
from botocore.exceptions import ClientError

from deploy.settings import ACCOUNT, FUNCTION_NAME, REGION, SCHEDULE_NAME, SCHEDULER_ROLE, role_arn

scheduler = boto3.client("scheduler", region_name=REGION)

RATE = sys.argv[1] if len(sys.argv) > 1 else "rate(6 hours)"
FUNCTION_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION_NAME}"


def spec() -> dict:
    return {
        "Name": SCHEDULE_NAME,
        "ScheduleExpression": RATE,
        "Description": "DonorPanel: close, forecast, chase",
        # Off: a forecast that drifts by minutes is fine, but predictable timing makes
        # "did the tick run" answerable without reading logs.
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": {
            "Arn": FUNCTION_ARN,
            "RoleArn": role_arn(SCHEDULER_ROLE),
            "Input": json.dumps({"mode": "tick"}),
            "RetryPolicy": {"MaximumRetryAttempts": 2,
                            "MaximumEventAgeInSeconds": 3600},
        },
    }


def main() -> None:
    try:
        scheduler.create_schedule(**spec())
        print(f"  created {SCHEDULE_NAME} at {RATE}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConflictException":
            raise
        scheduler.update_schedule(**spec())
        print(f"  updated {SCHEDULE_NAME} to {RATE}")

    got = scheduler.get_schedule(Name=SCHEDULE_NAME)
    print(f"  {got['State']}  {got['ScheduleExpression']}  -> {got['Target']['Arn']}")


if __name__ == "__main__":
    main()
