"""The Lambda side: webhook receiver, scheduled tick, and the graph runs.

One function, three modes, because three functions would mean three roles, three
deployments and three sets of drift.
"""
import asyncio
import json
import logging
import os

import boto3

from donorpanel.adapters.channels import Outbound, TelegramChannel, registry
from donorpanel.config import config
from donorpanel.services import forecast, pool

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# httpx logs the full request URL, and a Telegram URL carries the bot token in its path.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

SECRET_HEADER = "x-telegram-bot-api-secret-token"


def _lambda():
    return boto3.client("lambda", region_name=config.aws_region)


def _agentcore():
    return boto3.client("bedrock-agentcore", region_name=config.aws_region)


def ask_asha(sender: str, prompt: str, channel: str = "telegram") -> dict:
    """AgentCore Runtime when it is configured, this process when it is not.

    The fallback is the whole reason Runtime is safe to depend on two days out: it runs
    the identical code, so a Runtime outage costs the architecture story and not the
    demo."""
    from donorpanel.entrypoints.runtime import session_id

    if config.agentcore_runtime_arn:
        try:
            response = _agentcore().invoke_agent_runtime(
                agentRuntimeArn=config.agentcore_runtime_arn,
                runtimeSessionId=session_id(sender),
                runtimeUserId=str(sender),
                payload=json.dumps({"prompt": prompt, "sender": sender,
                                    "channel": channel}).encode(),
            )
            return json.loads(response["response"].read())
        except Exception:
            log.warning("runtime invoke failed, answering in process", exc_info=True)

    from donorpanel import chat

    carry: dict = {}
    answer = chat.reply(pool.ensure(), prompt, sender=sender, channel=channel,
                        carry=carry)
    return {"text": answer, "launch": carry.get("launch")}


def _send(channel_name: str, recipient: str, body: str) -> None:
    channel = registry().get(channel_name)
    if channel:
        asyncio.run(channel.send(Outbound(recipient=recipient, body=body)))


def _self_invoke(payload: dict) -> None:
    name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if not name:
        log.info("not on lambda, running %s inline", payload.get("mode"))
        search(payload)
        return
    _lambda().invoke(FunctionName=name, InvocationType="Event",
                     Payload=json.dumps(payload).encode())


def webhook(body: dict, headers: dict) -> dict:
    if config.telegram_webhook_secret and \
            headers.get(SECRET_HEADER) != config.telegram_webhook_secret:
        log.warning("webhook called without the shared secret")
        return {"statusCode": 403, "body": "no"}

    message = TelegramChannel().webhook_update(body)
    if message is None:
        return {"statusCode": 200, "body": "ignored"}

    out = ask_asha(message.sender, message.body, message.channel)
    if out.get("text"):
        _send(message.channel, message.reply_to, out["text"])
    if out.get("launch"):
        # After the reply, never before: the graph takes most of a minute and Telegram
        # retries anything it considers slow.
        _self_invoke({"mode": "search", "ask": out["launch"],
                      "reply_to": message.reply_to, "channel": message.channel})
    return {"statusCode": 200, "body": "ok"}


def search(event: dict) -> dict:
    from donorpanel.entrypoints.poller import _summarise
    from donorpanel.graph import flow

    panel = pool.ensure()
    try:
        out = flow.run(event["ask"], panel, None, None, "public")
        told = _summarise(panel, out)
    except Exception:
        log.warning("chat-started request failed", exc_info=True)
        told = ("I could not finish searching just now. A coordinator will pick this up "
                "and come back to you.")
    _send(event.get("channel", "telegram"), event["reply_to"], told)
    return {"ok": True}


def tick(_event: dict) -> dict:
    out = forecast.tick(pool.ensure())
    log.info("forecast opened %d of %d due", len(out["opened"]), out["due"])
    return out


def handler(event: dict, _context=None) -> dict:
    """Routes on the event shape. Nothing raises: an exception reaching API Gateway is a
    500 to Telegram, and Telegram answers a 500 by sending the same message again."""
    try:
        mode = event.get("mode")
        if mode == "tick":
            return tick(event)
        if mode == "search":
            return search(event)

        path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
        if path.endswith("/api/public"):
            return {"statusCode": 200,
                    "headers": {"content-type": "application/json",
                                "access-control-allow-origin": "*"},
                    "body": json.dumps(public_pool())}

        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        body = event.get("body") or "{}"
        return webhook(json.loads(body), headers)
    except Exception:
        log.exception("handler failed")
        return {"statusCode": 200, "body": "error logged"}


def public_pool() -> dict:
    panel = pool.ensure()
    patient = panel.get_patient(pool.PATIENT["patient_id"])
    counts = pool.headcount(panel)
    return {"bot": config.telegram_bot_username, "donors": counts["donors"],
            "cities": counts["cities"], "requests": counts["requests"],
            "reached": counts["reached"],
            "patient": {"name": patient.name, "blood_group": patient.blood_group,
                        "condition": patient.condition.value, "city": patient.city,
                        "hospital": patient.hospital} if patient else None}
