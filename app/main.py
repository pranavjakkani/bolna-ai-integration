import json
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("bolna_integration")

app = FastAPI(title="Bolna AI Integration")


def _stringify_transcript(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=True)


def extract_call_details(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id", "unknown"),
        "agent_id": payload.get("agent_id", "unknown"),
        "status": payload.get("status", "unknown"),
        "duration": payload.get("telephony_data", {}).get("duration")
        or payload.get("conversation_time")
        or 0,
        "transcript": _stringify_transcript(payload.get("transcript")),
    }


def should_fetch_full_execution(call: dict[str, Any], api_key: str | None) -> bool:
    if not api_key:
        return False
    if call["id"] == "unknown":
        return False
    return not call["transcript"] or not call["duration"]


def fetch_execution(execution_id: str, api_key: str) -> dict[str, Any]:
    url = f"https://api.bolna.ai/executions/{execution_id}"
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()


def merge_missing_fields(call: dict[str, Any], fallback_payload: dict[str, Any]) -> dict[str, Any]:
    fallback_call = extract_call_details(fallback_payload)
    if not call["transcript"]:
        call["transcript"] = fallback_call["transcript"]
    if not call["duration"]:
        call["duration"] = fallback_call["duration"]
    if call["agent_id"] == "unknown":
        call["agent_id"] = fallback_call["agent_id"]
    return call


def build_slack_payload(call: dict[str, Any]) -> dict[str, Any]:
    transcript = call["transcript"] or "Transcript not available."
    if len(transcript) > 2900:
        transcript = f"{transcript[:2900]}..."

    return {
        "text": f"Bolna call completed: {call['id']}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Bolna Call Completed"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Call ID*\n{call['id']}"},
                    {"type": "mrkdwn", "text": f"*Agent ID*\n{call['agent_id']}"},
                    {"type": "mrkdwn", "text": f"*Duration (s)*\n{call['duration']}"},
                    {"type": "mrkdwn", "text": f"*Status*\n{call['status']}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Transcript*\n```{transcript}```"},
            },
        ],
    }


def post_to_slack(slack_webhook_url: str, message: dict[str, Any]) -> None:
    response = httpx.post(slack_webhook_url, json=message, timeout=15.0)
    response.raise_for_status()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/bolna")
async def bolna_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    logger.info("Received Bolna webhook payload: %s", json.dumps(payload, ensure_ascii=True))

    call = extract_call_details(payload)

    if call["status"] != "completed":
        logger.info("Ignoring Bolna webhook with status=%s for id=%s", call["status"], call["id"])
        return {"status": "ignored", "reason": "non-completed event", "call_id": call["id"]}

    bolna_api_key = os.getenv("BOLNA_API_KEY")
    if should_fetch_full_execution(call, bolna_api_key):
        try:
            fallback_payload = fetch_execution(call["id"], bolna_api_key)
            call = merge_missing_fields(call, fallback_payload)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch fallback execution for %s: %s", call["id"], exc)

    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not slack_webhook_url:
        raise HTTPException(status_code=500, detail="SLACK_WEBHOOK_URL is not configured")

    try:
        post_to_slack(slack_webhook_url, build_slack_payload(call))
    except httpx.HTTPError as exc:
        logger.exception("Failed to deliver Slack alert for call %s", call["id"])
        raise HTTPException(status_code=502, detail=f"Slack delivery failed: {exc}") from exc

    logger.info("Delivered Slack alert for completed call id=%s", call["id"])
    return {"status": "sent", "call_id": call["id"]}
