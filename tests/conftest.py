import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

BUCKET = "donorpanel-test"


@pytest.fixture
def store():
    with mock_aws():
        from donorpanel.storage import ObjectStore

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        yield ObjectStore(s3=s3, bucket=BUCKET)
