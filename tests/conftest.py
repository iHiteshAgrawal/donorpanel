import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def ddb():
    with mock_aws():
        from donorpanel.storage import table as t

        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName="donorpanel",
            KeySchema=[{"AttributeName": t.PK, "KeyType": "HASH"},
                       {"AttributeName": t.SK, "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": t.PK, "AttributeType": "S"},
                {"AttributeName": t.SK, "AttributeType": "S"},
                {"AttributeName": t.GSI1PK, "AttributeType": "S"},
                {"AttributeName": t.GSI1SK, "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": t.GSI1,
                "KeySchema": [{"AttributeName": t.GSI1PK, "KeyType": "HASH"},
                              {"AttributeName": t.GSI1SK, "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()
        yield resource.Table("donorpanel")
