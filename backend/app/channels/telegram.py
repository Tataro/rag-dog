"""Telegram webhook adapter.

Validates `X-Telegram-Bot-Api-Secret-Token`, enforces the chat-id allowlist,
runs the same query pipeline as the web channel in a background task, and
posts the reply via the Bot API.
"""
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..config import settings
from ..db import SessionLocal
from ..generation.pipeline import answer_query
from ..security.verify import verify_telegram
from .base import format_bot_reply

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("", responses={401: {"description": "bad telegram signature"}})
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict:
    if not verify_telegram(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=401, detail="bad telegram signature")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}  # ignore non-message updates silently

    chat_id = str(message["chat"]["id"])
    text = (message.get("text") or "").strip()
    if not text:
        return {"ok": True}

    allowlist = settings.telegram_allowlist
    if allowlist and chat_id not in allowlist:
        log.warning("telegram: dropping message from non-allowlisted chat %s", chat_id)
        return {"ok": True}

    background.add_task(
        _handle_telegram_message,
        chat_id,
        text,
        message.get("message_id"),
    )
    return {"ok": True}


async def _handle_telegram_message(chat_id: str, text: str, reply_to: int | None) -> None:
    try:
        # FIXME(ADR 0004): this channel is descoped/unwired. The call below uses the
        # pre-multi-user answer_query signature and will TypeError if re-wired — the
        # bot first needs a Google<->chat-id account-linking flow to obtain a user_id.
        async with SessionLocal() as session:
            result = await answer_query(session, channel="telegram", external_id=chat_id, text=text)
        reply = format_bot_reply(result)
        await _send_telegram_message(chat_id, reply, reply_to=reply_to)
    except Exception:
        log.exception("telegram: failed to handle message for chat %s", chat_id)


async def _send_telegram_message(chat_id: str, text: str, *, reply_to: int | None) -> None:
    if not settings.telegram_bot_token:
        log.error("telegram: bot token not configured; cannot reply")
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            log.error("telegram: sendMessage failed: %s %s", resp.status_code, resp.text)
