import boto3
import pytest
from moto import mock_aws

BUCKET = "donorpanel-test"


@pytest.fixture
def store(monkeypatch):
    # Scoped to this fixture on purpose. Setting these at module import would
    # override the real credentials file and break the live Bedrock tests.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    with mock_aws():
        from donorpanel.adapters.storage import ObjectStore

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        yield ObjectStore(s3=s3, bucket=BUCKET)
