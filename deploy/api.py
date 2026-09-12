"""HTTP API in front of the Lambda, then points Telegram at it.

Two routes only: the webhook Telegram posts to, and the pool the landing page reads.
"""
import boto3
import httpx

from deploy.settings import ACCOUNT, FUNCTION_NAME, REGION
from donorpanel.config import config

api = boto3.client("apigatewayv2", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)

API_NAME = "donorpanel"
ROUTES = ("POST /webhook", "GET /api/public")
FUNCTION_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION_NAME}"


def find() -> dict | None:
    for item in api.get_apis(MaxResults="100").get("Items", []):
        if item["Name"] == API_NAME:
            return item
    return None


def ensure_api() -> dict:
    existing = find()
    if existing:
        print(f"  api {API_NAME} exists")
        return existing
    made = api.create_api(Name=API_NAME, ProtocolType="HTTP",
                          Description="DonorPanel webhook and public pool",
                          Tags={"project": "donorpanel"})
    print(f"  created api {API_NAME}")
    return made


def ensure_routes(api_id: str) -> None:
    integrations = api.get_integrations(ApiId=api_id).get("Items", [])
    if integrations:
        integration_id = integrations[0]["IntegrationId"]
    else:
        integration_id = api.create_integration(
            ApiId=api_id, IntegrationType="AWS_PROXY",
            IntegrationUri=FUNCTION_ARN, PayloadFormatVersion="2.0",
            # The graph can run the full Lambda timeout; the default 30s would cut it.
            TimeoutInMillis=30000)["IntegrationId"]
        print("  created integration")

    have = {r["RouteKey"] for r in api.get_routes(ApiId=api_id).get("Items", [])}
    for route in ROUTES:
        if route in have:
            continue
        api.create_route(ApiId=api_id, RouteKey=route,
                         Target=f"integrations/{integration_id}")
        print(f"  route {route}")

    stages = {s["StageName"] for s in api.get_stages(ApiId=api_id).get("Items", [])}
    if "$default" not in stages:
        api.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
        print("  stage $default")


def allow_invoke(api_id: str) -> None:
    try:
        lam.add_permission(
            FunctionName=FUNCTION_NAME, StatementId="apigateway-invoke",
            Action="lambda:InvokeFunction", Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{api_id}/*/*")
        print("  api gateway may invoke the function")
    except lam.exceptions.ResourceConflictException:
        print("  invoke permission already granted")


def set_webhook(url: str) -> None:
    token = config.telegram_bot_token
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": url, "secret_token": config.telegram_webhook_secret,
              "allowed_updates": ["message"]},
        timeout=20).json()
    if not response.get("ok"):
        raise SystemExit(f"setWebhook failed: {response}")
    print(f"  telegram now posts to {url}")


def main() -> None:
    made = ensure_api()
    api_id = made["ApiId"]
    ensure_routes(api_id)
    allow_invoke(api_id)
    endpoint = api.get_api(ApiId=api_id)["ApiEndpoint"]
    print(f"  endpoint {endpoint}")
    set_webhook(f"{endpoint}/webhook")
    print(f"\nadd this to web/.env:\n  VITE_API_URL={endpoint}")


if __name__ == "__main__":
    main()
