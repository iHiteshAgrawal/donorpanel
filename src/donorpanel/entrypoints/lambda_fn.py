"""The Lambda side: webhook receiver, scheduled tick, and the graph runs.

One function, three modes, because three functions would mean three roles, three
deployments and three sets of drift.
"""
import asyncio
import json
import logging
import os

import boto3
from botocore.config import Config as BotoConfig

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


# Without a read timeout this call waits until Lambda kills the whole invocation at 300s,
# so the handler never returns, API Gateway answers Telegram 503, and Telegram redelivers
# the message. Cut it off early enough that the in-process fallback still has room to run.
# botocore counts max_attempts as retries on top of the first call, so 0 means try once.
# Set to 1 this waited out two full 90s timeouts before falling back, taking 187s.
_runtime_client = BotoConfig(retries={"max_attempts": 0}, connect_timeout=5,
                             read_timeout=60)


def _agentcore():
    return boto3.client("bedrock-agentcore", region_name=config.aws_region,
                        config=_runtime_client)


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

    from donorpanel.services import chat

    carry: dict = {}
    try:
        answer = chat.reply(pool.ensure(), prompt, sender=sender, channel=channel,
                            carry=carry)
    except Exception as exc:
        # Runtime is down or Bedrock is throttling, and the fallback hit the same wall.
        # Silence is the worst answer available: somebody messaged asking for blood.
        log.warning("both runtime and in process failed", exc_info=True)
        return {"text": apology(exc), "launch": None}
    return {"text": answer, "launch": carry.get("launch")}


def apology(exc: Exception) -> str:
    throttled = "throttl" in str(exc).lower() or "ThrottlingException" in str(exc)
    if throttled:
        return ("I am getting more messages than I can answer this minute. Please send "
                "that again shortly and I will pick it straight up.")
    return ("Something went wrong at my end, not yours. Please try again in a moment, "
            "and a coordinator will step in if it keeps happening.")


def _send(channel_name: str, recipient: str, body: str) -> None:
    channel = registry().get(channel_name)
    if channel:
        asyncio.run(channel.send(Outbound(recipient=recipient, body=body)))


def _self_invoke(payload: dict) -> None:
    name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if not name:
        # Off Lambda there is nothing to invoke, so run the mode here. Dispatch on it
        # rather than assuming search, which is what this did when search was the only
        # asynchronous mode.
        log.info("not on lambda, running %s inline", payload.get("mode"))
        (reply if payload.get("mode") == "reply" else search)(payload)
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

    # Acknowledge before answering. API Gateway caps an HTTP API integration at 30s and
    # that is the hard maximum, but a model call plus session load runs past it, so the
    # reply used to arrive as a 503. Telegram reads a 503 as "send it again" and redelivers
    # the same message every couple of minutes, which is how one "hi" became 3,737 throttle
    # events. The answer is sent from the async invocation below, over the Telegram API.
    _self_invoke({"mode": "reply", "sender": message.sender, "text": message.body,
                  "reply_to": message.reply_to, "channel": message.channel})
    return {"statusCode": 200, "body": "ok"}


def reply(event: dict) -> dict:
    message, sender = event["text"], event["sender"]
    channel, reply_to = event.get("channel", "telegram"), event["reply_to"]
    out = ask_asha(sender, message, channel)
    if out.get("text"):
        _send(channel, reply_to, out["text"])
    if out.get("launch"):
        _self_invoke({"mode": "search", "ask": out["launch"],
                      "reply_to": reply_to, "channel": channel})
    return {"ok": True}


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
        if mode == "reply":
            return reply(event)

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
