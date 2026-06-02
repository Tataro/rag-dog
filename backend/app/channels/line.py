"""LINE webhook adapter.

Verifies `X-Line-Signature` HMAC-SHA256, enforces the user-id allowlist,
runs the shared query pipeline in a background task, and replies via the LINE
Messaging API.
"""
import json
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..config import settings
from ..db import SessionLocal
from ..generation.pipeline import answer_query
from ..security.verify import verify_line
from .base import format_bot_reply

router = APIRouter()
log = logging.getLogger(__name__)

_LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
_LINE_MAX_TEXT = 5000  # LINE text message hard limit


@router.post("", responses={401: {"description": "bad line signature"}})
async def line_webhook(
    request: Request,
    background: BackgroundTasks,
    x_line_signature: Annotated[str | None, Header()] = None,
) -> dict:
    body = await request.body()
    if not verify_line(body, x_line_signature):
        raise HTTPException(status_code=401, detail="bad line signature")

    payload = json.loads(body.decode("utf-8"))
    events = payload.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        if msg.get("type") != "text":
            continue

        user_id = (event.get("source") or {}).get("userId") or ""
        text = (msg.get("text") or "").strip()
        reply_token = event.get("replyToken")
        if not text or not reply_token or not user_id:
            continue

        allowlist = settings.line_allowlist
        if allowlist and user_id not in allowlist:
            log.warning("line: dropping message from non-allowlisted user %s", user_id)
            continue

        background.add_task(_handle_line_message, user_id, text, reply_token)

    return {"ok": True}


async def _handle_line_message(user_id: str, text: str, reply_token: str) -> None:
    try:
        # FIXME(ADR 0004): this channel is descoped/unwired. The call below uses the
        # pre-multi-user answer_query signature and will TypeError if re-wired — the
        # bot first needs a Google<->LINE-user-id account-linking flow for a user_id.
        async with SessionLocal() as session:
            result = await answer_query(session, channel="line", external_id=user_id, text=text)
        reply = format_bot_reply(result)[:_LINE_MAX_TEXT]
        await _reply_line(reply_token, reply)
    except Exception:
        log.exception("line: failed to handle message for user %s", user_id)


async def _reply_line(reply_token: str, text: str) -> None:
    if not settings.line_channel_access_token:
        log.error("line: access token not configured; cannot reply")
        return
    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_LINE_REPLY_URL, headers=headers, json=payload)
        if resp.status_code >= 400:
            log.error("line: reply failed: %s %s", resp.status_code, resp.text)
