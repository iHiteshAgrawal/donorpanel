from decimal import Decimal
from typing import Any

import boto3

from ..config import config

PK, SK = "pk", "sk"
GSI1, GSI1PK, GSI1SK = "pool-index", "gsi1pk", "gsi1sk"

MESSAGE_PAD = 12


def resource():
    kwargs: dict[str, Any] = {"region_name": config.aws_region}
    if config.dynamodb_endpoint:
        kwargs["endpoint_url"] = config.dynamodb_endpoint
    return boto3.resource("dynamodb", **kwargs)


def get_table():
    return resource().Table(config.table_name)


def ensure_table() -> None:
    ddb = resource()
    existing = {t.name for t in ddb.tables.all()}
    if config.table_name in existing:
        return
    ddb.create_table(
        TableName=config.table_name,
        KeySchema=[{"AttributeName": PK, "KeyType": "HASH"},
                   {"AttributeName": SK, "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": PK, "AttributeType": "S"},
            {"AttributeName": SK, "AttributeType": "S"},
            {"AttributeName": GSI1PK, "AttributeType": "S"},
            {"AttributeName": GSI1SK, "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": GSI1,
            "KeySchema": [{"AttributeName": GSI1PK, "KeyType": "HASH"},
                          {"AttributeName": GSI1SK, "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"},
        }],
        BillingMode="PAY_PER_REQUEST",
    ).wait_until_exists()


def donor_key(donor_id: str) -> dict[str, str]:
    return {PK: f"DONOR#{donor_id}", SK: "PROFILE"}


def pool_key(region: str, blood_group: str, donor_id: str) -> dict[str, str]:
    return {GSI1PK: f"POOL#{region}#{blood_group}", GSI1SK: f"DONOR#{donor_id}"}


def patient_key(patient_id: str) -> dict[str, str]:
    return {PK: f"PATIENT#{patient_id}", SK: "PROFILE"}


def credit_key(patient_id: str) -> dict[str, str]:
    return {PK: f"PATIENT#{patient_id}", SK: "CREDIT"}


def request_key(request_id: str) -> dict[str, str]:
    return {PK: f"REQUEST#{request_id}", SK: "PROFILE"}


def contact_key(request_id: str, donor_id: str) -> dict[str, str]:
    return {PK: f"REQUEST#{request_id}", SK: f"CONTACT#{donor_id}"}


def session_key(session_id: str) -> dict[str, str]:
    return {PK: f"SESSION#{session_id}", SK: "SESSION"}


def agent_key(session_id: str, agent_id: str) -> dict[str, str]:
    return {PK: f"SESSION#{session_id}", SK: f"AGENT#{agent_id}"}


def message_key(session_id: str, agent_id: str, message_id: int) -> dict[str, str]:
    return {PK: f"SESSION#{session_id}",
            SK: f"MSG#{agent_id}#{message_id:0{MESSAGE_PAD}d}"}


def multi_agent_key(session_id: str, multi_agent_id: str) -> dict[str, str]:
    return {PK: f"SESSION#{session_id}", SK: f"MULTIAGENT#{multi_agent_id}"}


def encode(value: Any) -> Any:
    # DynamoDB rejects float, so every number goes in as Decimal and comes back
    # out as Decimal. str() first, otherwise Decimal(0.1) carries binary noise.
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def decode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value
