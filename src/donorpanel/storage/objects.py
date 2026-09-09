import json
from typing import Any

import boto3
from botocore.exceptions import ClientError

from ..config import config

DONOR = "donors/{donor_id}.json"
POOL = "pool/{region}/{blood_group}/{donor_id}"
PATIENT = "patients/{patient_id}.json"
CREDIT = "credits/{patient_id}.json"
REQUEST = "requests/{request_id}.json"
PATIENT_REQUEST = "patient-requests/{patient_id}/{request_id}"
CONTACT = "contacts/{request_id}/{donor_id}.json"
SESSION_PREFIX = "sessions/"


def client():
    return boto3.client("s3", region_name=config.aws_region)


def ensure_bucket() -> None:
    s3 = client()
    try:
        s3.head_bucket(Bucket=config.bucket)
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "403"):
            raise
    kwargs: dict[str, Any] = {"Bucket": config.bucket}
    # us-east-1 is the one region that rejects an explicit LocationConstraint.
    if config.aws_region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": config.aws_region}
    try:
        s3.create_bucket(**kwargs)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass


class ObjectStore:
    def __init__(self, s3=None, bucket: str | None = None):
        self._s3 = s3 or client()
        self._bucket = bucket or config.bucket

    def put(self, key: str, payload: dict[str, Any]) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key,
                            Body=json.dumps(payload).encode(),
                            ContentType="application/json")

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(body)

    def touch(self, key: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=b"")

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def keys(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        found: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            found.extend(obj["Key"] for obj in page.get("Contents", []))
        return found
